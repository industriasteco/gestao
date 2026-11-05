"""Extrai somente o cabeçalho do DOCX fornecido, sem executar código ou acessar links."""
import hashlib
import re
import unicodedata
from io import BytesIO
from pathlib import PurePath
from zipfile import ZipFile,BadZipFile
from defusedxml.ElementTree import fromstring
from defusedxml.common import DefusedXmlException
from xml.etree.ElementTree import ParseError
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from .models import Company,ProposalProfile
from .receipt_layout import brand_code
from .workflow import event

W={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


def read_profile(data):
    if not data or len(data)>12*1024*1024:raise ValidationError('Selecione um modelo DOCX de até 12 MB.')
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(item.file_size for item in archive.infolist())>90*1024*1024:raise ValidationError('Modelo descompactado muito grande.')
            root=fromstring(archive.read('word/document.xml'),forbid_dtd=True,forbid_entities=True,forbid_external=True)
    except (BadZipFile,KeyError,ParseError,DefusedXmlException,ValueError):raise ValidationError('Não foi possível ler o modelo DOCX.')
    def text(node):return ''.join(p.text or '' for p in node.findall('.//w:t',W)).strip()
    body=root.find('w:body',W)
    if body is None:raise ValidationError('Modelo sem conteúdo.')
    all_text=re.sub(r'\s','',text(body)).upper()
    if 'PROPOSTACOMERCIAL' not in all_text:raise ValidationError('Selecione o modelo de proposta comercial.')
    cells=body.findall('w:tbl/w:tr/w:tc',W)
    if len(cells)<2:raise ValidationError('Cabeçalho de empresa não encontrado.')
    lines=[text(p) for p in cells[1].findall('w:p',W) if text(p)]
    index=next((i for i,line in enumerate(lines) if 'CNPJ:' in line.upper()),None)
    if index is None or index<2 or len(lines)<index+3:raise ValidationError('Cabeçalho incompleto: confira nome, CNPJ, endereço e contato.')
    tax_id=re.sub(r'\D','',lines[index])
    if len(tax_id)!=14:raise ValidationError('CNPJ do cabeçalho inválido.')
    contact=lines[index+2]
    email_match=re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',contact)
    email=email_match.group() if email_match else ''
    phone=contact.replace(email,'').strip(' |')
    paragraphs=[text(p) for p in body.findall('w:p',W) if text(p)]
    responsible=''
    for i,line in enumerate(paragraphs):
        if line.lower()=='responsável pela proposta' and i:responsible=paragraphs[i-1]
    return dict(display_name=lines[0],subtitle=lines[1],legal_name=lines[index-1],tax_id=tax_id,address=lines[index+1],phone=phone,email=email,responsible=responsible)


@transaction.atomic
def import_profile(user,company,data,filename):
    if not user.is_superuser:raise PermissionDenied
    Company.objects.select_for_update().get(pk=company.pk)
    values=read_profile(data)
    name=''.join(c for c in unicodedata.normalize('NFKD',values['display_name'].upper()) if not unicodedata.combining(c))
    expected='NONA' if 'NONA' in name else 'TECO' if 'TECO' in name else ''
    if expected!=brand_code(company.code):raise ValidationError('A empresa do cabeçalho do modelo não corresponde à empresa selecionada.')
    profile,_=ProposalProfile.objects.get_or_create(company=company)
    before={key:getattr(profile,key) for key in values}
    for key,value in values.items():setattr(profile,key,value)
    profile.source_filename=PurePath(filename).name[:200];profile.source_sha256=hashlib.sha256(data).hexdigest()
    profile.full_clean();profile.save()
    event(user,profile,'IMPORTAR_CABECALHO_PROPOSTA',before=before,after=values,reason='Dados do modelo confirmados para propostas. Cadastro fiscal e notinhas anteriores não foram alterados.')
    return profile
