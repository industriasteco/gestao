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
            elif name in ('client','product','supplier'):field.queryset=field.queryset.filter(company__in=companies(user))
        for field in self.fields.values():
            if isinstance(field,forms.DateField):field.widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'})
    def clean(self):
        data=super().clean();co=data.get('company')
        for field in ('client','product','supplier'):
            linked=data.get(field)
            if linked and co and linked.company_id!=co.pk:raise ValidationError('Selecione cadastros da mesma empresa.')
        return data

class CompanyForm(ScopedForm):
    class Meta:
        model=Company;fields=['code','name','legal_name','cnpj','address','phone','email','fiscal_system']
        labels={'code':'Código','name':'Nome da empresa','legal_name':'Razão social','cnpj':'CNPJ (somente confirmado)','address':'Endereço da emissora','phone':'Telefone da emissora','email':'E-mail da emissora','fiscal_system':'Sistema fiscal atual (Imagem, Multicomp ou outro)'}

class ClientForm(ScopedForm):
    class Meta:
        model=Client;fields=['company','name','legal_name','tax_id','email','phone','address','notes']
        labels={'company':'Empresa','name':'Nome do cliente','legal_name':'Razão social','tax_id':'CPF / CNPJ confirmado (somente números)','email':'E-mail para fechamento','phone':'Telefone / WhatsApp','address':'Endereço','notes':'Observações'}

