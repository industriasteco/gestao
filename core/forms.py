from decimal import Decimal
from django.utils import timezone
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
    amount=forms.DecimalField(label='Preço padrão (R$)', required=False, min_value=0, max_digits=15, decimal_places=4)
    valid_from=forms.DateField(label='Preço válido a partir de', required=False, initial=timezone.localdate, widget=forms.DateInput(attrs={'type':'date'}))
    def clean(self):
        data=super().clean()
        if data.get('amount') is not None and not data.get('valid_from'):
            self.add_error('valid_from','Informe a data de vigência do preço.')
        return data
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
        model=Recurrence;fields=['company','client','product','quantity','slot','time','shift','weekdays','valid_from','valid_until','notes']
        labels={'company':'Empresa','client':'Cliente','product':'Produto','quantity':'Quantidade padrão','slot':'Identificação da entrega','time':'Horário','shift':'Turno','valid_from':'Início','valid_until':'Fim','notes':'Instruções de preparo e entrega'}

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

class InlinePriceForm(forms.Form):
    product = forms.ModelChoiceField(queryset=Product.objects.none(), label='Produto')
    amount = forms.DecimalField(label='Valor negociado (R$)', min_value=0, max_digits=15, decimal_places=4)
    valid_from = forms.DateField(label='Válido a partir de', widget=forms.DateInput(attrs={'type':'date'}))
    def __init__(self, *args, company, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(company=company, active=True)

class ReceivableForm(ScopedForm):
    class Meta:
        model=Receivable
        fields=['company','client','reference','issued_on','due_on','amount','notes']
        labels={'company':'Empresa','client':'Cliente','reference':'Número / referência única','issued_on':'Emissão','due_on':'Vencimento','amount':'Valor confirmado (R$)','notes':'Observações'}

class PaymentForm(forms.Form):
    amount=forms.DecimalField(label='Valor recebido (R$)', min_value=Decimal('0.01'), max_digits=15, decimal_places=2)
    date=forms.DateField(label='Data do recebimento', widget=forms.DateInput(attrs={'type':'date'}))
    reference=forms.UUIDField(widget=forms.HiddenInput)

class StockItemForm(ScopedForm):
    class Meta:
        model=StockItem; fields=['company','name','unit','minimum']
        labels={'company':'Empresa','name':'Insumo ou produto','unit':'Unidade','minimum':'Estoque mínimo'}

class StockMovementForm(forms.Form):
    item=forms.ModelChoiceField(queryset=StockItem.objects.none(), label='Item de estoque')
    quantity=forms.DecimalField(label='Quantidade (+ entrada / − saída)', max_digits=15, decimal_places=3)
    date=forms.DateField(label='Data', widget=forms.DateInput(attrs={'type':'date'}))
    reason=forms.CharField(label='Motivo', max_length=250)
    key=forms.UUIDField(widget=forms.HiddenInput)
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['item'].queryset=StockItem.objects.filter(company__in=companies(user))

class WorkbookForm(forms.Form):
    company=forms.ModelChoiceField(queryset=Company.objects.none(), label='Empresa dos clientes')
    file=forms.FileField(label='Planilha de rotinas (.xlsm ou .xlsx)')
    start=forms.DateField(label='Iniciar rotinas a partir de', widget=forms.DateInput(attrs={'type':'date'}))
    confirm=forms.BooleanField(label='Cadastrar clientes, produtos e rotinas estáveis. Não importar pedidos nem valores antigos.')
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['company'].queryset=companies(user)
    def clean_file(self):
        file=self.cleaned_data['file']
        if not file.name.lower().endswith(('.xlsm','.xlsx')) or file.size>12*1024*1024:
            raise ValidationError('Selecione uma planilha XLSM/XLSX de até 12 MB.')
        return file
