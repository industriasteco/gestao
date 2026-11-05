"""Preparação inicial e ativação do controle gerencial, sem emissão fiscal."""
from django.core.exceptions import PermissionDenied,ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Company,Client,Product,Recurrence,Order
from .services import companies,prices_on
from .receipt_layout import brand_code
from .workflow import event


def production_companies(user):
    scope=companies(user)
    return scope.filter(operational_enabled=True) if scope.filter(operational_enabled=True).exists() else scope


def production_orders(user):
    scope=production_companies(user)
    rows=Order.objects.filter(company__in=scope)
    return rows.filter(synthetic=False) if scope.filter(operational_enabled=True).exists() else rows


def company_checks(company):
    return [
        ('Empresa ativa',company.active,'/cadastros/empresas/'),
        ('Marca TECO ou NONA configurada',brand_code(company.code) in ('TECO','NONA'),f'/empresas/{company.pk}/'),
        ('CNPJ da empresa informado',bool(company.cnpj and len(company.cnpj)==14 and company.cnpj.isdigit()),f'/empresas/{company.pk}/'),
        ('Razão social informada',bool(company.legal_name.strip()),f'/empresas/{company.pk}/'),
        ('Endereço e telefone da empresa informados',bool(company.address.strip() and company.phone.strip()),f'/empresas/{company.pk}/'),
        ('Ao menos um cliente ativo',Client.objects.filter(company=company,active=True).exists(),'/cadastros/clientes/'),
        ('Ao menos um produto ativo',Product.objects.filter(company=company,active=True).exists(),'/cadastros/produtos/'),
        ('Preço de venda cadastrado para começar',prices_on(timezone.localdate()).filter(company=company,product__active=True).exists(),'/cadastros/precos/'),
    ]


def require_operational(company):
    if not company.operational_enabled:raise ValidationError('Ative a operação desta empresa em Começar operação antes de emitir documentos reais.')
    required=company_checks(company)[:5]
    pending=[label for label,ok,_ in required if not ok]
    if pending:raise ValidationError('Complete o cadastro da empresa: '+', '.join(pending)+'.')


@transaction.atomic
def activate_operation(user,company):
    if not user.is_superuser:raise PermissionDenied
    company=Company.objects.select_for_update().get(pk=company.pk)
    pending=[label for label,ok,_ in company_checks(company) if not ok]
    if pending:raise ValidationError('Complete antes de ativar: '+', '.join(pending)+'.')
    if company.operational_enabled:return company
    company.operational_enabled=True;company.save(update_fields=['operational_enabled'])
    event(user,company,'ATIVAR_OPERACAO_GERENCIAL',after={'operational_enabled':True,'fiscal_issuing':False},reason='Cadastros conferidos pelo administrador para pedidos, produção e comprovantes não fiscais.')
    return company


@transaction.atomic
def reset_routines(user,company=None):
    if not user.is_superuser:raise PermissionDenied
    scope=companies(user)
    if company:scope=scope.filter(pk=company.pk)
    count=0
    for selected in scope.select_for_update().order_by('pk'):
        rules=list(Recurrence.objects.select_for_update().filter(company=selected,archived=False))
        for rule in rules:
            event(user,rule,'RETIRAR_ROTINA_INICIAL',before={'active':rule.active,'auto_prepare':rule.auto_prepare,'weekdays':rule.weekdays},after={'archived':True,'active':False,'auto_prepare':False},reason='Recomeçar programação por solicitação do administrador; pedidos existentes preservados.')
        count+=len(rules)
        Recurrence.objects.filter(pk__in=[rule.pk for rule in rules]).update(archived=True,active=False,auto_prepare=False)
        Client.objects.filter(company=selected).exclude(recurring_weekdays=[]).update(recurring_weekdays=[])
        selected.routines_reset_at=timezone.now();selected.save(update_fields=['routines_reset_at'])
        event(user,selected,'REINICIAR_PROGRAMACAO',after={'routines_retired':len(rules),'orders_deleted':0})
    return count