class ProductForm(ScopedForm):
    amount=forms.DecimalField(label='Valor de venda padrão (R$)', required=False, min_value=0, max_digits=15, decimal_places=4)
    valid_from=forms.DateField(label='Preço válido a partir de', required=False, initial=timezone.localdate, widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    def clean(self):
        data=super().clean()
        if data.get('amount') is not None and not data.get('valid_from'):
            self.add_error('valid_from','Informe a data de vigência do preço.')
        return data
    class Meta:
        model=Product;fields=['company','name','unit','production_cost']
        labels={'company':'Empresa','name':'Nome do produto','unit':'Unidade (UN, KG...)','production_cost':'Custo de produção por unidade (R$)'}

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
        model=Order;fields=['shift','baker','separator','driver','notes']
        labels={'shift':'Turno','baker':'Padeiro responsável','separator':'Responsável pela separação','driver':'Motorista','notes':'Observações'}

class MonthForm(forms.Form):
    company=forms.ModelChoiceField(queryset=Company.objects.none(),label='Empresa')
    client=forms.ModelChoiceField(queryset=Client.objects.none(),label='Cliente')
    month=forms.DateField(label='Mês (selecione dia 1)',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
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
    valid_from = forms.DateField(label='Válido a partir de', widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
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
    date=forms.DateField(label='Data do recebimento', widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    reference=forms.UUIDField(widget=forms.HiddenInput)

class StockItemForm(ScopedForm):
    class Meta:
        model=StockItem; fields=['company','name','unit','minimum']
        labels={'company':'Empresa','name':'Insumo ou produto','unit':'Unidade','minimum':'Estoque mínimo'}

class StockMovementForm(forms.Form):
    item=forms.ModelChoiceField(queryset=StockItem.objects.none(), label='Item de estoque')
    quantity=forms.DecimalField(label='Quantidade (+ entrada / − saída)', max_digits=15, decimal_places=3)
    date=forms.DateField(label='Data', widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    reason=forms.CharField(label='Motivo', max_length=250)
    key=forms.UUIDField(widget=forms.HiddenInput)
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['item'].queryset=StockItem.objects.filter(company__in=companies(user))

class WorkbookForm(forms.Form):
    company=forms.ModelChoiceField(queryset=Company.objects.none(), label='Empresa dos clientes')
    file=forms.FileField(label='Planilha de rotinas (.xlsm ou .xlsx)')
    start=forms.DateField(label='Iniciar rotinas a partir de', widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    confirm=forms.BooleanField(label='Cadastrar clientes, produtos e rotinas estáveis. Não importar pedidos nem valores antigos.')
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['company'].queryset=companies(user)
    def clean_file(self):
        file=self.cleaned_data['file']
        if not file.name.lower().endswith(('.xlsm','.xlsx')) or file.size>12*1024*1024:
            raise ValidationError('Selecione uma planilha XLSM/XLSX de até 12 MB.')
        return file

class ProductionRecordForm(ScopedForm):
    class Meta:
        model=ProductionRecord
        fields=['company','product','date','shift','batch','quantity','losses','baker','notes']
        labels={'company':'Empresa','product':'Produto','date':'Data da produção','shift':'Turno','batch':'Identificação do lote','quantity':'Quantidade total produzida','losses':'Quantidade perdida (parte do total)','baker':'Padeiro responsável','notes':'Observações / motivo das perdas'}
    def clean(self):
        data=super().clean()
        if data.get('date') and data['date']>timezone.localdate():self.add_error('date','Registre somente a produção já realizada.')
        if data.get('quantity') is not None and data['quantity']<=0:self.add_error('quantity','Informe uma quantidade positiva.')
        if data.get('losses') and not data.get('notes'):self.add_error('notes','Descreva as perdas para conferência.')
        return data

class DriverForm(ScopedForm):
    class Meta:
        model=Driver;fields=['company','name','phone','vehicle','active']
        labels={'company':'Empresa','name':'Nome do motorista','phone':'Telefone','vehicle':'Veículo / placa','active':'Ativo'}

class DeliveryRouteForm(ScopedForm):
    class Meta:
        model=DeliveryRoute;fields=['company','name','driver','notes','active']
        labels={'company':'Empresa','name':'Nome da rota','driver':'Motorista responsável','notes':'Instruções da rota','active':'Ativa'}
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,user=user,**kwargs)
        self.fields['driver'].queryset=Driver.objects.filter(company__in=companies(user),active=True)
    def clean(self):
        data=super().clean()
        if data.get('driver') and data.get('company') and data['driver'].company_id!=data['company'].pk:
            self.add_error('driver','Selecione um motorista da mesma empresa.')
        return data

class RouteStopForm(forms.ModelForm):
    sequence=forms.IntegerField(label='Ordem da parada (1, 2, 3...)',min_value=1)
    class Meta:
        model=RouteStop;fields=['client','sequence','instructions']
        labels={'client':'Cliente','sequence':'Ordem da parada (1, 2, 3...)','instructions':'Instruções de entrega'}
    def __init__(self,*args,route,**kwargs):
        super().__init__(*args,**kwargs)
        self.instance.route=route
        self.fields['client'].queryset=Client.objects.filter(company=route.company,active=True)

class ManifestForm(forms.Form):
    route=forms.ModelChoiceField(queryset=DeliveryRoute.objects.none(),label='Rota')
    date=forms.DateField(label='Dia das entregas',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['route'].queryset=DeliveryRoute.objects.filter(company__in=companies(user),active=True,driver__active=True)

class ManifestLineForm(forms.ModelForm):
    class Meta:
        model=ManifestLine;fields=['delivery_status','payment_method','reported_amount','receivable','evidence']
        labels={'delivery_status':'Situação da entrega','payment_method':'Forma de pagamento informada','reported_amount':'Valor em dinheiro informado pelo motorista (R$)','receivable':'Conta a receber vinculada (opcional)','evidence':'Observação / comprovante da entrega e pagamento'}
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['receivable'].queryset=Receivable.objects.filter(company=self.instance.manifest.company,client=self.instance.order.client,voided=False)
        self.fields['receivable'].help_text='Somente pedidos reais podem baixar contas. Pedidos de homologação apenas simulam o malote.'

class CashBagForm(forms.Form):
    reference=forms.CharField(label='Número / identificação do malote',max_length=100)
    counted=forms.DecimalField(label='Dinheiro contado pela empresa (R$)',min_value=0,max_digits=15,decimal_places=2)
    notes=forms.CharField(label='Observação da conferência (obrigatória se houver diferença)',required=False,widget=forms.Textarea)

class StatementForm(forms.Form):
    company=forms.ModelChoiceField(queryset=Company.objects.none(),label='Empresa fornecedora')
    client=forms.ModelChoiceField(queryset=Client.objects.none(),label='Cliente')
    start=forms.DateField(label='Início do período',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    end=forms.DateField(label='Fim do período',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['company'].queryset=companies(user)
        self.fields['client'].queryset=Client.objects.filter(company__in=companies(user))
    def clean(self):
        data=super().clean()
        if data.get('company') and data.get('client') and data['client'].company_id!=data['company'].pk:raise ValidationError('Selecione cliente e empresa compatíveis.')
        if data.get('start') and data.get('end'):
            if data['end']<data['start']:raise ValidationError('O fim do período deve ser igual ou posterior ao início.')
            if data['end']>timezone.localdate():raise ValidationError('Fechamentos só podem incluir períodos já realizados.')
        return data

class ShiftResponsiblesForm(forms.Form):
    night=forms.CharField(label='Padeiro noturno',max_length=100,required=False)
    daytime=forms.CharField(label='Padeiro diurno',max_length=100,required=False)
    separator=forms.CharField(label='Responsável pela separação',max_length=100,required=False)

class SupplierForm(ScopedForm):
    class Meta:
        model=Supplier
        fields=['company','name','trade_name','tax_id','email','phone','address','notes','active']
        labels={'company':'Empresa compradora','name':'Razão social / nome do fornecedor','trade_name':'Nome fantasia','tax_id':'CPF / CNPJ (somente números)','email':'E-mail','phone':'Telefone','address':'Endereço','notes':'Observações','active':'Ativo'}
    def clean_tax_id(self):
        import re
        tax_id=self.cleaned_data.get('tax_id','').strip()
        if tax_id and not re.fullmatch(r'(?:\d{11}|\d{14})',tax_id):raise ValidationError('Informe 11 dígitos de CPF ou 14 de CNPJ, ou deixe pendente.')
        return tax_id

class PayableForm(ScopedForm):
    class Meta:
        model=Payable
        fields=['company','supplier','reference','issued_on','due_on','amount','notes','synthetic']
        labels={'company':'Empresa','supplier':'Fornecedor','reference':'Número / referência única','issued_on':'Emissão','due_on':'Vencimento','amount':'Valor a pagar (R$)','notes':'Observações','synthetic':'Conta de teste (fora dos totais reais)'}
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,user=user,**kwargs)
        self.fields['supplier'].queryset=Supplier.objects.filter(company__in=companies(user),active=True)
    def clean(self):
        data=super().clean()
        if data.get('issued_on') and data['issued_on']>timezone.localdate():self.add_error('issued_on','A data de emissão está no futuro.')
        return data

class InvoiceUploadForm(forms.Form):
    company=forms.ModelChoiceField(queryset=Company.objects.none(),label='Empresa destinatária da nota')
    file=forms.FileField(label='XML completo da NF-e (até 5 MB)')
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['company'].queryset=companies(user)
    def clean_file(self):
        file=self.cleaned_data['file']
        if not file.name.lower().endswith('.xml') or file.size>5*1024*1024:raise ValidationError('Selecione um arquivo XML de até 5 MB.')
        return file

class InvoiceInstallmentForm(forms.Form):
    reference=forms.CharField(label='Parcela / referência',max_length=60)
    due_on=forms.DateField(label='Vencimento',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    amount=forms.DecimalField(label='Valor da parcela (R$)',min_value=Decimal('.01'),max_digits=15,decimal_places=2)

class DisbursementForm(forms.Form):
    amount=forms.DecimalField(label='Valor pago (R$)',min_value=Decimal('.01'),max_digits=15,decimal_places=2)
    date=forms.DateField(label='Data do pagamento',widget=forms.DateInput(format='%Y-%m-%d',attrs={'type':'date'}))
    method=forms.ChoiceField(label='Forma de pagamento',choices=Disbursement._meta.get_field('method').choices)
    evidence=forms.CharField(label='Referência do comprovante / observação',min_length=3,widget=forms.Textarea)
    reference=forms.UUIDField(widget=forms.HiddenInput)

class PayableFilterForm(forms.Form):
    company=forms.ModelChoiceField(queryset=Company.objects.none(),required=False,label='Empresa')
    status=forms.ChoiceField(label='Situação',required=False,choices=[('','Todas'),('open','Em aberto'),('overdue','Vencidas'),('paid','Quitadas')])
    q=forms.CharField(label='Fornecedor ou referência',required=False,max_length=200)
    def __init__(self,*args,user,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['company'].queryset=companies(user)
