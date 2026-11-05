"""Leitura local de XML NF-e 4.00. Sem conexão fiscal, execução ou entidades externas."""
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError
from django.core.exceptions import ValidationError

NS={'n':'http://www.portalfiscal.inf.br/nfe'}
MAX_XML=5*1024*1024


def valid_access_key(key):
    if not re.fullmatch(r'\d{44}',key):return False
    total=sum(int(digit)*(2+index%8) for index,digit in enumerate(reversed(key[:43])))
    remainder=total%11
    return int(key[-1])==(0 if remainder<2 else 11-remainder)


def value(node,path,*,required=False,limit=200):
    item=node.find(path,NS)
    result=(item.text or '').strip() if item is not None else ''
    if required and not result:raise ValidationError(f'XML sem campo obrigatório: {path.split("/")[-1].replace("n:","")}.')
    if len(result)>limit:raise ValidationError('Um campo do XML ultrapassa o tamanho permitido.')
    return result


def money(text):
    if not re.fullmatch(r'\d{1,13}(?:\.\d{1,2})?',text or ''):raise ValidationError('Valor monetário inválido no XML.')
    try:amount=Decimal(text)
    except InvalidOperation:raise ValidationError('Valor monetário inválido no XML.')
    if not amount.is_finite() or amount<0:raise ValidationError('Valor monetário inválido no XML.')
    return amount.quantize(Decimal('.01'))


def xml_date(text):
    try:
        if 'T' in text:return datetime.fromisoformat(text.replace('Z','+00:00')).date()
        return date.fromisoformat(text)
    except (ValueError,TypeError):raise ValidationError('Data inválida no XML.')


