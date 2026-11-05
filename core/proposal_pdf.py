"""Layout A4 baseado no Modelo_Orcamento_Nona_Cecilia_Em_Branco.docx."""
from io import BytesIO
from xml.sax.saxutils import escape
from decimal import Decimal
from datetime import date
from pathlib import Path
import reportlab
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate,Paragraph,Table,TableStyle,Spacer,Image,HRFlowable,KeepTogether,LongTable
from .receipt_layout import receipt_logo,number

GOLD=colors.HexColor('#A37C3A')
DARK=colors.HexColor('#3D3025')
INK=colors.HexColor('#4B4743')
MUTED=colors.HexColor('#7B7167')
PALE=colors.HexColor('#F7F2E9')
WIDTH,HEIGHT=A4
MARGIN=51.85
CONTENT=WIDTH-2*MARGIN
# Fontes distribuídas pelo próprio ReportLab, incorporadas ao documento para
# manter acentuação e medidas iguais no navegador e na impressão.
FONT='ProposalVera';BOLD='ProposalVeraBold'
FONT_DIR=Path(reportlab.__file__).parent/'fonts'
pdfmetrics.registerFont(TTFont(FONT,str(FONT_DIR/'Vera.ttf')))
pdfmetrics.registerFont(TTFont(BOLD,str(FONT_DIR/'VeraBd.ttf')))


def tax_id(value):
    if len(value)==14:return f'{value[:2]}.{value[2:5]}.{value[5:8]}/{value[8:12]}-{value[12:]}'
    if len(value)==11:return f'{value[:3]}.{value[3:6]}.{value[6:9]}-{value[9:]}'
    return value


