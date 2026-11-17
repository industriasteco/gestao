"""Vendas entregues, recebíveis e registro da nota emitida no sistema externo."""
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from .models import Company,Order,Receivable
from .services import authorize
from .billing import configure_item,item_price,subtotal
from .workflow import event


@transaction.atomic
def recognize_delivered_sales(user,client,start,end,terms_days,evidence):
    authorize(user,client.company,'core.add_receivable')
    authorize(user,client.company,'core.confirm_delivery')
    Company.objects.select_for_update().get(pk=client.company_id)
    if not client.company.operational_enabled or not client.company.active or not client.active:raise ValidationError('Empresa ou cliente não está ativo para operação.')
    if start>end or end>timezone.localdate():raise ValidationError('Selecione um período realizado válido.')
    if terms_days is None or not 0<=terms_days<=3650:raise ValidationError('Informe o prazo após a emissão da nota, de 0 a 3650 dias.')
    if len(evidence.strip())<5:raise ValidationError('Registre a confirmação das entregas.')
    orders=list(Order.objects.select_for_update().filter(company=client.company,client=client,date__range=(start,end),synthetic=False).exclude(status='CANCELADO').order_by('date','pk').prefetch_related('items__product__company'))
    if not orders:raise ValidationError('Nenhum pedido real neste período.')
    ids=sorted(str(order.pk) for order in orders)
    overlaps=Q(pk__in=[])
    for pk in ids:overlaps|=Q(source_orders__contains=[pk])
    linked=list(Receivable.objects.select_for_update().filter(company=client.company,voided=False).filter(overlaps))
    if linked:
        if len(linked)==1 and sorted(linked[0].source_orders)==ids:return linked[0]
        raise ValidationError('Há pedidos já vinculados a outra conta a receber. Confira as referências para evitar cobrança duplicada.')
    total=Decimal(0)
    for order in orders:
        amount=Decimal(0)
        for item in order.items.all():
            if item.quantity<=0:continue
            if not item.billing_unit and item.unit_price_snapshot is None:configure_item(item)
            if item.unit_price_snapshot is None:
                item.unit_price_snapshot=item_price(item)
                item.full_clean();item.save(update_fields=['unit_price_snapshot','billing_unit','billing_factor'])
            amount+=subtotal(item,item.unit_price_snapshot)
        if amount<=0:raise ValidationError('Pedido sem valor positivo confirmado.')
        before={'status':order.status,'delivered_at':str(order.delivered_at)}
        if order.status in ('PRE_LANCADO','CONFERIDO','EMITIDO'):order.status='ENTREGUE'
        if not order.delivered_at:order.delivered_at=timezone.now()
        order.delivery_evidence=evidence.strip();order.save(update_fields=['status','delivered_at','delivery_evidence'])
        event(user,order,'RECONHECER_VENDA_ENTREGUE',before,{'status':order.status,'amount':str(amount),'external_invoice_issued':False},evidence)
        total+=amount
    row=Receivable(company=client.company,client=client,reference=f'Pedidos {client.name[:60]} {start:%d/%m/%Y} a {end:%d/%m/%Y}',
        issued_on=timezone.localdate(),due_on=None,terms_days=terms_days,amount=total,source_orders=ids,
        notes=f'Entregas confirmadas de {start:%d/%m/%Y} a {end:%d/%m/%Y}. Prazo: {terms_days} dias após a emissão da nota no sistema externo. Vencimento aguardando emissão. '+evidence.strip())
    row.full_clean();row.save()
    event(user,client,'REGISTRAR_VENDAS_E_RECEBIVEL',after={'receivable':str(row.pk),'orders':ids,'amount':str(total),'terms_days':terms_days,'due_on':None},reason=evidence)
    return row


@transaction.atomic
def record_external_invoice(user,receivable,number,issued_on):
    authorize(user,receivable.company,'core.change_receivable')
    row=Receivable.objects.select_for_update().get(pk=receivable.pk)
    number=number.strip()
    if row.voided or not number or len(number)>50 or issued_on>timezone.localdate():raise ValidationError('Confira o número e a data da nota já emitida no sistema externo.')
    if row.external_invoice_number:
        if row.external_invoice_number==number and row.external_invoice_date==issued_on:return row
        raise ValidationError('A nota desta conta já foi registrada. Preserve o histórico e solicite a correção.')
    row.external_invoice_number=number;row.external_invoice_date=issued_on
    if row.terms_days is not None:row.due_on=issued_on+timedelta(days=row.terms_days)
    row.full_clean();row.save(update_fields=['external_invoice_number','external_invoice_date','due_on'])
    event(user,row,'REGISTRAR_NOTA_EXTERNA',after={'number':number,'issued_on':str(issued_on),'due_on':str(row.due_on)},reason='Número e data informados pelo operador; emissão realizada no sistema fiscal externo.')
    return row
