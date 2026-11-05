import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q, F
from django.core.validators import RegexValidator

class Entity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class Meta:
        abstract = True

class Company(Entity):
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=150)
    legal_name = models.CharField(max_length=200, blank=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    fiscal_system = models.CharField(max_length=100, blank=True)
    cnpj = models.CharField(max_length=14, null=True, blank=True, unique=True, validators=[RegexValidator(r'^\d{14}$')])
    active = models.BooleanField(default=True)
    def __str__(self): return self.name

class Membership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['user','company'],name='unique_membership')]

class Client(Entity):
    name = models.CharField(max_length=200)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    legal_name = models.CharField(max_length=200, blank=True)
    tax_id = models.CharField(max_length=14, blank=True, validators=[RegexValidator(r'^(?:\d{11}|\d{14})$', 'Informe CPF com 11 ou CNPJ com 14 dígitos, ou deixe pendente.')])
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    requires_purchase_order = models.BooleanField(default=False)
    def __str__(self): return self.name

class Product(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    unit = models.CharField(max_length=20, default='UN')
    active = models.BooleanField(default=True)
    production_cost = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(production_cost__isnull=True)|Q(production_cost__gte=0), name='product_cost_positive')]
    def __str__(self): return self.name

class Price(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=15, decimal_places=4)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gte=0),name='positive_price'),models.CheckConstraint(condition=Q(valid_until__isnull=True)|Q(valid_until__gte=F('valid_from')),name='price_dates')]

class Recurrence(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    slot = models.CharField(max_length=60)
    time = models.TimeField()
    shift = models.CharField(max_length=10,choices=[('NOTURNO','Noturno'),('DIURNO','Diurno')])
    weekdays = models.JSONField(default=list)
    valid_from = models.DateField()
    valid_until = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    source_key = models.CharField(max_length=250, null=True, blank=True, unique=True)
    class Meta:
        permissions = [('activate_recurrence','Ativar recorrência'),('prepare_day','Preparar dia'),('review_staging','Revisar staging')]
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=0),name='recurrence_quantity')]

class Order(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    recurrence = models.ForeignKey(Recurrence, on_delete=models.PROTECT, null=True, blank=True)
    date = models.DateField(db_index=True)
    slot = models.CharField(max_length=60)
    time = models.TimeField()
    shift = models.CharField(max_length=10,blank=True,choices=[('NOTURNO','Noturno'),('DIURNO','Diurno')])
    status = models.CharField(max_length=20,default='PRE_LANCADO',choices=[('PRE_LANCADO','Pré-lançado'),('CONFERIDO','Conferido'),('CANCELADO','Cancelado'),('EMITIDO','Documento emitido'),('ENTREGUE','Entrega confirmada'),('LIBERADO_FECHAMENTO','Liberado para fechamento'),('FECHADO','Fechado')])
    idempotency_key = models.CharField(max_length=250,unique=True)
    preparation_rules = models.JSONField(default=list, blank=True)
    synthetic = models.BooleanField(default=True)
    baker = models.CharField(max_length=100, blank=True)
    driver = models.CharField(max_length=100, blank=True)
    separator = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    issued_snapshot = models.JSONField(default=dict, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_evidence = models.TextField(blank=True)
    commercial_number = models.CharField(max_length=40, blank=True)
    purchase_order = models.CharField(max_length=50, blank=True)
    class Meta:
        permissions = [('check_production','Conferir produção'),('issue_document','Emitir documento de teste'),('confirm_delivery','Confirmar entrega de teste'),('close_month','Aprovar fechamento de teste'),('cancel_issued','Cancelar pedido emitido')]
        indexes = [models.Index(fields=['company','date','status'])]

class OrderItem(Entity):
    order = models.ForeignKey(Order,on_delete=models.PROTECT,related_name='items')
    product = models.ForeignKey(Product,on_delete=models.PROTECT)
    product_name = models.CharField(max_length=200)
    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=15,decimal_places=3)
    unit_price_snapshot = models.DecimalField(max_digits=15,decimal_places=4,null=True,blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(quantity__gte=0),name='item_quantity')]

class ImportBatch(Entity):
    filename = models.CharField(max_length=200)
    sha256 = models.CharField(max_length=64,unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Candidate(Entity):
    batch = models.ForeignKey(ImportBatch,on_delete=models.PROTECT,related_name='rows')
    row_number = models.PositiveIntegerField()
    raw = models.JSONField()
    category = models.CharField(max_length=40)
    approved = models.BooleanField(default=False)
    active = models.BooleanField(default=False)
    billable = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True)
    reason = models.TextField(blank=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(billable=False),name='legacy_never_billable'),models.CheckConstraint(condition=Q(active=False),name='candidate_never_active'),models.UniqueConstraint(fields=['batch','row_number'],name='unique_source_row')]