def render_proposal(snapshot):
    out=BytesIO();company=snapshot['company'];logo=receipt_logo(company['code'])
    styles={
        'body':ParagraphStyle('proposal_body',fontName=FONT,fontSize=9,leading=12,textColor=INK),
        'small':ParagraphStyle('proposal_small',fontName=FONT,fontSize=7.5,leading=9.5,textColor=MUTED),
        'company':ParagraphStyle('proposal_company',fontName=BOLD,fontSize=19,leading=22,textColor=DARK),
        'gold':ParagraphStyle('proposal_gold',fontName=BOLD,fontSize=8.5,leading=11,textColor=GOLD),
        'title':ParagraphStyle('proposal_title',fontName=BOLD,fontSize=18,leading=22,textColor=DARK),
        'client':ParagraphStyle('proposal_client',fontName=BOLD,fontSize=11,leading=14,textColor=DARK),
        'header':ParagraphStyle('proposal_header',fontName=BOLD,fontSize=8,leading=10,textColor=colors.white),
        'right':ParagraphStyle('proposal_right',fontName=BOLD,fontSize=9,leading=12,textColor=DARK,alignment=2),
        'total':ParagraphStyle('proposal_total',fontName=BOLD,fontSize=18,leading=23,textColor=colors.white,alignment=2),
        'total_label':ParagraphStyle('proposal_total_label',fontName=BOLD,fontSize=8.5,leading=11,textColor=colors.HexColor('#E3CEA7')),
        'total_terms':ParagraphStyle('proposal_total_terms',fontName=FONT,fontSize=8.5,leading=11,textColor=colors.HexColor('#F0E8DA')),
    }
    def p(value,style='body'):
        return Paragraph(escape(str(value or '')).replace('\n','<br/>'),styles[style])
    def section(label):return [Spacer(1,10),p(label,'gold'),Spacer(1,6)]
    def page(canvas,doc):
        canvas.saveState()
        if logo.exists():
            canvas.setFillAlpha(.035)
            canvas.drawImage(ImageReader(str(logo)),(WIDTH-260)/2,HEIGHT/2-120,width=260,height=240,preserveAspectRatio=True,mask='auto')
            canvas.setFillAlpha(1)
        canvas.setStrokeColor(GOLD);canvas.setLineWidth(2.8);canvas.line(MARGIN,HEIGHT-30,WIDTH-MARGIN,HEIGHT-30)
        canvas.setStrokeColor(colors.HexColor('#E5DCCF'));canvas.setLineWidth(.45);canvas.line(MARGIN,35,WIDTH-MARGIN,35)
        canvas.setFillColor(MUTED);canvas.setFont(FONT,7)
        canvas.drawString(MARGIN,23,company['name'][:65])
        canvas.drawRightString(WIDTH-MARGIN,23,f'Orçamento comercial · Página {doc.page}')
        canvas.restoreState()
    head=[p(company['name'],'company'),p(company['subtitle'],'gold'),Spacer(1,5),p(company.get('legal_name',''),'small'),p('CNPJ: '+(tax_id(company.get('tax_id','')) or 'Pendente de informação'),'small'),p(company.get('address',''),'small'),p('  |  '.join(v for v in [company.get('phone',''),company.get('email','')] if v),'small')]
    logo_cell=''
    if logo.exists():
        width,height=ImageReader(str(logo)).getSize();scale=min(78/width,80/height)
        logo_cell=Image(str(logo),width=width*scale,height=height*scale)
    table=Table([[logo_cell,head]],colWidths=[89.3,CONTENT-89.3])
    table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    flow=[table,Spacer(1,8),HRFlowable(width='100%',thickness=.8,color=colors.HexColor('#D7BE8B')),Spacer(1,10),p('P R O P O S T A   C O M E R C I A L','gold'),Spacer(1,4),p('Orçamento — '+snapshot['title'],'title')]
    if snapshot['summary']:flow.extend([Spacer(1,5),p(snapshot['summary'])])
    issued=date.fromisoformat(snapshot['issued_on']).strftime('%d/%m/%Y')
    valid_until=date.fromisoformat(snapshot['valid_until']).strftime('%d/%m/%Y')
    flow.extend([Spacer(1,6),p(f'{snapshot["number"]} · Emissão: {issued} · Válida até: {valid_until}','small'),Spacer(1,12)])
    client=[p('CLIENTE / DESTINATÁRIO','gold'),Spacer(1,4),p(snapshot['customer_name'],'client'),p('CPF/CNPJ: '+(tax_id(snapshot['customer_tax_id']) or 'Não informado')),p('Endereço: '+(snapshot['customer_address'] or 'Não informado'))]
    client_table=Table([[client]],colWidths=[CONTENT]);client_table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.45,colors.HexColor('#E5DCCF')),('LEFTPADDING',(0,0),(-1,-1),12),('RIGHTPADDING',(0,0),(-1,-1),12),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    flow.append(client_table);flow+=section('DESCRIÇÃO E INVESTIMENTO')
    rows=[[p(label,'header') for label in ['SERVIÇO / PRODUTO','QTD.','VALOR UNITÁRIO','TOTAL']]]
    for item in snapshot['items']:
        quantity=number(item['quantity'],3).rstrip('0').rstrip(',')
        rows.append([p(item['description']),p(quantity+' '+item['unit']),p('R$ '+number(item['unit_price'],2 if Decimal(item['unit_price'])==Decimal(item['unit_price']).quantize(Decimal('.01')) else 4)),p('R$ '+number(item['total']),'right')])
    while len(rows)<5:rows.append([p(''),p(''),p(''),p('')])
    investment=LongTable(rows,colWidths=[CONTENT*.41,CONTENT*.17,CONTENT*.20,CONTENT*.22],repeatRows=1,minRowHeights=[25]+[23]*(len(rows)-1))
    investment.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),GOLD),('LINEBELOW',(0,1),(-1,-1),.4,colors.HexColor('#E5DCCF')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#FBF9F5')])]))
    flow.append(investment)
    menu=[line.strip().lstrip('•● ').strip() for line in snapshot['included_items'].splitlines() if line.strip()]
    if menu:
        flow+=section('CARDÁPIO / ITENS INCLUSOS')
        cells=[p('•  '+item) for item in menu]
        if len(cells)%2:cells.append(p(''))
        menu_table=LongTable([cells[index:index+2] for index in range(0,len(cells),2)],colWidths=[CONTENT/2]*2)
        menu_table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
        flow.append(menu_table)
    flow.append(Spacer(1,12))
    conditions=p(snapshot['conditions'],'total_terms')
    long_conditions=conditions.wrap(CONTENT*.63-26,HEIGHT)[1]>100
    total_box=Table([[[p('VALOR TOTAL DO ORÇAMENTO','total_label'),Spacer(1,4),p('Condições comerciais detalhadas abaixo.','total_terms') if long_conditions else conditions],p('R$ '+number(snapshot['total']),'total')]],colWidths=[CONTENT*.63,CONTENT*.37])
    total_box.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),DARK),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),13),('RIGHTPADDING',(0,0),(-1,-1),13),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    flow.append(total_box)
    if long_conditions:flow+=section('CONDIÇÕES COMERCIAIS');flow.append(p(snapshot['conditions']))
    flow.append(Spacer(1,8))
    validity=f'Validade do orçamento: {snapshot["valid_days"]} dias.'
    if snapshot['notes']:validity+='  |  Observações: '+snapshot['notes']
    note=Table([[p(validity)]],colWidths=[CONTENT]);note.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),('TOPPADDING',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    if p(validity).wrap(CONTENT-20,HEIGHT)[1]>120:flow.append(p(validity))
    else:flow.append(note)
    flow.append(KeepTogether([Spacer(1,14),p('_____________________________________','small'),p(snapshot['responsible'],'gold'),p('Responsável pela proposta','small')]))
    SimpleDocTemplate(out,pagesize=A4,leftMargin=MARGIN,rightMargin=MARGIN,topMargin=43,bottomMargin=49,title='Proposta comercial '+snapshot['number'],author=company['name']).build(flow,onFirstPage=page,onLaterPages=page)
    return out.getvalue()
