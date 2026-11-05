"""Fechamento comercial para aprovação; não emite nota fiscal nem cria dívida."""
import hashlib
import uuid
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Company, Order, ClientStatement, StatementLine, Document
from .services import authorize
from .workflow import event


def eligible_orders(company,client,start,end):
    if client.company_id!=company.pk:raise ValidationError('Cliente de outra empresa.')
    return Order.objects.filter(company=company,client=client,date__range=(start,end),status__in=['ENTREGUE','LIBERADO_FECHAMENTO'],delivered_at__isnull=False).exclude(issued_snapshot={}).order_by('date','time','pk')


@transaction.atomic
def create_statement(user,company,client,start,end,purchase_order=''):
    authorize(user,company,'core.add_clientstatement')
    Company.objects.select_for_update().get(pk=company.pk)
    purchase_order=purchase_order.strip()
    if len(purchase_order)>50:raise ValidationError('A ordem de compra deve ter até 50 caracteres.')
    if start>end or end>timezone.localdate():raise ValidationError('Confira o período realizado para fechamento.')
    existing=ClientStatement.objects.filter(company=company,client=client,start=start,end=end).exclude(status='CANCELADO').first()
    if existing:
        if purchase_order and existing.purchase_order!=purchase_order:raise ValidationError('Já existe fechamento preservado neste período. Para informar outra OC, revise o fechamento antes de gerar novamente.')
        return existing
    orders=list(eligible_orders(company,client,start,end).select_for_update().prefetch_related('items'))
    if not orders:raise ValidationError('Nenhuma entrega confirmada e emitida disponível neste período. Pedidos planejados não entram no fechamento.')
    if len({o.synthetic for o in orders})>1:raise ValidationError('Não misture pedidos de teste e reais no mesmo fechamento.')
    if StatementLine.objects.filter(order__in=orders,active=True).exists():raise ValidationError('Há pedidos já incluídos em outro fechamento. Confira os períodos para evitar duplicidade.')
    statement_id=uuid.uuid4();lines=[];total=Decimal(0);order_totals={}
    for order in orders:
        amount=Decimal(0)
        for item in order.items.all():
            if item.quantity<=0:continue
            if item.unit_price_snapshot is None:raise ValidationError('Há pedido sem preço congelado na emissão; revise o documento antes de fechar.')
            subtotal=(item.quantity*item.unit_price_snapshot).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            amount+=subtotal
            lines.append({'date':str(order.date),'order':str(order.pk),'number':order.commercial_number,'purchase_order':order.issued_snapshot.get('purchase_order','') or purchase_order,
                'product':item.product_name,'unit':item.unit,'quantity':str(item.quantity),'price':str(item.unit_price_snapshot),'total':str(subtotal)})
        if not amount and not order.items.filter(quantity__gt=0).exists():raise ValidationError('Há pedido entregue sem itens positivos.')
        order_totals[order.pk]=amount;total+=amount
    snapshot={'company':company.name,'company_tax_id':company.cnpj or '', 'client':client.name,'legal_name':client.legal_name,
        'company_code':company.code,'company_address':company.address,'company_phone':company.phone,'company_email':company.email,
        'client_tax_id':client.tax_id,'address':client.address,'email':client.email,'phone':client.phone,
        'start':str(start),'end':str(end),'purchase_order':purchase_order,'total':str(total),'synthetic':orders[0].synthetic,'items':lines,'reference':str(statement_id)[:8].upper()}
    data=statement_pdf(snapshot)
    doc=Document.objects.create(company=company,key=f'statement:{statement_id}',kind='FECHAMENTO_CLIENTE',data=data,sha256=hashlib.sha256(data).hexdigest())
    statement=ClientStatement.objects.create(id=statement_id,company=company,client=client,start=start,end=end,total=total,purchase_order=purchase_order,snapshot=snapshot,document=doc,actor=user)
    StatementLine.objects.bulk_create([StatementLine(statement=statement,order=order,amount=order_totals[order.pk]) for order in orders])
    event(user,statement,'GERAR_FECHAMENTO_CLIENTE',after={'start':str(start),'end':str(end),'purchase_order':purchase_order,'total':str(total),'orders':len(orders),'sha256':doc.sha256})
    return statement


