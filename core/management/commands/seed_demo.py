from datetime import date,time
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group,Permission
from core.models import *
from core.services import stage
from django.conf import settings

class Command(BaseCommand):
    help='Cria apenas cadastros artificiais; carrega CSVs exclusivamente em staging.'
    def handle(self,*args,**kwargs):
        for name,perms in {'ADMINISTRADOR':[], 'GESTAO_PRODUCAO':['prepare_day','activate_recurrence','check_production','review_staging','issue_document','confirm_delivery','cancel_issued'],'ATENDIMENTO_PEDIDOS':['prepare_day'],'PADEIRO':[],'SEPARACAO_ENTREGAS':['confirm_delivery'],'FINANCEIRO':['issue_document','close_month'],'AUDITOR_LEITURA':[]}.items():
            group,_=Group.objects.get_or_create(name=name)
            group.permissions.set(Permission.objects.filter(content_type__app_label='core') if name=='ADMINISTRADOR' else Permission.objects.filter(content_type__app_label='core',codename__in=perms))
        for code,name,shift in [('TECO','PANIFICADORA DO TECO','NOTURNO'),('NONA','NONA CECÍLIA','DIURNO')]:
            co,_=Company.objects.get_or_create(code=code,defaults={'name':name})
            client,_=Client.objects.get_or_create(company=co,name='CLIENTE ARTIFICIAL — '+code)
            product,_=Product.objects.get_or_create(company=co,name='PÃO TESTE (ARTIFICIAL)')
            rule,_=Recurrence.objects.get_or_create(company=co,client=client,product=product,slot='1ª entrega teste',defaults=dict(quantity=100,time=time(6),shift=shift,weekdays=list(range(1,8)),valid_from=date(2026,1,1)))
            # Demo activation is explicit and audited; never applies to legacy rows.
            if not rule.active:
                rule.active=True;rule.save();Audit.objects.create(entity=str(rule.pk),action='ATIVACAO_DEMO_ARTIFICIAL',reason='Fixture exclusivamente artificial, sem preço ou CNPJ')
        for path in (settings.BASE_DIR/'reference/03_DADOS_PARA_MIGRACAO').glob('*.csv'): stage(path)
        self.stdout.write('Exemplos artificiais preparados, sem preços ou CNPJs inventados. CSVs locais ficam só em staging; na hospedagem, carregue em Dados antigos.')