def parse_nfe(data):
    if not data or len(data)>MAX_XML:raise ValidationError('Selecione um XML de até 5 MB.')
    try:root=fromstring(data,forbid_dtd=True,forbid_entities=True,forbid_external=True)
    except (ParseError,DefusedXmlException,ValueError):raise ValidationError('XML inválido ou com conteúdo externo não permitido.')
    if root.tag!='{'+NS['n']+'}nfeProc':raise ValidationError('Envie o XML completo da NF-e (nfeProc), com protocolo. Eventos, resumos e arquivos PDF não são aceitos.')
    if sum(1 for _ in root.iter())>25000:raise ValidationError('XML contém elementos demais.')
    nodes=root.findall('n:NFe/n:infNFe',NS)
    if len(nodes)!=1:raise ValidationError('O arquivo deve conter exatamente uma NF-e.')
    info=nodes[0]
    if info.get('versao')!='4.00':raise ValidationError('Este importador aceita XML NF-e versão 4.00.')
    identifier=info.get('Id') or ''
    if not identifier.startswith('NFe'):raise ValidationError('Identificação da NF-e inválida.')
    key=identifier.removeprefix('NFe')
    if not valid_access_key(key):raise ValidationError('Chave de acesso da NF-e inválida.')
    protocol=root.find('n:protNFe/n:infProt',NS)
    if protocol is None or value(protocol,'n:cStat',required=True) not in ('100','150'):
        raise ValidationError('O XML não contém protocolo informado de autorização (100 ou 150).')
    if value(protocol,'n:chNFe',required=True)!=key:raise ValidationError('Chave do protocolo diferente da chave da NF-e.')
    ide=info.find('n:ide',NS);emit=info.find('n:emit',NS);dest=info.find('n:dest',NS)
    if ide is None or emit is None or dest is None:raise ValidationError('XML sem identificação, emitente ou destinatário.')
    if value(ide,'n:tpNF',required=True)!='1' or value(ide,'n:finNFe',required=True)!='1':
        raise ValidationError('Importe uma nota de venda normal do fornecedor. Devoluções, ajustes e complementos exigem tratamento próprio.')
    environment=value(ide,'n:tpAmb',required=True)
    if environment not in ('1','2') or value(protocol,'n:tpAmb',required=True)!=environment:raise ValidationError('Ambiente fiscal inválido ou divergente no protocolo.')
    issuer=value(emit,'n:CNPJ') or value(emit,'n:CPF')
    if not re.fullmatch(r'(?:\d{11}|\d{14})',issuer):raise ValidationError('CPF/CNPJ do fornecedor inválido.')
    recipient=value(dest,'n:CNPJ',required=True)
    if not re.fullmatch(r'\d{14}',recipient):raise ValidationError('O destinatário precisa ter CNPJ de 14 dígitos.')
    if issuer==recipient:raise ValidationError('A nota foi emitida pela própria destinatária; não será tratada como compra.')
    model=value(ide,'n:mod',required=True);series=value(ide,'n:serie',required=True);number=value(ide,'n:nNF',required=True)
    if model not in ('55','65') or not re.fullmatch(r'\d{1,3}',series) or not re.fullmatch(r'\d{1,9}',number) or int(number)<=0:
        raise ValidationError('Modelo, série ou número da nota inválidos.')
    issued_on=xml_date(value(ide,'n:dhEmi') or value(ide,'n:dEmi',required=True))
    if (key[:2]!=value(ide,'n:cUF',required=True) or key[2:6]!=issued_on.strftime('%y%m')
        or key[6:20]!=issuer.zfill(14) or key[20:22]!=model or key[22:25]!=series.zfill(3)
        or key[25:34]!=number.zfill(9) or key[34]!=value(ide,'n:tpEmis',required=True)
        or key[35:43]!=value(ide,'n:cNF',required=True) or key[-1]!=value(ide,'n:cDV',required=True)):
        raise ValidationError('Os dados da nota não correspondem à chave de acesso.')
    total=money(value(info,'n:total/n:ICMSTot/n:vNF',required=True))
    installments=[];references=set()
    for index,dup in enumerate(info.findall('n:cobr/n:dup',NS),1):
        reference=value(dup,'n:nDup',limit=60) or str(index).zfill(3)
        due_text=value(dup,'n:dVenc');due=xml_date(due_text) if due_text else None;amount=money(value(dup,'n:vDup',required=True))
        if reference in references or amount<=0 or (due is not None and due<issued_on):raise ValidationError('Duplicata repetida, valor zero ou vencimento anterior à emissão.')
        references.add(reference)
        installments.append({'reference':reference,'due_on':str(due) if due else '','amount':str(amount)})
    if len(installments)>120:raise ValidationError('Limite de 120 parcelas por nota.')
    summed=sum((Decimal(row['amount']) for row in installments),Decimal(0))
    fat=info.find('n:cobr/n:fat',NS)
    net=money(value(fat,'n:vLiq',required=True)) if fat is not None else None
    if fat is not None:
        original=value(fat,'n:vOrig');discount=value(fat,'n:vDesc')
        if original and discount and money(original)-money(discount)!=net:raise ValidationError('Valor líquido da fatura não corresponde ao original menos desconto.')
    target=net if net is not None else (summed if installments else total)
    if target>total or summed>total:raise ValidationError('A fatura/parcelas ultrapassa o valor total da NF-e.')
    if installments and target!=summed:raise ValidationError('A soma das duplicatas não corresponde ao valor líquido da fatura.')
    warnings=[]
    if not installments:warnings.append('XML sem duplicatas com vencimentos. Informe as parcelas antes de gerar contas; não foi presumido vencimento nem quitação.')
    if any(not row['due_on'] for row in installments):warnings.append('Há duplicatas sem vencimento. Complete as datas para gerar as contas; valores do XML serão preservados.')
    if target<total:warnings.append(f'A fatura/parcelas totaliza {target} para uma nota de {total}. Confira a diferença; nenhum valor foi considerado pago automaticamente.')
    if environment=='2':warnings.append('XML de homologação: contas geradas são de teste e ficam fora dos totais reais do painel.')
    warnings.append('Leitura local do XML. Assinatura digital e situação atual na SEFAZ não foram verificadas; confira o documento do fornecedor.')
    address=emit.find('n:enderEmit',NS)
    address_text=''
    if address is not None:address_text=', '.join(filter(None,[value(address,'n:xLgr'),value(address,'n:nro'),value(address,'n:xBairro'),value(address,'n:xMun'),value(address,'n:UF'),value(address,'n:CEP')]))
    items=[]
    for det in info.findall('n:det',NS):
        product=det.find('n:prod',NS)
        if product is not None:items.append({'code':value(product,'n:cProd',limit=60),'description':value(product,'n:xProd'),'unit':value(product,'n:uCom',limit=20),'quantity':value(product,'n:qCom',limit=30),'total':value(product,'n:vProd',limit=30),'ncm':value(product,'n:NCM',limit=8),'cfop':value(product,'n:CFOP',limit=4)})
    result={'access_key':key,'number':str(int(number)),'series':str(int(series)),'model':model,'issued_on':str(issued_on),
        'total':str(total),'financial_total':str(target),'environment':environment,'recipient':recipient,
        'supplier':{'tax_id':issuer,'name':value(emit,'n:xNome',required=True),'trade_name':value(emit,'n:xFant'),'address':address_text,'phone':value(address,'n:fone',limit=100) if address is not None else ''},
        'installments':installments,'warnings':warnings,'items':items,'invoice_reference':value(fat,'n:nFat',limit=60) if fat is not None else '',
        'payment_methods':[{'code':value(pay,'n:tPag',limit=2),'amount':value(pay,'n:vPag',limit=30)} for pay in info.findall('n:pag/n:detPag',NS)]}
    result['payload_hash']=hashlib.sha256(json.dumps(result,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return result
