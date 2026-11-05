import hashlib
from pathlib import PurePath
from datetime import date
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import Company,Supplier,PurchaseInvoice,Payable,Disbursement
from .services import authorize,companies
from .workflow import event
from .nfe_import import parse_nfe


@transaction.atomic
def stage_invoice(user,company,data,filename):
    authorize(user,company,'core.add_purchaseinvoice')
    company=Company.objects.select_for_update().get(pk=company.pk)
    if not company.cnpj:raise ValidationError('Preencha e confira o CNPJ da empresa antes de importar XML.')
    parsed=parse_nfe(data)
    if company.cnpj!=parsed['recipient']:raise ValidationError('O CNPJ destinatário da nota não pertence à empresa selecionada.')
    if date.fromisoformat(parsed['issued_on'])>timezone.localdate():raise ValidationError('A data de emissão da nota está no futuro.')
    existing=PurchaseInvoice.objects.filter(access_key=parsed['access_key']).first()
    if existing:
        if existing.company_id!=company.pk:raise ValidationError('A nota já está vinculada a outra empresa.')
        if existing.payload_hash!=parsed['payload_hash']:raise ValidationError('Já existe XML dessa chave com dados diferentes. O documento original foi preservado.')
        return existing,False
    data_supplier=parsed['supplier']
    supplier,created=Supplier.objects.get_or_create(company=company,tax_id=data_supplier['tax_id'],defaults={key:data_supplier[key] for key in ('name','trade_name','address','phone')})
    if created:event(user,supplier,'CADASTRAR_FORNECEDOR_XML',after={'name':supplier.name,'tax_id':supplier.tax_id})
    if not supplier.active:raise ValidationError('O fornecedor está inativo. Revise seu cadastro antes de importar.')
    invoice=PurchaseInvoice(company=company,supplier=supplier,access_key=parsed['access_key'],number=parsed['number'],series=parsed['series'],model=parsed['model'],issued_on=parsed['issued_on'],total=parsed['total'],financial_total=parsed['financial_total'],environment=parsed['environment'],installments=parsed['installments'],summary=parsed,xml=data,sha256=hashlib.sha256(data).hexdigest(),payload_hash=parsed['payload_hash'],filename=PurePath(filename).name[:200],actor=user)
    invoice.full_clean();invoice.save()
    event(user,invoice,'RECEBER_XML_COMPRA',after={'key':invoice.access_key,'total':str(invoice.total),'installments':len(invoice.installments)},reason='XML guardado para conferência. Nenhuma conta, movimentação de estoque ou pagamento criado.')
    return invoice,True


@transaction.atomic
def confirm_invoice(user,invoice,manual_installments=None):
    authorize(user,invoice.company,'core.add_payable')
    Company.objects.select_for_update().get(pk=invoice.company_id)
    invoice=PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status=='FINANCEIRO_GERADO':return list(invoice.payables.all())
    if invoice.status!='EM_REVISAO':raise ValidationError('Nota arquivada. Não é possível gerar contas automaticamente.')
    if not invoice.supplier.active:raise ValidationError('Fornecedor inativo; confira o cadastro.')
    needs_dates=any(not row['due_on'] for row in invoice.installments)
    if needs_dates:
        if not manual_installments:raise ValidationError('Complete os vencimentos das duplicatas antes de gerar as contas.')
        expected={row['reference']:row for row in invoice.installments}
        received={str(row['reference']).strip():row for row in manual_installments}
        if len(received)!=len(manual_installments) or set(received)!=set(expected):raise ValidationError('Preserve as referências das duplicatas do XML.')
        for reference,row in received.items():
            original=expected[reference]
            if Decimal(row['amount'])!=Decimal(original['amount']):raise ValidationError('Preserve os valores das duplicatas do XML.')
            if original['due_on'] and str(row['due_on'])!=original['due_on']:raise ValidationError('Preserve os vencimentos já informados no XML.')
    source=manual_installments if needs_dates else (invoice.installments or manual_installments or [])
    if not source:raise ValidationError('O XML não traz vencimentos. Informe as parcelas confirmadas antes de gerar as contas.')
    if len(source)>120:raise ValidationError('Limite de 120 parcelas.')
    total=Decimal(0);references=set();rows=[]
    for row in source:
        reference=str(row['reference']).strip();amount=Decimal(row['amount']);due=row['due_on']
        if isinstance(due,str):
            try:due=date.fromisoformat(due)
            except ValueError:raise ValidationError('Vencimento inválido.')
        if not reference or len(reference)>60 or reference in references:raise ValidationError('Identifique cada parcela com uma referência única, de até 60 caracteres.')
        if not amount.is_finite() or amount<=0 or amount!=amount.quantize(Decimal('.01')) or due<invoice.issued_on:raise ValidationError('Confira o valor e o vencimento das parcelas.')
        references.add(reference);total+=amount
        rows.append((reference,due,amount))
    if total!=invoice.financial_total:raise ValidationError('A soma das parcelas deve corresponder ao valor financeiro da nota/fatura.')
    payables=[]
    for reference,due,amount in rows:
        payable=Payable(company=invoice.company,supplier=invoice.supplier,invoice=invoice,reference=f'NFE:{invoice.access_key}:{reference}',installment=reference,issued_on=invoice.issued_on,due_on=due,amount=amount,synthetic=invoice.environment=='2',notes='Parcela da NF-e importada; vencimento conferido pelo operador.')
        payable.full_clean();payable.save();payables.append(payable)
        event(user,payable,'GERAR_PARCELA_XML',after={'amount':str(amount),'due_on':str(due),'invoice':str(invoice.pk)})
    invoice.status='FINANCEIRO_GERADO';invoice.save(update_fields=['status'])
    event(user,invoice,'CONFIRMAR_FINANCEIRO_XML',after={'count':len(payables),'amount':str(total),'synthetic':invoice.environment=='2'})
    return payables


