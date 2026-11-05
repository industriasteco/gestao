import hashlib
import uuid
from datetime import timedelta
from decimal import Decimal,ROUND_HALF_UP
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from .models import Company,CommercialProposal,ProposalItem,ProposalProfile,Document,Price
from .services import authorize
from .receipt_layout import brand_code
from .workflow import event

FIELDS=['company','client','title','summary','issued_on','valid_days','customer_name','customer_tax_id','customer_address','included_items','conditions','notes','responsible']


def header_values(company):
    profile=ProposalProfile.objects.filter(company=company).first()
    def pick(field,fallback=''):return getattr(profile,field,'') or fallback
    return dict(code=company.code,name=pick('display_name',company.name),subtitle=pick('subtitle','PANIFICADORA' if brand_code(company.code)=='TECO' else 'PADARIA'),
        legal_name=pick('legal_name',company.legal_name),tax_id=pick('tax_id',company.cnpj or ''),address=pick('address',company.address),
        phone=pick('phone',company.phone),email=pick('email',company.email),responsible=pick('responsible'))


def prepare_values(values):
    values=dict(values);company=values['company'];client=values.get('client')
    if client:
        if client.company_id!=company.pk:raise ValidationError('Cliente de outra empresa.')
        values['customer_name']=values.get('customer_name') or client.legal_name or client.name
        values['customer_tax_id']=values.get('customer_tax_id') or client.tax_id
        values['customer_address']=values.get('customer_address') or client.address
    values['responsible']=values.get('responsible') or header_values(company)['responsible']
    return values


def resolve_lines(company,client,day,lines):
    if not lines or len(lines)>100:raise ValidationError('Inclua de 1 a 100 itens na proposta.')
    resolved=[];total=Decimal(0)
    for row in lines:
        product=row.get('product');description=row.get('description','').strip();unit=row.get('unit','').strip()
        amount=row.get('unit_price');quantity=row['quantity']
        if product:
            if product.company_id!=company.pk or not product.active:raise ValidationError('Produto inativo ou de outra empresa.')
            description=description or product.name;unit=unit or product.unit
            if amount is None:
                prices=Price.objects.filter(company=company,product=product,valid_from__lte=day).filter(Q(valid_until__isnull=True)|Q(valid_until__gte=day))
                special=prices.filter(client=client) if client else prices.none()
                selected=special if special.exists() else prices.filter(client__isnull=True)
                if selected.count()!=1:raise ValidationError('Preço ausente ou sobreposto. Informe o valor unitário negociado para cada item.')
                amount=selected.get().amount
        if not description or len(description)>500:raise ValidationError('Informe a descrição do serviço ou produto, com até 500 caracteres.')
        if amount is None:raise ValidationError('Informe o valor unitário dos itens que não estão no catálogo.')
        if not quantity.is_finite() or quantity<=0 or not amount.is_finite() or amount<0:raise ValidationError('Confira quantidades e preços dos itens.')
        subtotal=(quantity*amount).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        total+=subtotal
        resolved.append(dict(product=product,description=description,quantity=quantity,unit=unit or 'UN',unit_price=amount,total=subtotal))
    if total>=Decimal('100000000000000'):raise ValidationError('Total da proposta excede o limite.')
    return resolved,total


@transaction.atomic
def save_proposal(user,values,lines,key,instance=None):
    values=prepare_values(values);company=values['company']
    authorize(user,company,'core.change_commercialproposal' if instance else 'core.add_commercialproposal')
    Company.objects.select_for_update().get(pk=company.pk)
    if not company.active or brand_code(company.code) not in ('TECO','NONA'):raise ValidationError('Selecione uma emissora ativa TECO ou NONA.')
    if instance:
        proposal=CommercialProposal.objects.select_for_update().get(pk=instance.pk)
        if proposal.company_id!=company.pk:raise ValidationError('A empresa da proposta não pode ser alterada.')
        if proposal.status!='RASCUNHO' or proposal.document_id:raise ValidationError('PDF já preservado. Crie uma revisão para mudar a proposta.')
    else:
        proposal=CommercialProposal.objects.filter(pk=key).first()
        if proposal:
            if proposal.company_id!=company.pk or proposal.actor_id!=user.pk:raise ValidationError('Identificador de proposta já utilizado.')
            return proposal
        proposal=CommercialProposal(id=key,actor=user,number=f'PROP-{values["issued_on"]:%Y%m%d}-{str(key).replace("-","")[:12].upper()}')
    for name in FIELDS:setattr(proposal,name,values.get(name))
    resolved,total=resolve_lines(company,proposal.client,proposal.issued_on,lines)
    proposal.total=total;proposal.full_clean();proposal.save()
    proposal.items.all().delete()
    for sequence,row in enumerate(resolved,1):
        item=ProposalItem(proposal=proposal,sequence=sequence,**{name:row[name] for name in ['product','description','quantity','unit','unit_price']})
        item.full_clean();item.save()
    event(user,proposal,'SALVAR_PROPOSTA',after={'total':str(total),'items':len(resolved),'company':str(company.pk)})
    return proposal


