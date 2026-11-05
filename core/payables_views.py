import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.db.models import Sum,Q
from django.forms import formset_factory
from django.http import HttpResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.utils import timezone
from .models import Supplier,Payable,PurchaseInvoice
from .services import companies
from .forms import SupplierForm,PayableForm,InvoiceUploadForm,InvoiceInstallmentForm,DisbursementForm,PayableFilterForm
from .payables_services import stage_invoice,confirm_invoice,payable_balances,pay,void_payable,archive_invoice
from .workflow import event


def require(user,codename):
    if not user.has_perm('core.'+codename):raise PermissionDenied


@login_required
def payables(request):
    require(request.user,'view_payable')
    form=PayableForm(request.POST or None,user=request.user,initial={'issued_on':timezone.localdate()})
    if request.method=='POST':
        require(request.user,'add_payable')
        if form.is_valid():
            with transaction.atomic():
                row=form.save();event(request.user,row,'CADASTRAR_CONTA_A_PAGAR',after={'amount':str(row.amount),'due_on':str(row.due_on),'synthetic':row.synthetic})
            messages.success(request,'Conta a pagar cadastrada. Nenhum pagamento bancário foi realizado.');return redirect('payables')
    filters=PayableFilterForm(request.GET or None,user=request.user)
    rows=payable_balances(request.user)
    if request.GET:
        if filters.is_valid():
            selected=filters.cleaned_data
            if selected.get('company'):rows=[r for r in rows if r.company_id==selected['company'].pk]
            if selected.get('q'):
                query=selected['q'].casefold();rows=[r for r in rows if query in r.supplier.name.casefold() or query in r.reference.casefold()]
            status=selected.get('status')
            if status=='open':rows=[r for r in rows if r.balance>0]
            elif status=='paid':rows=[r for r in rows if r.balance<=0]
            elif status=='overdue':rows=[r for r in rows if r.days_late]
        else:rows=[]
    rows.sort(key=lambda row:(-row.days_late,row.due_on,row.supplier.name))
    real=[r for r in rows if not r.synthetic]
    today=timezone.localdate()
    return render(request,'core/payables.html',dict(form=form,filters=filters,rows=rows,
        open_total=sum((r.balance for r in real if r.balance>0),Decimal(0)),late_total=sum((r.balance for r in real if r.days_late),Decimal(0)),
        upcoming_total=sum((r.balance for r in real if r.balance>0 and today<=r.due_on<=today+timedelta(days=7)),Decimal(0)),test_count=sum(r.synthetic for r in rows),
        pending=PurchaseInvoice.objects.filter(company__in=companies(request.user),status='EM_REVISAO').count()))


@login_required
def suppliers(request):
    require(request.user,'view_supplier')
    form=SupplierForm(request.POST or None,user=request.user)
    if request.method=='POST':
        require(request.user,'add_supplier')
        if form.is_valid():
            row=form.save();event(request.user,row,'CADASTRAR_FORNECEDOR');return redirect('suppliers')
    return render(request,'core/suppliers.html',{'form':form,'rows':Supplier.objects.filter(company__in=companies(request.user)).select_related('company').order_by('name')})


@login_required
def supplier_detail(request,pk):
    require(request.user,'view_supplier')
    supplier=get_object_or_404(Supplier,pk=pk,company__in=companies(request.user))
    form=SupplierForm(request.POST or None,instance=supplier,user=request.user);form.fields['company'].disabled=True
    if request.method=='POST':
        require(request.user,'change_supplier')
        if form.is_valid():
            row=form.save();event(request.user,row,'EDITAR_FORNECEDOR');messages.success(request,'Fornecedor atualizado.');return redirect('supplier_detail',pk=pk)
    rows=[r for r in payable_balances(request.user) if r.supplier_id==supplier.pk]
    return render(request,'core/supplier_detail.html',dict(supplier=supplier,form=form,rows=rows))


@login_required
def invoices(request):
    require(request.user,'view_purchaseinvoice')
    form=InvoiceUploadForm(request.POST or None,request.FILES or None,user=request.user)
    if request.method=='POST':
        require(request.user,'add_purchaseinvoice')
        if form.is_valid():
            try:
                data=form.cleaned_data;file=data['file']
                invoice,created=stage_invoice(request.user,data['company'],file.read(),file.name)
                messages.success(request,'XML recebido. Confira as parcelas para gerar as contas a pagar.' if created else 'Essa nota já foi importada. Nenhum fornecedor, parcela ou pagamento foi duplicado.')
                return redirect('invoice_detail',pk=invoice.pk)
            except ValidationError as exc:form.add_error(None,exc)
    rows=PurchaseInvoice.objects.filter(company__in=companies(request.user)).select_related('company','supplier').order_by('-created_at')[:100]
    return render(request,'core/purchase_invoices.html',{'form':form,'rows':rows})


