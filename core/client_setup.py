"""Condições e rotina semanal confirmadas durante o cadastro/primeiro pedido."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Company,Recurrence
from .services import authorize
from .management_services import set_current_price
from .workflow import event
from .catalog import product_available


def client_prices_data(formset,company):
    rows=[form.cleaned_data for form in formset if form.cleaned_data and not form.cleaned_data.get('DELETE')]
    if any(not product_available(row['product'],company) for row in rows):raise ValidationError('Há produto indisponível para a empresa do cliente.')
    return rows


def save_client_prices(user,client,rows):
    for row in rows:set_current_price(user,client.company,row['product'],row['amount'],client)


def recurring_days(client):
    days=client.recurring_weekdays
    if not isinstance(days,list) or any(type(day) is not int or day not in range(1,8) for day in days):raise ValidationError('Confira os dias recorrentes do cliente.')
    return sorted(set(days))


@transaction.atomic
def sync_client_days(user,client,previous_days):
    authorize(user,client.company,'core.change_client')
    days=recurring_days(client)
    if days==sorted(previous_days):return
    Company.objects.select_for_update().get(pk=client.company_id)
    for rule in Recurrence.objects.select_for_update().filter(client=client,auto_prepare=True,archived=False):
        before=list(rule.weekdays);rule.weekdays=days;rule.save(update_fields=['weekdays'])
        event(user,rule,'ALTERAR_DIAS_CLIENTE',{'weekdays':before},{'weekdays':days})
    event(user,client,'ALTERAR_DIAS_RECORRENTES',{'weekdays':previous_days},{'weekdays':days})


@transaction.atomic
def save_recurring_items(user,client,lines,slot,time,shift,notes='',origin=None,replace=False):
    authorize(user,client.company,'core.add_recurrence')
    Company.objects.select_for_update().get(pk=client.company_id)
    days=recurring_days(client)
    if not days:raise ValidationError('Marque os dias recorrentes no cadastro do cliente.')
    if not time or shift not in ('NOTURNO','DIURNO') or not slot.strip():raise ValidationError('Informe identificação, horário e turno da rotina.')
    if not client.active or not client.company.active:raise ValidationError('Cliente ou empresa inativo.')
    if origin and (origin.client_id!=client.pk or origin.company_id!=client.company_id):raise ValidationError('Pedido de outra empresa ou cliente.')
    grouped={}
    for line in lines:
        product=line['product'];quantity=line['quantity']
        if not product_available(product,client.company) or not product.active:raise ValidationError('Produto inativo ou indisponível para esta empresa.')
        if not quantity.is_finite() or quantity<=0:raise ValidationError('Informe quantidades positivas para a rotina.')
        grouped.setdefault(product.pk,[product,Decimal(0)])[1]+=quantity
    if not grouped or len(grouped)>100:raise ValidationError('Informe de 1 a 100 produtos recorrentes.')
    existing=Recurrence.objects.select_for_update().filter(client=client,auto_prepare=True,archived=False,slot=slot,time=time,shift=shift)
    by_product={};rules=[]
    for rule in existing:by_product.setdefault(rule.product_id,[]).append(rule)
    start=max(timezone.localdate(),origin.date) if origin else timezone.localdate()
    for product_id,(product,quantity) in grouped.items():
        candidates=by_product.get(product_id,[])
        rule=candidates[0] if candidates else Recurrence(company=client.company,client=client,product=product)
        before={'quantity':str(rule.quantity),'weekdays':rule.weekdays,'active':rule.active} if rule.pk and not rule._state.adding else {}
        rule.quantity=quantity;rule.slot=slot;rule.time=time;rule.shift=shift;rule.weekdays=days
        rule.valid_from=start;rule.valid_until=None;rule.notes=notes;rule.active=True;rule.auto_prepare=True
        rule.full_clean();rule.save();rules.append(rule)
        event(user,rule,'SALVAR_ROTINA_CLIENTE',before,{'quantity':str(quantity),'weekdays':days,'auto_prepare':True,'active':True})
    keep=[rule.pk for rule in rules]
    previous=existing.exclude(pk__in=keep) if replace else existing.filter(product_id__in=grouped).exclude(pk__in=keep)
    for rule in previous:
        if rule.active:
            rule.active=False;rule.save(update_fields=['active']);event(user,rule,'SUBSTITUIR_ROTINA_CLIENTE',{'active':True},{'active':False})
    if origin:
        origin.preparation_rules=[str(rule.pk) for rule in rules];origin.recurrence=rules[0]
        origin.save(update_fields=['preparation_rules','recurrence'])
    return rules
