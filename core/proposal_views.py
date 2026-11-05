import hashlib
import uuid
from decimal import Decimal,ROUND_HALF_UP
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.forms import formset_factory
from django.http import HttpResponse
from django.shortcuts import render,redirect,get_object_or_404
from django.utils import timezone
from .models import CommercialProposal,ProposalProfile,Company
from .forms import CommercialProposalForm,ProposalItemForm,ProposalProfileForm
from .services import companies
from .workflow import event
from .proposal_services import save_proposal,generate_proposal,proposal_action,revise_proposal,header_values


def require(user,permission):
    if not user.has_perm('core.'+permission):raise PermissionDenied


@login_required
def proposals(request):
    require(request.user,'view_commercialproposal')
    rows=CommercialProposal.objects.filter(company__in=companies(request.user)).select_related('company','client','previous').order_by('-created_at')
    query=request.GET.get('q','').strip()
    if query:
        from django.db.models import Q
        rows=rows.filter(Q(number__icontains=query)|Q(customer_name__icontains=query)|Q(title__icontains=query))
    return render(request,'core/proposals.html',{'rows':rows[:150],'q':query,'companies':companies(request.user)})


@login_required
def proposal_edit(request,pk=None):
    require(request.user,'change_commercialproposal' if pk else 'add_commercialproposal')
    instance=get_object_or_404(CommercialProposal,pk=pk,company__in=companies(request.user)) if pk else None
    if instance and (instance.status!='RASCUNHO' or instance.document_id):
        messages.info(request,'Proposta já preservada. Crie uma revisão para fazer alterações.');return redirect('proposal_detail',pk=pk)
    initial={'key':instance.pk} if instance else {'issued_on':timezone.localdate(),'valid_days':60,'key':uuid.uuid4()}
    form=CommercialProposalForm(request.POST or None,user=request.user,instance=instance,initial=initial)
    if instance:form.fields['company'].disabled=True
    ItemSet=formset_factory(ProposalItemForm,extra=0 if instance else 4,max_num=100,validate_max=True,can_delete=True)
    items_initial=[dict(product=item.product_id,description=item.description,quantity=item.quantity,unit=item.unit,unit_price=item.unit_price) for item in instance.items.all()] if instance else None
    items=ItemSet(request.POST or None,form_kwargs={'user':request.user},initial=items_initial)
    if request.method=='POST' and form.is_valid() and items.is_valid():
        try:
            values={key:form.cleaned_data.get(key) for key in ['company','client','title','summary','issued_on','valid_days','customer_name','customer_tax_id','customer_address','included_items','conditions','notes','responsible']}
            proposal=save_proposal(request.user,values,[item.cleaned_data for item in items if item.cleaned_data and not item.cleaned_data.get('DELETE')],form.cleaned_data['key'],instance)
            messages.success(request,'Rascunho salvo. Nenhum pedido, cobrança ou preço de cadastro foi alterado.');return redirect('proposal_detail',pk=proposal.pk)
        except ValidationError as exc:form.add_error(None,exc)
    return render(request,'core/proposal_form.html',{'form':form,'items':items,'proposal':instance})


@login_required
def proposal_detail(request,pk):
    require(request.user,'view_commercialproposal')
    proposal=get_object_or_404(CommercialProposal.objects.select_related('company','client','document','previous'),pk=pk,company__in=companies(request.user))
    if request.method=='POST':
        try:
            action=request.POST.get('action')
            if action=='generate':
                generate_proposal(request.user,proposal)
                messages.success(request,'PDF da proposta gerado e preservado. Nenhuma mensagem enviada ao cliente.')
            elif action=='revise':
                key=uuid.UUID(request.POST.get('key',''))
                new=revise_proposal(request.user,proposal,key);return redirect('proposal_edit',pk=new.pk)
            else:proposal_action(request.user,proposal,action,request.POST.get('evidence',''))
            return redirect('proposal_detail',pk=pk)
        except (ValueError,TypeError):messages.error(request,'Identificador de revisão inválido.')
        except ValidationError as exc:messages.error(request,'; '.join(exc.messages))
    rows=[]
    for item in proposal.items.all():
        item.line_total=(item.quantity*item.unit_price).quantize(Decimal('.01'),rounding=ROUND_HALF_UP);rows.append(item)
    return render(request,'core/proposal_detail.html',dict(proposal=proposal,rows=rows,header=proposal.snapshot.get('company') or header_values(proposal.company),revision_key=uuid.uuid4()))


@login_required
def proposal_document(request,pk):
    require(request.user,'view_commercialproposal')
    proposal=get_object_or_404(CommercialProposal.objects.select_related('document'),pk=pk,company__in=companies(request.user))
    if not proposal.document_id or proposal.status=='CANCELADA':return HttpResponse('Proposta sem PDF disponível ou cancelada.',status=409)
    data=bytes(proposal.document.data)
    if hashlib.sha256(data).hexdigest()!=proposal.document.sha256:return HttpResponse('Integridade do PDF divergente.',status=409)
    response=HttpResponse(data,content_type='application/pdf')
    response['Content-Disposition']=f'inline; filename="proposta-{proposal.number}.pdf"'
    response['Cache-Control']='private, no-store';return response


@login_required
def proposal_profile(request,pk):
    if not request.user.is_superuser:raise PermissionDenied
    company=get_object_or_404(Company,pk=pk,pk__in=companies(request.user).values('pk'))
    profile=ProposalProfile.objects.filter(company=company).first()
    values=header_values(company)
    initial=dict(display_name=values['name'],subtitle=values['subtitle'],legal_name=values['legal_name'],tax_id=values['tax_id'],address=values['address'],phone=values['phone'],email=values['email'],responsible=values['responsible'])
    form=ProposalProfileForm(request.POST if request.method=='POST' and request.POST.get('action')!='import' else None,instance=profile,initial=initial if profile is None else None)
    if request.method=='POST':
        try:
            if request.POST.get('action')=='import':
                file=request.FILES.get('file')
                if not file or not file.name.lower().endswith('.docx') or file.size>12*1024*1024:raise ValidationError('Selecione um DOCX de até 12 MB.')
                from .proposal_reference import import_profile
                import_profile(request.user,company,file.read(),file.name)
                messages.success(request,'Cabeçalho do modelo carregado apenas para propostas desta empresa.');return redirect('proposal_profile',pk=pk)
            if form.is_valid():
                with transaction.atomic():
                    obj=form.save(commit=False);obj.company=company;obj.full_clean();obj.save();event(request.user,obj,'CONFIGURAR_CABECALHO_PROPOSTA',after={key:str(value) for key,value in form.cleaned_data.items()})
                messages.success(request,'Cabeçalho das propostas atualizado. PDFs existentes foram preservados.');return redirect('proposal_profile',pk=pk)
        except ValidationError as exc:form.add_error(None,exc)
    return render(request,'core/proposal_profile.html',{'company':company,'form':form,'profile':profile})
