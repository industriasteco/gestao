import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .models import *
from .forms import (ClientForm, ProductForm, InlinePriceForm, ReceivableForm, PaymentForm,
                    StockItemForm, StockMovementForm, WorkbookForm, RecurrenceForm)
from .services import companies, authorize
from .management_services import balances, receive, move_stock, set_price
from .workflow import event


def admin_only(user):
    if not user.is_superuser:
        raise PermissionDenied


def range_dates(request):
    today=timezone.localdate()
    try:
        start=date.fromisoformat(request.GET.get('start',today.replace(day=1).isoformat()))
        end=date.fromisoformat(request.GET.get('end',today.isoformat()))
        if start>end:raise ValueError
    except ValueError:
        raise ValidationError('Confira o período: a data inicial deve ser anterior à final.')
    return start,end


@login_required
def dashboard(request):
    if not request.user.has_perm('core.view_receivable'):raise PermissionDenied
    scope=companies(request.user)
    try:start,end=range_dates(request)
    except ValidationError as exc:
        messages.error(request,'; '.join(exc.messages));return redirect('dashboard')
    if request.GET.get('company'):
        scope=scope.filter(pk=request.GET['company'])
    orders=Order.objects.filter(company__in=scope,date__range=(start,end)).exclude(status='CANCELADO')
    # O fluxo atual só emite documentos de homologação. Indicadores de venda não
    # incluem esses testes nem pedidos ainda não emitidos.
    sold=orders.filter(synthetic=False,status__in=['EMITIDO','ENTREGUE','LIBERADO_FECHAMENTO','FECHADO'])
    items=OrderItem.objects.filter(order__in=sold)
    revenue=Decimal(0); by_company=defaultdict(Decimal); by_client=defaultdict(Decimal)
    unpriced=items.filter(unit_price_snapshot__isnull=True).count()
    for item in items.select_related('order__company','order__client'):
        if item.unit_price_snapshot is None:continue
        value=(item.quantity*item.unit_price_snapshot).quantize(Decimal('.01'))
        revenue+=value;by_company[item.order.company.name]+=value;by_client[(item.order.client_id,item.order.client.name)]+=value
    top_products=list(items.values('product__name','unit').annotate(quantity=Sum('quantity')).order_by('-quantity')[:8])
    for row in top_products:
        maximum=max((x['quantity'] for x in top_products if x['unit']==row['unit']),default=1)
        row['percent']=round(row['quantity']/maximum*100)
    scope_ids=set(scope.values_list('pk',flat=True))
    accounts=[r for r in balances(request.user) if r.company_id in scope_ids]
    overdue=sorted([r for r in accounts if r.balance>0 and r.days_late], key=lambda r:(-r.days_late,-r.balance))
    debtors={r.client_id for r in overdue}
    stock=StockItem.objects.filter(company__in=scope).annotate(balance=Sum('movements__quantity'))
    low_stock=[r for r in stock if (r.balance or Decimal(0))<=r.minimum]
    obligations=[]
    if request.user.has_perm('core.view_payable'):
        from .payables_services import payable_balances
        obligations=[row for row in payable_balances(request.user) if row.company_id in scope_ids and not row.synthetic and row.balance>0]
    obligations.sort(key=lambda row:(-row.days_late,row.due_on))
    payable_total=sum((row.balance for row in obligations),Decimal(0))
    payable_late=sum((row.balance for row in obligations if row.days_late),Decimal(0))
    context=dict(start=start,end=end,all_companies=companies(request.user),selected_company=request.GET.get('company',''),
        payable_total=payable_total,payable_late=payable_late,obligations=obligations[:8],
        revenue=revenue,by_company=sorted(by_company.items()),top_clients=sorted(by_client.items(),key=lambda x:-x[1])[:8],
        top_products=top_products,overdue=overdue[:10],overdue_total=sum((r.balance for r in overdue),Decimal(0)),
        overdue_clients=len(debtors),open_total=sum((r.balance for r in accounts if r.balance>0),Decimal(0)),
        low_stock=low_stock,order_count=orders.count(),sold_count=sold.count(),unpriced=unpriced,
        clients=Client.objects.filter(company__in=scope,active=True).count(),
        rules=Recurrence.objects.filter(company__in=scope,active=True).count(),
        units=list(items.values('unit').annotate(quantity=Sum('quantity'))),
        test_orders=orders.filter(synthetic=True).count(),
        missing_costs=Product.objects.filter(company__in=scope,active=True,production_cost__isnull=True).count(),
        costed_loss=sum((r.losses*r.cost_snapshot for r in ProductionRecord.objects.filter(company__in=scope,date__range=(start,end),cost_snapshot__isnull=False)),Decimal(0)),
        uncosted_production=ProductionRecord.objects.filter(company__in=scope,date__range=(start,end),cost_snapshot__isnull=True).count(),
        produced=ProductionRecord.objects.filter(company__in=scope,date__range=(start,end)).values('unit').annotate(quantity=Sum('quantity'),losses=Sum('losses')),
        pending_bags=DeliveryManifest.objects.filter(company__in=scope).filter(Q(cash_bag__isnull=True)|Q(cash_bag__status='DIVERGENTE')).count())
    return render(request,'core/dashboard.html',context)


