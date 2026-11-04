from django.core.management.base import BaseCommand
from core.backup import restore_check
class Command(BaseCommand):
    help='Restaura cópia efêmera em banco separado e confere dados/PDFs/auditoria; não altera origem.'
    def handle(self,*args,**kwargs):self.stdout.write(str(restore_check()))
