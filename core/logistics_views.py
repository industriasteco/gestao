import uuid
from decimal import Decimal
from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum,Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from .models import *
from .forms import (ProductionRecordForm, DriverForm, DeliveryRouteForm, RouteStopForm,
                    ManifestForm, ManifestLineForm, CashBagForm)
from .services import companies, production
from .operations import production_orders
from .management_views import admin_only
from .workflow import event
from .logistics_services import register_production, build_manifest, report_delivery, check_cash_bag


@login_required
def production_actual(request):
    try:day=date.fromisoformat(request.GET.get('date',str(timezone.localdate())))
    except ValueError:
        messages.error(request,'Selecione uma data válida.');return redirect('production_actual')
    form=ProductionRecordForm(request.POST or None,user=request.user,initial={'date':timezone.localdate(),'planned_for':day,'batch':str(uuid.uuid4())[:8],'losses':0})
    if request.method=='POST':
        if not request.user.has_perm('core.add_productionrecord'):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        if form.is_valid():
            try:
                record=register_production(request.user,form.save(commit=False))
                messages.success(request,'Produção realizada registrada. Quantidade útil e perdas atualizadas; nenhum pedido criado.')
                return redirect(f'/producao/realizada/?date={record.planned_for}')
            except ValidationError as exc:form.add_error(None,exc)
    rows=ProductionRecord.objects.filter(company__in=companies(request.user)).filter(Q(planned_for=day)|Q(planned_for__isnull=True,date=day)).select_related('company','product','actor').order_by('shift','product__name','created_at')
    totals={}
    for record in rows:
        record.good=record.quantity-record.losses
        group=totals.setdefault(record.unit,{'quantity':Decimal(0),'losses':Decimal(0),'good':Decimal(0)})
        group['quantity']+=record.quantity;group['losses']+=record.losses;group['good']+=record.good
        record.total_cost=record.quantity*record.cost_snapshot if record.cost_snapshot is not None else None
    day_orders=production_orders(request.user).filter(date=day)
    planned=production(day_orders)
    comparison={}
    for item in OrderItem.objects.filter(order__in=day_orders).exclude(order__status='CANCELADO').select_related('order__company','product'):
        key=(item.order.company_id,item.product_id,item.unit)
        group=comparison.setdefault(key,dict(company=item.order.company.code,product=item.product_name,unit=item.unit,planned=Decimal(0),produced=Decimal(0),losses=Decimal(0)))
        group['planned']+=item.quantity
    for record in rows:
        key=(record.company_id,record.product_id,record.unit)
        group=comparison.setdefault(key,dict(company=record.company.code,product=record.product.name,unit=record.unit,planned=Decimal(0),produced=Decimal(0),losses=Decimal(0)))
        group['produced']+=record.quantity;group['losses']+=record.losses
    for group in comparison.values():
        group['good']=group['produced']-group['losses'];group['gap']=group['good']-group['planned'];group['shortage']=-group['gap']
    return render(request,'core/production_actual.html',dict(form=form,rows=rows,totals=totals.items(),day=day,planned=planned,comparison=comparison.values()))


@login_required
def routes(request):
    driver_form=DriverForm(user=request.user)
    route_form=DeliveryRouteForm(user=request.user)
    if request.method=='POST':
        admin_only(request.user)
        form=driver_form=DriverForm(request.POST,user=request.user) if request.POST.get('action')=='driver' else driver_form
        if request.POST.get('action')!='driver':form=route_form=DeliveryRouteForm(request.POST,user=request.user)
        if form.is_valid():
            with transaction.atomic():
                obj=form.save();event(request.user,obj,'CADASTRAR_LOGISTICA',after={k:str(v) for k,v in form.cleaned_data.items()})
            messages.success(request,'Cadastro salvo.');return redirect('routes')
    return render(request,'core/routes.html',dict(driver_form=driver_form,route_form=route_form,
        routes=DeliveryRoute.objects.filter(company__in=companies(request.user)).select_related('company','driver').prefetch_related('stops'),
        drivers=Driver.objects.filter(company__in=companies(request.user)).select_related('company')))


@login_required
def route_detail(request,pk):
    route=get_object_or_404(DeliveryRoute,pk=pk,company__in=companies(request.user))
    route_form=DeliveryRouteForm(instance=route,user=request.user)
    route_form.fields['company'].disabled=True
    stop_form=RouteStopForm(route=route)
    if request.method=='POST':
        admin_only(request.user)
        if request.POST.get('action')=='route':
            route_form=DeliveryRouteForm(request.POST,instance=route,user=request.user);route_form.fields['company'].disabled=True
            if route_form.is_valid():
                obj=route_form.save();event(request.user,obj,'EDITAR_ROTA');return redirect('route_detail',pk=pk)
        elif request.POST.get('action')=='remove':
            stop=get_object_or_404(RouteStop,pk=request.POST.get('stop'),route=route)
            with transaction.atomic():
                event(request.user,stop,'REMOVER_PARADA',before={'route':str(route.pk),'client':str(stop.client_id),'sequence':stop.sequence})
                stop.delete()
            messages.success(request,'Parada removida da rota. Romaneios anteriores foram preservados.');return redirect('route_detail',pk=pk)
        else:
            instance=RouteStop.objects.filter(pk=request.POST.get('stop'),route=route).first() if request.POST.get('stop') else None
            stop_form=RouteStopForm(request.POST,route=route,instance=instance)
            if stop_form.is_valid():
                with transaction.atomic():
                    obj=stop_form.save();event(request.user,obj,'SALVAR_PARADA',after={'client':str(obj.client_id),'sequence':obj.sequence})
                return redirect('route_detail',pk=pk)
    return render(request,'core/route_detail.html',dict(route=route,route_form=route_form,stop_form=stop_form,stops=route.stops.select_related('client')))


