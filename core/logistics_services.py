from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from .models import (Company, ProductionRecord, DeliveryRoute, Order, DeliveryManifest, ManifestLine, CashBag)
from .services import authorize, price_for
from .workflow import event
from .management_services import receive


@transaction.atomic
def register_production(user, record):
    authorize(user,record.company,'core.add_productionrecord')
    Company.objects.select_for_update().get(pk=record.company_id)
    if record.product.company_id!=record.company_id or record.date>timezone.localdate():
        raise ValidationError('Confira a empresa do produto e a data da produção.')
    if record.losses and not record.notes.strip():
        raise ValidationError('Informe o motivo das perdas.')
    record.unit=record.product.unit
    record.cost_snapshot=record.product.production_cost
    record.actor=user
    record.full_clean();record.save()
    event(user,record,'REGISTRAR_PRODUCAO',after={'product':str(record.product_id),'quantity':str(record.quantity),'losses':str(record.losses),'cost':str(record.cost_snapshot),'date':str(record.date)})
    return record


@transaction.atomic
def build_manifest(user, route, day):
    authorize(user,route.company,'core.add_deliverymanifest')
    Company.objects.select_for_update().get(pk=route.company_id)
    route=DeliveryRoute.objects.select_for_update().select_related('driver').get(pk=route.pk)
    if not route.active or not route.driver.active or route.driver.company_id!=route.company_id:
        raise ValidationError('Confira a rota e o motorista ativo da mesma empresa.')
    old=DeliveryManifest.objects.filter(route=route,date=day).first()
    if old:return old
    stops=list(route.stops.select_related('client'))
    if not stops:raise ValidationError('Cadastre os clientes e a ordem de entrega da rota.')
    if any(s.client.company_id!=route.company_id for s in stops):raise ValidationError('A rota contém cliente de outra empresa.')
    orders=list(Order.objects.select_for_update().filter(company=route.company,date=day,client__in=[s.client for s in stops],client__active=True).exclude(status='CANCELADO').select_related('client').prefetch_related('items__product').order_by('time','id'))
    if not orders:raise ValidationError('Não há pedidos nessa rota e data. Prepare primeiro os novos pedidos do dia.')
    if any(order.status not in ('EMITIDO','ENTREGUE','LIBERADO_FECHAMENTO') for order in orders):raise ValidationError('Há pedidos sem documento emitido. Confira os pedidos e emita os documentos antes de organizar a saída da rota.')
    if ManifestLine.objects.filter(order__in=orders).exists():raise ValidationError('Um dos pedidos já pertence a outro romaneio. Confira as rotas para evitar entrega duplicada.')
    manifest=DeliveryManifest.objects.create(route=route,company=route.company,date=day,driver_name=route.driver.name,vehicle=route.driver.vehicle,notes=route.notes,actor=user)
    stops_by_client={s.client_id:s for s in stops}
    for order in orders:
        stop=stops_by_client[order.client_id]
        snapshot=[];total=Decimal(0);complete=True
        for item in order.items.all():
            if item.quantity<=0:continue
            amount=item.unit_price_snapshot
            if amount is None:
                try:amount=price_for(order.company,order.client,item.product,day)
                except ValidationError:complete=False
            if amount is not None:total+=(amount*item.quantity).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            snapshot.append({'product':item.product_name,'quantity':str(item.quantity),'unit':item.unit,'price':str(amount) if amount is not None else None})
        if not snapshot:raise ValidationError('Há um pedido sem itens positivos; revise antes de gerar o romaneio.')
        ManifestLine.objects.create(manifest=manifest,order=order,sequence=stop.sequence,client_name=order.client.name,address=order.client.address,
            instructions='\n'.join(x for x in [stop.instructions,'OC DO CLIENTE: '+order.issued_snapshot.get('purchase_order','') if order.issued_snapshot.get('purchase_order') else '',order.notes] if x),items_snapshot=snapshot,amount_due=total if complete else None)
    event(user,manifest,'GERAR_ROMANEIO',after={'date':str(day),'route':str(route.pk),'orders':len(orders),'driver':manifest.driver_name})
    return manifest