class Audit(Entity):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT,null=True)
    entity = models.CharField(max_length=100)
    action = models.CharField(max_length=100)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reason = models.TextField(blank=True)
    at = models.DateTimeField(auto_now_add=True)

class RuleItem(Entity):
    rule = models.ForeignKey(Recurrence,on_delete=models.PROTECT,related_name='extra_items')
    product = models.ForeignKey(Product,on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=15,decimal_places=3)
    class Meta:
        constraints=[models.CheckConstraint(condition=Q(quantity__gte=0),name='rule_extra_qty'),models.UniqueConstraint(fields=['rule','product'],name='unique_rule_extra')]

class RuleException(Entity):
    rule = models.ForeignKey(Recurrence,on_delete=models.PROTECT)
    date = models.DateField()
    suspended = models.BooleanField(default=True)
    quantity = models.DecimalField(max_digits=15,decimal_places=3,null=True,blank=True)
    reason = models.TextField()
    class Meta:
        constraints=[models.UniqueConstraint(fields=['rule','date'],name='rule_exception_date')]

class Document(Entity):
    company = models.ForeignKey(Company,on_delete=models.PROTECT)
    order = models.ForeignKey(Order,on_delete=models.PROTECT,null=True,blank=True)
    key = models.CharField(max_length=220,unique=True)
    kind = models.CharField(max_length=30)
    data = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    layout = models.CharField(max_length=30,default='v1-homologacao')
    company_scope = models.JSONField(default=list, blank=True)
    superseded = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

class Closure(Entity):
    company = models.ForeignKey(Company,on_delete=models.PROTECT)
    client = models.ForeignKey(Client,on_delete=models.PROTECT)
    month = models.DateField()
    total = models.DecimalField(max_digits=16,decimal_places=2)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    document = models.ForeignKey(Document,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints=[models.UniqueConstraint(fields=['company','client','month'],name='unique_closure')]

class ClosureLine(Entity):
    closure = models.ForeignKey(Closure,on_delete=models.PROTECT,related_name='lines')
    order = models.OneToOneField(Order,on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=16,decimal_places=2)

class Reconciliation(Entity):
    candidate = models.OneToOneField(Candidate,on_delete=models.PROTECT)
    original_number = models.CharField(max_length=120,unique=True)
    evidence = models.TextField()
    reason = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


class Receivable(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    reference = models.CharField(max_length=120)
    issued_on = models.DateField()
    due_on = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    notes = models.TextField(blank=True)
    voided = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name='receivable_positive'),
            models.CheckConstraint(condition=Q(due_on__gte=F('issued_on')), name='receivable_dates'),
            models.UniqueConstraint(fields=['company', 'reference'], name='receivable_reference'),
        ]


class Payment(Entity):
    receivable = models.ForeignKey(Receivable, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateField()
    reference = models.CharField(max_length=120)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name='payment_positive'),
            models.UniqueConstraint(fields=['receivable', 'reference'], name='payment_reference'),
        ]


class StockItem(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    unit = models.CharField(max_length=20, default='KG')
    minimum = models.DecimalField(max_digits=15, decimal_places=3, default=0)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company', 'name'], name='stock_name'),
                       models.CheckConstraint(condition=Q(minimum__gte=0), name='stock_minimum')]


class StockMovement(Entity):
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='movements')
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    date = models.DateField()
    reason = models.CharField(max_length=250)
    key = models.UUIDField(unique=True, default=uuid.uuid4)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(quantity=0), name='stock_nonzero')]


class ProductionRecord(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    product = models.ForeignKey(Product, on_delete=models.PROTECT)
    date = models.DateField(db_index=True)
    shift = models.CharField(max_length=10, choices=[('NOTURNO','Noturno'),('DIURNO','Diurno')])
    batch = models.CharField(max_length=80)
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    losses = models.DecimalField(max_digits=15, decimal_places=3, default=0)
    unit = models.CharField(max_length=20)
    cost_snapshot = models.DecimalField(max_digits=15, decimal_places=4, null=True, blank=True)
    baker = models.CharField(max_length=100)
    notes = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='produced_positive'),
            models.CheckConstraint(condition=Q(losses__gte=0)&Q(losses__lte=F('quantity')), name='production_losses'),
            models.UniqueConstraint(fields=['company','product','date','shift','batch'], name='production_batch'),
        ]


class Driver(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=40, blank=True)
    vehicle = models.CharField(max_length=100, blank=True)
    active = models.BooleanField(default=True)
    def __str__(self):return self.name


