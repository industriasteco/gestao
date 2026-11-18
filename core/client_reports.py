"""Relatório preservado de pedidos reais para conferência pelo cliente."""
import hashlib
import json
from collections import OrderedDict
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from xml.sax.saxutils import escape
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Company, Order, Document
from .billing import configure_item, item_price, decimal_text
from .services import authorize
from .workflow import event


def report_prefix(client):
    return f'client-report:{client.pk}:'


def orders_snapshot(client, start, end, orders):
    if start>end or end>timezone.localdate():raise ValidationError('Informe um período realizado válido para o relatório.')
    rows=[]
    for order in orders:
        if order.client_id!=client.pk or order.company_id!=client.company_id or order.synthetic or order.status=='CANCELADO':
            raise ValidationError('O relatório aceita somente pedidos reais deste cliente e empresa.')
        for item in sorted(order.items.all(),key=lambda item:str(item.pk)):
            if item.quantity<=0:continue
            if not item.billing_unit and item.unit_price_snapshot is None:configure_item(item)
            price=item.unit_price_snapshot if item.unit_price_snapshot is not None else item_price(item)
            row={'order':str(order.pk),'item':str(item.pk),'date':str(order.date),'period':order.slot,'product_id':str(item.product_id),'product':item.product_name,
                 'ordered_quantity':decimal_text(item.quantity),'ordered_unit':item.unit,
                 'quantity':decimal_text(item.billed_quantity),'unit':item.billed_unit,'price':str(price),'billing_factor':str(item.billing_factor)}
            rows.append(row)
    return compose_snapshot(client,start,end,rows)


def compose_snapshot(client,start,end,rows):
    if start>end or end>timezone.localdate():raise ValidationError('Informe um período realizado válido para o relatório.')
    if not rows:raise ValidationError('Não há itens de pedidos reais neste período.')
    rows=[{**row,**{field:decimal_text(Decimal(row[field])) for field in ('ordered_quantity','quantity','billing_factor')}} for row in rows]
    groups=OrderedDict()
    for row in rows:
        price=Decimal(row['price'])
        row['total']=str((Decimal(row['quantity'])*price).quantize(Decimal('.01'),rounding=ROUND_HALF_UP))
        key=(row['product_id'],row['product'],row['ordered_unit'],row['unit'],price)
        group=groups.setdefault(key,{'product':row['product'],'ordered_unit':row['ordered_unit'],'unit':row['unit'],'price':price,'ordered_quantity':Decimal(0),'quantity':Decimal(0),'total':Decimal(0)})
        group['ordered_quantity']+=Decimal(row['ordered_quantity']);group['quantity']+=Decimal(row['quantity'])
        group['total']+=Decimal(row['total'])
    summary=[];total=Decimal(0)
    def delivery_key(row):
        period=row.get('period','').casefold()
        rank=0 if 'manh' in period else 2 if 'tarde' in period else 1
        return row['date'],rank,period,row['order'],row['product'],row['item']
    rows.sort(key=delivery_key)
    for group in sorted(groups.values(),key=lambda group:(group['product'],group['unit'],group['price'])):
        amount=group['total']
        total+=amount
        summary.append({**{k:str(v) for k,v in group.items()},'ordered_quantity':decimal_text(group['ordered_quantity']),
                        'quantity':decimal_text(group['quantity']),'total':str(amount)})
    company=client.company
    return {'company':company.name,'company_code':company.code,'legal_name':company.legal_name,'company_tax_id':company.cnpj or '',
            'address':company.address,'phone':company.phone,'client':client.name,'client_id':str(client.pk),
            'start':str(start),'end':str(end),'orders':len({r['order'] for r in rows}),
            'items':rows,'summary':summary,'total':str(total),'basis':'soma_das_linhas_diarias_arredondadas'}


