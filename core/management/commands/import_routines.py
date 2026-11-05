from datetime import date
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from core.models import Company
from core.excel_import import import_workbook

class Command(BaseCommand):
    help='Analisa outubro e cadastra somente clientes, produtos e rotinas; nunca importa pedidos antigos.'
    def add_arguments(self,parser):
        parser.add_argument('file')
        parser.add_argument('--company',required=True)
        parser.add_argument('--user',required=True)
        parser.add_argument('--start',required=True,type=date.fromisoformat)
    def handle(self,*args,**options):
        try:
            company=Company.objects.get(code=options['company'])
            user=get_user_model().objects.get(username=options['user'],is_superuser=True,is_active=True)
            path=Path(options['file'])
            batch,created,_=import_workbook(user,company,path.read_bytes(),path.name,options['start'])
        except (Company.DoesNotExist,get_user_model().DoesNotExist,OSError,ValidationError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f'{"Rotinas cadastradas" if created else "Arquivo já processado"}. Pedidos criados: 0. Lote: {batch.pk}')