@login_required
def driver_detail(request,pk):
    driver=get_object_or_404(Driver,pk=pk,company__in=companies(request.user))
    form=DriverForm(request.POST or None,instance=driver,user=request.user);form.fields['company'].disabled=True
    if request.method=='POST':
        admin_only(request.user)
        if form.is_valid():
            obj=form.save();event(request.user,obj,'EDITAR_MOTORISTA');return redirect('routes')
    return render(request,'core/driver_detail.html',{'driver':driver,'form':form})


@login_required
def manifests(request):
    form=ManifestForm(request.POST or None,user=request.user,initial={'date':timezone.localdate()})
    if request.method=='POST':
        if not request.user.has_perm('core.add_deliverymanifest'):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        if form.is_valid():
            try:
                row=build_manifest(request.user,form.cleaned_data['route'],form.cleaned_data['date'])
                return redirect('manifest_detail',pk=row.pk)
            except ValidationError as exc:form.add_error(None,exc)
    rows=DeliveryManifest.objects.filter(company__in=companies(request.user)).select_related('route','company').order_by('-date','-created_at')[:100]
    return render(request,'core/manifests.html',{'form':form,'rows':rows})


def line_status(line,bag):
    if not line.payment_reported:return 'A informar'
    if line.payment_method in ('PIX','CARTAO'):return line.get_payment_method_display()+' · conferir comprovante'
    if line.reported_amount<=0:return 'Não pagou / a prazo'
    partial=line.amount_due is not None and line.reported_amount<line.amount_due
    if bag and bag.status=='CONFERIDO':return 'Parcial · malote conferido' if partial else 'Pago · malote conferido'
    return 'Parcial informado · conferir malote' if partial else 'Pago informado · conferir malote'


@login_required
def manifest_detail(request,pk):
    manifest=get_object_or_404(DeliveryManifest,pk=pk,company__in=companies(request.user))
    bag=CashBag.objects.filter(manifest=manifest).first()
    form=CashBagForm(initial={'counted':bag.counted if bag else None,'reference':bag.reference if bag else ''})
    if request.method=='POST':
        if not request.user.has_perm('core.add_cashbag'):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        form=CashBagForm(request.POST)
        if form.is_valid():
            try:
                bag=check_cash_bag(request.user,manifest,form.cleaned_data['reference'],form.cleaned_data['counted'],form.cleaned_data['notes'])
                messages.success(request,'Malote conferido. Contas vinculadas de pedidos reais foram atualizadas.' if bag.status=='CONFERIDO' else 'Diferença registrada. Nenhuma conta foi baixada; reconfira o malote.')
                return redirect('manifest_detail',pk=pk)
            except ValidationError as exc:form.add_error(None,exc)
    lines=list(manifest.lines.select_related('order','receivable'))
    for line in lines:line.payment_status=line_status(line,bag)
    declared=sum((line.reported_amount for line in lines),Decimal(0))
    total=sum((line.amount_due for line in lines if line.amount_due is not None),Decimal(0))
    return render(request,'core/manifest_detail.html',dict(manifest=manifest,lines=lines,bag=bag,form=form,declared=declared,total=total,
        unknown=sum(line.amount_due is None for line in lines),difference=bag.counted-bag.declared if bag else None,
        synthetic=any(line.order.synthetic for line in lines)))


@login_required
def manifest_line(request,pk):
    line=get_object_or_404(ManifestLine.objects.select_related('manifest','order'),pk=pk,manifest__company__in=companies(request.user))
    form=ManifestLineForm(request.POST or None,instance=line)
    if request.method=='POST':
        if not request.user.has_perm('core.change_manifestline'):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied
        if form.is_valid():
            try:
                report_delivery(request.user,line,form.cleaned_data)
                messages.success(request,'Retorno informado. O pagamento depende da conferência do malote.');return redirect('manifest_detail',pk=line.manifest_id)
            except ValidationError as exc:form.add_error(None,exc)
    return render(request,'core/manifest_line.html',{'line':line,'form':form})


@login_required
def manifest_pdf(request,pk):
    manifest=get_object_or_404(DeliveryManifest.objects.select_related('route','company'),pk=pk,company__in=companies(request.user))
    from .logistics_pdf import render_manifest
    bag=CashBag.objects.filter(manifest=manifest).first()
    lines=list(manifest.lines.select_related('order','receivable'))
    for line in lines:line.payment_status=line_status(line,bag)
    response=HttpResponse(render_manifest(manifest,lines,bag),content_type='application/pdf')
    response['Content-Disposition']=f'inline; filename="romaneio-{str(manifest.pk)[:8]}.pdf"'
    response['Cache-Control']='private, no-store'
    return response

@login_required
def team(request):
    admin_only(request.user)
    from django.contrib.auth.models import User
    from .team import TeamForm,create_member
    form=TeamForm(request.POST or None,user=request.user)
    if request.method=='POST':
        if request.POST.get('action')=='deactivate':
            user=get_object_or_404(User,pk=request.POST.get('member'),is_superuser=False)
            user.is_active=False;user.save(update_fields=['is_active'])
            event(request.user,user,'DESATIVAR_COLABORADOR')
            messages.success(request,'Acesso desativado. Os registros do colaborador foram preservados.');return redirect('team')
        if form.is_valid():
            create_member(form,request.user)
            messages.success(request,'Colaborador cadastrado. Oriente-o a entrar com sua conta individual.');return redirect('team')
    members=Membership.objects.select_related('user','company').prefetch_related('user__groups').order_by('user__first_name','user__username')
    return render(request,'core/team.html',{'form':form,'members':members})
