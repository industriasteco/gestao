"""Importação rastreável de notas de outubro; nunca executa VBA."""
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import date, time
from decimal import Decimal, InvalidOperation
from io import BytesIO
from zipfile import ZipFile, BadZipFile
from django.core.exceptions import ValidationError
from django.db import transaction
from openpyxl import load_workbook
from .models import (Company, Client, Product, ImportBatch, Candidate, Recurrence, Audit)


def normalized(value):
    return ' '.join(str(value or '').strip().upper().split())


def canonical(value):
    name = normalized(value)
    aliases = {'P. ÁG/MARG.': 'P. ÁG C/ MARG.', 'P. LEITE/MARG.': 'P. LEITE C/ MARG.'}
    return aliases.get(name, name)


def quantity(value):
    if isinstance(value, bool):
        return None
    try:
        result = Decimal(str(value).strip().replace(',', '.'))
        return result if result.is_finite() and 0 < result < Decimal('1000000000') and result.as_tuple().exponent >= -3 else None
    except (InvalidOperation, ValueError):
        return None


def read_workbook(data):
    if len(data) > 12 * 1024 * 1024:
        raise ValidationError('A planilha deve ter até 12 MB.')
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(f.file_size for f in archive.infolist()) > 90 * 1024 * 1024:
                raise ValidationError('Planilha descompactada muito grande.')
        book = load_workbook(BytesIO(data), data_only=True, read_only=True, keep_links=False)
    except (BadZipFile, KeyError, ValueError, OSError):
        raise ValidationError('Não foi possível ler a planilha XLSX/XLSM.')
    orders, warnings, days = [], [], []
    try:
        for sheet in book:
            match = re.fullmatch(r'(\d{1,2})-outubro-(\d{2})_MD', sheet.title, re.I)
            if not match:
                continue
            try:
                day = date(2000 + int(match[2]), 10, int(match[1]))
            except ValueError:
                raise ValidationError('Data inválida no nome da aba.')
            if sheet.max_row > 5000:
                raise ValidationError('Aba de notas excede 5.000 linhas.')
            days.append(day)
            rows = list(sheet.iter_rows(max_col=11, values_only=True))
            for index, row in enumerate(rows):
                if normalized(row[0]) != 'CLIENTE:':
                    continue
                client = normalized(row[1])
                if not client:
                    warnings.append(f'{sheet.title}:{index+1}: cliente vazio')
                    continue
                header_date = rows[index-1][3] if index else None
                if hasattr(header_date, 'date'):
                    header_date = header_date.date()
                if header_date != day:
                    warnings.append(f'{sheet.title}:{index+1}: data interna divergente; pedido separado para conferência')
                    continue
                items, notes, problems = [], [], []
                # Uma via por bloco. A segunda via, nas colunas G:K, não é somada.
                for offset, line in enumerate(rows[index+2:index+22], index+3):
                    if normalized(line[0]) in ('CLIENTE:', 'PEDIDO Nº') or 'PANIFICADORA' in normalized(line[1]):
                        break
                    description = normalized(line[1])
                    qty = quantity(line[0])
                    if tuple(normalized(v) for v in line[:2]) != tuple(normalized(v) for v in line[6:8]):
                        problems.append({'row': offset, 'quantity': str(line[0] or ''), 'description': description,
                            'reason': f'Vias divergentes: quantidade na segunda via = {line[6]}. Conferir manualmente.'})
                        if description:notes.append(description)
                        continue
                    if qty:
                        if not description or len(description) > 65 or re.match(r'^\d', description):
                            problems.append({'row': offset, 'quantity': str(qty), 'description': description,
                                             'reason': 'Descrição composta ou ausente; revisar item/unidade.'})
                            if description:
                                notes.append(description)
                        else:
                            items.append({'product': canonical(description), 'description': description, 'quantity': str(qty)})
                    elif description and not description.startswith('FINANCEIRO@'):
                        # Linhas zeradas com textos longos são observações, não produtos.
                        if re.match(r'^\d', description) or len(description) > 35 or re.search(r'EMBAL|CORTAD|ENTREG|SAQUIN|SEM |COM |\+', description):
                            notes.append(description)
                orders.append({'date': day.isoformat(), 'client': client, 'sheet': sheet.title,
                               'row': index+1, 'items': items, 'notes': list(dict.fromkeys(notes)), 'problems': problems})
    finally:
        book.close()
    if not days:
        raise ValidationError('Não há abas de outubro no formato 1-outubro-26_MD.')
    return {'orders': orders, 'days': sorted(set(days)), 'warnings': warnings,
            'clients': len({o['client'] for o in orders}),
            'products': len({i['product'] for o in orders for i in o['items']})}