class DeliveryRoute(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    def __str__(self):return self.name


class RouteStop(Entity):
    route = models.ForeignKey(DeliveryRoute, on_delete=models.PROTECT, related_name='stops')
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    sequence = models.PositiveIntegerField()
    instructions = models.TextField(blank=True)
    class Meta:
        ordering=['sequence']
        constraints = [models.UniqueConstraint(fields=['route','sequence'],name='route_sequence'),
                       models.UniqueConstraint(fields=['route','client'],name='route_client')]


class DeliveryManifest(Entity):
    route = models.ForeignKey(DeliveryRoute, on_delete=models.PROTECT)
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    date = models.DateField()
    driver_name = models.CharField(max_length=150)
    vehicle = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['route','date'],name='manifest_route_date')]


class ManifestLine(Entity):
    manifest = models.ForeignKey(DeliveryManifest, on_delete=models.PROTECT, related_name='lines')
    order = models.OneToOneField(Order, on_delete=models.PROTECT)
    sequence = models.PositiveIntegerField()
    client_name = models.CharField(max_length=200)
    address = models.TextField(blank=True)
    instructions = models.TextField(blank=True)
    items_snapshot = models.JSONField(default=list)
    amount_due = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    receivable = models.ForeignKey(Receivable, on_delete=models.PROTECT, null=True, blank=True)
    reported_amount = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    payment_reported = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=15, default='PRAZO', choices=[('PRAZO','Não pagou / a prazo'),('DINHEIRO','Dinheiro no malote'),('PIX','PIX informado'),('CARTAO','Cartão informado')])
    delivery_status = models.CharField(max_length=15, default='PENDENTE', choices=[('PENDENTE','Pendente'),('ENTREGUE','Entregue'),('NAO_ENTREGUE','Não entregue')])
    evidence = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering=['sequence','id']
        constraints = [models.CheckConstraint(condition=Q(reported_amount__gte=0),name='manifest_reported_positive')]


class CashBag(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    manifest = models.OneToOneField(DeliveryManifest, on_delete=models.PROTECT, related_name='cash_bag')
    reference = models.CharField(max_length=100)
    declared = models.DecimalField(max_digits=15, decimal_places=2)
    counted = models.DecimalField(max_digits=15, decimal_places=2)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=[('CONFERIDO','Conferido'),('DIVERGENTE','Divergente')])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    checked_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(declared__gte=0)&Q(counted__gte=0),name='cashbag_positive'),
                       models.UniqueConstraint(fields=['company','reference'],name='cashbag_reference')]


class ClientStatement(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    start = models.DateField()
    end = models.DateField()
    total = models.DecimalField(max_digits=16, decimal_places=2)
    purchase_order = models.CharField(max_length=50, blank=True)
    snapshot = models.JSONField(default=dict)
    document = models.OneToOneField(Document, on_delete=models.PROTECT)
    status = models.CharField(max_length=15, default='RASCUNHO', choices=[('RASCUNHO','Pronto para enviar'),('ENVIADO','Enviado / aguardando cliente'),('APROVADO','Aprovado pelo cliente'),('REJEITADO','Cliente pediu revisão'),('CANCELADO','Cancelado')])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    sent_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_evidence = models.TextField(blank=True)
    communication = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(end__gte=F('start')),name='statement_period'),
                       models.CheckConstraint(condition=Q(total__gte=0),name='statement_total_positive')]


class StatementLine(Entity):
    statement = models.ForeignKey(ClientStatement, on_delete=models.PROTECT, related_name='lines')
    order = models.ForeignKey(Order, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    active = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['order'],condition=Q(active=True),name='one_active_statement_per_order')]


class Supplier(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, blank=True)
    tax_id = models.CharField(max_length=14, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    active = models.BooleanField(default=True)
    def __str__(self): return self.name
    class Meta:
        constraints = [models.UniqueConstraint(fields=['company','tax_id'], condition=~Q(tax_id=''), name='supplier_tax_id')]


class PurchaseInvoice(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    access_key = models.CharField(max_length=44, unique=True)
    number = models.CharField(max_length=9)
    series = models.CharField(max_length=3)
    model = models.CharField(max_length=2)
    issued_on = models.DateField()
    total = models.DecimalField(max_digits=16, decimal_places=2)
    financial_total = models.DecimalField(max_digits=16, decimal_places=2)
    environment = models.CharField(max_length=1, choices=[('1','Produção'),('2','Homologação / teste')])
    status = models.CharField(max_length=20, default='EM_REVISAO', choices=[('EM_REVISAO','Conferir parcelas'),('FINANCEIRO_GERADO','Contas a pagar geradas'),('ARQUIVADA','Arquivada sem financeiro')])
    installments = models.JSONField(default=list, blank=True)
    summary = models.JSONField(default=dict)
    xml = models.BinaryField()
    sha256 = models.CharField(max_length=64)
    payload_hash = models.CharField(max_length=64)
    filename = models.CharField(max_length=200)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(total__gte=0)&Q(financial_total__gte=0)&Q(financial_total__lte=F('total')), name='purchase_invoice_totals')]


