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
    def __str__(self): return self.name

class Product(Entity):
    company = models.ForeignKey(Company, on_delete=models.PROTECT)
    name = models.CharField(max_length=200)
    unit = models.CharField(max_length=20, default='UN')
    active = models.BooleanField(default=True)
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
    synthetic = models.BooleanField(default=True)
    baker = models.CharField(max_length=100, blank=True)
    driver = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    issued_snapshot = models.JSONField(default=dict, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_evidence = models.TextField(blank=True)
    commercial_number = models.CharField(max_length=40, blank=True)
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
