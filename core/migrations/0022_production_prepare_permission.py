from django.db import migrations


def allow_prepare(apps,schema_editor):
    Group=apps.get_model('auth','Group');Permission=apps.get_model('auth','Permission')
    group=Group.objects.filter(name='ERP_PRODUCAO').first()
    permission=Permission.objects.filter(content_type__app_label='core',codename='prepare_day').first()
    if group and permission:group.permissions.add(permission)


class Migration(migrations.Migration):
    dependencies=[('core','0021_retire_preloaded_routines')]
    operations=[migrations.RunPython(allow_prepare,migrations.RunPython.noop)]
