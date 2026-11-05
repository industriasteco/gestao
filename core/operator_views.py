import hashlib
from datetime import date
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.http import HttpResponse,FileResponse,JsonResponse
from django.views.decorators.http import require_POST
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.urls import reverse
from io import BytesIO
from .models import *
from .services import companies,authorize,require,activate,prices_on
from django.utils import timezone
from .management_services import set_current_price
from .forms import *
from . import workflow
from .client_setup import client_prices_data,save_client_prices,save_recurring_items

@login_required
def guide(request):return render(request,'core/guide.html')

@login_required
def records(request,kind):
    options={'empresas':(Company,CompanyForm),'clientes':(Client,ClientForm),'produtos':(Product,ProductForm),'precos':(Price,PriceForm),'recorrencias':(Recurrence,RecurrenceForm)}
    if kind not in options:return redirect('records',kind='clientes')
    model,form_type=options[kind]
    client_prices=client_price_forms(request.user,request.POST if request.method=='POST' else None) if kind=='clientes' else None
    if request.method=='POST':
        if not request.user.is_superuser:raise PermissionDenied
        if request.POST.get('action')=='activate' and kind=='recorrencias':
            rule=get_object_or_404(Recurrence,pk=request.POST.get('rule'),company__in=companies(request.user))
            try:activate(request.user,rule,request.POST.get('reason',''))
            except ValidationError as e:messages.error(request,'; '.join(e.messages))
            return redirect('records',kind=kind)
        form=form_type(request.POST,user=request.user)
        valid=form.is_valid()
        if client_prices is not None:valid=client_prices.is_valid() and valid
        if valid:
            try:
                price_rows=client_prices_data(client_prices,form.cleaned_data['company']) if client_prices is not None else []
                with transaction.atomic():
                    if kind=='precos':
                        data=form.cleaned_data
                        obj=set_current_price(request.user,data['company'],data['product'],data['amount'],data.get('client'))
                    else:
                        obj=form.save()
                        if kind=='clientes':save_client_prices(request.user,obj,price_rows)
                        if kind=='produtos' and form.cleaned_data.get('amount') is not None:
                            set_current_price(request.user,obj.company,obj,form.cleaned_data['amount'])
                    workflow.event(request.user,obj,'CADASTRAR',after={k:str(v) for k,v in form.cleaned_data.items()})
                messages.success(request,'Preço atual salvo.' if kind=='precos' else 'Cadastro salvo. Nenhum documento ou cobrança criado.')
                return redirect('records',kind=kind)
            except ValidationError as exc:form.add_error(None,exc)
    else:form=form_type(user=request.user)
    rows=companies(request.user) if model is Company else model.objects.filter(company__in=companies(request.user))
    if kind=='recorrencias':rows=rows.filter(archived=False)
    today=timezone.localdate()
    price_history=None
    if kind=='precos':
        price_history=rows.select_related('product','client','company').order_by('-valid_from','product__name')
        rows=prices_on(today).filter(company__in=companies(request.user)).select_related('product','client','company').order_by('company__name','product__name','client__name')
    if kind=='produtos':
        for row in rows:
            current=prices_on(today).filter(product=row,client__isnull=True)
            row.current_price=current.first().amount if current.count()==1 else None
            row.gross_profit=row.current_price-row.production_cost if row.current_price is not None and row.production_cost is not None else None
    if kind=='clientes':
        from .management_services import balances
        overdue={r.client_id for r in balances(request.user) if r.days_late}
        known={r.client_id for r in balances(request.user)}
        for row in rows:row.financial_status='Inadimplente' if row.pk in overdue else ('Adimplente' if row.pk in known else 'Sem histórico financeiro')
    return render(request,'core/records.html',dict(kind=kind,rows=rows,form=form,options=options,price_history=price_history,today=today,client_prices=client_prices))