class Payable(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    invoice = models.ForeignKey(PurchaseInvoice, on_delete=models.PROTECT, null=True, blank=True, related_name='payables')
    reference = models.CharField(max_length=120)
    installment = models.CharField(max_length=60, blank=True)
    issued_on = models.DateField()
    due_on = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    notes = models.TextField(blank=True)
    voided = models.BooleanField(default=False)
    synthetic = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0),name='payable_positive'),
                       models.CheckConstraint(condition=Q(due_on__gte=F('issued_on')),name='payable_dates'),
                       models.UniqueConstraint(fields=['company','reference'],name='payable_reference')]


class Disbursement(Entity):
    payable = models.ForeignKey(Payable, on_delete=models.PROTECT, related_name='payments')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    date = models.DateField()
    method = models.CharField(max_length=15, choices=[('PIX','PIX'),('BOLETO','Boleto'),('TRANSFERENCIA','Transferência'),('DINHEIRO','Dinheiro'),('CARTAO','Cartão'),('OUTRO','Outro')])
    reference = models.CharField(max_length=120)
    evidence = models.TextField()
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0),name='disbursement_positive'),
                       models.UniqueConstraint(fields=['payable','reference'],name='disbursement_reference')]


class ProposalProfile(Entity):
    company = models.OneToOneField(Company, on_delete=models.PROTECT, related_name='proposal_profile')
    display_name = models.CharField(max_length=200, blank=True)
    subtitle = models.CharField(max_length=100, blank=True)
    legal_name = models.CharField(max_length=200, blank=True)
    tax_id = models.CharField(max_length=14, blank=True, validators=[RegexValidator(r'^\d{14}$', 'Informe o CNPJ com 14 dígitos ou deixe pendente.')])
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    responsible = models.CharField(max_length=200, blank=True)
    source_filename = models.CharField(max_length=200, blank=True)
    source_sha256 = models.CharField(max_length=64, blank=True)


class CommercialProposal(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, null=True, blank=True)
    number = models.CharField(max_length=50, unique=True)
    title = models.CharField(max_length=200)
    summary = models.TextField(blank=True, max_length=2000)
    issued_on = models.DateField()
    valid_days = models.PositiveSmallIntegerField(default=60)
    customer_name = models.CharField(max_length=200)
    customer_tax_id = models.CharField(max_length=14, blank=True, validators=[RegexValidator(r'^(?:\d{11}|\d{14})$', 'Informe CPF/CNPJ somente com números.')])
    customer_address = models.TextField(blank=True, max_length=1500)
    included_items = models.TextField(blank=True, max_length=6000)
    conditions = models.TextField(blank=True, max_length=3000)
    notes = models.TextField(blank=True, max_length=3000)
    responsible = models.CharField(max_length=200)
    total = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    status = models.CharField(max_length=15, default='RASCUNHO', choices=[('RASCUNHO','Rascunho'),('GERADA','PDF gerado'),('ENVIADA','Enviada ao cliente'),('APROVADA','Aprovada pelo cliente'),('RECUSADA','Recusada pelo cliente'),('CANCELADA','Cancelada')])
    document = models.OneToOneField(Document, on_delete=models.PROTECT, null=True, blank=True)
    snapshot = models.JSONField(default=dict, blank=True)
    previous = models.ForeignKey('self', on_delete=models.PROTECT, null=True, blank=True, related_name='revisions')
    evidence = models.TextField(blank=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        constraints = [models.CheckConstraint(condition=Q(valid_days__gte=1)&Q(valid_days__lte=3650),name='proposal_validity'),
                       models.CheckConstraint(condition=Q(total__gte=0),name='proposal_positive_total')]


class ProposalItem(Entity):
    proposal = models.ForeignKey(CommercialProposal, on_delete=models.CASCADE, related_name='items')
    sequence = models.PositiveIntegerField()
    product = models.ForeignKey(Product, on_delete=models.PROTECT, null=True, blank=True)
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    unit = models.CharField(max_length=20, default='UN')
    unit_price = models.DecimalField(max_digits=15, decimal_places=4)
    class Meta:
        ordering=['sequence']
        constraints = [models.CheckConstraint(condition=Q(quantity__gt=0)&Q(unit_price__gte=0),name='proposal_item_values'),
                       models.UniqueConstraint(fields=['proposal','sequence'],name='proposal_item_sequence')]
