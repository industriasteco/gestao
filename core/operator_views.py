import hashlib
from datetime import date
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction
from django.http import HttpResponse,FileResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from django.urls import reverse
from io import BytesIO
from .models import *
from .services import companies,authorize,require,activate
from .forms import *
from . import workflow

@login_required
def guide(request):return render(request,'core/guide.html')

@login_required
def records(request,kind):
    options={'empresas':(Company,CompanyForm),'clientes':(Client,ClientForm),'produtos':(Product,ProductForm),'precos':(Price,PriceForm),'recorrencias':(Recurrence,RecurrenceForm)}
    if kind not in options:return redirect('records',kind='clientes')
    model,form_type=options[kind]
    if request.method=='POST':
        if not request.user.is_superuser:raise PermissionDenied
        if request.POST.get('action')=='activate' and kind=='recorrencias':
            rule=get_object_or_404(Recurrence,pk=request.POST.get('rule'),company__in=companies(request.user))
            try:activate(request.user,rule,request.POST.get('reason',''))
            except ValidationError as e:messages.error(request,'; '.join(e.messages))
            return redirect('records',kind=kind)
        form=form_type(request.POST,user=request.user)
        if form.is_valid():
            with transaction.atomic():
                obj=form.save()
                if kind=='produtos' and form.cleaned_data.get('amount') is not None:
                    from .management_services import set_price
                    set_price(request.user,obj.company,obj,form.cleaned_data['amount'],form.cleaned_data['valid_from'])
                workflow.event(request.user,obj,'CADASTRAR',after={k:str(v) for k,v in form.cleaned_data.items()})
            messages.success(request,'Cadastro salvo. Nenhum documento ou cobrança criado.')
            return redirect('records',kind=kind)
    else:form=form_type(user=request.user)
    rows=companies(request.user) if model is Company else model.objects.filter(company__in=companies(request.user))
    if kind=='produtos':
        from django.utils import timezone
        from django.db.models import Q
        today=timezone.localdate()
        for row in rows:
            current=Price.objects.filter(product=row,client__isnull=True,valid_from__lte=today).filter(Q(valid_until__isnull=True)|Q(valid_until__gte=today))
            row.current_price=current.first().amount if current.count()==1 else None
            row.gross_profit=row.current_price-row.production_cost if row.current_price is not None and row.production_cost is not None else None
    if kind=='clientes':
        from .management_services import balances
        overdue={r.client_id for r in balances(request.user) if r.days_late}
        known={r.client_id for r in balances(request.user)}
        for row in rows:row.financial_status='Inadimplente' if row.pk in overdue else ('Adimplente' if row.pk in known else 'Sem histórico financeiro')
    return render(request,'core/records.html',dict(kind=kind,rows=rows,form=form,options=options))

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
            messages.success(request,'Operação de teste registrada com auditoria.')
        except ValidationError as e:messages.error(request,'; '.join(e.messages))
        return redirect('order',pk=pk)
    price_preview=[]
    for item in order.items.select_related('product').all():
        try:price=workflow.price_for(order.company,order.client,item.product,order.date)
        except ValidationError:price='PENDENTE DE CONFERÊNCIA'
        price_preview.append((item,price))
    return render(request,'core/order.html',dict(order=order,form=form,documents=Document.objects.filter(order=order),price_preview=price_preview))

@login_required
def document(request,pk):
    doc=get_object_or_404(Document,pk=pk,company__in=companies(request.user))
    allowed={str(pk) for pk in companies(request.user).values_list('pk',flat=True)}
    if doc.company_scope and not set(doc.company_scope).issubset(allowed):raise PermissionDenied
    if not (request.user.has_perm('core.issue_document') or request.user.has_perm('core.close_month')):raise PermissionDenied
    if doc.superseded:return render(request,'core/doc_cancelled.html',{'doc':doc},status=409)
    if hashlib.sha256(bytes(doc.data)).hexdigest()!=doc.sha256:return HttpResponse('Integridade do documento divergente. Contate o responsável.',status=409)
    response=FileResponse(BytesIO(bytes(doc.data)),content_type='application/pdf',filename='HOMOLOGACAO_NAO_COBRAR.pdf')
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
    form=ManualOrderForm(request.POST or None,user=request.user,initial={'date':timezone.localdate(),'key':uuid.uuid4(),'slot':'1ª entrega'})
    ItemSet=formset_factory(ManualItemForm,extra=4,max_num=100,validate_max=True)
    items=ItemSet(request.POST or None,form_kwargs={'user':request.user})
    if request.method=='POST' and form.is_valid() and items.is_valid():
        try:
            company=form.cleaned_data['company'];authorize(request.user,company,'core.prepare_day')
            lines=[item.cleaned_data for item in items if item.cleaned_data]
            if not lines or not any(line['quantity']>0 for line in lines):raise ValidationError('Inclua ao menos um item com quantidade positiva.')
            if any(line['product'].company_id!=company.pk for line in lines):raise ValidationError('Todos os produtos devem pertencer à empresa do pedido.')
            with transaction.atomic():
                Company.objects.select_for_update().get(pk=company.pk)
                key='manual:'+str(form.cleaned_data['key'])
                order=Order.objects.filter(idempotency_key=key).first()
                if order is None:
                    order=form.save(commit=False);order.idempotency_key=key;order.synthetic=True;order.save()
                    for line in lines:
                        p=line['product'];OrderItem.objects.create(order=order,product=p,product_name=p.name,unit=p.unit,quantity=line['quantity'])
                    workflow.event(request.user,order,'PEDIDO_MANUAL_TESTE',after={'items':len(lines)})
                elif order.company_id!=company.pk:raise ValidationError('Chave já usada para outra empresa.')
            return redirect('order',pk=order.pk)
        except ValidationError as e:form.add_error(None,e)
    return render(request,'core/new_order.html',{'form':form,'items':items})

@login_required
def start_demo(request):
    if request.method!='POST':return HttpResponse(status=405)
    if not request.user.is_superuser:raise PermissionDenied
    from django.core.management import call_command
    from django.utils import timezone
    from .services import prepare
    import io
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
