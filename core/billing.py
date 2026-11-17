"""Quantidade de produção separada da quantidade comercial, preservada por pedido."""
from decimal import Decimal, ROUND_HALF_UP
from django.core.exceptions import ValidationError


def conversion(product, billing_unit):
    unit = product.unit.upper()
    billing_unit = billing_unit or product.unit
    if billing_unit == product.unit:
        return {'billing_unit': product.unit, 'billing_factor': Decimal(1)}
    if billing_unit == 'KG' and unit == 'KG':
        return {'billing_unit': 'KG', 'billing_factor': Decimal(1)}
    if billing_unit != 'KG' or unit != 'UN' or not product.unit_weight_g or product.unit_weight_g <= 0:
        raise ValidationError('Para faturar unidades em kg, cadastre o peso por unidade em gramas no produto.')
    return {'billing_unit': 'KG', 'billing_factor': product.unit_weight_g / Decimal(1000)}


def validate_quantity(item):
    quantity=Decimal(item.quantity)
    if item.billed_unit == 'KG' and item.unit.upper() == 'UN' and quantity != quantity.to_integral_value():
        raise ValidationError('Informe a quantidade inteira de pães em unidades; o peso em kg é calculado automaticamente.')
    if not item.billing_factor.is_finite() or item.billing_factor <= 0:
        raise ValidationError('Fator de conversão inválido.')


def configure_item(item, selection=''):
    from .services import price_condition_for
    try:
        price = price_condition_for(item.order.company, item.order.client, item.product, item.order.date)
    except ValidationError:
        # Preço pendente continua permitido no rascunho; emissão exige conferência.
        price = None
    billing_unit = item.product.unit if selection == 'PRODUCT' else selection
    billing_unit = billing_unit or (price.billing_unit if price else '') or item.product.unit
    for key, value in conversion(item.product, billing_unit).items(): setattr(item, key, value)
    validate_quantity(item)
    return item


def item_price(item):
    from .services import price_condition_for
    price = price_condition_for(item.order.company, item.order.client, item.product, item.order.date)
    if (price.billing_unit or item.product.unit) != item.billed_unit:
        raise ValidationError('A unidade do preço difere do faturamento do pedido. Confira a condição negociada antes de emitir.')
    return price.amount


def subtotal(item, price):
    return (item.billed_quantity * price).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


def decimal_text(value):
    return format(value, 'f').rstrip('0').rstrip('.') if '.' in format(value, 'f') else format(value, 'f')


def snapshot(item, price):
    return dict(name=item.product_name, unit=item.billed_unit, quantity=decimal_text(item.billed_quantity),
                ordered_quantity=decimal_text(item.quantity), ordered_unit=item.unit,
                billing_factor=decimal_text(item.billing_factor), price=str(price), total=str(subtotal(item, price)))
