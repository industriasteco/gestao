"""Teste de restauração isolado; nunca remove ou substitui o banco de origem."""
import copy,hashlib,io,json,secrets,tempfile,os
import psycopg
from psycopg import sql
from django.conf import settings
from django.core.management import call_command
from django.db import connections
from .models import Document,Audit,Order

def restore_check():
    config=copy.deepcopy(connections['default'].settings_dict)
    target='teco_restore_'+secrets.token_hex(6)
    alias='restore_validation'
    control=psycopg.connect(host=config['HOST'],port=config['PORT'],user=config['USER'],password=config['PASSWORD'],dbname='postgres',autocommit=True)
    buffer=io.StringIO()
    call_command('dumpdata','contenttypes','auth','core','sessions',database='default',stdout=buffer,verbosity=0,use_natural_foreign_keys=True,use_natural_primary_keys=True)
    data=buffer.getvalue()
    expected={name:count for name,count in [('orders',Order.objects.count()),('documents',Document.objects.count()),('audit',Audit.objects.count())]}
    fd,path=tempfile.mkstemp(prefix='erp-backup-',suffix='.json')
    os.chmod(path,0o600)
    try:
        with os.fdopen(fd,'w') as f:f.write(data)
        control.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target)))
        config['NAME']=target;connections.databases[alias]=config
        call_command('migrate',database=alias,interactive=False,verbosity=0,stdout=io.StringIO())
        call_command('loaddata',path,database=alias,verbosity=0,stdout=io.StringIO())
        actual={'orders':Order.objects.using(alias).count(),'documents':Document.objects.using(alias).count(),'audit':Audit.objects.using(alias).count()}
        if actual!=expected:raise ValueError('Contagens após restauração divergentes')
        for doc in Document.objects.using(alias).all():
            if hashlib.sha256(bytes(doc.data)).hexdigest()!=doc.sha256:raise ValueError('Hash de PDF restaurado divergente')
        return {'counts':actual,'sha256':hashlib.sha256(data.encode()).hexdigest(),'restored':True}
    finally:
        os.unlink(path)
        if alias in connections.databases:
            connections[alias].close();del connections[alias];connections.databases.pop(alias,None)
        control.execute(sql.SQL('DROP DATABASE IF EXISTS {}').format(sql.Identifier(target)))
        control.close()
