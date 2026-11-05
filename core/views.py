from datetime import date
from decimal import Decimal, InvalidOperation
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError, PermissionDenied
from django.shortcuts import render,redirect,get_object_or_404
from django.contrib import messages
from .models import *
from .workflow import cancel as cancel_workflow
from .services import companies,prepare,production,review,check_production,adjust,cancel,stage_bytes

@login_required
def daily(request):
    try: day=date.fromisoformat(request.GET.get('date',str(timezone.localdate())))
    except ValueError: return render(request,'core/error.html',status=400)
    if request.method=='POST':
        try:
            if request.POST.get('action')=='responsibles':
                from .forms import ShiftResponsiblesForm
                from .day_finalization import assign_shift_responsibles
                form=ShiftResponsiblesForm(request.POST)
                if not form.is_valid():raise ValidationError('Confira os nomes dos responsáveis (até 100 caracteres).')
                count=assign_shift_responsibles(request.user,day,**form.cleaned_data)
                messages.success(request,f'Responsáveis atualizados em {count} pedidos ainda não emitidos.')
            if request.POST.get('action')=='finalize':
                from .day_finalization import finalize_day
                docs=finalize_day(request.user,day)
                return render(request,'core/day_finalized.html',{'day':day,'receipts':docs[0],'production_doc':docs[1]})
            if request.POST.get('action')=='prepare': messages.success(request,f'{prepare(request.user,day)} pedidos preparados. Nenhuma emissão realizada.')
            elif request.POST.get('action')=='adjust': adjust(request.user,request.POST['order'],Decimal(request.POST['quantity']),request.POST.get('reason',''),request.POST.get('item') or None)
            elif request.POST.get('action')=='cancel': cancel_workflow(request.user,request.POST['order'],request.POST.get('reason',''))
            elif request.POST.get('action')=='check': check_production(request.user,day);messages.success(request,'Produção conferida. Nenhuma entrega ou emissão confirmada.')
        except (InvalidOperation,KeyError,Order.DoesNotExist,OrderItem.DoesNotExist): messages.error(request,'Dados inválidos')
        except ValidationError as e: messages.error(request,'; '.join(e.messages))
        return redirect(f'/pedidos-dia/?date={day}')
    orders=Order.objects.filter(company__in=companies(request.user),date=day).select_related('company','client').prefetch_related('items')
    return render(request,'core/daily.html',dict(day=day.isoformat(),orders=orders,production=production(orders),companies=companies(request.user)))

@login_required
def staging(request):
    if not request.user.has_perm('core.review_staging'): raise PermissionDenied
    if request.method=='POST':
        try:
            if 'file' in request.FILES:
                file=request.FILES['file']
                if file.size>5*1024*1024:raise ValidationError('Limite: 5 MB por CSV.')
                batch=stage_bytes(file.read(),file.name)
                messages.success(request,f'{batch.rows.count()} linhas recebidas somente para revisão. Nenhum pedido criado.')
            else:
                c=get_object_or_404(Candidate,pk=request.POST.get('candidate'))
                review(request.user,c,request.POST.get('reason',''))
                messages.success(request,'Revisão registrada. Nenhum cadastro ou pedido criado.')
        except ValidationError as e:messages.error(request,'; '.join(e.messages))
        return redirect('staging')
    from django.core.paginator import Paginator
    rows=Candidate.objects.select_related('batch').order_by('batch__filename','row_number')
    if request.GET.get('batch'): rows=rows.filter(batch_id=request.GET['batch'])
    return render(request,'core/staging.html',{'page':Paginator(rows,30).get_page(request.GET.get('page')),'batches':ImportBatch.objects.all(),'batch':request.GET.get('batch','')})
