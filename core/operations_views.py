import uuid
from datetime import timedelta
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.shortcuts import render,redirect,get_object_or_404
from django.utils import timezone
from .models import Company,Recurrence,Audit
from .services import companies
from .operations import company_checks,activate_operation,reset_routines


@login_required
def operations_start(request):
    if not request.user.is_superuser:raise PermissionDenied
    if request.method=='POST':
        try:
            if request.POST.get('confirm')!='yes':raise ValidationError('Marque a confirmação da ação escolhida.')
            if request.POST.get('action')=='activate':
                company=get_object_or_404(Company,pk=request.POST.get('company'),pk__in=companies(request.user).values('pk'))
                activate_operation(request.user,company)
                messages.success(request,f'Operação gerencial ativada para {company.name}. Os novos pedidos são operacionais; as notinhas continuam não fiscais.')
            elif request.POST.get('action')=='reset':
                key=str(uuid.UUID(request.POST.get('key','')))
                with transaction.atomic():
                    list(companies(request.user).select_for_update().order_by('pk'))
                    if not Audit.objects.filter(actor=request.user,action='RESET_PROGRAMACAO_CONFIRMADO',after__key=key).exists():
                        count=reset_routines(request.user)
                        Audit.objects.create(actor=request.user,entity='PROGRAMACAO',action='RESET_PROGRAMACAO_CONFIRMADO',after={'key':key,'routines_retired':count})
                        messages.success(request,f'{count} rotinas retiradas da programação. Cadastros, pedidos e documentos foram preservados.')
            else:raise ValidationError('Ação desconhecida.')
        except (ValidationError,ValueError,TypeError) as exc:messages.error(request,'; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Identificador de ação inválido.')
        return redirect('operations_start')
    rows=[]
    for company in companies(request.user).order_by('code'):
        checks=company_checks(company)
        rows.append({'company':company,'checks':checks,'ready':all(ok for _,ok,_ in checks),'complete':sum(ok for _,ok,_ in checks)})
    return render(request,'core/operations_start.html',{'rows':rows,'tomorrow':timezone.localdate()+timedelta(days=1),'routine_count':Recurrence.objects.filter(company__in=companies(request.user),archived=False).count(),'reset_key':uuid.uuid4()})
