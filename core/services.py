import csv, hashlib, io
from collections import defaultdict
from decimal import Decimal
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from .models import *

def companies(user):
    return Company.objects.all() if user.is_superuser else Company.objects.filter(membership__user=user)

def authorize(user, company, permission):
    if not user.has_perm(permission) or not companies(user).filter(pk=company.pk).exists():
        Audit.objects.create(actor=user,entity=str(company.pk),action='ACESSO_NEGADO',reason=permission)
        raise PermissionDenied

@transaction.atomic
def activate(user, rule, reason):
    authorize(user,rule.company,'core.activate_recurrence')
    if rule.archived:raise ValidationError('Esta rotina foi retirada da programação. Cadastre uma nova rotina confirmada.')
    if not reason.strip(): raise ValidationError('Motivo obrigatório')
    rule.active=True; rule.full_clean(); rule.save()
    Audit.objects.create(actor=user,entity=str(rule.pk),action='ATIVAR',after={'active':True},reason=reason)

@transaction.atomic
def prepare(user, day, automatic_only=False):
    from .operations import production_companies
    scope=production_companies(user)
    list(Company.objects.select_for_update().filter(pk__in=scope.values('pk')).order_by('pk'))
    rules=Recurrence.objects.select_for_update().filter(active=True,archived=False,company__in=scope,valid_from__lte=day).filter(Q(valid_until__isnull=True)|Q(valid_until__gte=day)).select_related('company','client','product')
    if automatic_only:rules=rules.filter(auto_prepare=True)
    groups=defaultdict(list)
    for rule in rules:
        authorize(user,rule.company,'core.prepare_day')
        if day.isoweekday() not in rule.weekdays:continue
        exception=RuleException.objects.filter(rule=rule,date=day).first()
        if exception and exception.suspended:continue
        if not rule.client.active or not rule.product.active or not rule.company.active:continue
        if rule.client.company_id!=rule.company_id or rule.product.company_id!=rule.company_id:raise ValidationError('Empresa incompatível')
        prefix='operational' if rule.company.operational_enabled else 'planned'
        key=f'{prefix}:{rule.company_id}:{rule.client_id}:{day}:{rule.slot}:{rule.time}:{rule.shift}'
        groups[key].append((rule,exception))
    count=0
    for key,group in groups.items():
        rule=group[0][0]
        rule_ids=[str(r.pk) for r,_ in group]
        existing=Order.objects.filter(company=rule.company,client=rule.client,date=day,synthetic=not rule.company.operational_enabled)
        # Compatibilidade com os pedidos anteriores e rastreio de todos os fixos
        # agrupados: editar horário/turno não cria outra cópia na mesma data.
        if existing.filter(recurrence_id__in=rule_ids).exists():continue
        if any(existing.filter(preparation_rules__contains=[pk]).exists() for pk in rule_ids):continue
        order,created=Order.objects.get_or_create(idempotency_key=key,defaults=dict(company=rule.company,client=rule.client,recurrence=rule,preparation_rules=rule_ids,date=day,slot=rule.slot,time=rule.time,shift=rule.shift,synthetic=not rule.company.operational_enabled,notes='\n'.join(dict.fromkeys(r.notes for r,_ in group if r.notes))))
        if not created:continue
        lines={}
        for rule,exception in group:
            qty=exception.quantity if exception and exception.quantity is not None else rule.quantity
            lines[rule.product_id]=(rule.product,lines.get(rule.product_id,(None,Decimal(0)))[1]+qty)
            for extra in rule.extra_items.select_related('product').all():
                if extra.product.company_id!=rule.company_id:raise ValidationError('Produto extra de outra empresa')
                lines[extra.product_id]=(extra.product,lines.get(extra.product_id,(None,Decimal(0)))[1]+extra.quantity)
        for product,qty in lines.values():
            OrderItem.objects.create(order=order,product=product,product_name=product.name,unit=product.unit,quantity=qty)
        Audit.objects.create(actor=user,entity=str(order.pk),action='PRE_LANCAR',after={'date':str(day),'source':'RECORRENCIA'})
        count+=1
    return count

def production(orders):
    rows=defaultdict(lambda:dict(NOTURNO=Decimal(0),DIURNO=Decimal(0),SEM_TURNO=Decimal(0),total=Decimal(0)))
    for item in OrderItem.objects.filter(order__in=orders.exclude(status='CANCELADO'),quantity__gt=0).select_related('order'):
        row=rows[(item.product_name,item.unit)]
        row[item.order.shift or 'SEM_TURNO']+=item.quantity; row['total']+=item.quantity
    return [dict(product=k[0],unit=k[1],**v) for k,v in sorted(rows.items())]

@transaction.atomic
def check_production(user,day):
    from .operations import production_orders
    orders=production_orders(user).select_for_update().filter(date=day,status__in=['PRE_LANCADO','CONFERIDO'],pk__in=OrderItem.objects.filter(quantity__gt=0).values('order_id'))
    for order in orders:
        authorize(user,order.company,'core.check_production')
        if not order.shift or not order.items.filter(quantity__gt=0).exists(): raise ValidationError('Turno ou itens ausentes')
    for order in orders:
        if order.status=='CONFERIDO': continue
        order.status='CONFERIDO';order.save(update_fields=['status'])
        Audit.objects.create(actor=user,entity=str(order.pk),action='CONFERIR_PRODUCAO',before={'status':'PRE_LANCADO'},after={'status':'CONFERIDO'})

