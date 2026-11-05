import csv
import hashlib
from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404,redirect,render
from django.utils import timezone
from .models import ClientStatement,StatementLine
from .forms import StatementForm
from .services import companies
from .statements import eligible_orders,create_statement,statement_action


@login_required
def statements(request):
    if not request.user.has_perm('core.view_clientstatement'):raise PermissionDenied
    today=timezone.localdate()
    form=StatementForm(request.POST or request.GET or None,user=request.user,initial={'start':today.replace(day=1),'end':today})
    preview=[]
    if form.is_valid():
        data=form.cleaned_data
        try:
            preview=eligible_orders(data['company'],data['client'],data['start'],data['end'])
            if request.method=='POST' and request.POST.get('action')=='generate':
                if request.POST.get('confirm')!='yes':raise ValidationError('Confira os pedidos e marque a confirmação para gerar o demonstrativo.')
                row=create_statement(request.user,**data)
                return redirect('statement_detail',pk=row.pk)
        except ValidationError as exc:form.add_error(None,exc)
    rows=ClientStatement.objects.filter(company__in=companies(request.user)).select_related('client','company').order_by('-created_at')[:100]
    return render(request,'core/statements.html',{'form':form,'rows':rows,'preview':preview})


@login_required
def statement_detail(request,pk):
    if not request.user.has_perm('core.view_clientstatement'):raise PermissionDenied
    row=get_object_or_404(ClientStatement.objects.select_related('company','client','document'),pk=pk,company__in=companies(request.user))
    if request.method=='POST':
        try:
            statement_action(request.user,row,request.POST.get('action'),request.POST.get('evidence',''))
            messages.success(request,'Situação registrada. Nenhuma mensagem enviada automaticamente e nenhuma nota fiscal emitida.')
            return redirect('statement_detail',pk=pk)
        except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
    return render(request,'core/statement_detail.html',{'row':row})


@login_required
def statement_document(request,pk):
    if not request.user.has_perm('core.view_clientstatement'):raise PermissionDenied
    row=get_object_or_404(ClientStatement.objects.select_related('document'),pk=pk,company__in=companies(request.user))
    if row.status=='CANCELADO':return HttpResponse('Fechamento cancelado. Consulte o histórico.',status=409)
    data=bytes(row.document.data)
    if hashlib.sha256(data).hexdigest()!=row.document.sha256:return HttpResponse('Falha na integridade do PDF.',status=409)
    response=HttpResponse(data,content_type='application/pdf')
    response['Content-Disposition']=f'inline; filename="fechamento-{str(row.pk)[:8]}.pdf"'
    response['Cache-Control']='private, no-store';return response


@login_required
def statement_export(request,pk):
    if not request.user.has_perm('core.view_clientstatement'):raise PermissionDenied
    row=get_object_or_404(ClientStatement,pk=pk,company__in=companies(request.user))
    if row.status!='APROVADO':return HttpResponse('Registre a aprovação do cliente antes de exportar.',status=409)
    response=HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition']=f'attachment; filename="fechamento-aprovado-{str(row.pk)[:8]}.csv"'
    response['Cache-Control']='private, no-store';response.write('\ufeff')
    writer=csv.writer(response,delimiter=';')
    def cell(value):
        value=str(value or '')
        return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
    writer.writerow(['Finalidade','Empresa','Cliente','CPF_CNPJ','Inicio','Fim','Pedido','Data','Produto','Unidade','Quantidade','Valor_unitario','Valor_total'])
    for item in row.snapshot['items']:
        writer.writerow([cell(v) for v in ['HOMOLOGACAO - NAO EMITIR NOTA REAL' if row.snapshot['synthetic'] else 'Apoio ao preenchimento fiscal - validar dados tributarios',row.snapshot['company'],row.snapshot['legal_name'] or row.snapshot['client'],row.snapshot['client_tax_id'],row.start,row.end,item['number'] or item['order'],item['date'],item['product'],item['unit'],item['quantity'],item['price'],item['total']]])
    return response