@login_required
def invoice_detail(request,pk):
    require(request.user,'view_purchaseinvoice')
    invoice=get_object_or_404(PurchaseInvoice.objects.select_related('company','supplier'),pk=pk,company__in=companies(request.user))
    requires_schedule=not invoice.installments or any(not row['due_on'] for row in invoice.installments)
    ItemSet=formset_factory(InvoiceInstallmentForm,extra=0 if invoice.installments else 3,max_num=120,validate_max=True)
    items=ItemSet(request.POST if request.method=='POST' and requires_schedule and request.POST.get('action')=='confirm' else None,initial=invoice.installments)
    if invoice.installments:
        for item,original in zip(items.forms,invoice.installments):
            item.fields['reference'].disabled=True;item.fields['amount'].disabled=True
            if original['due_on']:item.fields['due_on'].disabled=True
    if request.method=='POST':
        try:
            action=request.POST.get('action')
            if action=='confirm':
                require(request.user,'add_payable')
                if request.POST.get('confirm')!='yes':raise ValidationError('Confira o documento e marque a confirmação das parcelas.')
                schedule=None
                if requires_schedule:
                    if not items.is_valid():raise ValidationError('Confira os valores e vencimentos das parcelas informadas.')
                    schedule=[item.cleaned_data for item in items if item.cleaned_data]
                rows=confirm_invoice(request.user,invoice,schedule)
                messages.success(request,f'{len(rows)} parcelas disponíveis em Contas a pagar. Nenhum pagamento realizado.');return redirect('invoice_detail',pk=pk)
            elif action=='archive':
                archive_invoice(request.user,invoice,request.POST.get('reason',''))
                messages.success(request,'XML arquivado, sem criar contas nem considerar a nota paga.');return redirect('invoice_detail',pk=pk)
        except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
    rows=list(invoice.payables.annotate(paid=Sum('payments__amount')).order_by('due_on','installment'))
    for row in rows:row.balance=row.amount-(row.paid or Decimal(0))
    return render(request,'core/purchase_invoice_detail.html',dict(invoice=invoice,items=items,rows=rows,requires_schedule=requires_schedule))


@login_required
def invoice_xml(request,pk):
    require(request.user,'view_purchaseinvoice')
    invoice=get_object_or_404(PurchaseInvoice,pk=pk,company__in=companies(request.user))
    data=bytes(invoice.xml)
    if hashlib.sha256(data).hexdigest()!=invoice.sha256:return HttpResponse('Integridade do XML divergente. Consulte o responsável.',status=409)
    response=HttpResponse(data,content_type='application/xml')
    response['Content-Disposition']=f'attachment; filename="NFe-{invoice.access_key}.xml"'
    response['Cache-Control']='private, no-store';response['X-Content-Type-Options']='nosniff'
    return response


@login_required
def payable_detail(request,pk):
    require(request.user,'view_payable')
    payable=get_object_or_404(Payable.objects.select_related('company','supplier','invoice'),pk=pk,company__in=companies(request.user))
    form=DisbursementForm(request.POST if request.method=='POST' and request.POST.get('action')!='void' else None,initial={'date':timezone.localdate(),'reference':uuid.uuid4()})
    if request.method=='POST':
        require(request.user,'change_payable')
        try:
            if request.POST.get('action')=='void':
                void_payable(request.user,payable,request.POST.get('reason',''));messages.success(request,'Conta cancelada com histórico preservado.');return redirect('payable_detail',pk=pk)
            elif form.is_valid():
                data=form.cleaned_data
                pay(request.user,payable,data['amount'],data['date'],data['method'],str(data['reference']),data['evidence'])
                messages.success(request,'Pagamento registrado no controle interno.');return redirect('payable_detail',pk=pk)
        except ValidationError as exc:form.add_error(None,exc)
    payable.paid=payable.payments.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    payable.balance=payable.amount-payable.paid
    return render(request,'core/payable_detail.html',dict(row=payable,form=form,payments=payable.payments.select_related('actor').order_by('-date','id')))


@login_required
def fiscal_overview(request):
    require(request.user,'view_purchaseinvoice')
    return render(request,'core/fiscal_overview.html',dict(companies=companies(request.user),invoice_count=PurchaseInvoice.objects.filter(company__in=companies(request.user)).count()))