@login_required
def order_detail(request,pk):
    order=get_object_or_404(Order,pk=pk,company__in=companies(request.user))
    form=ProductionInfoForm(instance=order)
    if request.method=='POST':
        action=request.POST.get('action')
        try:
            if action=='info':
                form=ProductionInfoForm(request.POST,instance=order)
                if form.is_valid():
                    workflow.update_info(request.user,order.pk,{key:form.cleaned_data[key] for key in ['purchase_order','shift','baker','separator','driver','notes']},form.cleaned_data['reason'])
                else:return render(request,'core/order.html',dict(order=order,form=form,documents=Document.objects.filter(order=order)))
            elif action=='issue':
                if request.POST.get('confirm')!='yes':raise ValidationError('Marque a confirmação da prévia antes de emitir.')
                doc=workflow.issue(request.user,order.pk)
                return redirect('document',pk=doc.pk)
            elif action=='deliver':workflow.deliver(request.user,order.pk,request.POST.get('evidence',''))
            elif action=='release':workflow.release(request.user,order.pk)
            elif action=='cancel':workflow.cancel(request.user,order.pk,request.POST.get('reason',''))
            messages.success(request,'Operação registrada com auditoria.')
        except ValidationError as e:messages.error(request,'; '.join(e.messages))
        return redirect('order',pk=pk)
    price_preview=[]
    for item in order.items.select_related('product').all():
        try:price=workflow.price_for(order.company,order.client,item.product,order.date)
        except ValidationError:price='PENDENTE DE CONFERÊNCIA'
        price_preview.append((item,price))
    return render(request,'core/order.html',dict(order=order,form=form,documents=Document.objects.filter(order=order),price_preview=price_preview,can_confirm_delivery=order.synthetic or order.date<=timezone.localdate()))

@login_required
def document(request,pk):
    doc=get_object_or_404(Document,pk=pk,company__in=companies(request.user))
    allowed={str(pk) for pk in companies(request.user).values_list('pk',flat=True)}
    if doc.company_scope and not set(doc.company_scope).issubset(allowed):raise PermissionDenied
    if not (request.user.has_perm('core.issue_document') or request.user.has_perm('core.close_month')):raise PermissionDenied
    if doc.superseded:return render(request,'core/doc_cancelled.html',{'doc':doc},status=409)
    if hashlib.sha256(bytes(doc.data)).hexdigest()!=doc.sha256:return HttpResponse('Integridade do documento divergente. Contate o responsável.',status=409)
    response=FileResponse(BytesIO(bytes(doc.data)),content_type='application/pdf',filename=f'documento-{doc.kind.lower()}-{str(doc.pk)[:8]}.pdf')
    response['Cache-Control']='private, no-store';return response

@login_required
def monthly(request):
    form=MonthForm(request.POST or request.GET or None,user=request.user)
    orders=[];closures=Closure.objects.filter(company__in=companies(request.user)).select_related('company','client','document')
    if form.is_valid():
        values=form.cleaned_data
        try:
            if request.method=='POST' and request.POST.get('approve')=='yes':
                closure=workflow.close(request.user,values['company'],values['client'],values['month'])
                messages.success(request,f'Fechamento de teste salvo: {closure.lines.count()} pedidos. Nenhuma cobrança enviada.')
                return redirect('document',pk=closure.document_id)
            orders=workflow.eligible(request.user,values['company'],values['client'],values['month'])
        except ValidationError as e:messages.error(request,'; '.join(e.messages))
    return render(request,'core/monthly.html',dict(form=form,orders=orders,closures=closures))

@login_required
def audit(request):
    if not request.user.is_superuser:raise PermissionDenied
    return render(request,'core/audit.html',{'events':Audit.objects.select_related('actor').order_by('-at')[:200]})

@login_required
def daily_pdf(request):
    if request.method!='POST':return HttpResponse(status=405)
    try:
        company=get_object_or_404(Company,pk=request.POST.get('company'),pk__in=companies(request.user).values('pk'))
        doc=workflow.daily_document(request.user,date.fromisoformat(request.POST['date']),company)
        return redirect('document',pk=doc.pk)
    except (ValidationError,ValueError,KeyError) as e:
        messages.error(request,str(e));return redirect('daily')

