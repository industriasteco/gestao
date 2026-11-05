from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from .templatetags.erp import brl


def render_manifest(manifest,lines,bag):
    out=BytesIO();styles=getSampleStyleSheet();story=[]
    small=styles['BodyText'];small.fontSize=9;small.leading=13
    def p(value):return Paragraph(escape(str(value or '')).replace('\n','<br/>'),small)
    title=f'Romaneio de entrega - {manifest.company.name}'
    story.extend([Paragraph(escape(title),styles['Title']),p('CONTROLE DE ENTREGA E MALOTE - NÃO É DOCUMENTO FISCAL'),Spacer(1,10),
        p(f'Rota: {manifest.route.name} | Data: {manifest.date:%d/%m/%Y}'),p(f'Motorista: {manifest.driver_name} | Veículo: {manifest.vehicle}'),p(f'Referência: {str(manifest.pk)[:8].upper()}')])
    if any(line.order.synthetic for line in lines):story.append(p('HOMOLOGAÇÃO - PEDIDOS DE TESTE - NÃO COBRAR'))
    story.extend([p(manifest.notes),Spacer(1,12)])
    for line in lines:
        block=[p(f'{line.sequence}. {line.client_name}'),p(line.address)]
        for item in line.items_snapshot:block.append(p(f'{item["quantity"]} {item["unit"]} - {item["product"]}'))
        block.extend([p(line.instructions),p(f'Valor previsto: {brl(line.amount_due)} | Dinheiro informado: {brl(line.reported_amount)}'),
            p(f'Pagamento: {line.payment_status} | Entrega: {line.get_delivery_status_display()}'),p(line.evidence)])
        if line.order.status=='CANCELADO':block.append(p('ATENÇÃO: PEDIDO CANCELADO APÓS A GERAÇÃO. NÃO ENTREGAR / NÃO COBRAR.'))
        if bag and bag.status=='CONFERIDO' and line.reported_amount>0 and not line.receivable_id:
            block.append(p('Sem conta vinculada: não houve baixa no financeiro.'))
        if not bag:block.extend([p('Preencher no retorno: [ ] pagou  [ ] não pagou  [ ] parcial  Valor R$: __________________'),p('Recebedor / assinatura: __________________________  Observações: __________________________')])
        from reportlab.platypus import HRFlowable
        story.extend(block)
        story.extend([Spacer(1,8),HRFlowable(width='100%',thickness=.5,color=colors.HexColor('#d6dfd7')),Spacer(1,10)])
    declared=sum(line.reported_amount for line in lines)
    story.extend([Spacer(1,10),Paragraph('Conferência do malote',styles['Heading2']),p(f'Dinheiro informado pelo motorista: {brl(declared)}')])
    if bag:
        story.extend([p(f'Malote: {bag.reference} | Contado: {brl(bag.counted)} | Diferença: {brl(bag.counted-bag.declared)}'),p(f'Situação: {bag.get_status_display()} | Conferido por: {bag.actor} | {bag.checked_at:%d/%m/%Y %H:%M}'),p(bag.notes)])
    else:story.extend([p('Conferência pendente. Dinheiro contado: R$ ______________ Malote nº: ______________'),p('Conferido por: _________________________ Data: ______________ Assinatura: _________________________')])
    SimpleDocTemplate(out,pagesize=A4,rightMargin=42,leftMargin=42,topMargin=35,bottomMargin=35,title=title).build(story)
    return out.getvalue()