@login_required
def client_detail(request,pk):
    client=get_object_or_404(Client,pk=pk,company__in=companies(request.user))
    edit=ClientForm(instance=client,user=request.user)
    price=InlinePriceForm(company=client.company,initial={'valid_from':timezone.localdate()})
    if request.method=='POST':
        admin_only(request.user)
        if request.POST.get('action')=='edit':
            edit=ClientForm(request.POST,instance=client,user=request.user)
            edit.fields['company'].disabled=True
            if edit.is_valid():
                obj=edit.save();event(request.user,obj,'EDITAR_CLIENTE');messages.success(request,'Dados do cliente atualizados.');return redirect('client_detail',pk=pk)
        else:
            price=InlinePriceForm(request.POST,company=client.company)
            if price.is_valid():
                try:
                    set_price(request.user,client.company,price.cleaned_data['product'],price.cleaned_data['amount'],price.cleaned_data['valid_from'],client)
                    messages.success(request,'Preço negociado salvo com histórico.');return redirect('client_detail',pk=pk)
                except ValidationError as exc:price.add_error(None,exc)
    accounts=[r for r in balances(request.user) if r.client_id==client.pk] if request.user.has_perm('core.view_receivable') else []
    overdue=[r for r in accounts if r.days_late]
    status='Inadimplente' if overdue else ('Adimplente' if accounts else 'Sem histórico financeiro')
    return render(request,'core/client_detail.html',dict(client=client,edit=edit,price_form=price,
        status=status,accounts=accounts,pending=Candidate.objects.filter(category='ROTINA_A_CONFERIR',raw__client=' '.join(client.name.upper().split())) if request.user.is_superuser else Candidate.objects.none(),prices=Price.objects.filter(client=client).select_related('product').order_by('-valid_from'),
        rules=Recurrence.objects.filter(client=client).select_related('product').order_by('product__name','time'),
        orders=Order.objects.filter(client=client).order_by('-date')[:20],
        events=Audit.objects.filter(Q(entity=str(client.pk))|Q(entity__in=[str(pk) for pk in Price.objects.filter(client=client).values_list('id',flat=True)])).order_by('-at')[:30]))