@transaction.atomic
def review(user,candidate,reason):
    if not user.has_perm('core.review_staging'): raise PermissionDenied
    if not reason.strip(): raise ValidationError('Justificativa obrigatória')
    candidate=Candidate.objects.select_for_update().get(pk=candidate.pk)
    if candidate.approved: return
    candidate.approved=True;candidate.reviewed_by=user;candidate.reason=reason;candidate.save()
    Audit.objects.create(actor=user,entity=str(candidate.pk),action='APROVAR_REVISAO_SEM_IMPORTAR',reason=reason)

def stage(path):
    return stage_bytes(path.read_bytes(),path.name)

@transaction.atomic
def stage_bytes(data,filename):
    from pathlib import PurePath
    filename=PurePath(filename).name
    if not filename.lower().endswith('.csv') or len(data)>5*1024*1024:raise ValidationError('Selecione CSV de até 5 MB.')
    try:
        reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
        rows=list(reader)
    except (UnicodeError,csv.Error):raise ValidationError('CSV deve estar em UTF-8 e separado por vírgulas.')
    if not reader.fieldnames or len(reader.fieldnames)>80 or len(rows)>10000 or any(None in row for row in rows):raise ValidationError('CSV com estrutura inválida ou mais de 10.000 linhas.')
    batch,created=ImportBatch.objects.get_or_create(sha256=hashlib.sha256(data).hexdigest(),defaults={'filename':filename})
    if not created:return batch
    category='RECORRENCIA_SUGERIDA' if 'recorrencias' in filename else 'NOTA_ANTIGA' if 'auditoria_' in filename else 'PREVISAO' if 'previsao_' in filename else 'REFERENCIA'
    Candidate.objects.bulk_create([Candidate(batch=batch,row_number=i,raw=row,category=category) for i,row in enumerate(rows,2)])
    return batch


def prices_on(day):
    return Price.objects.filter(superseded=False,valid_from__lte=day).filter(Q(valid_until__isnull=True)|Q(valid_until__gte=day))


def price_for(company,client,product,day):
    if product.company_id!=company.pk or client.company_id!=company.pk: raise ValidationError('Empresa incompatível')
    prices=prices_on(day).filter(company=company,product=product)
    selected=prices.filter(client=client)
    if not selected.exists(): selected=prices.filter(client__isnull=True)
    if selected.count()!=1: raise ValidationError('Preço ausente ou vigências sobrepostas')
    return selected.get().amount

def financial_operation(*args,**kwargs):
    raise ValidationError('Emissão, entrega financeira e fechamento bloqueados até homologação.')

@transaction.atomic
def adjust(user,order_id,quantity,reason,item_id=None):
    order=Order.objects.select_for_update().get(pk=order_id)
    authorize(user,order.company,'core.prepare_day')
    if order.status!='PRE_LANCADO': raise ValidationError('Somente pré-lançamentos podem ser ajustados')
    if not reason.strip() or not quantity.is_finite() or quantity<0: raise ValidationError('Quantidade ou motivo inválido')
    item=order.items.get(pk=item_id) if item_id else order.items.get()
    before=str(item.quantity);item.quantity=quantity;item.full_clean();item.save()
    Audit.objects.create(actor=user,entity=str(order.pk),action='AJUSTAR',before={'quantity':before},after={'quantity':str(quantity)},reason=reason)

@transaction.atomic
def cancel(user,order_id,reason):
    order=Order.objects.select_for_update().get(pk=order_id)
    authorize(user,order.company,'core.check_production')
    if not reason.strip(): raise ValidationError('Motivo obrigatório')
    if order.status=='CANCELADO': return
    before=order.status;order.status='CANCELADO';order.save()
    Audit.objects.create(actor=user,entity=str(order.pk),action='CANCELAR',before={'status':before},after={'status':'CANCELADO'},reason=reason)

_prepare, _check_production, _activate, _adjust, _cancel = prepare, check_production, activate, adjust, cancel

def require(user,permission):
    if not user.has_perm(permission):
        Audit.objects.create(actor=user,entity='PERMISSOES',action='ACESSO_NEGADO',reason=permission)
        raise PermissionDenied

def prepare(user,day,automatic_only=False):
    require(user,'core.prepare_day')
    return _prepare(user,day,automatic_only=automatic_only)

def check_production(user,day):
    require(user,'core.check_production')
    return _check_production(user,day)

def activate(user,rule,reason):
    authorize(user,rule.company,'core.activate_recurrence')
    return _activate(user,rule,reason)

def adjust(user,order_id,quantity,reason,item_id=None):
    authorize(user,Order.objects.get(pk=order_id).company,'core.prepare_day')
    return _adjust(user,order_id,quantity,reason,item_id)

def cancel(user,order_id,reason):
    authorize(user,Order.objects.get(pk=order_id).company,'core.check_production')
    return _cancel(user,order_id,reason)
