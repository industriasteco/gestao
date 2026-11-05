"""Equivalente transacional de FinalizarDia: notinhas + produção, sem novos pedidos."""
import hashlib
from django.core.exceptions import ValidationError
from django.db import transaction
from .models import Company,Order,OrderItem,Document
from .services import companies,authorize,production,require
from .workflow import issue,event
from . import pdf


@transaction.atomic
def finalize_day(user,day):
    require(user,'core.issue_document')
    scope=list(companies(user).order_by('pk'))
    for company in scope:Company.objects.select_for_update().get(pk=company.pk)
    positive=OrderItem.objects.filter(quantity__gt=0).values('order_id')
    orders=list(Order.objects.select_for_update().filter(company__in=scope,date=day,pk__in=positive).exclude(status='CANCELADO').select_related('company','client').order_by('client__name','time','slot','pk'))
    if not orders:raise ValidationError('Não há itens positivos para finalizar nesta data.')
    for order in orders:
        authorize(user,order.company,'core.issue_document')
        if not order.synthetic:raise ValidationError('Operação real depende da liberação da homologação.')
        if order.status=='PRE_LANCADO':raise ValidationError('Confira os turnos e execute Conferir produção antes de finalizar o dia.')
        from .receipt_layout import brand_code
        if brand_code(order.company.code) not in ('TECO','NONA'):raise ValidationError('Configure o código da emissora como TECO ou NONA antes de finalizar as notinhas deste modelo.')
        if not order.company.cnpj:raise ValidationError(f'Cadastre o CNPJ confirmado da empresa {order.company.name} antes de finalizar, conforme o modelo de automação.')
        if not order.baker.strip() or not order.shift:raise ValidationError('Informe o padeiro de cada turno antes de finalizar.')
    for order in orders:
        issue(user,order.pk)
        order.refresh_from_db()
    scope_ids=sorted({str(order.company_id) for order in orders})
    digest=hashlib.sha256('|'.join(f'{order.pk}:{order.issued_at}' for order in orders).encode()).hexdigest()[:32]
    scope_hash=hashlib.sha256('|'.join(scope_ids).encode()).hexdigest()[:16]
    prefix=f'finalize:{day}:{scope_hash}:{digest}'
    documents=[]
    for kind in ('notinhas','producao'):
        key=prefix+':'+kind
        doc=Document.objects.filter(key=key).first()
        if doc is None:
            try:
                data=pdf.receipts([order.issued_snapshot for order in orders]) if kind=='notinhas' else planned_pdf(day,orders)
            except ValueError as exc:raise ValidationError(str(exc)) from exc
            doc=Document.objects.create(company=orders[0].company,company_scope=scope_ids,key=key,kind='DIA_'+kind.upper(),data=data,sha256=hashlib.sha256(data).hexdigest(),layout='excel-v2-ibis-retrato')
            event(user,doc,'FINALIZAR_DIA',after={'date':str(day),'orders':len(orders),'companies':scope_ids,'kind':kind,'sha256':doc.sha256})
        documents.append(doc)
    return documents


def planned_pdf(day,orders):
    from io import BytesIO
    from xml.sax.saxutils import escape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,PageBreak
    from .templatetags.erp import weekday
    stream=BytesIO();styles=getSampleStyleSheet();flow=[]
    rows=production(Order.objects.filter(pk__in=[order.pk for order in orders]))
    for index,shift in enumerate(('GERAL','NOTURNO','DIURNO')):
        if index:flow.append(PageBreak())
        flow.extend([Paragraph('RESUMO GERAL - PRODUÇÃO' if shift=='GERAL' else 'LISTA DE PRODUÇÃO - '+shift,styles['Title']),
            Paragraph('Data: '+day.strftime('%d/%m/%Y'),styles['Normal']),
            Paragraph('PLANEJAMENTO - HOMOLOGAÇÃO - NÃO COMPROVA PRODUÇÃO REALIZADA',styles['Normal'])])
        for period in ('NOTURNO','DIURNO'):
            names=', '.join(sorted({order.baker for order in orders if order.shift==period}))
            flow.append(Paragraph(escape('Padeiro '+period.lower()+': '+names),styles['Normal']))
        flow.append(Spacer(1,12))
        data=[['Produto','Un.','Noturno','Diurno','Total']]
        for row in rows:
            if shift!='GERAL' and not row[shift]:continue
            n=row['NOTURNO'] if shift!='DIURNO' else 0;d=row['DIURNO'] if shift!='NOTURNO' else 0
            data.append([Paragraph(escape(row['product']),styles['Normal']),row['unit'],str(n),str(d),str(n+d)])
        table=Table(data,colWidths=[250,40,70,70,70],repeatRows=1)
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf2e7')),('GRID',(0,0),(-1,-1),.25,colors.HexColor('#d0dcd4')),('VALIGN',(0,0),(-1,-1),'TOP')]))
        flow.extend([table,Spacer(1,20),Paragraph('Conferido por: ___________________________________',styles['Normal'])])
    SimpleDocTemplate(stream,pagesize=A4,leftMargin=36,rightMargin=36,topMargin=36,bottomMargin=36).build(flow)
    return stream.getvalue()

@transaction.atomic
def assign_shift_responsibles(user,day,night,daytime,separator):
    require(user,'core.prepare_day')
    rows=list(Order.objects.select_for_update().filter(company__in=companies(user),date=day,status__in=['PRE_LANCADO','CONFERIDO'],pk__in=OrderItem.objects.filter(quantity__gt=0).values('order_id')))
    names={'NOTURNO':night.strip(),'DIURNO':daytime.strip()}
    for order in rows:
        if not names.get(order.shift):raise ValidationError('Informe o turno e o padeiro de cada turno que possui pedidos.')
    for order in rows:
        order.baker=names[order.shift];order.separator=separator.strip();order.save(update_fields=['baker','separator'])
        event(user,order,'RESPONSAVEIS_DO_DIA',after={'baker':order.baker,'separator':order.separator,'shift':order.shift})
    return len(rows)
