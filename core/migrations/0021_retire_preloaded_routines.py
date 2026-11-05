from django.db import migrations
from django.utils import timezone


def retire_preloaded(apps,schema_editor):
    Company=apps.get_model('core','Company');Client=apps.get_model('core','Client')
    Recurrence=apps.get_model('core','Recurrence');Audit=apps.get_model('core','Audit')
    now=timezone.now()
    # Rotinas confirmadas no novo fluxo do cliente têm auto_prepare=True.
    # As antigas, inclusive as importadas, saem da programação sem excluir FKs.
    rows=list(Recurrence.objects.filter(archived=False,auto_prepare=False))
    events=[Audit(entity=str(rule.pk),action='RETIRAR_PRE_CADASTRO',before={'active':rule.active,'weekdays':rule.weekdays,'quantity':str(rule.quantity)},after={'active':False,'archived':True},reason='Solicitação de começar a programação do zero; cadastros e pedidos preservados.') for rule in rows]
    Audit.objects.bulk_create(events)
    Recurrence.objects.filter(pk__in=[rule.pk for rule in rows]).update(active=False,auto_prepare=False,archived=True)
    affected={rule.client_id for rule in rows}
    keep=Recurrence.objects.filter(archived=False,active=True).values('client_id')
    Client.objects.filter(pk__in=affected).exclude(pk__in=keep).update(recurring_weekdays=[])
    for company in Company.objects.all():
        company.routines_reset_at=now;company.save(update_fields=['routines_reset_at'])
        Audit.objects.create(entity=str(company.pk),action='INICIAR_PROGRAMACAO_ZERO',after={'routines_retired':sum(rule.company_id==company.pk for rule in rows),'orders_deleted':0},reason='Limpeza inicial solicitada pelo usuário. Novas rotinas confirmadas são preservadas.')


class Migration(migrations.Migration):
    dependencies=[('core','0020_operational_start')]
    operations=[migrations.RunPython(retire_preloaded,migrations.RunPython.noop)]
