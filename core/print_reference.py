"""Lê apenas a configuração das emissoras; não importa pedidos nem executa VBA."""
from io import BytesIO
from zipfile import ZipFile,BadZipFile
from django.core.exceptions import ValidationError
from django.db import transaction
from openpyxl import load_workbook
from .models import Company
from .receipt_layout import brand_code
from .workflow import event


@transaction.atomic
def load_company_reference(user,data):
    if not user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    if len(data)>12*1024*1024:raise ValidationError('Limite: 12 MB.')
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(info.file_size for info in archive.infolist())>90*1024*1024:raise ValidationError('Arquivo descompactado excede o limite.')
        book=load_workbook(BytesIO(data),read_only=True,data_only=True,keep_links=False)
        if 'EMPRESAS' not in book.sheetnames:raise ValidationError('Não foi encontrada a aba EMPRESAS do modelo.')
        count=0
        for row in book['EMPRESAS'].iter_rows(min_row=8,max_row=9,max_col=8,values_only=True):
            code=brand_code(str(row[0] or ''))
            if code not in ('TECO','NONA'):continue
            company,_=Company.objects.get_or_create(code=code,defaults={'name':str(row[1] or code).strip()})
            values={'legal_name':row[2],'address':row[4],'phone':row[5],'email':row[6]}
            before={};after={}
            for field,value in values.items():
                if value and not getattr(company,field):
                    before[field]='';setattr(company,field,str(value).strip());after[field]=str(value).strip()
            # CNPJs nunca são inferidos nem substituídos por células vazias.
            if row[3] and not company.cnpj:
                import re
                digits=re.sub(r'\D','',str(row[3]))
                if len(digits)==14:company.cnpj=digits;after['cnpj']=digits
            company.full_clean();company.save()
            event(user,company,'CARREGAR_DADOS_EMISSORA',before=before,after=after,reason='Configuração das empresas na planilha; sem importar pedidos, clientes ou vínculos presumidos.')
            count+=1
        return count
    except (BadZipFile,KeyError,ValueError,OSError) as exc:raise ValidationError('Não foi possível ler o modelo de impressão.') from exc
    finally:
        if 'book' in locals():book.close()
