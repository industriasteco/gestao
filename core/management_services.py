"""Preços, recebimentos e estoque com histórico e isolamento por empresa."""
from datetime import timedelta
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from .models import Company, Product, Price, Receivable, Payment, StockItem, StockMovement
from .services import authorize
from .workflow import event
from .catalog import product_available


@transaction.atomic
def set_price(user, company, product, amount, start, client=None):
    authorize(user, company, 'core.change_price')
    Company.objects.select_for_update().get(pk=company.pk)
    if not product_available(product,company) or (client and client.company_id != company.pk):
        raise ValidationError('Produto e cliente devem pertencer à empresa selecionada.')
    if not amount.is_finite() or amount < 0:
        raise ValidationError('Informe um preço válido.')
    rows = Price.objects.select_for_update().filter(company=company, product=product, client=client, superseded=False)
    if rows.filter(valid_from__gte=start).exists():
        raise ValidationError('Já existe preço nesta data ou em data posterior. Escolha uma nova vigência.')
    current = rows.filter(Q(valid_until__isnull=True) | Q(valid_until__gte=start))
    if current.count() > 1:
        raise ValidationError('Há preços sobrepostos; revise o histórico antes de continuar.')
    for old in current:
        before = str(old.valid_until)
        old.valid_until = start-timedelta(days=1)
        old.save(update_fields=['valid_until'])
        event(user, old, 'ENCERRAR_VIGENCIA', {'valid_until': before}, {'valid_until': str(old.valid_until)})
    price = Price(company=company, product=product, client=client, amount=amount, valid_from=start)
    price.full_clean(); price.save()
    event(user, price, 'DEFINIR_PRECO', after={'amount': str(amount), 'valid_from': str(start), 'client': str(client.pk) if client else ''})
    return price


@transaction.atomic
def set_current_price(user, company, product, amount, client=None):
    """Troca o preço agora; datas e substituições são registradas internamente."""
    authorize(user, company, 'core.change_price')
    Company.objects.select_for_update().get(pk=company.pk)
    if not product_available(product,company) or (client and client.company_id != company.pk):
        raise ValidationError('Produto e cliente devem pertencer à empresa selecionada.')
    if not amount.is_finite() or amount < 0:
        raise ValidationError('Informe um preço válido.')
    today = timezone.localdate()
    price = Price(company=company, product=product, client=client, amount=amount, valid_from=today)
    price.full_clean()
    rows = Price.objects.select_for_update().filter(company=company, product=product, client=client, superseded=False)
    current = list(rows.filter(valid_from__lte=today).filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today)))
    if len(current) == 1 and current[0].amount == amount and current[0].valid_until is None and not rows.filter(valid_from__gt=today).exists():
        return current[0]
    for old in rows.filter(Q(valid_until__isnull=True) | Q(valid_until__gte=today)):
        before = {'amount': str(old.amount), 'valid_from': str(old.valid_from), 'valid_until': str(old.valid_until), 'superseded': old.superseded}
        if old.valid_from < today:
            old.valid_until = today-timedelta(days=1)
            old.save(update_fields=['valid_until'])
        else:
            # Preserva inclusive várias trocas no mesmo dia e cadastros futuros.
            old.superseded = True
            old.save(update_fields=['superseded'])
        event(user, old, 'SUBSTITUIR_PRECO', before, {'valid_until': str(old.valid_until), 'superseded': old.superseded}, reason='Novo preço atual informado, sem prazo de término.')
    price.save()
    event(user, price, 'DEFINIR_PRECO_ATUAL', after={'amount': str(amount), 'valid_from': str(today), 'client': str(client.pk) if client else ''})
    return price


def balances(user, day=None):
    from .services import companies
    day = day or timezone.localdate()
    rows = Receivable.objects.filter(company__in=companies(user), voided=False).select_related('client', 'company').annotate(paid=Sum('payments__amount'))
    result = []
    for row in rows:
        row.balance = row.amount-(row.paid or Decimal(0))
        row.days_late = max((day-row.due_on).days, 0) if row.balance > 0 else 0
        result.append(row)
    return result


@transaction.atomic
def receive(user, receivable, amount, day, reference):
    authorize(user, receivable.company, 'core.change_receivable')
    row = Receivable.objects.select_for_update().get(pk=receivable.pk)
    existing = Payment.objects.filter(receivable=row, reference=reference).first()
    if existing:
        if existing.amount != amount or existing.date != day:
            raise ValidationError('Referência de recebimento já usada com outros dados.')
        return existing
    paid = row.payments.aggregate(total=Sum('amount'))['total'] or Decimal(0)
    if row.voided or not amount.is_finite() or amount <= 0 or amount > row.amount-paid:
        raise ValidationError('Recebimento inválido ou superior ao saldo em aberto.')
    if day < row.issued_on or day > timezone.localdate():
        raise ValidationError('Recebimento deve estar entre a emissão e hoje.')
    payment = Payment(receivable=row, amount=amount, date=day, reference=reference.strip(), actor=user)
    payment.full_clean(); payment.save()
    event(user, row, 'RECEBER', after={'amount': str(amount), 'date': str(day), 'reference': reference})
    return payment


@transaction.atomic
def move_stock(user, item, quantity, day, reason, key):
    authorize(user, item.company, 'core.change_stockitem')
    item = StockItem.objects.select_for_update().get(pk=item.pk)
    existing = StockMovement.objects.filter(key=key).first()
    if existing:
        if existing.item_id != item.pk or existing.quantity != quantity or existing.date != day or existing.reason != reason:
            raise ValidationError('Identificador de movimento já utilizado.')
        return existing
    if not quantity.is_finite() or not quantity or not reason.strip() or day > timezone.localdate():
        raise ValidationError('Informe quantidade, data até hoje e motivo do movimento.')
    balance = item.movements.aggregate(total=Sum('quantity'))['total'] or Decimal(0)
    if balance+quantity < 0:
        raise ValidationError('Saída superior ao saldo disponível.')
    # Impede saldo negativo também na sequência histórica de movimentos retroativos.
    movements = list(item.movements.values_list('date', 'quantity')) + [(day, quantity)]
    running = Decimal(0)
    by_day = {}
    for when, value in movements:
        by_day[when] = by_day.get(when, Decimal(0)) + value
    for when in sorted(by_day):
        running += by_day[when]
        if running < 0:
            raise ValidationError('O movimento deixaria o estoque negativo em uma data posterior.')
    movement = StockMovement(item=item, quantity=quantity, date=day, reason=reason, key=key, actor=user)
    movement.full_clean(); movement.save()
    event(user, item, 'MOVIMENTAR_ESTOQUE', after={'quantity': str(quantity), 'date': str(day), 'reason': reason})
    return movement