@login_required
def new_order(request):
    import uuid
    from django.forms import formset_factory
    from django.utils import timezone
    try:initial_day=date.fromisoformat(request.GET.get('date',str(timezone.localdate())))
    except ValueError:initial_day=timezone.localdate()
    form=ManualOrderForm(request.POST or None,user=request.user,initial={'date':initial_day,'key':uuid.uuid4(),'slot':'1ª entrega'})
    ItemSet=formset_factory(ManualItemForm,extra=4,max_num=100,validate_max=True)
    items=ItemSet(request.POST or None,form_kwargs={'user':request.user})
    if request.method=='POST' and form.is_valid() and items.is_valid():
        try:
            company=form.cleaned_data['company'];authorize(request.user,company,'core.prepare_day')
            lines=[item.cleaned_data for item in items if item.cleaned_data]
            if not lines or not any(line['quantity']>0 for line in lines):raise ValidationError('Inclua ao menos um item com quantidade positiva.')
            if any(line['product'].company_id!=company.pk for line in lines):raise ValidationError('Todos os produtos devem pertencer à empresa do pedido.')
            prices={}
            for line in lines:
                amount=line.get('client_price')
                if amount is not None:
                    previous=prices.setdefault(line['product'].pk,amount)
                    if previous!=amount:raise ValidationError('Informe o mesmo preço nas linhas repetidas de um produto.')
            with transaction.atomic():
                Company.objects.select_for_update().get(pk=company.pk)
                key='manual:'+str(form.cleaned_data['key'])
                order=Order.objects.filter(idempotency_key=key).first()
                if order is None:
                    order=form.save(commit=False);order.idempotency_key=key;order.synthetic=not company.operational_enabled;order.save()
                    for line in lines:
                        p=line['product'];OrderItem.objects.create(order=order,product=p,product_name=p.name,unit=p.unit,quantity=line['quantity'])
                        if p.pk in prices:set_current_price(request.user,company,p,prices.pop(p.pk),order.client)
                    if form.cleaned_data.get('repeat_weekly'):
                        save_recurring_items(request.user,order.client,[line for line in lines if line['quantity']>0],order.slot,order.time,order.shift,order.notes,origin=order,replace=True)
                    workflow.event(request.user,order,'PEDIDO_MANUAL_TESTE' if order.synthetic else 'PEDIDO_MANUAL',after={'items':len(lines)})
                elif order.company_id!=company.pk:raise ValidationError('Chave já usada para outra empresa.')
            return redirect('order',pk=order.pk)
        except ValidationError as e:form.add_error(None,e)
    configured=set(Recurrence.objects.filter(company__in=companies(request.user),auto_prepare=True,archived=False).values_list('client_id',flat=True))
    schedules={str(client.pk):{'weekdays':client.recurring_weekdays,'configured':client.pk in configured} for client in Client.objects.filter(company__in=companies(request.user))}
    return render(request,'core/new_order.html',{'form':form,'items':items,'client_schedules':schedules,
        'quick_client_prices':client_price_forms(request.user,prefix='quick_client_prices'),
        'quick_client':ClientForm(user=request.user,prefix='quick_client'),
        'quick_product':ProductForm(user=request.user,prefix='quick_product')})


