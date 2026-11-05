"""Perfis operacionais: cada colaborador usa sua própria conta."""
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User, Group, Permission
from django.db import transaction
from .models import Membership, Audit
from .services import companies

ROLES={
    'PRODUCAO':('Produção',['view_order','view_product','view_client','check_production','add_productionrecord','view_productionrecord']),
    'ENTREGA':('Entregas',['view_order','view_client','view_deliverymanifest','view_manifestline','change_manifestline','confirm_delivery','view_deliveryroute','view_driver']),
    'FINANCEIRO':('Financeiro',['view_order','view_client','view_product','view_price','view_receivable','add_receivable','change_receivable','view_payment','add_payment','add_cashbag','view_cashbag','view_deliverymanifest','view_manifestline','view_clientstatement','add_clientstatement','change_clientstatement','view_supplier','add_supplier','change_supplier','view_purchaseinvoice','add_purchaseinvoice','change_purchaseinvoice','view_payable','add_payable','change_payable','view_disbursement','add_disbursement']),
}

class TeamForm(UserCreationForm):
    company=forms.ModelChoiceField(queryset=Membership.objects.none(),label='Empresa de acesso')
    role=forms.ChoiceField(choices=[(key,value[0]) for key,value in ROLES.items()],label='Função no ERP')
    class Meta:
        model=User;fields=['username','first_name','company','role','password1','password2']
        labels={'username':'Nome para entrar no sistema','first_name':'Nome do colaborador'}
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['company'].queryset=companies(user)

@transaction.atomic
def create_member(form,actor):
    user=form.save(commit=False);user.is_staff=False;user.is_superuser=False;user.save()
    key=form.cleaned_data['role'];label,permissions=ROLES[key]
    group,_=Group.objects.get_or_create(name='ERP_'+key)
    group.permissions.set(Permission.objects.filter(content_type__app_label='core',codename__in=permissions))
    user.groups.add(group)
    company=form.cleaned_data['company'];Membership.objects.create(user=user,company=company)
    Audit.objects.create(actor=actor,entity=str(user.pk),action='CRIAR_COLABORADOR',after={'role':key,'company':str(company.pk)},reason='Acesso operacional com conta individual; senha não registrada em auditoria.')
    return user