@login_required
def product_detail(request,pk):
    product=get_object_or_404(Product,pk=pk,company__in=companies(request.user))
    form=ProductForm(request.POST or None,instance=product,user=request.user)
    form.fields['company'].disabled=True
    if request.method=='POST':
        admin_only(request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    product=form.save()
                    if form.cleaned_data.get('amount') is not None:
                        set_price(request.user,product.company,product,form.cleaned_data['amount'],form.cleaned_data['valid_from'])
                    event(request.user,product,'EDITAR_PRODUTO')
                messages.success(request,'Produto e preço salvos.');return redirect('product_detail',pk=pk)
            except ValidationError as exc:form.add_error(None,exc)
    from .services import price_for
    today=timezone.localdate()
    current=Price.objects.filter(product=product,client__isnull=True,valid_from__lte=today).filter(Q(valid_until__isnull=True)|Q(valid_until__gte=today))
    sale=current.first().amount if current.count()==1 else None
    profit=sale-product.production_cost if sale is not None and product.production_cost is not None else None
    margin=(profit/sale*100) if profit is not None and sale else None
    return render(request,'core/product_detail.html',dict(product=product,form=form,sale=sale,profit=profit,margin=margin,
        prices=Price.objects.filter(product=product).select_related('client').order_by('-valid_from')))


@login_required
def finance(request):
    if not request.user.has_perm('core.view_receivable'):raise PermissionDenied
    form=ReceivableForm(request.POST or None,user=request.user,initial={'issued_on':timezone.localdate()})
    if request.method=='POST':
        if not request.user.has_perm('core.add_receivable'):raise PermissionDenied
        if form.is_valid():
            with transaction.atomic():
                obj=form.save();event(request.user,obj,'CADASTRAR_RECEBIVEL',after={'amount':str(obj.amount),'due_on':str(obj.due_on)})
            messages.success(request,'Conta registrada. Nenhuma mensagem de cobrança enviada.');return redirect('finance')
    rows=sorted(balances(request.user),key=lambda r:(-r.days_late,r.due_on))
    return render(request,'core/finance.html',dict(form=form,rows=rows))


@login_required
def payment(request,pk):
    if not request.user.has_perm('core.view_receivable'):raise PermissionDenied
    row=get_object_or_404(Receivable,pk=pk,company__in=companies(request.user))
    form=PaymentForm(request.POST or None,initial={'date':timezone.localdate(),'reference':uuid.uuid4()})
    if request.method=='POST':
        if not request.user.has_perm('core.change_receivable'):raise PermissionDenied
        if form.is_valid():
            try:
                receive(request.user,row,form.cleaned_data['amount'],form.cleaned_data['date'],str(form.cleaned_data['reference']))
                messages.success(request,'Recebimento registrado. Saldo e situação do cliente atualizados.');return redirect('finance')
            except ValidationError as exc:form.add_error(None,exc)
    row.balance=row.amount-(row.payments.aggregate(total=Sum('amount'))['total'] or Decimal(0))
    return render(request,'core/payment.html',dict(row=row,form=form,payments=row.payments.order_by('-date')))


@login_required
def stock(request):
    item_form=StockItemForm(user=request.user)
    move_form=StockMovementForm(user=request.user,initial={'date':timezone.localdate(),'key':uuid.uuid4()})
    if request.method=='POST':
        admin_only(request.user)
        if request.POST.get('action')=='item':
            item_form=StockItemForm(request.POST,user=request.user)
            if item_form.is_valid():
                obj=item_form.save();event(request.user,obj,'CADASTRAR_ESTOQUE');return redirect('stock')
        else:
            move_form=StockMovementForm(request.POST,user=request.user)
            if move_form.is_valid():
                try:
                    data=move_form.cleaned_data;move_stock(request.user,data['item'],data['quantity'],data['date'],data['reason'],data['key'])
                    messages.success(request,'Movimento registrado.');return redirect('stock')
                except ValidationError as exc:move_form.add_error(None,exc)
    rows=list(StockItem.objects.filter(company__in=companies(request.user)).select_related('company').annotate(balance=Sum('movements__quantity')))
    for row in rows:row.balance=row.balance or Decimal(0);row.low=row.balance<=row.minimum
    return render(request,'core/stock.html',dict(rows=rows,item_form=item_form,move_form=move_form,
        movements=StockMovement.objects.filter(item__company__in=companies(request.user)).select_related('item','actor').order_by('-date','-id')[:50]))


@login_required
def routines_import(request):
    admin_only(request.user)
    form=WorkbookForm(request.POST or None,request.FILES or None,user=request.user,initial={'start':timezone.localdate()})
    if request.method=='POST' and form.is_valid():
        from .excel_import import import_workbook
        try:
            values=form.cleaned_data
            batch,created,analysis=import_workbook(request.user,values['company'],values['file'].read(),values['file'].name,values['start'])
            messages.success(request,'Cadastros e rotinas preparados. Nenhum pedido antigo importado.' if created else 'Planilha já processada. Nenhum cadastro duplicado.')
            return redirect('routines')
        except ValidationError as exc:form.add_error(None,exc)
    return render(request,'core/routines_import.html',{'form':form})


@login_required
def routines(request):
    rows=Recurrence.objects.filter(company__in=companies(request.user)).select_related('client','product','company').order_by('client__name','product__name')
    query=request.GET.get('q','').strip()
    if query:rows=rows.filter(Q(client__name__icontains=query)|Q(product__name__icontains=query))
    pending=Candidate.objects.filter(category__in=['ROTINA_A_CONFERIR','ITEM_A_CONFERIR']) if request.user.is_superuser else Candidate.objects.none()
    return render(request,'core/routines.html',{'rows':rows,'pending':pending,'q':query})


@login_required
def routine_detail(request,pk):
    row=get_object_or_404(Recurrence,pk=pk,company__in=companies(request.user))
    form=RecurrenceForm(request.POST or None,instance=row,user=request.user)
    for name in ('company','client','product'):form.fields[name].disabled=True
    if request.method=='POST':
        admin_only(request.user)
        if request.POST.get('action')=='toggle':
            with transaction.atomic():
                row=Recurrence.objects.select_for_update().get(pk=pk)
                row.active=not row.active;row.save(update_fields=['active']);event(request.user,row,'ALTERAR_ROTINA',after={'active':row.active})
            return redirect('routines')
        if form.is_valid():
            with transaction.atomic():
                Company.objects.select_for_update().get(pk=row.company_id)
                obj=form.save(commit=False)
                # Mudanças valem para novas datas: pedidos já preparados são preservados.
                obj.save();event(request.user,obj,'EDITAR_ROTINA',after={k:str(v) for k,v in form.cleaned_data.items()})
            messages.success(request,'Rotina atualizada para os próximos preparos. Pedidos existentes foram preservados.');return redirect('routines')
    return render(request,'core/routine_detail.html',{'form':form,'row':row})


@login_required
def home(request):
    if 'date' in request.GET:
        from .views import daily
        return daily(request)
    if not request.user.has_perm('core.view_receivable'):
        from .logistics_views import manifests,production_actual
        if request.user.has_perm('core.add_productionrecord'):return production_actual(request)
        if request.user.has_perm('core.view_deliverymanifest'):return manifests(request)
        from .views import daily
        return daily(request)
    return dashboard(request)

@login_required
def company_detail(request,pk):
    company=get_object_or_404(Company,pk=pk,pk__in=companies(request.user).values('pk'))
    from .forms import CompanyForm
    form=CompanyForm(request.POST or None,instance=company,user=request.user)
    form.fields['code'].disabled=True
    if request.method=='POST':
        admin_only(request.user)
        if form.is_valid():
            with transaction.atomic():
                obj=form.save();event(request.user,obj,'EDITAR_EMPRESA',after={name:str(value) for name,value in form.cleaned_data.items() if name in form.changed_data})
            messages.success(request,'Dados da empresa atualizados. Documentos já emitidos foram preservados.');return redirect('company_detail',pk=pk)
    return render(request,'core/company_detail.html',{'company':company,'form':form})
