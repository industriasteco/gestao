"""Fluxos transacionais de homologação. Nenhum pedido real é faturado."""
import hashlib
from datetime import date
from decimal import Decimal,ROUND_HALF_UP
from functools import wraps
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import *
from .services import authorize,price_for,companies,require
from . import pdf

MONEY=Decimal('0.01')

def event(user,obj,action,before=None,after=None,reason=''):
    return Audit.objects.create(actor=user,entity=str(obj.pk),action=action,before=before or {},after=after or {},reason=reason)

def permitted(permission):
    def decorator(fn):
        @wraps(fn)
        def wrapper(user,order_id,*args,**kwargs):
            order=Order.objects.get(pk=order_id)
            authorize(user,order.company,permission)
            if not order.synthetic:raise ValidationError('Operação real bloqueada: use pedidos artificiais na homologação.')
            return fn(user,order_id,*args,**kwargs)
        return wrapper
    return decorator

def store_document(company,key,kind,data,order=None):
    return Document.objects.create(company=company,key=key,kind=kind,data=data,sha256=hashlib.sha256(data).hexdigest(),order=order)

@permitted('core.issue_document')
@transaction.atomic
def issue(user,order_id):
    order=Order.objects.select_for_update().select_related('company','client').get(pk=order_id)
    if order.status in ('EMITIDO','ENTREGUE','LIBERADO_FECHAMENTO','FECHADO'):
        return Document.objects.get(key=f'order:{order.pk}:v1')
    if order.status!='CONFERIDO':raise ValidationError('Confira a produção antes de emitir.')
    if not order.shift or not order.baker.strip():raise ValidationError('Informe turno e padeiro antes de emitir.')
    if order.client.company_id!=order.company_id:raise ValidationError('Empresa do cliente incompatível.')
    if not order.company.active or not order.client.active:raise ValidationError('Empresa ou cliente inativo.')
    items=[];total=Decimal(0)
    for item in order.items.select_related('product').filter(quantity__gt=0).order_by('pk'):
        if not item.product.active:raise ValidationError('Produto inativo.')
        amount=price_for(order.company,order.client,item.product,order.date)
        line=(amount*item.quantity).quantize(MONEY,rounding=ROUND_HALF_UP)
        item.unit_price_snapshot=amount;item.save(update_fields=['unit_price_snapshot'])
        items.append(dict(name=item.product_name,unit=item.unit,quantity=str(item.quantity),price=str(amount),total=str(line)))
        total+=line
    if not items:raise ValidationError('Pedido sem itens positivos.')
    # CNPJ intentionally stays missing in homologation; never invent a tax identity.
    number=f'{order.company.code}-TESTE-{str(order.pk)[:12].upper()}'
    snapshot=dict(company_code=order.company.code,company_name=order.company.name,legal_name=order.company.legal_name,company_address=order.company.address,company_phone=order.company.phone,company_email=order.company.email,client_address=order.client.address,client_contact=order.client.phone or order.client.email,baker=order.baker,separator=order.separator,shift=order.shift,notes=order.notes,cnpj=order.company.cnpj,client_name=order.client.name,date=str(order.date),slot=order.slot,time=str(order.time)[:5],number=number,items=items,total=str(total),ibis=order.client.name.strip().upper()=='IBIS')
    try:data=pdf.receipts([snapshot])
    except ValueError as exc:raise ValidationError(str(exc)) from exc
    # # failure rolls back all state and snapshots
    document=store_document(order.company,f'order:{order.pk}:v1','NOTINHAS',data,order)
    order.issued_snapshot=snapshot;order.commercial_number=number;order.issued_at=timezone.now();order.status='EMITIDO';order.save()
    event(user,order,'EMITIR_TESTE',{'status':'CONFERIDO'},{'status':'EMITIDO','sha256':document.sha256})
    return document

@permitted('core.confirm_delivery')
@transaction.atomic
def deliver(user,order_id,evidence):
    order=Order.objects.select_for_update().get(pk=order_id)
    if not evidence.strip():raise ValidationError('Descreva a evidência da entrega de teste.')
    if order.status in ('ENTREGUE','LIBERADO_FECHAMENTO','FECHADO'):return order
    if order.status!='EMITIDO':raise ValidationError('A entrega só pode ser confirmada após emissão.')
    order.status='ENTREGUE';order.delivered_at=timezone.now();order.delivery_evidence=evidence;order.save()
    event(user,order,'CONFIRMAR_ENTREGA_TESTE',{'status':'EMITIDO'},{'status':'ENTREGUE'},evidence)
    return order

@permitted('core.close_month')
@transaction.atomic
def release(user,order_id):
    order=Order.objects.select_for_update().get(pk=order_id)
    if order.status=='LIBERADO_FECHAMENTO':return order
    if order.status!='ENTREGUE' or not order.delivered_at or not order.issued_snapshot:raise ValidationError('Entrega comprovada e preços congelados são obrigatórios.')
    order.status='LIBERADO_FECHAMENTO';order.save(update_fields=['status'])
    event(user,order,'LIBERAR_TESTE',{'status':'ENTREGUE'},{'status':'LIBERADO_FECHAMENTO'})
    return order

