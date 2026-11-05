import uuid
from io import BytesIO
from zipfile import ZipFile
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User,Permission
from django.core.exceptions import ValidationError,PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from pypdf import PdfReader
from .models import *
from .proposal_services import save_proposal,generate_proposal,proposal_action,revise_proposal
from .proposal_reference import read_profile,import_profile
from .team import TeamForm,create_member


def sample_docx():
    source='''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:tbl><w:tr><w:tc><w:p/></w:tc><w:tc>
<w:p><w:r><w:t>NONA CECÍLIA</w:t></w:r></w:p><w:p><w:r><w:t>P A D A R I A</w:t></w:r></w:p>
<w:p><w:r><w:t>RAZAO ARTIFICIAL NONA</w:t></w:r></w:p><w:p><w:r><w:t>CNPJ: 22.222.222/2222-22</w:t></w:r></w:p>
<w:p><w:r><w:t>Endereco de proposta artificial 398</w:t></w:r></w:p><w:p><w:r><w:t>Telefone artificial | teste@example.invalid</w:t></w:r></w:p>
</w:tc></w:tr></w:tbl><w:p><w:r><w:t>P R O P O S T A C O M E R C I A L</w:t></w:r></w:p><w:p><w:r><w:t>RESPONSAVEL ARTIFICIAL</w:t></w:r></w:p><w:p><w:r><w:t>Responsável pela proposta</w:t></w:r></w:p></w:body></w:document>'''
    out=BytesIO()
    with ZipFile(out,'w') as archive:archive.writestr('word/document.xml',source.encode())
    return out.getvalue()


class ProposalsTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.nona=Company.objects.create(code='NONA',name='NONA ARTIFICIAL',cnpj='11111111111111',address='Endereço original de teste')
        self.teco=Company.objects.create(code='TECO',name='TECO ARTIFICIAL',cnpj='33333333333333')
        self.customer=Client.objects.create(company=self.nona,name='Cliente artificial',address='Endereço artificial do cliente')
        self.product=Product.objects.create(company=self.nona,name='Pão artificial',unit='UN')
        self.today=timezone.localdate()
        Price.objects.create(company=self.nona,product=self.product,amount=2,valid_from=self.today)
        Price.objects.create(company=self.nona,product=self.product,client=self.customer,amount=Decimal('1.5'),valid_from=self.today)
        self.client.force_login(self.user)

    def values(self,company=None):
        return dict(company=company or self.nona,client=None,title='Serviço artificial',summary='Resumo artificial para teste',issued_on=self.today,valid_days=60,customer_name='CLIENTE ARTIFICIAL',customer_tax_id='',customer_address='Endereço artificial',included_items='Pão artificial\nCafé de teste',conditions='Condições artificiais',notes='Proposta de teste, sem contratação real',responsible='RESPONSÁVEL ARTIFICIAL')

    def lines(self,count=1):return [dict(product=None,description=f'Serviço artificial {index}',quantity=Decimal('3'),unit='UN',unit_price=Decimal('12.50')) for index in range(count)]

    def proposal(self,company=None,count=1):return save_proposal(self.user,self.values(company),self.lines(count),uuid.uuid4())

    def test_proposal_pdf_uses_source_sections_and_correct_company_logo(self):
        for company,logo_size in [(self.nona,(1448,1086)),(self.teco,(534,580))]:
            with self.subTest(company=company.code):
                values=self.values(company)
                values['title']='Serviço de alimentação · modelo ilustrativo'
                values['included_items']='\n'.join(f'Item de cardápio artificial {n}' for n in range(8))
                lines=self.lines(4)
                lines[0].update(quantity=Decimal('100'),unit='refeição',unit_price=Decimal('.3750'))
                proposal=save_proposal(self.user,values,lines,uuid.uuid4());document=generate_proposal(self.user,proposal)
                reader=PdfReader(BytesIO(document.data));text='\n'.join(page.extract_text() for page in reader.pages)
                self.assertEqual(len(reader.pages),1)
                for title in ['CLIENTE / DESTINATÁRIO','DESCRIÇÃO E INVESTIMENTO','CARDÁPIO / ITENS INCLUSOS','VALOR TOTAL DO ORÇAMENTO','Responsável pela proposta']:
                    self.assertIn(title,text)
                self.assertIn(company.name,text);self.assertIn('150,00',text)
                self.assertIn(logo_size,[item.image.size for item in reader.pages[0].images])
                self.assertLess(float(reader.pages[0].mediabox.width),float(reader.pages[0].mediabox.height))

    def test_negotiated_price_and_explicit_override_do_not_update_catalogue(self):
        values=self.values();values['client']=self.customer
        line=dict(product=self.product,description='',quantity=Decimal('10'),unit='',unit_price=None)
        proposal=save_proposal(self.user,values,[line],uuid.uuid4())
        self.assertEqual(proposal.total,15);self.assertEqual(proposal.items.get().unit_price,Decimal('1.5'))
        proposal=save_proposal(self.user,values,[dict(line,unit_price=Decimal('3'))],uuid.uuid4())
        self.assertEqual(proposal.total,30)
        self.assertEqual(Price.objects.get(product=self.product,client=self.customer).amount,Decimal('1.5'))

    def test_missing_price_rejects_without_saving_and_does_not_invent_price(self):
        with self.assertRaises(ValidationError):save_proposal(self.user,self.values(),[dict(product=None,description='Serviço teste',quantity=Decimal(1),unit='UN',unit_price=None)],uuid.uuid4())
        self.assertEqual(CommercialProposal.objects.count(),0)

    def test_generate_and_create_are_idempotent(self):
        key=uuid.uuid4();proposal=save_proposal(self.user,self.values(),self.lines(),key)
        again=save_proposal(self.user,self.values(),self.lines(),key)
        self.assertEqual(proposal.pk,again.pk)
        first=generate_proposal(self.user,proposal);second=generate_proposal(self.user,proposal)
        self.assertEqual(first.pk,second.pk);self.assertEqual(Document.objects.count(),1)

    def test_reference_import_only_updates_proposal_header_for_matching_company(self):
        profile=import_profile(self.user,self.nona,sample_docx(),'ARTIFICIAL.docx')
        self.nona.refresh_from_db()
        self.assertEqual(self.nona.cnpj,'11111111111111');self.assertEqual(self.nona.address,'Endereço original de teste')
        self.assertEqual(profile.tax_id,'22222222222222');self.assertEqual(profile.responsible,'RESPONSAVEL ARTIFICIAL')
        with self.assertRaises(ValidationError):import_profile(self.user,self.teco,sample_docx(),'ARTIFICIAL.docx')
        proposal=self.proposal();document=generate_proposal(self.user,proposal)
        text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(document.data)).pages)
        self.assertIn('RAZAO ARTIFICIAL NONA',text);self.assertIn('22.222.222/2222-22',text)
        self.assertIn('Endereco de proposta artificial 398',text)

    def test_generated_pdf_is_preserved_after_header_or_catalogue_changes(self):
        import_profile(self.user,self.nona,sample_docx(),'ARTIFICIAL.docx')
        proposal=self.proposal();doc=generate_proposal(self.user,proposal);original=bytes(doc.data)
        ProposalProfile.objects.filter(company=self.nona).update(display_name='NOVO NOME ARTIFICIAL')
        self.product.name='Novo nome de produto';self.product.save()
        self.assertEqual(bytes(generate_proposal(self.user,proposal).data),original)
        with self.assertRaises(ValidationError):save_proposal(self.user,self.values(),self.lines(),proposal.pk,instance=proposal)

    def test_revisions_create_new_drafts_without_replacing_original_pdf(self):
        proposal=self.proposal();document=generate_proposal(self.user,proposal);original=bytes(document.data)
        key=uuid.uuid4();new=revise_proposal(self.user,proposal,key);again=revise_proposal(self.user,proposal,key)
        self.assertEqual(new.pk,again.pk);self.assertEqual(new.status,'RASCUNHO');self.assertIsNone(new.document)
        self.assertEqual(new.previous_id,proposal.pk)
        document.refresh_from_db();self.assertEqual(bytes(document.data),original)

    def test_client_acceptance_does_not_create_order_recurrence_or_financial_entries(self):
        proposal=self.proposal();generate_proposal(self.user,proposal)
        with self.assertRaises(ValidationError):proposal_action(self.user,proposal,'approve','Aceite artificial sem envio')
        proposal_action(self.user,proposal,'send','Envio artificial por e-mail')
        proposal_action(self.user,proposal,'approve','Aceite artificial recebido por e-mail')
        proposal.refresh_from_db();self.assertEqual(proposal.status,'APROVADA')
        for model in [Order,Recurrence,Receivable,Payable]:self.assertEqual(model.objects.count(),0)

    def test_cancelled_pdf_is_unavailable_and_audited(self):
        proposal=self.proposal();generate_proposal(self.user,proposal)
        proposal_action(self.user,proposal,'cancel','Cancelamento artificial de teste')
        self.assertEqual(self.client.get(f'/propostas/{proposal.pk}/pdf/').status_code,409)
        proposal.refresh_from_db();self.assertTrue(proposal.document.superseded)

    def test_many_items_are_paginated_without_losing_last_item_or_total(self):
        proposal=self.proposal(count=60);document=generate_proposal(self.user,proposal)
        reader=PdfReader(BytesIO(document.data));self.assertGreater(len(reader.pages),1)
        text='\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('Serviço artificial 59',text);self.assertIn('2.250,00',text)

    def test_company_scope_and_profile_configuration_are_protected(self):
        proposal=self.proposal();generate_proposal(self.user,proposal)
        user=User.objects.create_user('leitor')
        Membership.objects.create(user=user,company=self.teco)
        user.user_permissions.add(Permission.objects.get(codename='view_commercialproposal',content_type__app_label='core'))
        self.client.force_login(user)
        self.assertEqual(self.client.get(f'/propostas/{proposal.pk}/').status_code,404)
        self.assertEqual(self.client.get(f'/propostas/{proposal.pk}/pdf/').status_code,404)
        self.assertEqual(self.client.get(f'/propostas/cabecalho/{self.nona.pk}/').status_code,403)

    def test_catalogue_product_and_client_cannot_cross_companies(self):
        other=Product.objects.create(company=self.teco,name='Produto de outra empresa')
        with self.assertRaises(ValidationError):save_proposal(self.user,self.values(),[dict(product=other,description='',quantity=Decimal(1),unit='',unit_price=Decimal(1))],uuid.uuid4())
        other_client=Client.objects.create(company=self.teco,name='Cliente outra empresa')
        values=self.values();values['client']=other_client
        with self.assertRaises(ValidationError):save_proposal(self.user,values,self.lines(),uuid.uuid4())
        self.assertEqual(CommercialProposal.objects.count(),0)

    def test_draft_edit_retains_date_and_validity(self):
        values=self.values();values['issued_on']=self.today-timedelta(days=5);values['valid_days']=30
        proposal=save_proposal(self.user,values,self.lines(),uuid.uuid4())
        response=self.client.get(f'/propostas/{proposal.pk}/editar/')
        self.assertEqual(response.context['form']['issued_on'].value(),values['issued_on'])
        self.assertEqual(response.context['form']['valid_days'].value(),30)

    def test_new_form_accepts_free_service_and_ignores_blank_extra_items(self):
        key=uuid.uuid4()
        data=dict(company=str(self.nona.pk),client='',key=str(key),title='Serviço teste',summary='',issued_on=str(self.today),valid_days='60',customer_name='CLIENTE ARTIFICIAL',customer_tax_id='',customer_address='',included_items='Café\nPão',conditions='Condição teste',notes='',responsible='Responsável teste')
        data.update({'form-TOTAL_FORMS':'4','form-INITIAL_FORMS':'0'})
        for index in range(4):data.update({f'form-{index}-product':'',f'form-{index}-description':'Serviço teste' if index==0 else '',f'form-{index}-quantity':'1',f'form-{index}-unit':'',f'form-{index}-unit_price':'12.50' if index==0 else ''})
        response=self.client.post('/propostas/nova/',data)
        self.assertEqual(response.status_code,302)
        proposal=CommercialProposal.objects.get(pk=key)
        self.assertEqual(proposal.items.count(),1);self.assertEqual(proposal.total,Decimal('12.5'))

    def test_all_proposal_pages_render_and_commercial_user_lands_on_proposals(self):
        proposal=self.proposal()
        for url in ['/propostas/','/propostas/nova/',f'/propostas/{proposal.pk}/',f'/propostas/{proposal.pk}/editar/',f'/propostas/cabecalho/{self.nona.pk}/']:
            with self.subTest(url=url):self.assertEqual(self.client.get(url).status_code,200)
        form=TeamForm({'username':'comercial','company':str(self.nona.pk),'role':'COMERCIAL','password1':'Artificial-Password-1248!','password2':'Artificial-Password-1248!'},user=self.user)
        self.assertTrue(form.is_valid(),form.errors)
        user=create_member(form,self.user);self.client.force_login(user)
        self.assertContains(self.client.get('/'),'Propostas comerciais')
        self.assertFalse(user.has_perm('core.add_receivable'))

    def test_draft_edit_can_remove_an_item_and_recalculates_total(self):
        proposal=self.proposal(count=2)
        data={key:str(value.pk) if hasattr(value,'pk') else value for key,value in self.values().items()}
        data.update(client='',key=str(proposal.pk),company=str(self.nona.pk))
        data.update({'form-TOTAL_FORMS':'2','form-INITIAL_FORMS':'2'})
        for index in range(2):
            data.update({f'form-{index}-product':'',f'form-{index}-description':f'Serviço artificial {index}',f'form-{index}-quantity':'3',f'form-{index}-unit':'UN',f'form-{index}-unit_price':'12.50'})
        data['form-1-DELETE']='on'
        response=self.client.post(f'/propostas/{proposal.pk}/editar/',data)
        self.assertEqual(response.status_code,302)
        proposal.refresh_from_db()
        self.assertEqual(proposal.items.count(),1);self.assertEqual(proposal.total,Decimal('37.50'))

    def test_invalid_docx_is_rejected(self):
        with self.assertRaises(ValidationError):read_profile(b'not docx')
