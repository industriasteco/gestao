from django.db import migrations
from django.db.models import Q


def configure(apps,schema_editor):
    Company=apps.get_model('core','Company')
    Audit=apps.get_model('core','Audit')
    alias=schema_editor.connection.alias
    mappings=[(Q(code__iexact='TECO'),'Sistema Imagem'),
              (Q(code__iexact='NONA')|Q(code__iexact='NONA CECÍLIA')|Q(code__iexact='NONA CECILIA'),'Multicomp')]
    for condition,system in mappings:
        for company in Company.objects.using(alias).filter(condition,fiscal_system=''):
            company.fiscal_system=system;company.save(using=alias,update_fields=['fiscal_system'])
            Audit.objects.using(alias).create(entity=str(company.pk),action='DEFINIR_EMISSOR_FISCAL',after={'fiscal_system':system},reason='Sistema atual informado pelo usuário. Cadastro da preferência, sem configurar conexão ou emissão fiscal.')


class Migration(migrations.Migration):
    dependencies=[('core','0013_company_fiscal_system_and_more')]
    operations=[migrations.RunPython(configure,migrations.RunPython.noop)]