@transaction.atomic
def report_delivery(user, line, data):
    authorize(user,line.manifest.company,'core.change_manifestline')
    manifest=DeliveryManifest.objects.select_for_update().get(pk=line.manifest_id)
    if CashBag.objects.filter(manifest=manifest).exists():raise ValidationError('Malote já recebido. Os relatos da rota estão preservados; registre a correção na conferência do malote.')
    line=ManifestLine.objects.select_for_update().select_related('order').get(pk=line.pk)
    amount=data['reported_amount']
    if line.order.status=='CANCELADO' and data['delivery_status']=='ENTREGUE':raise ValidationError('Pedido cancelado não pode ser entregue.')
    if manifest.date>timezone.localdate():raise ValidationError('Registre o retorno somente no dia da entrega ou depois.')
    if not amount.is_finite() or amount<0 or (amount>0 and (line.amount_due is None or amount>line.amount_due)):
        raise ValidationError('Valor informado inválido, superior ao pedido ou preço ainda pendente.')
    if data['delivery_status']=='PENDENTE' or (data['delivery_status']!='ENTREGUE' and amount>0):
        raise ValidationError('Informe se entregou. Cobrança em dinheiro exige entrega informada.')
    if not data['evidence'].strip():raise ValidationError('Registre a observação da entrega e do pagamento, mesmo quando não houve pagamento.')
    method=data.get('payment_method','DINHEIRO' if amount>0 else 'PRAZO')
    if method!='DINHEIRO' and amount>0:raise ValidationError('Dinheiro do malote exige a forma Dinheiro. PIX e cartão não entram na soma do malote.')
    if method=='DINHEIRO' and amount<=0:raise ValidationError('Informe o valor recebido em dinheiro ou selecione Não pagou / a prazo.')
    if method in ('PIX','CARTAO') and data['delivery_status']!='ENTREGUE':raise ValidationError('Pagamento eletrônico informado exige entrega informada.')
    account=data.get('receivable')
    if account and (account.company_id!=manifest.company_id or account.client_id!=line.order.client_id or account.voided):
        raise ValidationError('A conta precisa ser do mesmo cliente e empresa.')
    if account and line.order.synthetic:raise ValidationError('Pedido de teste não pode baixar uma conta real.')
    for field in ('delivery_status','reported_amount','receivable','evidence'):setattr(line,field,data.get(field))
    line.payment_method=method
    line.payment_reported=True;line.full_clean();line.save()
    if line.delivery_status=='ENTREGUE' and line.order.synthetic and line.order.status=='EMITIDO':
        from .workflow import deliver
        deliver(user,line.order_id,line.evidence)
    event(user,line,'RELATAR_ENTREGA_MALOTE',after={'delivery_status':line.delivery_status,'reported_amount':str(amount),'account':str(account.pk) if account else ''},reason=line.evidence)
    return line


@transaction.atomic
def check_cash_bag(user, manifest, reference, counted, notes):
    authorize(user,manifest.company,'core.add_cashbag')
    Company.objects.select_for_update().get(pk=manifest.company_id)
    manifest=DeliveryManifest.objects.select_for_update().get(pk=manifest.pk)
    existing=CashBag.objects.select_for_update().filter(manifest=manifest).first()
    if existing and existing.status=='CONFERIDO':
        if existing.reference!=reference or existing.counted!=counted:raise ValidationError('Malote já conferido. Valores preservados; não é possível substituí-los.')
        return existing
    if manifest.date>timezone.localdate():raise ValidationError('Não é possível conferir malote de entrega futura.')
    lines=list(manifest.lines.select_for_update(of=('self',)).select_related('order','receivable'))
    if not lines or any(not line.payment_reported for line in lines):raise ValidationError('Registre a entrega e o pagamento ou não pagamento de todos os clientes antes de conferir o malote.')
    if any(line.order.status=='CANCELADO' and line.reported_amount>0 for line in lines):raise ValidationError('Há pagamento em pedido cancelado. Resolva a devolução antes de conferir o malote.')
    declared=sum((line.reported_amount for line in lines),Decimal(0))
    if not counted.is_finite() or counted<0:raise ValidationError('Informe o dinheiro contado no malote.')
    if counted!=declared and not notes.strip():raise ValidationError('Explique a diferença entre o valor declarado e o dinheiro contado.')
    if existing and existing.reference!=reference:raise ValidationError('Use a identificação original do malote na reconferência.')
    status='CONFERIDO' if counted==declared else 'DIVERGENTE'
    before={'counted':str(existing.counted),'status':existing.status} if existing else {}
    bag=existing or CashBag(manifest=manifest,company=manifest.company)
    bag.reference=reference;bag.declared=declared;bag.counted=counted;bag.notes=notes;bag.status=status;bag.actor=user
    if existing:bag.checked_at=timezone.now()
    bag.full_clean();bag.save()
    if status=='CONFERIDO':
        for line in sorted(lines,key=lambda l:str(l.receivable_id or l.pk)):
            if line.reported_amount>0 and line.receivable:
                if line.order.synthetic:raise ValidationError('Pedido de teste não pode registrar recebimento financeiro real.')
                receive(user,line.receivable,line.reported_amount,timezone.localdate(),f'malote:{bag.pk}:{line.pk}')
    event(user,bag,'CONFERIR_MALOTE',before=before,after={'declared':str(declared),'counted':str(counted),'status':status},reason=notes)
    return bag