@transaction.atomic
def statement_action(user,statement,action,evidence):
    authorize(user,statement.company,'core.change_clientstatement')
    statement=ClientStatement.objects.select_for_update().get(pk=statement.pk)
    if len(evidence.strip())<5:raise ValidationError('Descreva o destinatário e meio de envio, ou a evidência recebida do cliente (mínimo 5 caracteres).')
    before=statement.status
    if action=='send' and statement.status in ('RASCUNHO','REJEITADO'):
        statement.status='ENVIADO';statement.sent_at=timezone.now();statement.communication=evidence
    elif action=='approve' and statement.status=='ENVIADO':
        statement.status='APROVADO';statement.approved_at=timezone.now();statement.approval_evidence=evidence
    elif action=='reject' and statement.status=='ENVIADO':
        statement.status='REJEITADO';statement.approval_evidence=evidence
    elif action=='cancel' and statement.status in ('RASCUNHO','ENVIADO','REJEITADO'):
        statement.status='CANCELADO';statement.approval_evidence=evidence
        StatementLine.objects.filter(statement=statement).update(active=False)
        Document.objects.filter(pk=statement.document_id).update(superseded=True)
    else:raise ValidationError('Esta ação não é permitida na situação atual. Fechamento aprovado exige processo próprio de correção.')
    statement.save()
    event(user,statement,'SITUACAO_FECHAMENTO',before={'status':before},after={'status':statement.status},reason=evidence)
    return statement


def statement_pdf(snapshot):
    from io import BytesIO
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
    from .templatetags.erp import brl,brl4
    output=BytesIO();styles=getSampleStyleSheet();small=styles['BodyText'];small.fontSize=9;small.leading=13
    def p(value):return Paragraph(escape(str(value or '')),small)
    story=[Paragraph('Demonstrativo de fornecimento',styles['Title']),p(f'Referência: {snapshot["reference"]}'),p(snapshot['company']),p('CNPJ da emissora: '+(snapshot.get('company_tax_id') or 'Pendente')),
        p(f'Cliente: {snapshot["legal_name"] or snapshot["client"]} | CPF/CNPJ: {snapshot["client_tax_id"] or "Pendente"}'),
        p(snapshot['address']),p(f'Período: {snapshot["start"]} a {snapshot["end"]}'),Spacer(1,12)]
    if snapshot.get('purchase_order'):story.extend([p('Ordem de compra do fechamento: '+snapshot['purchase_order']),Spacer(1,6)])
    if snapshot['synthetic']:story.extend([p('HOMOLOGAÇÃO - PEDIDOS DE TESTE - NÃO COBRAR'),Spacer(1,10)])
    rows=[[p(v) for v in ['Data','Ordem de compra','Produto','Qtd.','Un.','Valor unit.','Total']]]
    for item in snapshot['items']:
        rows.append([p(item['date']),p(item.get('purchase_order','')),p(item['product']),p(item['quantity']),p(item['unit']),p(brl4(item['price'])),p(brl(item['total']))])
    table=Table(rows,colWidths=[58,85,140,42,30,75,70],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf2e7')),('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#dce4dd')),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7)]))
    story.extend([table,Spacer(1,14),Paragraph(escape('Total fornecido: '+brl(snapshot['total'])),styles['Heading2']),p('Demonstrativo para conferência e aprovação do cliente. Não é nota fiscal. Não substitui o controle de pagamentos e não gera cobrança automaticamente.'),Spacer(1,12),p('Cliente / responsável: ______________________________________________'),p('Aprovação / ressalvas: ______________________________________________'),p('Data: ____________________ Assinatura: _____________________________')])
    SimpleDocTemplate(output,pagesize=A4,leftMargin=36,rightMargin=36,topMargin=32,bottomMargin=32).build(story)
    return output.getvalue()
