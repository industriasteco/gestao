from django.db.models import Q
from django import forms
from django.core.exceptions import ValidationError
from .models import *
from .services import companies

class ScopedForm(forms.ModelForm):
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.user=user
        for name,field in self.fields.items():
            if name=='company':field.queryset=companies(user)
            elif name in ('client','product'):field.queryset=field.queryset.filter(company__in=companies(user))
        for field in self.fields.values():
            if isinstance(field,forms.DateField):field.widget=forms.DateInput(attrs={'type':'date'})
    def clean(self):
        data=super().clean();co=data.get('company')
        for field in ('client','product'):
            linked=data.get(field)
            if linked and co and linked.company_id!=co.pk:raise ValidationError('Selecione cliente e produto da mesma empresa.')
        return data

class CompanyForm(ScopedForm):
    class Meta:
        model=Company;fields=['code','name','legal_name','cnpj']
        labels={'code':'Código','name':'Nome da empresa','legal_name':'Razão social','cnpj':'CNPJ (somente confirmado)'}

class ClientForm(ScopedForm):
    class Meta:
        model=Client;fields=['company','name','address','notes']
        labels={'company':'Empresa','name':'Nome do cliente','address':'Endereço','notes':'Observações'}

class ProductForm(ScopedForm):
    class Meta:
        model=Product;fields=['company','name','unit']
        labels={'company':'Empresa','name':'Nome do produto','unit':'Unidade (UN, KG...)'}

class PriceForm(ScopedForm):
    class Meta:
        model=Price;fields=['company','client','product','amount','valid_from','valid_until']
        labels={'company':'Empresa','client':'Cliente (vazio = preço padrão)','product':'Produto','amount':'Preço confirmado','valid_from':'Válido desde','valid_until':'Válido até'}
    def clean(self):
        data=super().clean()
        if all(data.get(k) is not None for k in ('company','product','valid_from')):
            rows=Price.objects.filter(company=data['company'],product=data['product'],client=data.get('client'))
            if data.get('valid_until'):rows=rows.filter(valid_from__lte=data['valid_until'])
            rows=rows.filter(Q(valid_until__isnull=True)|Q(valid_until__gte=data['valid_from']))
            if rows.exists():raise ValidationError('Já existe preço nesta vigência. Revise as datas, sem alterar o histórico.')
        return data

class RecurrenceForm(ScopedForm):
    weekdays=forms.TypedMultipleChoiceField(label='Dias de entrega',choices=[(1,'Segunda'),(2,'Terça'),(3,'Quarta'),(4,'Quinta'),(5,'Sexta'),(6,'Sábado'),(7,'Domingo')],coerce=int,widget=forms.CheckboxSelectMultiple)
    class Meta:
        model=Recurrence;fields=['company','client','product','quantity','slot','time','shift','weekdays','valid_from','valid_until']
        labels={'company':'Empresa','client':'Cliente','product':'Produto','quantity':'Quantidade padrão','slot':'Identificação da entrega','time':'Horário','shift':'Turno','valid_from':'Início','valid_until':'Fim'}

class ProductionInfoForm(forms.ModelForm):
    reason=forms.CharField(label='Motivo do ajuste',min_length=3)
    class Meta:
        model=Order;fields=['shift','baker','driver','notes']
        labels={'shift':'Turno','baker':'Padeiro responsável','driver':'Motorista','notes':'Observações'}

class MonthForm(forms.Form):
    company=forms.ModelChoiceField(queryset=Company.objects.none(),label='Empresa')
    client=forms.ModelChoiceField(queryset=Client.objects.none(),label='Cliente')
    month=forms.DateField(label='Mês (selecione dia 1)',widget=forms.DateInput(attrs={'type':'date'}))
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['company'].queryset=companies(user)
        self.fields['client'].queryset=Client.objects.filter(company__in=companies(user))

class ManualOrderForm(ScopedForm):
    key=forms.UUIDField(widget=forms.HiddenInput)
    class Meta:
        model=Order;fields=['company','client','date','time','slot','shift','baker','driver','notes']
        labels={'company':'Empresa','client':'Cliente','date':'Dia da entrega','time':'Horário','slot':'Identificação da entrega','shift':'Turno','baker':'Padeiro','driver':'Motorista','notes':'Observações'}

class ManualItemForm(forms.Form):
    product=forms.ModelChoiceField(queryset=Product.objects.none(),label='Produto')
    quantity=forms.DecimalField(label='Quantidade',min_value=0,max_digits=15,decimal_places=3)
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['product'].queryset=Product.objects.filter(company__in=companies(user),active=True)
