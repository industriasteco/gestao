from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from django.test import TestCase
from django.contrib.auth.models import User,Permission
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from .models import *
from .nfe_import import parse_nfe,valid_access_key
from .payables_services import stage_invoice,confirm_invoice,payable_balances,pay,void_payable,archive_invoice
from .team import TeamForm,create_member


def sample_xml(environment='2',duplicates=True,missing_date=False):
    today=timezone.localdate();issued=today-timedelta(days=1)
    first_due=today+timedelta(days=29);second_due=today+timedelta(days=59)
    base='35'+issued.strftime('%y%m')+'22222222222222'+'55'+'001'+'000000123'+'1'+'12345678'
    weight=2;total=0
    for digit in base[::-1]:
        total+=int(digit)*weight;weight=2 if weight==9 else weight+1
    check=11-total%11;check=0 if check>=10 else check
    key=base+str(check)
    dups=''
    if duplicates:
        due1=f'<dVenc>{first_due}</dVenc>' if not missing_date else ''
        dups=f'<dup><nDup>001</nDup>{due1}<vDup>100.00</vDup></dup><dup><nDup>002</nDup><dVenc>{second_due}</dVenc><vDup>200.00</vDup></dup>'
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<!-- ARQUIVO ARTIFICIAL DE TESTE. NAO E DOCUMENTO FISCAL. -->
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00"><NFe><infNFe Id="NFe{key}" versao="4.00">
<ide><cUF>35</cUF><cNF>12345678</cNF><mod>55</mod><serie>1</serie><nNF>123</nNF><dhEmi>{issued}T08:00:00-03:00</dhEmi><tpNF>1</tpNF><tpEmis>1</tpEmis><cDV>{check}</cDV><tpAmb>{environment}</tpAmb><finNFe>1</finNFe></ide>
<emit><CNPJ>22222222222222</CNPJ><xNome>FORNECEDOR ARTIFICIAL DE TESTE</xNome><xFant>TESTE</xFant><enderEmit><xLgr>Rua artificial</xLgr><nro>1</nro><xBairro>Teste</xBairro><xMun>Teste</xMun><UF>SP</UF><CEP>00000000</CEP></enderEmit></emit>
<dest><CNPJ>11111111111111</CNPJ><xNome>DESTINATARIO ARTIFICIAL</xNome></dest>
<det nItem="1"><prod><cProd>ART-01</cProd><xProd>PRODUTO ARTIFICIAL</xProd><NCM>00000000</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>30.0000</qCom><vProd>300.00</vProd></prod></det>
<total><ICMSTot><vNF>300.00</vNF></ICMSTot></total><cobr><fat><nFat>TESTE-123</nFat><vOrig>300.00</vOrig><vDesc>0.00</vDesc><vLiq>300.00</vLiq></fat>{dups}</cobr>
<pag><detPag><tPag>15</tPag><vPag>300.00</vPag></detPag></pag>
</infNFe></NFe><protNFe versao="4.00"><infProt><tpAmb>{environment}</tpAmb><chNFe>{key}</chNFe><nProt>000000000000000</nProt><cStat>100</cStat><xMotivo>ARTIFICIAL DE TESTE</xMotivo></infProt></protNFe></nfeProc>'''.encode()


class PayablesTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.company=Company.objects.create(code='TEST',name='Empresa artificial',cnpj='11111111111111')
        self.today=timezone.localdate()
        self.client.force_login(self.user)

    def invoice(self,**options):return stage_invoice(self.user,self.company,sample_xml(**options),'ARTIFICIAL.xml')[0]

    def test_xml_parses_invoice_and_installments_without_inventing_due_dates(self):
        parsed=parse_nfe(sample_xml())
        self.assertTrue(valid_access_key(parsed['access_key']))
        self.assertEqual((parsed['total'],parsed['financial_total']),('300.00','300.00'))
        self.assertEqual(len(parsed['installments']),2)
        self.assertEqual(parsed['installments'][0]['amount'],'100.00')
        self.assertEqual(parsed['supplier']['name'],'FORNECEDOR ARTIFICIAL DE TESTE')
        self.assertEqual(parse_nfe(sample_xml(duplicates=False))['installments'],[])
        self.assertEqual(parse_nfe(sample_xml(missing_date=True))['installments'][0]['due_on'],'')

    def test_xml_stage_then_confirmation_is_idempotent_and_does_not_touch_stock_orders_or_payments(self):
        data=sample_xml();invoice,created=stage_invoice(self.user,self.company,data,'ARTIFICIAL.xml')
        self.assertTrue(created);self.assertEqual(Supplier.objects.count(),1)
        self.assertEqual(Payable.objects.count(),0)
        rows=confirm_invoice(self.user,invoice)
        self.assertEqual([r.amount for r in rows],[100,200])
        self.assertTrue(all(row.synthetic for row in rows))
        again,created=stage_invoice(self.user,self.company,data,'REENVIADO.xml')
        self.assertFalse(created);self.assertEqual(again.pk,invoice.pk)
        confirm_invoice(self.user,invoice)
        self.assertEqual(Payable.objects.count(),2)
        self.assertEqual(Order.objects.count(),0);self.assertEqual(StockMovement.objects.count(),0);self.assertEqual(Disbursement.objects.count(),0)

    def test_recipient_and_access_key_fields_are_checked_before_saving(self):
        other=Company.objects.create(code='OTHER',name='Outra artificial',cnpj='33333333333333')
        with self.assertRaises(ValidationError):stage_invoice(self.user,other,sample_xml(),'TESTE.xml')
        with self.assertRaises(ValidationError):parse_nfe(sample_xml().replace(b'<nNF>123</nNF>',b'<nNF>124</nNF>'))
        self.assertEqual(PurchaseInvoice.objects.count(),0);self.assertEqual(Supplier.objects.count(),0)

    def test_no_cnpj_or_issuer_selling_to_itself_cannot_create_purchase(self):
        self.company.cnpj=None;self.company.save()
        with self.assertRaises(ValidationError):self.invoice()
        self.assertEqual(PurchaseInvoice.objects.count(),0)

    def test_malformed_entities_event_or_unapproved_protocol_are_rejected(self):
        samples=[b'not xml',b'<!DOCTYPE x [<!ENTITY y SYSTEM "file:///etc/passwd">]><x>&y;</x>',b'<resNFe/>',sample_xml().replace(b'<cStat>100</cStat>',b'<cStat>101</cStat>')]
        for data in samples:
            with self.subTest(data=data[:40]):
                with self.assertRaises(ValidationError):parse_nfe(data)
        with self.assertRaises(ValidationError):parse_nfe(b'x'*(5*1024*1024+1))

    def test_installment_totals_duplicates_and_dates_must_match_invoice(self):
        data=sample_xml()
        for altered in [data.replace(b'<vDup>200.00</vDup>',b'<vDup>201.00</vDup>'),data.replace(b'<nDup>002</nDup>',b'<nDup>001</nDup>'),data.replace(str(self.today+timedelta(days=29)).encode(),b'2000-01-01')]:
            with self.assertRaises(ValidationError):parse_nfe(altered)

    def test_same_key_with_changed_economic_content_cannot_replace_original(self):
        invoice=self.invoice();original=bytes(invoice.xml)
        changed=sample_xml().replace(b'PRODUTO ARTIFICIAL',b'PRODUTO MODIFICADO')
        with self.assertRaises(ValidationError):stage_invoice(self.user,self.company,changed,'ALTERADO.xml')
        invoice.refresh_from_db();self.assertEqual(bytes(invoice.xml),original)
        # White space outside the data does not duplicate the same note.
        _,created=stage_invoice(self.user,self.company,sample_xml().replace(b'</nfeProc>',b'\n</nfeProc>'),'COPIA.xml')
        self.assertFalse(created)

    def test_missing_installments_need_manual_schedule_and_sum(self):
        invoice=self.invoice(duplicates=False)
        with self.assertRaises(ValidationError):confirm_invoice(self.user,invoice)
        with self.assertRaises(ValidationError):confirm_invoice(self.user,invoice,[{'reference':'001','due_on':self.today,'amount':Decimal('299')}])
        rows=confirm_invoice(self.user,invoice,[{'reference':'001','due_on':self.today,'amount':Decimal('300')}])
        self.assertEqual(len(rows),1);self.assertEqual(rows[0].due_on,self.today)

    def test_missing_date_keeps_the_xml_values_and_existing_dates(self):
        invoice=self.invoice(missing_date=True)
        with self.assertRaises(ValidationError):confirm_invoice(self.user,invoice)
        schedule=[{'reference':'001','due_on':self.today,'amount':Decimal('100')},{'reference':'002','due_on':self.today+timedelta(days=59),'amount':Decimal('200')}]
        wrong=[dict(schedule[0],amount=99),dict(schedule[1],amount=201)]
        with self.assertRaises(ValidationError):confirm_invoice(self.user,invoice,wrong)
        rows=confirm_invoice(self.user,invoice,schedule)
        self.assertEqual(len(rows),2);self.assertEqual(rows[0].amount,100)

    def test_partial_payment_updates_balance_without_duplicate_or_overpayment(self):
        rows=confirm_invoice(self.user,self.invoice(environment='1'));row=rows[0]
        a=pay(self.user,row,Decimal('40'),self.today,'PIX','PAYMENT-1','Comprovante artificial')
        b=pay(self.user,row,Decimal('40'),self.today,'PIX','PAYMENT-1','Comprovante artificial')
        self.assertEqual(a.pk,b.pk);self.assertEqual(Disbursement.objects.count(),1)
        self.assertEqual(next(r for r in payable_balances(self.user) if r.pk==row.pk).balance,60)
        with self.assertRaises(ValidationError):pay(self.user,row,Decimal('61'),self.today,'PIX','PAYMENT-2','Comprovante artificial')
        with self.assertRaises(ValidationError):pay(self.user,row,Decimal('1'),self.today+timedelta(days=1),'PIX','PAYMENT-3','Comprovante artificial')
        with self.assertRaises(ValidationError):void_payable(self.user,row,'Cancelar conta com pagamento')

    def test_test_invoices_are_excluded_from_real_dashboard_totals(self):
        confirm_invoice(self.user,self.invoice())
        response=self.client.get('/contas-a-pagar/')
        self.assertEqual(response.context['open_total'],0);self.assertEqual(response.context['test_count'],2)
        self.assertEqual(self.client.get('/').context['payable_total'],0)

    def test_real_invoices_are_included_in_payable_dashboard(self):
        confirm_invoice(self.user,self.invoice(environment='1'))
        self.assertEqual(self.client.get('/contas-a-pagar/').context['open_total'],300)
        self.assertEqual(self.client.get('/').context['payable_total'],300)

    def test_private_xml_download_and_finance_are_company_scoped(self):
        invoice=self.invoice();rows=confirm_invoice(self.user,invoice)
        response=self.client.get(f'/notas-de-compra/{invoice.pk}/xml/')
        self.assertEqual(response.content,sample_xml())
        other=Company.objects.create(code='OTHER',name='Outra artificial')
        user=User.objects.create_user('viewer');Membership.objects.create(user=user,company=other)
        user.user_permissions.add(*Permission.objects.filter(content_type__app_label='core',codename__in=['view_payable','view_purchaseinvoice','view_supplier']))
        self.client.force_login(user)
        for url in [f'/notas-de-compra/{invoice.pk}/',f'/notas-de-compra/{invoice.pk}/xml/',f'/contas-a-pagar/{rows[0].pk}/',f'/fornecedores/{invoice.supplier_id}/']:
            self.assertEqual(self.client.get(url).status_code,404)
        self.assertNotContains(self.client.get('/contas-a-pagar/'),'FORNECEDOR ARTIFICIAL DE TESTE')
        self.assertEqual(self.client.post('/contas-a-pagar/',{}).status_code,403)

    def test_archive_and_void_preserve_records(self):
        invoice=self.invoice(duplicates=False);archive_invoice(self.user,invoice,'Compra sem financeiro a gerar neste controle')
        with self.assertRaises(ValidationError):confirm_invoice(self.user,invoice,[{'reference':'1','due_on':self.today,'amount':300}])
        self.assertEqual(Payable.objects.count(),0)
        supplier=invoice.supplier
        row=Payable.objects.create(company=self.company,supplier=supplier,reference='MANUAL',issued_on=self.today,due_on=self.today,amount=10)
        void_payable(self.user,row,'Despesa cadastrada incorretamente')
        self.assertEqual(Payable.objects.count(),1);self.assertEqual(payable_balances(self.user),[])

    def test_supplier_and_payable_forms_reject_company_mismatch(self):
        other=Company.objects.create(code='OTHER',name='Outra artificial')
        supplier=Supplier.objects.create(company=other,name='Fornecedor de outra empresa')
        response=self.client.post('/contas-a-pagar/',{'company':str(self.company.pk),'supplier':str(supplier.pk),'reference':'ERRADO','issued_on':str(self.today),'due_on':str(self.today),'amount':'10'})
        self.assertEqual(response.status_code,200);self.assertEqual(Payable.objects.count(),0)

    def test_upload_preview_confirmation_and_new_pages_render(self):
        response=self.client.post('/notas-de-compra/',{'company':str(self.company.pk),'file':SimpleUploadedFile('ARTIFICIAL.xml',sample_xml(),content_type='application/xml')})
        self.assertEqual(response.status_code,302)
        invoice=PurchaseInvoice.objects.get()
        self.assertEqual(self.client.get(response.url).status_code,200)
        response=self.client.post(response.url,{'action':'confirm','confirm':'yes'})
        self.assertEqual(response.status_code,302);self.assertEqual(Payable.objects.count(),2)
        for url in ['/contas-a-pagar/','/notas-de-compra/',f'/notas-de-compra/{invoice.pk}/',f'/contas-a-pagar/{invoice.payables.first().pk}/','/fornecedores/',f'/fornecedores/{invoice.supplier_id}/','/fiscal/']:
            with self.subTest(url=url):self.assertEqual(self.client.get(url).status_code,200)

    def test_missing_date_form_preserves_xml_reference_and_amount(self):
        invoice=self.invoice(missing_date=True)
        response=self.client.post(f'/notas-de-compra/{invoice.pk}/',{'action':'confirm','confirm':'yes','form-TOTAL_FORMS':'2','form-INITIAL_FORMS':'2','form-0-reference':'MUDADO','form-0-amount':'999','form-0-due_on':str(self.today),'form-1-reference':'MUDADO2','form-1-amount':'999','form-1-due_on':'2000-01-01'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(list(invoice.payables.order_by('installment').values_list('installment','amount')),[('001',Decimal('100')),('002',Decimal('200'))])

    def test_financial_role_can_import_purchase_xml_but_production_role_cannot(self):
        for key,username,expected in [('FINANCEIRO','financeiro',True),('PRODUCAO','producao',False)]:
            form=TeamForm({'username':username,'company':str(self.company.pk),'role':key,'password1':'Artificial-Password-5831!','password2':'Artificial-Password-5831!'},user=self.user)
            self.assertTrue(form.is_valid(),form.errors)
            user=create_member(form,self.user)
            self.assertEqual(user.has_perm('core.add_purchaseinvoice'),expected)
            self.client.force_login(user)
            self.assertEqual(self.client.get('/contas-a-pagar/').status_code,200 if expected else 403)

    def test_company_editor_allows_confirming_cnpj_and_fiscal_system_without_changing_code(self):
        response=self.client.get(f'/empresas/{self.company.pk}/')
        self.assertEqual(response.status_code,200)
        response=self.client.post(f'/empresas/{self.company.pk}/',{'code':'ALTERADO','name':self.company.name,'legal_name':'','cnpj':'11111111111111','address':'Endereço artificial','phone':'','email':'','fiscal_system':'Sistema Imagem'})
        self.assertEqual(response.status_code,302)
        self.company.refresh_from_db();self.assertEqual(self.company.code,'TEST')
        self.assertEqual(self.company.fiscal_system,'Sistema Imagem')

    def test_payment_date_is_usable_in_browser_and_post_reduces_balance(self):
        row=confirm_invoice(self.user,self.invoice())[0]
        url=f'/contas-a-pagar/{row.pk}/'
        response=self.client.get(url)
        self.assertContains(response,f'value="{self.today}"')
        form=response.context['form']
        self.assertIn(f'value="{self.today}"',str(form['date']))
        response=self.client.post(url,{'amount':'30.00','date':str(self.today),'method':'PIX','reference':str(form.initial['reference']),'evidence':'Comprovante artificial de teste'})
        self.assertEqual(response.status_code,302)
        response=self.client.get(url)
        self.assertEqual(response.context['row'].balance,70)
