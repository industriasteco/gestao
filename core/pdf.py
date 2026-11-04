"""PDFs privados de homologação; medidas físicas em pontos, sem escalonamento."""
from io import BytesIO
from decimal import Decimal
from xml.sax.saxutils import escape
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from django.conf import settings

WIDTH,HEIGHT=A4

def logo(code):
    return settings.BASE_DIR/'core/assets'/({'TECO':'teco.png','NONA':'nona.png'}.get(code,'SEM_MARCA_APROVADA'))

def header(c,s,x,y,width,customer):
    path=logo(s['company_code'])
    if path.exists(): c.drawImage(ImageReader(str(path)),x,y-20*mm,width=23*mm,height=20*mm,preserveAspectRatio=True,mask='auto')
    c.setFont('Helvetica-Bold',9);c.drawString(x+25*mm,y-4*mm,s['company_name'][:38])
    c.setFont('Helvetica',7)
    c.drawString(x+25*mm,y-9*mm,'CNPJ: '+(s.get('cnpj') or 'PENDENTE DE VALIDACAO'))
    c.drawString(x+25*mm,y-14*mm,'VIA CLIENTE' if customer else 'VIA EMPRESA / SEM VALORES')
    c.setFont('Helvetica-Bold',8);c.drawString(x,y-25*mm,s['client_name'][:60])
    c.setFont('Helvetica',7);c.drawString(x,y-30*mm,f"{s['number']} | {s['date']} | {s['slot']} {s['time']}")
    c.drawString(x,y-35*mm,'HOMOLOGACAO - NAO COBRAR - DOCUMENTO NAO FISCAL')

def receipts(snapshots):
    buffer=BytesIO();c=canvas.Canvas(buffer,pagesize=A4,pageCompression=0,invariant=1)
    c.setTitle('Comprovantes de homologacao - NAO COBRAR')
    slot=0
    for s in snapshots:
        chunks=[s['items'][i:i+10] for i in range(0,len(s['items']),10)] or [[]]
        for part,items in enumerate(chunks,1):
            if s['ibis']:
                if slot: c.showPage();slot=0
                for customer in (False,True):
                    header(c,s,10*mm,HEIGHT-10*mm,190*mm,customer)
                    c.setFont('Helvetica',9);y=HEIGHT-58*mm
                    for item in items:
                        line=f"{item['quantity']} {item['unit']} | {item['name']}"
                        if customer: line+=f" | R$ {item['price']} | R$ {item['total']}"
                        c.drawString(12*mm,y,line[:120]);y-=7*mm
                    c.drawString(12*mm,y-8*mm,f'Parte {part}/{len(chunks)} - imprimir a 100%, tamanho real')
                    c.showPage()
                    header(c,s,10*mm,HEIGHT-10*mm,190*mm,customer)
                    # Exactly 5 columns x 2 rows, each 40 mm wide x 60 mm high.
                    c.setFont('Helvetica',8)
                    for row in range(2):
                        for col in range(5):
                            x=(5+col*40)*mm;y=(HEIGHT/mm-65-(row+1)*60)*mm
                            c.rect(x,y,40*mm,60*mm)
                            c.drawCentredString(x+20*mm,y+30*mm,f'ETIQUETA {row*5+col+1} / 40 x 60 mm')
                    c.showPage()
            else:
                for customer in (False,True):
                    if slot==4:c.showPage();slot=0
                    x=(5+(slot%2)*105)*mm;y=HEIGHT-(5+(slot//2)*148)*mm
                    header(c,s,x,y,100*mm,customer)
                    c.setFont('Helvetica',7);iy=y-44*mm
                    for item in items:
                        c.drawString(x,iy,f"{item['quantity']} {item['unit']} | {item['name']}"[:59]);iy-=4*mm
                        if customer:c.drawString(x+3*mm,iy,f"Unit. R$ {item['price']} | Total R$ {item['total']}");iy-=4*mm
                    c.setFont('Helvetica-Bold',7)
                    if customer:c.drawString(x,y-133*mm,'TOTAL PEDIDO R$ '+s['total'])
                    c.drawString(x,y-138*mm,f'Parte {part}/{len(chunks)} - NAO COBRAR')
                    slot+=1
        # Prevent an accidental fifth receipt overflowing when switching to IBIS.
    if slot:c.showPage()
    c.save();return buffer.getvalue()

def monthly(company,client,month,orders,total):
    stream=BytesIO();styles=getSampleStyleSheet()
    flow=[Paragraph('HOMOLOGAÇÃO — NÃO COBRAR — DOCUMENTO NÃO FISCAL',styles['Heading2']),
          Paragraph(escape(f'{company.name} / {client.name} / {month:%m/%Y}'),styles['Heading3']),Spacer(1,12)]
    data=[['Pedido','Data / entrega','Produto','Qtd','Unitário','Subtotal']]
    for order in orders:
        s=order.issued_snapshot
        for item in s['items']:
            data.append([s['number'],s['date']+' '+s['time'],Paragraph(escape(item['name']),styles['Normal']),item['quantity'],item['price'],item['total']])
    table=Table(data,repeatRows=1,colWidths=[85,100,145,55,60,65])
    table.setStyle(TableStyle([('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),9),('GRID',(0,0),(-1,-1),.2,colors.lightgrey)]))
    flow.extend([table,Spacer(1,16),Paragraph('TOTAL R$ '+str(total),styles['Heading2'])])
    SimpleDocTemplate(stream,pagesize=A4,rightMargin=30,leftMargin=30,topMargin=30,bottomMargin=30).build(flow)
    return stream.getvalue()
