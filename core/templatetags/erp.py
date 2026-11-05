from decimal import Decimal, InvalidOperation
from django import template
register = template.Library()
@register.filter
def brl(value):
    try:
        return 'R$ ' + f'{Decimal(value):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    except (InvalidOperation, TypeError, ValueError):
        return 'Pendente'
@register.filter
def weekday(value):
    return {1:'Segunda',2:'Terça',3:'Quarta',4:'Quinta',5:'Sexta',6:'Sábado',7:'Domingo'}.get(value, value)
