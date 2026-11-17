import hashlib
from datetime import date
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404,redirect
from django.views.decorators.http import require_POST
from .models import Client,Document
from .services import companies
from .client_reports import create_client_report,report_prefix


@login_required
@require_POST
def generate(request,pk):
    if not request.user.has_perm('core.view_clientstatement'):raise PermissionDenied
    client=get_object_or_404(Client.objects.select_related('company'),pk=pk,company__in=companies(request.user))
    try:
        start=date.fromisoformat(request.POST.get('start',''));end=date.fromisoformat(request.POST.get('end',''))
        document=create_client_report(request.user,client,start,end)
        return redirect('client_report_document',pk=client.pk,document_id=document.pk)
    except (ValueError,ValidationError) as exc:
        messages.error(request,'; '.join(exc.messages) if isinstance(exc,ValidationError) else 'Informe o início e o fim do período.')
        return redirect('client_detail',pk=client.pk)


@login_required
def document(request,pk,document_id):
    if not request.user.has_perm('core.view_clientstatement'):raise PermissionDenied
    client=get_object_or_404(Client,pk=pk,company__in=companies(request.user))
    row=get_object_or_404(Document,pk=document_id,company=client.company,kind='RELATORIO_PEDIDOS_CLIENTE',key__startswith=report_prefix(client))
    if row.superseded:return HttpResponse('Este relatório foi cancelado. Consulte o histórico do cliente.',status=409)
    data=bytes(row.data)
    if hashlib.sha256(data).hexdigest()!=row.sha256:return HttpResponse('Integridade do relatório divergente.',status=409)
    response=HttpResponse(data,content_type='application/pdf')
    response['Content-Disposition']=f'inline; filename="relatorio-pedidos-{str(client.pk)[:8]}-{row.key.split(":")[2]}-{row.key.split(":")[3]}.pdf"'
    response['Cache-Control']='private, no-store'
    return response