@permitted('core.check_production')
def cancel(user,order_id,reason):
    if not reason.strip():raise ValidationError('Motivo obrigatório.')
    order=Order.objects.get(pk=order_id)
    if order.status in ('EMITIDO','ENTREGUE','LIBERADO_FECHAMENTO','FECHADO'):authorize(user,order.company,'core.cancel_issued')
    with transaction.atomic():
        order=Order.objects.select_for_update().get(pk=order_id)
        if StatementLine.objects.filter(order=order,active=True).exists():raise ValidationError('Pedido incluído em fechamento de cliente. Revise o fechamento antes de cancelar.')
        if order.status=='FECHADO':raise ValidationError('Fechamento aprovado: correção comercial exige processo separado.')
        if order.status=='CANCELADO':return
        before=order.status;order.status='CANCELADO';order.save(update_fields=['status'])
        Document.objects.filter(order=order).update(superseded=True)
        Document.objects.filter(company=order.company,key__startswith=f'daily:{order.company_id}:{order.date}:').update(superseded=True)
        Document.objects.filter(company_scope__contains=[str(order.company_id)],key__startswith=f'finalize:{order.date}:').update(superseded=True)
        event(user,order,'CANCELAR',{'status':before},{'status':'CANCELADO'},reason)

def eligible(user,company,client,month):
    authorize(user,company,'core.close_month')
    if client.company_id!=company.pk:raise ValidationError('Cliente de outra empresa.')
    return Order.objects.filter(company=company,client=client,date__year=month.year,date__month=month.month,status='LIBERADO_FECHAMENTO',delivered_at__isnull=False,synthetic=True).exclude(issued_snapshot={}).exclude(statementline__active=True).order_by('date','time','pk')

def close(user,company,client,month):
    authorize(user,company,'core.close_month')
    if month.day!=1:raise ValidationError('Referência deve iniciar no primeiro dia do mês.')
    with transaction.atomic():
        # Serializes concurrent closure approvals, including an initially empty selection.
        Company.objects.select_for_update().get(pk=company.pk)
        if client.company_id!=company.pk:raise ValidationError('Cliente de outra empresa.')
        old=Closure.objects.filter(company=company,client=client,month=month).first()
        if old:return old
        orders=list(eligible(user,company,client,month).select_for_update())
        if not orders:raise ValidationError('Nenhum pedido entregue e liberado para este fechamento.')
        total=sum((Decimal(o.issued_snapshot['total']) for o in orders),Decimal(0)).quantize(MONEY)
        data=pdf.monthly(company,client,month,orders,total)
        doc=store_document(company,f'closure:{company.pk}:{client.pk}:{month}','FECHAMENTO_TESTE',data)
        closure=Closure.objects.create(company=company,client=client,month=month,total=total,actor=user,document=doc)
        for order in orders:
            ClosureLine.objects.create(closure=closure,order=order,amount=Decimal(order.issued_snapshot['total']))
            order.status='FECHADO';order.save(update_fields=['status'])
        event(user,closure,'APROVAR_FECHAMENTO_TESTE',after={'orders':len(orders),'total':str(total)})
        return closure

def daily_document(user,day,company):
    authorize(user,company,'core.issue_document')
    with transaction.atomic():
        Company.objects.select_for_update().get(pk=company.pk)
        orders=list(Order.objects.filter(company=company,date=day,status__in=['EMITIDO','ENTREGUE','LIBERADO_FECHAMENTO','FECHADO']).order_by('time','pk'))
        if not orders:raise ValidationError('Nenhum documento emitido para esta data/empresa.')
        digest=hashlib.sha256('|'.join(str(o.pk) for o in orders).encode()).hexdigest()
        key=f'daily:{company.pk}:{day}:{digest}'
        old=Document.objects.filter(key=key).first()
        if old:return old
        data=pdf.receipts([o.issued_snapshot for o in orders])
        doc=store_document(company,key,'DIA_TESTE',data)
        event(user,doc,'PDF_DIA_TESTE',after={'orders':len(orders),'sha256':doc.sha256})
        return doc

def reconcile(user,candidate,number,evidence,reason):
    require(user,'core.review_staging')
    if not all(x.strip() for x in (number,evidence,reason)):raise ValidationError('Número original, evidência e justificativa obrigatórios.')
    with transaction.atomic():
        candidate=Candidate.objects.select_for_update().get(pk=candidate.pk)
        if not candidate.approved or candidate.category!='NOTA_ANTIGA':raise ValidationError('Revise primeiro uma nota histórica.')
        found=Reconciliation.objects.filter(candidate=candidate).first()
        if found:
            if found.original_number!=number:raise ValidationError('Nota já conciliada com outro número.')
            return found
        if Reconciliation.objects.filter(original_number=number).exists():raise ValidationError('Número já conciliado. Não criar duplicata.')
        result=Reconciliation.objects.create(candidate=candidate,original_number=number,evidence=evidence,reason=reason,actor=user)
        event(user,result,'CONCILIAR_SEM_FATURAR',reason=reason)
        return result

@permitted('core.prepare_day')
@transaction.atomic
def update_info(user,order_id,values,reason):
    order=Order.objects.select_for_update().get(pk=order_id)
    if order.status not in ('PRE_LANCADO','CONFERIDO'):raise ValidationError('Pedido emitido: dados históricos não podem ser alterados.')
    before={field:str(getattr(order,field)) for field in values}
    for field,value in values.items():setattr(order,field,value)
    order.full_clean();order.save()
    event(user,order,'AJUSTAR_PRODUCAO',before,{k:str(v) for k,v in values.items()},reason)