@transaction.atomic
def create_client_report(user, client, start, end):
    authorize(user,client.company,'core.add_clientstatement')
    company=Company.objects.select_for_update().get(pk=client.company_id)
    if not company.operational_enabled:raise ValidationError('Ative a operação da empresa antes de gerar relatórios de pedidos reais.')
    orders=list(Order.objects.select_for_update().filter(client=client,company=company,date__range=(start,end),synthetic=False)
                .exclude(status='CANCELADO').order_by('date','time','pk').prefetch_related('items__product__company'))
    snapshot=orders_snapshot(client,start,end,orders)
    digest=hashlib.sha256(json.dumps(snapshot,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    key=f'{report_prefix(client)}{start}:{end}:{digest}'
    previous=Document.objects.filter(key=key).first()
    if previous:return previous
    data=client_report_pdf(snapshot)
    document=Document.objects.create(company=company,key=key,kind='RELATORIO_PEDIDOS_CLIENTE',layout='client-orders-v1',data=data,sha256=hashlib.sha256(data).hexdigest())
    event(user,client,'GERAR_RELATORIO_PEDIDOS',after={'document':str(document.pk),'start':str(start),'end':str(end),'orders':snapshot['orders'],'total':snapshot['total'],'basis':snapshot['basis'],'sha256':document.sha256})
    return document


def client_report_pdf(snapshot):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image
    from .receipt_layout import receipt_logo,number
    output=BytesIO();styles=getSampleStyleSheet();body=styles['BodyText'];body.fontSize=8.5;body.leading=11
    def p(value):return Paragraph(escape(str(value or '')),body)
    def br_date(value):return '/'.join(reversed(value.split('-')))
    logo=receipt_logo(snapshot['company_code'])
    heading=[p(snapshot['legal_name'] or snapshot['company']),p('CNPJ: '+snapshot['company_tax_id']),p(snapshot['address']),p(snapshot['phone'])]
    if snapshot['legal_name'] and snapshot['legal_name']!=snapshot['company']:heading.insert(0,p(snapshot['company']))
    story=[]
    if logo.exists():
        from PIL import Image as PillowImage
        with PillowImage.open(logo) as bitmap:
            bitmap.thumbnail((264,192),PillowImage.Resampling.LANCZOS)
            logo_data=BytesIO();bitmap.save(logo_data,format='PNG');logo_data.seek(0)
        story.append(Table([[Image(logo_data,width=66,height=48,kind='proportional'),heading]],colWidths=[80,430]))
    else:story.extend(heading)
    story.extend([Spacer(1,12),Paragraph('Demonstrativo de pedidos',styles['Title']),
        p('Cliente: '+snapshot['client']),p('Período: '+br_date(snapshot['start'])+' a '+br_date(snapshot['end'])),
        p(str(snapshot['orders'])+' pedidos registrados para conferência do cliente.'),Spacer(1,14),
        Paragraph('Resumo por produto para faturamento',styles['Heading2'])])
    summary=[[p(v) for v in ['Produto','Qtd. pedida','Peso / qtd. faturada','Preço','Subtotal']]]
    for row in snapshot['summary']:
        summary.append([p(row['product']),p(number(row['ordered_quantity'],3).rstrip('0').rstrip(',')+' '+row['ordered_unit']),
            p(number(row['quantity'],6).rstrip('0').rstrip(',')+' '+row['unit']),p('R$ '+number(row['price'],4)+'/'+row['unit']),p('R$ '+number(row['total']))])
    def table(rows,widths):
        result=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
        result.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f1ec')),('VALIGN',(0,0),(-1,-1),'TOP'),
            ('LINEBELOW',(0,0),(-1,-1),.3,colors.HexColor('#d2ddd5')),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        return result
    story.extend([table(summary,[170,80,100,80,80]),Spacer(1,10),Paragraph('Total do período: R$ '+number(snapshot['total']),styles['Heading2']),
        p('Total calculado pela soma dos valores de cada linha diária, arredondados para centavos. O resumo por produto soma essas mesmas linhas.'),
        Spacer(1,14),Paragraph('Detalhamento por data',styles['Heading2'])])
    details=[[p(v) for v in ['Data','Entrega','Produto','Qtd. pedida','Peso / qtd. faturada','Preço / un.','Valor total']]]
    for row in snapshot['items']:
        details.append([p(br_date(row['date'])),p(row.get('period','')),p(row['product']),p(number(row['ordered_quantity'],3).rstrip('0').rstrip(',')+' '+row['ordered_unit']),
            p(number(row['quantity'],6).rstrip('0').rstrip(',')+' '+row['unit']),p('R$ '+number(row['price'],4)+'/'+row['unit']),p('R$ '+number(row['total']))])
    story.extend([table(details,[58,54,128,52,60,72,86]),Spacer(1,14),p('Documento para conferência de pedidos e valores. Não é nota fiscal.'),
        p('Conferido por: ______________________________________  Data: ____/____/________')])
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.drawRightString(A4[0]-42,22,f'Página {doc.page}')
    SimpleDocTemplate(output,pagesize=A4,leftMargin=42,rightMargin=42,topMargin=30,bottomMargin=36,title='Demonstrativo de pedidos - '+snapshot['client']).build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()