@login_required
@require_POST
def quick_record(request,kind):
    """Cadastros persistentes feitos sem sair do rascunho de pedido."""
    import uuid
    if not request.user.is_superuser:raise PermissionDenied
    options={'clientes':(Client,ClientForm,'quick_client'),'produtos':(Product,ProductForm,'quick_product')}
    if kind not in options:return JsonResponse({'message':'Cadastro indisponível.'},status=404)
    model,form_type,prefix=options[kind]
    form=form_type(request.POST,user=request.user,prefix=prefix)
    client_prices=client_price_forms(request.user,request.POST,prefix='quick_client_prices') if kind=='clientes' else None
    try:key=uuid.UUID(request.POST.get('request_key',''))
    except (ValueError,TypeError,AttributeError):return JsonResponse({'message':'Reabra o cadastro para tentar novamente.'},status=400)
    valid=form.is_valid()
    if client_prices is not None:valid=client_prices.is_valid() and valid
    if not valid:
        errors=[]
        if client_prices is not None:
            errors.extend(str(error) for error in client_prices.non_form_errors())
            for index,item in enumerate(client_prices,1):
                if item.cleaned_data.get('DELETE'):continue
                for field,issues in item.errors.items():
                    label=item.fields[field].label if field in item.fields else 'Preço'
                    errors.extend(f'Preço {index} · {label}: {issue}' for issue in issues)
        return JsonResponse({'errors':form.errors.get_json_data(),'price_errors':errors},status=400)
    company=form.cleaned_data['company']
    try:price_rows=client_prices_data(client_prices,company) if client_prices is not None else []
    except ValidationError as exc:return JsonResponse({'message':'; '.join(exc.messages)},status=400)
    values={name:str(value) if value is not None else '' for name,value in form.cleaned_data.items()}
    if client_prices is not None:values['prices']=[{'product':str(row['product'].pk),'amount':str(row['amount'])} for row in price_rows]
    created=False
    try:
        with transaction.atomic():
            Company.objects.select_for_update().get(pk=company.pk)
            obj=model.objects.filter(pk=key).first()
            if obj:
                original=Audit.objects.filter(actor=request.user,entity=str(key),action='CADASTRO_RAPIDO',after__kind=kind).first()
                if obj.company_id!=company.pk or not original or original.after.get('values')!=values:
                    return JsonResponse({'message':'O cadastro anterior já foi salvo com outros dados. Para cadastrar estes novos dados, confira e clique em salvar novamente.'},status=409)
            else:
                obj=form.save(commit=False);obj.pk=key;obj.full_clean();obj.save()
                if kind=='clientes':save_client_prices(request.user,obj,price_rows)
                if kind=='produtos' and form.cleaned_data.get('amount') is not None:
                    set_current_price(request.user,company,obj,form.cleaned_data['amount'])
                workflow.event(request.user,obj,'CADASTRO_RAPIDO',after={'kind':kind,'values':values})
                created=True
    except ValidationError as exc:return JsonResponse({'message':'; '.join(exc.messages)},status=400)
    record={'id':str(obj.pk),'name':obj.name,'company':str(obj.company_id)}
    if kind=='clientes':record.update(weekdays=obj.recurring_weekdays,configured=Recurrence.objects.filter(client=obj,auto_prepare=True,archived=False).exists())
    return JsonResponse({'record':record,'created':created},status=201 if created else 200)

@login_required
def start_demo(request):
    if request.method!='POST':return HttpResponse(status=405)
    if not request.user.is_superuser:raise PermissionDenied
    from django.core.management import call_command
    from django.utils import timezone
    from .services import prepare
    import io
    if Company.objects.filter(operational_enabled=True).exists():
        messages.info(request,'A operação está ativa. Cadastre seus clientes e produtos para começar.');return redirect('operations_start')
    call_command('seed_demo',stdout=io.StringIO())
    day=timezone.localdate();prepare(request.user,day)
    messages.success(request,'Exemplos artificiais preparados. Preços e CNPJs continuam vazios até sua conferência.')
    return redirect('daily')

@login_required
def print_reference(request):
    if not request.user.is_superuser:raise PermissionDenied
    if request.method=='POST':
        try:
            if 'file' not in request.FILES:raise ValidationError('Selecione a planilha de automação.')
            file=request.FILES['file']
            if file.size>12*1024*1024 or not file.name.lower().endswith(('.xlsx','.xlsm')):raise ValidationError('Selecione XLSX/XLSM de até 12 MB.')
            from .print_reference import load_company_reference
            count=load_company_reference(request.user,file.read())
            messages.success(request,f'{count} emissoras conferidas. Dados vazios foram preenchidos; nenhum pedido ou vínculo de cliente foi importado.')
            return redirect('records',kind='empresas')
        except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
    return render(request,'core/print_reference.html')
