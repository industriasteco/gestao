"""Quatro notinhas por A4, conforme MontarNota do modelo Excel enviado.

IBIS é tratado em core.pdf: retrato frente/verso, por escolha do usuário.
Não executa VBA nem depende de Excel na hospedagem.
"""
from decimal import Decimal
import unicodedata
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from django.conf import settings


def brand_code(value):
    code=''.join(c for c in unicodedata.normalize('NFKD',value.upper()) if not unicodedata.combining(c)).strip()
    if code in ('NONA','NONA CECILIA'):return 'NONA'
    return code


def number(value,places=2):
    return f'{Decimal(str(value)):,.{places}f}'.replace(',','X').replace('.',',').replace('X','.')


def text(c,value,x,y,width,size=7,bold=False,align='left',max_lines=1,leading=None):
    value=str(value or '').replace('\n',' ')
    font='Helvetica-Bold' if bold else 'Helvetica'
    words=value.split();lines=[];line=''
    for word in words:
        trial=(line+' '+word).strip()
        if stringWidth(trial,font,size)>width and line:
            lines.append(line);line=word
        else:line=trial
    if line:lines.append(line)
    if not lines:return
    if len(lines)>max_lines:
        # Reduz fonte antes de truncar texto: descrições longas nunca são cortadas.
        while len(lines)>max_lines and size>4.3:
            size-=.2;lines=[];line=''
            for word in words:
                trial=(line+' '+word).strip()
                if stringWidth(trial,font,size)>width and line:lines.append(line);line=word
                else:line=trial
            if line:lines.append(line)
        if len(lines)>max_lines:
            raise ValueError('Texto excede o espaço da notinha. Use abreviação confirmada no cadastro ou reduza as observações.')
    c.setFont(font,size)
    for i,line in enumerate(lines):
        yy=y-i*(leading or size+1)
        if align=='center':c.drawCentredString(x+width/2,yy,line)
        elif align=='right':c.drawRightString(x+width,yy,line)
        else:c.drawString(x,yy,line)


def common_receipt(c,s,items,part,parts,x,top,width,height,customer):
    """Duas cópias lado a lado; linhas/colunas seguem o VBA de referência."""
    c.saveState()
    c.setStrokeColor(colors.HexColor('#a0acb7'));c.setLineWidth(.45)
    c.rect(x,top-height,width,height)
    c.setFillColor(colors.HexColor('#f7f9fb'));c.rect(x,top-24,width,24,stroke=0,fill=1)
    c.setFillColor(colors.HexColor('#173451'))
    logo=settings.BASE_DIR/'core/assets'/({'TECO':'teco.png','NONA':'nona.png'}.get(brand_code(s['company_code']),'not-found'))
    if logo.exists():c.drawImage(ImageReader(str(logo)),x+4,top-44,width=42,height=42,preserveAspectRatio=True,mask='auto')
    text(c,s['company_name'],x+48,top-14,width-52,9,True,'center',2)
    c.setFillColor(colors.black)
    text(c,('Razão social: '+s['legal_name']) if s.get('legal_name') else 'CNPJ: '+(s.get('cnpj') or 'PENDENTE'),x+46,top-34,width-50,6.4,align='center',max_lines=2)
    meta=('CNPJ: '+(s.get('cnpj') or 'PENDENTE')+' | ') if s.get('legal_name') else ''
    text(c,meta+s.get('company_address',''),x+4,top-49,width-8,6.3,align='center',max_lines=2)
    text(c,'Tel.: '+s.get('company_phone',''),x+4,top-65,width-8,6.3,align='center')
    text(c,s.get('company_email',''),x+4,top-76,width-8,6.3,align='center')
    via='VIA CLIENTE - COM VALORES' if customer else 'VIA EMPRESA - SEM VALORES'
    text(c,'Pedido nº '+s['number']+'  '+via,x+4,top-91,width-8,6.4,True)
    text(c,'CLIENTE: '+s['client_name'],x+4,top-106,width-8,8,True,max_lines=2)
    from datetime import date
    when=date.fromisoformat(s['date']).strftime('%d/%m/%Y')
    text(c,f'DATA: {when} | ENTREGA: {s["time"]} / {s["slot"]} | FOLHA {part}/{parts}',x+4,top-128,width-8,6.6)
    address=s.get('client_address') or s.get('client_contact','')
    text(c,('ENDEREÇO: ' if s.get('client_address') else 'CONTATO: ')+address,x+4,top-141,width-8,6.4,max_lines=2)
    table_top=top-157
    widths=[width*.20,width*.50,width*.20,width*.10]
    headers=['QTD.','DESCRIÇÃO','PREÇO','VALOR']
    c.setFillColor(colors.HexColor('#f1f5f8'));c.rect(x,table_top-15,width,15,fill=1,stroke=0);c.setFillColor(colors.black)
    left=x
    for head,w in zip(headers,widths):text(c,head,left+3,table_top-10,w-6,6.5,True,align='left' if head=='DESCRIÇÃO' else 'center');left+=w
    row_height=15
    # O espaço reservado e as dez linhas são mantidos mesmo com menos itens.
    for index in range(10):
        bottom=table_top-15-(index+1)*row_height
        c.line(x,bottom,x+width,bottom)
        if index>=len(items):continue
        item=items[index]
        cells=[number(item['quantity'],3).rstrip('0').rstrip(','),item['name'],number(item['price']) if customer else '',number(item['total']) if customer else '']
        left=x
        for col,(value,w) in enumerate(zip(cells,widths)):
            text(c,value,left+3,bottom+row_height-7,w-6,6.2,align='left' if col==1 else 'right',max_lines=2 if col==1 else 1,leading=6)
            left+=w
    position=x
    for w in widths[:-1]:position+=w;c.line(position,table_top,position,table_top-15-10*row_height)
    c.line(x,table_top,x+width,table_top)
    after=table_top-15-10*row_height
    quantities=sum(Decimal(i['quantity']) for i in items)
    text(c,'QUANTIDADE DESTA FOLHA: '+number(quantities,3).rstrip('0').rstrip(','),x+4,after-13,width-8,6.7,True)
    if customer:
        total=sum(Decimal(i['total']) for i in items)
        text(c,'TOTAL DESTA FOLHA: R$ '+number(total),x+4,after-28,width-8,8.3,True,'right')
    else:text(c,'Conferência / embalagem: ______________________________',x+4,after-28,width-8,6.5)
    text(c,'Padeiro: '+s.get('baker','')+' | Separação: '+s.get('separator',''),x+4,after-43,width-8,6.3,max_lines=2)
    text(c,'Visto / recebido por: _________________________________',x+4,top-height+22,width-8,6.6)
    text(c,'HOMOLOGACAO - NAO COBRAR - DOCUMENTO NAO FISCAL',x+4,top-height+10,width-8,5.6,align='center')
    c.restoreState()