def inferred_patterns(analysis):
    """Moda por cliente/produto/dia, incluindo ausências como zero; sem extrapolar lacunas."""
    observations = defaultdict(dict)
    notes = defaultdict(set)
    for order in analysis['orders']:
        day = date.fromisoformat(order['date'])
        for item in order['items']:
            key = (order['client'], item['product'], day.isoweekday())
            observations[key][day] = observations[key].get(day, Decimal(0)) + Decimal(item['quantity'])
            notes[key].update(order['notes'])
    patterns = []
    for (client, product, weekday), values in sorted(observations.items()):
        available = [d for d in analysis['days'] if d.isoweekday() == weekday]
        counts = Counter(values.get(d, Decimal(0)) for d in available)
        ranked = counts.most_common()
        qty, frequency = ranked[0]
        stable = qty > 0 and frequency >= 2 and frequency / len(available) >= .6 and (len(ranked) == 1 or ranked[1][1] < frequency)
        positive = [v for v in values.values() if v > 0]
        patterns.append({'minimum': str(min(positive)), 'maximum': str(max(positive)),
                         'presence': len(values), 'client': client, 'product': product, 'weekday': weekday, 'quantity': str(qty),
                         'matches': frequency, 'samples': len(available), 'stable': stable,
                         'reason': 'Padrão estável.' if stable else ('Ausência é mais frequente nas datas disponíveis; compra ocasional.' if qty==0 else 'Quantidade varia ou evidência insuficiente; conferir com o cliente.'),
                         'notes': '\n'.join(sorted(notes[(client, product, weekday)]))})
    return patterns


@transaction.atomic
def import_workbook(user, company, data, filename, start):
    from .services import authorize
    authorize(user, company, 'core.review_staging')
    if not user.is_superuser:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    Company.objects.select_for_update().get(pk=company.pk)
    analysis = read_workbook(data)
    if start <= max(analysis['days']):
        raise ValidationError('O início da rotina deve ser posterior ao histórico importado.')
    digest = hashlib.sha256(data).hexdigest()
    batch, created = ImportBatch.objects.get_or_create(sha256=digest, defaults={'filename': filename[:200]})
    if not created:
        if Audit.objects.filter(entity=str(batch.pk), action='IMPORTAR_ROTINAS').exclude(after__company=str(company.pk)).exists():
            raise ValidationError('Esta planilha já foi importada para outra empresa.')
        return batch, False, analysis
    clients, products = {}, {}
    for entry in analysis['orders']:
        client_name = entry['client']
        matches = Client.objects.filter(company=company, name__iexact=client_name)
        if matches.count() > 1:
            raise ValidationError(f'Cadastro duplicado de cliente: {client_name}. Corrija antes de importar.')
        client = matches.first() or Client.objects.create(company=company, name=client_name)
        clients[client_name] = client
        for item in entry['items']:
            name = item['product']
            if name not in products:
                matches = Product.objects.filter(company=company, name__iexact=name)
                if matches.count() > 1:
                    raise ValidationError(f'Cadastro duplicado de produto: {name}.')
                products[name] = matches.first() or Product.objects.create(company=company, name=name)
        for problem in entry['problems']:
            Candidate.objects.create(batch=batch, row_number=1+batch.rows.count(), raw={**problem, 'client': client_name,
                'sheet': entry['sheet'], 'source_date': entry['date']}, category='ITEM_A_CONFERIR')
    for name, client in clients.items():
        notes=sorted({note for entry in analysis['orders'] if entry['client']==name for note in entry['notes']})
        if notes:
            addition='Observações históricas de outubro (conferir instruções atuais):\n'+'\n'.join(notes)
            if addition not in client.notes:
                client.notes=(client.notes+'\n\n'+addition).strip();client.save(update_fields=['notes'])
    for warning in analysis['warnings']:
        Candidate.objects.create(batch=batch, row_number=1+batch.rows.count(), raw={'reason':warning}, category='ITEM_A_CONFERIR')
    for pattern in inferred_patterns(analysis):
        if pattern['stable'] and clients[pattern['client']].active and products[pattern['product']].active:
            # Não duplica regras já existentes, mesmo de outra planilha.
            existing = Recurrence.objects.filter(company=company, client=clients[pattern['client']],
                product=products[pattern['product']], active=True)
            if any(pattern['weekday'] in rule.weekdays for rule in existing):
                pattern['stable'] = False
                pattern['reason'] = 'Já há uma rotina ativa; comparar antes de substituir.'
            else:
                Recurrence.objects.create(company=company, client=clients[pattern['client']], product=products[pattern['product']],
                    quantity=pattern['quantity'], slot='Rotina outubro', time=time(0), shift='NOTURNO',
                    weekdays=[pattern['weekday']], valid_from=start, active=True,
                    notes='Horário de entrega a conferir. Origem: outubro.\n'+pattern['notes'],
                    source_key=f'{digest}:{clients[pattern["client"]].pk}:{products[pattern["product"]].pk}:{pattern["weekday"]}')
        Candidate.objects.create(batch=batch, row_number=1+batch.rows.count(), raw=pattern,
            category='ROTINA_IMPORTADA' if pattern['stable'] else 'ROTINA_A_CONFERIR')
    Audit.objects.create(actor=user, entity=str(batch.pk), action='IMPORTAR_ROTINAS',
        after={'company': str(company.pk), 'orders_created': 0, 'clients': analysis['clients'], 'products': analysis['products'], 'start': str(start)},
        reason='Somente cadastros e rotinas; nenhum pedido antigo importado; rotinas por moda em ao menos 60% das datas disponíveis, mínimo 2 ocorrências. Turno noturno pela origem MD; horário pendente.')
    return batch, True, analysis
