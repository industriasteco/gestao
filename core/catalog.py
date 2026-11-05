"""Catálogo comum de TECO/NONA, com preços e documentos por empresa."""
from django.db.models import Q,F
from .models import Company,Product,Price
from .receipt_layout import brand_code

BRANDS={'TECO','NONA'}


def shared_brand(company):
    return brand_code(company.code) in BRANDS


def catalog_company_ids(scope):
    rows=list(Company.objects.values_list('pk','code'))
    allowed=set(scope.values_list('pk',flat=True))
    shared={pk for pk,code in rows if brand_code(code) in BRANDS}
    return allowed|shared if allowed&shared else allowed


def available_products(company):
    scope=Company.objects.filter(pk=company.pk)
    return Product.objects.filter(company_id__in=catalog_company_ids(scope)).select_related('company')


def products_for_user(user):
    from .services import companies
    return Product.objects.filter(company_id__in=catalog_company_ids(companies(user))).select_related('company')


def product_available(product,company):
    return product.company_id==company.pk or (shared_brand(company) and shared_brand(product.company))


def product_catalog_label(product):
    return 'TECO e NONA' if shared_brand(product.company) else product.company.name


def visible_prices(user):
    from .services import companies
    return Price.objects.filter(Q(company__in=companies(user))|Q(product__in=products_for_user(user),company_id=F('product__company_id'),client__isnull=True))


def price_scope_label(price):
    if price.client_id:return str(price.client)
    if price.company_id==price.product.company_id and shared_brand(price.company):return 'Padrão do catálogo TECO e NONA'
    return 'Padrão da empresa '+price.company.code