def payable_balances(user,day=None):
    day=day or timezone.localdate()
    rows=Payable.objects.filter(company__in=companies(user),voided=False).select_related('supplier','company','invoice').annotate(paid=Sum('payments__amount'))
    for row in rows:
        row.balance=row.amount-(row.paid or Decimal(0))
        row.days_late=max((day-row.due_on).days,0) if row.balance>0 else 0
    return list(rows)


@transaction.atomic
def pay(user,payable,amount,day,method,reference,evidence):
    authorize(user,payable.company,'core.change_payable')
    payable=Payable.objects.select_for_update().get(pk=payable.pk)
    existing=Disbursement.objects.filter(payable=payable,reference=reference).first()
    if existing:
        if (existing.amount,existing.date,existing.method,existing.evidence)!=(amount,day,method,evidence.strip()):raise ValidationError('Identificador de pagamento já utilizado com outros dados.')
        return existing
    paid=payable.payments.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    if payable.voided or not amount.is_finite() or amount<=0 or amount>payable.amount-paid:raise ValidationError('Pagamento inválido ou superior ao saldo da parcela.')
    if day<payable.issued_on or day>timezone.localdate():raise ValidationError('Registre a data de um pagamento já realizado, entre a emissão e hoje.')
    if len(evidence.strip())<3:raise ValidationError('Informe a referência do comprovante ou observação do pagamento.')
    payment=Disbursement(payable=payable,amount=amount,date=day,method=method,reference=reference,evidence=evidence.strip(),actor=user)
    payment.full_clean();payment.save()
    event(user,payable,'REGISTRAR_PAGAMENTO_FORNECEDOR',after={'amount':str(amount),'date':str(day),'method':method,'reference':reference},reason=evidence)
    return payment


@transaction.atomic
def void_payable(user,payable,reason):
    authorize(user,payable.company,'core.change_payable')
    payable=Payable.objects.select_for_update().get(pk=payable.pk)
    if len(reason.strip())<5:raise ValidationError('Descreva o motivo do cancelamento (mínimo 5 caracteres).')
    if payable.payments.exists():raise ValidationError('Parcela com pagamento registrado exige correção própria; não pode ser cancelada por esta ação.')
    if payable.voided:return payable
    payable.voided=True;payable.save(update_fields=['voided'])
    event(user,payable,'CANCELAR_CONTA_A_PAGAR',reason=reason)
    return payable

@transaction.atomic
def archive_invoice(user,invoice,reason):
    authorize(user,invoice.company,'core.change_purchaseinvoice')
    invoice=PurchaseInvoice.objects.select_for_update().get(pk=invoice.pk)
    if invoice.status!='EM_REVISAO' or len(reason.strip())<5:raise ValidationError('Somente uma nota ainda em revisão pode ser arquivada. Descreva o motivo.')
    invoice.status='ARQUIVADA';invoice.save(update_fields=['status'])
    event(user,invoice,'ARQUIVAR_XML_SEM_FINANCEIRO',reason=reason)
    return invoice