@transaction.atomic
def generate_proposal(user,proposal):
    authorize(user,proposal.company,'core.change_commercialproposal')
    Company.objects.select_for_update().get(pk=proposal.company_id)
    proposal=CommercialProposal.objects.select_for_update().get(pk=proposal.pk)
    if proposal.document_id:return proposal.document
    if proposal.status!='RASCUNHO':raise ValidationError('Somente rascunhos podem gerar um novo PDF.')
    if not proposal.company.active:raise ValidationError('Empresa inativa; revise o cadastro antes de gerar a proposta.')
    if brand_code(proposal.company.code) not in ('TECO','NONA'):raise ValidationError('Marca da empresa não configurada.')
    source=[dict(product=item.product,description=item.description,quantity=item.quantity,unit=item.unit,unit_price=item.unit_price) for item in proposal.items.select_related('product')]
    lines,total=resolve_lines(proposal.company,proposal.client,proposal.issued_on,source)
    snapshot={name:getattr(proposal,name) for name in ['number','title','summary','valid_days','customer_name','customer_tax_id','customer_address','included_items','conditions','notes','responsible']}
    snapshot.update(company=header_values(proposal.company),issued_on=str(proposal.issued_on),valid_until=str(proposal.issued_on+timedelta(days=proposal.valid_days)),total=str(total),items=[{key:str(row[key]) for key in ['description','quantity','unit','unit_price','total']} for row in lines])
    from .proposal_pdf import render_proposal
    data=render_proposal(snapshot)
    doc=Document.objects.create(company=proposal.company,key=f'proposal:{proposal.pk}',kind='PROPOSTA_COMERCIAL',layout='proposta-docx-v1',data=data,sha256=hashlib.sha256(data).hexdigest())
    proposal.document=doc;proposal.snapshot=snapshot;proposal.total=total;proposal.status='GERADA';proposal.save()
    event(user,proposal,'GERAR_PDF_PROPOSTA',after={'total':str(total),'sha256':doc.sha256})
    return doc


@transaction.atomic
def proposal_action(user,proposal,action,evidence):
    authorize(user,proposal.company,'core.change_commercialproposal')
    proposal=CommercialProposal.objects.select_for_update().get(pk=proposal.pk)
    if len(evidence.strip())<5:raise ValidationError('Registre o meio de envio ou a evidência da resposta do cliente (mínimo 5 caracteres).')
    transitions={'send':({'GERADA','ENVIADA'},'ENVIADA'),'approve':({'ENVIADA'},'APROVADA'),'reject':({'ENVIADA'},'RECUSADA'),'cancel':({'RASCUNHO','GERADA','ENVIADA','RECUSADA'},'CANCELADA')}
    allowed,next_status=transitions.get(action,(set(),''))
    if proposal.status not in allowed:raise ValidationError('Ação indisponível na situação atual da proposta.')
    if next_status=='CANCELADA' and proposal.document_id:Document.objects.filter(pk=proposal.document_id).update(superseded=True)
    previous=proposal.status;proposal.status=next_status;proposal.evidence=evidence.strip();proposal.save(update_fields=['status','evidence','updated_at'])
    event(user,proposal,'SITUACAO_PROPOSTA',before={'status':previous},after={'status':next_status},reason=evidence)
    return proposal


@transaction.atomic
def revise_proposal(user,proposal,key):
    authorize(user,proposal.company,'core.add_commercialproposal')
    Company.objects.select_for_update().get(pk=proposal.company_id)
    old=CommercialProposal.objects.select_for_update().get(pk=proposal.pk)
    existing=CommercialProposal.objects.filter(pk=key).first()
    if existing:
        if existing.previous_id!=old.pk or existing.company_id!=old.company_id:raise ValidationError('Identificador já utilizado.')
        return existing
    values={field:getattr(old,field) for field in FIELDS}
    source=[dict(product=item.product,description=item.description,quantity=item.quantity,unit=item.unit,unit_price=item.unit_price) for item in old.items.select_related('product')]
    new=save_proposal(user,values,source,key)
    new.previous=old;new.save(update_fields=['previous'])
    event(user,new,'REVISAR_PROPOSTA',after={'previous':str(old.pk)},reason='Novo rascunho; PDF e resposta anteriores preservados.')
    return new
