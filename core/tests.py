from datetime import date,time
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from io import BytesIO
from pypdf import PdfReader
from pypdf.generic import ContentStream
from . import workflow
from .backup import restore_check
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError,PermissionDenied
from django.db import transaction,DatabaseError
from django.conf import settings
from .models import *
from .services import *

class Acceptance(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('admin','', 'test-only')
        self.day=date(2026,11,4)
        self.co=Company.objects.create(code='TEST',name='Artificial')
        self.client_record=Client.objects.create(company=self.co,name='Cliente teste')
        self.product=Product.objects.create(company=self.co,name='Produto teste')
        self.rule=Recurrence.objects.create(company=self.co,client=self.client_record,product=self.product,quantity=10,slot='1',time=time(6),shift='NOTURNO',weekdays=[3],valid_from=self.day,active=True)
    def prepare(self):
        prepare(self.user,self.day);return Order.objects.get()
    def stage_file(self,prefix):
        paths=list((settings.BASE_DIR/'reference/03_DADOS_PARA_MIGRACAO').glob(prefix+'*.csv'))
        if paths:return stage(paths[0])
        # GitHub público: substituto explicitamente artificial, sem dados dos clientes.
        # Nesta tarefa as fontes privadas presentes acima são usadas de fato.
        count={'auditoria_':82,'previsao_':31,'recorrencias_':101}[prefix]
        content='client,qty,ativo_original\n'+''.join('CLIENTE ARTIFICIAL,1,NÃO\n' for _ in range(count))
        return stage_bytes(content.encode(),prefix+'ARTIFICIAL.csv')
    def issued(self,order=None):
        order=order or self.prepare()
        order.baker='PADEIRO DE TESTE';order.status='CONFERIDO';order.save()
        Price.objects.get_or_create(company=order.company,product=order.items.first().product,client=order.client,valid_from=self.day,defaults={'amount':Decimal('1.2500')})
        doc=workflow.issue(self.user,order.pk)
        order.refresh_from_db()
        return order,doc
    def released(self,order=None):
        order,doc=self.issued(order)
        workflow.deliver(self.user,order.pk,'EVIDÊNCIA ARTIFICIAL DE TESTE')
        workflow.release(self.user,order.pk)
        order.refresh_from_db();return order,doc
    def test_ct01_idempotence_and_manual_adjustment(self):
        order=self.prepare();adjust(self.user,order.pk,Decimal(17),'Ajuste artificial')
        self.assertEqual(prepare(self.user,self.day),0)
        self.assertEqual(order.items.get().quantity,17)
        self.assertEqual(Order.objects.count(),1)
    def test_ct02_multiple_deliveries_planning(self):
        self.rule.pk=None;self.rule.slot='2';self.rule.time=time(14);self.rule.shift='DIURNO';self.rule.save()
        prepare(self.user,self.day)
        self.assertEqual(Order.objects.count(),2)
        row=production(Order.objects.all())[0]
        self.assertEqual((row['NOTURNO'],row['DIURNO'],row['total']),(10,10,20))
    def test_ct03_company_isolation_and_production(self):
        co=Company.objects.create(code='OTHER',name='Outra')
        cl=Client.objects.create(company=co,name='Teste')
        pr=Product.objects.create(company=co,name=self.product.name)
        self.rule.pk=None;self.rule.company=co;self.rule.client=cl;self.rule.product=pr;self.rule.save()
        prepare(self.user,self.day)
        self.assertEqual(production(Order.objects.all())[0]['total'],20)
        viewer=User.objects.create_user('viewer');Membership.objects.create(user=viewer,company=co)
        self.assertEqual(Order.objects.filter(company__in=companies(viewer)).count(),1)
    def test_ct04_missing_shift_blocks(self):
        order=self.prepare();order.shift='';order.save()
        with self.assertRaises(ValidationError): check_production(self.user,self.day)
        order.refresh_from_db();self.assertEqual(order.status,'PRE_LANCADO')
    def test_ct05_missing_price_blocks(self):
        with self.assertRaises(ValidationError): price_for(self.co,self.client_record,self.product,self.day)
        with self.assertRaises(ValidationError): financial_operation()
    def test_ct06_price_version_does_not_touch_snapshot(self):
        order,doc=self.released()
        closure=workflow.close(self.user,self.co,self.client_record,self.day.replace(day=1))
        original=bytes(doc.data)
        Price.objects.create(company=self.co,product=self.product,amount=99,valid_from=date(2027,1,1))
        order.refresh_from_db();closure.refresh_from_db();doc.refresh_from_db()
        self.assertEqual(Decimal(order.issued_snapshot['total']),Decimal('12.50'))
        self.assertEqual(closure.total,Decimal('12.50'))
        self.assertEqual(bytes(doc.data),original)
    def test_ct07_cancellation_excludes_production_and_audits(self):
        order=self.prepare();cancel(self.user,order.pk,'Cancelamento teste')
        self.assertEqual(production(Order.objects.all()),[])
        self.assertTrue(Audit.objects.filter(action='CANCELAR').exists())
    def test_ct08_cancel_issued_document(self):
        order,doc=self.issued()
        with self.assertRaises(ValidationError):workflow.cancel(self.user,order.pk,'')
        user=User.objects.create_user('cancel_operator')
        from django.contrib.auth.models import Permission
        user.user_permissions.add(Permission.objects.get(codename='check_production'))
        Membership.objects.create(user=user,company=self.co)
        with self.assertRaises(PermissionDenied):workflow.cancel(user,order.pk,'Sem autorização especial')
        workflow.cancel(self.user,order.pk,'Cancelado para teste')
        doc.refresh_from_db();self.assertTrue(doc.superseded)
        self.assertTrue(bytes(doc.data).startswith(b'%PDF'))
        self.assertTrue(Audit.objects.filter(action='CANCELAR').exists())
    def test_ct09_ibis_duplex(self):
        self.co.code='TECO';self.co.save()
        self.client_record.name='IBIS';self.client_record.save()
        order,doc=self.issued();reader=PdfReader(BytesIO(doc.data))
        self.assertEqual(len(reader.pages),4)
        self.assertIn('VIA EMPRESA',reader.pages[0].extract_text())
        self.assertIn('VIA CLIENTE',reader.pages[2].extract_text())
        for page in reader.pages:
            self.assertAlmostEqual(float(page.mediabox.width),595.2756,places=3)
            self.assertLess(float(page.mediabox.width),float(page.mediabox.height))
            self.assertIn('Artificial',page.extract_text())
        for index in [1,3]:
            rectangles=[args for args,operator in ContentStream(reader.pages[index].get_contents(),reader).operations if operator==b're']
            self.assertEqual(len(rectangles),10)
            for rect in rectangles:
                self.assertAlmostEqual(float(rect[2]),40*72/25.4,places=3)
                self.assertAlmostEqual(float(rect[3]),60*72/25.4,places=3)
    def test_ct10_standard_receipts(self):
        order,doc=self.issued();reader=PdfReader(BytesIO(doc.data))
        self.assertEqual(len(reader.pages),1)
        text=reader.pages[0].extract_text()
        company,customer=text.split('VIA CLIENTE',1)
        self.assertNotIn('1,25',company);self.assertIn('1,25',customer)
        self.assertIn('SEM VALORES',company)
        # Two orders occupy exactly four receipts on one A4 page.
        other=Order.objects.create(company=self.co,client=self.client_record,date=self.day,slot='2',time=time(14),shift='DIURNO',idempotency_key='manual-2')
        OrderItem.objects.create(order=other,product=self.product,product_name=self.product.name,unit='UN',quantity=10)
        self.issued(other)
        daydoc=workflow.daily_document(self.user,self.day,self.co)
        self.assertEqual(len(PdfReader(BytesIO(daydoc.data)).pages),1)
        self.assertEqual(PdfReader(BytesIO(daydoc.data)).pages[0].extract_text().count('HOMOLOGACAO - NAO COBRAR'),4)
    def test_ct11_daily_pdf(self):
        order,doc=self.issued()
        a=workflow.daily_document(self.user,self.day,self.co)
        b=workflow.daily_document(self.user,self.day,self.co)
        self.assertEqual(a.pk,b.pk);self.assertEqual(Order.objects.count(),1)
        self.assertIn(order.commercial_number,PdfReader(BytesIO(a.data)).pages[0].extract_text())
    def test_ct12_monthly_closure(self):
        for n in range(30):
            order=Order.objects.create(company=self.co,client=self.client_record,date=self.day,slot=str(n),time=time(6),shift='NOTURNO',idempotency_key='monthly-'+str(n))
            OrderItem.objects.create(order=order,product=self.product,product_name=self.product.name,unit='UN',quantity=10)
            self.released(order)
        closure=workflow.close(self.user,self.co,self.client_record,self.day.replace(day=1))
        self.assertEqual(closure.lines.count(),30);self.assertEqual(closure.total,Decimal('375.00'))
        reader=PdfReader(BytesIO(closure.document.data));self.assertGreater(len(reader.pages),1)
        text=' '.join(page.extract_text() for page in reader.pages)
        for order in Order.objects.all():self.assertIn(order.commercial_number,text)
        self.assertEqual(workflow.close(self.user,self.co,self.client_record,self.day.replace(day=1)).pk,closure.pk)
    def test_ct13_history_never_orders(self):
        batch=self.stage_file('auditoria_');self.assertEqual(batch.rows.count(),82)
        self.assertFalse(batch.rows.filter(billable=True).exists());self.assertEqual(Order.objects.count(),0)
    def test_ct14_forecast_never_orders(self):
        batch=self.stage_file('previsao_');self.assertEqual(batch.rows.count(),31)
        self.assertEqual(Order.objects.count(),0)
    def test_ct15_legacy_candidates_inactive(self):
        batch=self.stage_file('recorrencias_');self.assertEqual(batch.rows.count(),101)
        self.assertFalse(batch.rows.filter(active=True).exists())
        self.assertEqual(batch.rows.first().raw['ativo_original'],'NÃO')
        self.assertEqual(Recurrence.objects.count(),1) # only synthetic fixture
    def test_ct16_reprint_idempotence(self):
        order,doc=self.issued();again=workflow.issue(self.user,order.pk)
        self.assertEqual(doc.pk,again.pk);self.assertEqual(bytes(doc.data),bytes(again.data))
        self.assertEqual(Order.objects.count(),1);self.assertEqual(Document.objects.count(),1)
    def test_ct17_pdf_failure_recovery(self):
        order=self.prepare();order.status='CONFERIDO';order.baker='TESTE';order.save()
        Price.objects.create(company=self.co,client=self.client_record,product=self.product,amount=1,valid_from=self.day)
        with patch('core.pdf.receipts',side_effect=RuntimeError('Falha artificial de renderização')):
            with self.assertRaises(RuntimeError):workflow.issue(self.user,order.pk)
        order.refresh_from_db();self.assertEqual(order.status,'CONFERIDO');self.assertEqual(Document.objects.count(),0)
        self.assertIsNone(order.items.get().unit_price_snapshot)
        workflow.issue(self.user,order.pk);self.assertEqual(Document.objects.count(),1)
    def test_ct18_restore_complete_backup(self):
        self.released()
        # Simula IDs de permissões diferentes após evolução incremental do banco.
        from django.contrib.auth.models import Permission
        Permission.objects.filter(content_type__app_label='core',codename='add_candidate').update(id=9999)
        original_databases=self.__class__.databases
        self.__class__.databases=original_databases|{'restore_validation'}
        try:result=restore_check()
        finally:self.__class__.databases=original_databases
        self.assertTrue(result['restored']);self.assertEqual(result['counts']['documents'],1)
        self.assertEqual(result['counts']['orders'],1);self.assertGreater(result['counts']['audit'],0)
    def test_ct19_denied_attempt_logged(self):
        user=User.objects.create_user('no_permission')
        with self.assertRaises(PermissionDenied): prepare(user,self.day)
        self.assertTrue(Audit.objects.filter(actor=user,action='ACESSO_NEGADO').exists())
        with self.assertRaises(ValidationError): financial_operation(user)
        with self.assertRaises(PermissionDenied):workflow.close(user,self.co,self.client_record,self.day.replace(day=1))
        self.assertTrue(Audit.objects.filter(actor=user,reason='core.close_month').exists())
    def test_ct20_review_cannot_create_order(self):
        candidate=self.stage_file('auditoria_').rows.first()
        with self.assertRaises(ValidationError):review(self.user,candidate,'')
        review(self.user,candidate,'Revisão humana')
        with self.assertRaises(ValidationError):workflow.reconcile(self.user,candidate,'','','')
        a=workflow.reconcile(self.user,candidate,'NOTA-ORIGINAL-123','Foto artificial identificada','Conciliação de teste')
        b=workflow.reconcile(self.user,candidate,'NOTA-ORIGINAL-123','Foto artificial identificada','Conciliação de teste')
        self.assertEqual(a.pk,b.pk);self.assertEqual(Order.objects.count(),0)
        self.assertEqual(Document.objects.count(),0)
    def test_staging_idempotent(self):
        a=self.stage_file('auditoria_');b=self.stage_file('auditoria_')
        self.assertEqual(a.pk,b.pk);self.assertEqual(Candidate.objects.count(),82)
    def test_audit_database_immutable(self):
        event=Audit.objects.create(entity='teste',action='TEST')
        with self.assertRaises(DatabaseError),transaction.atomic(): Audit.objects.filter(pk=event.pk).update(action='ALTERADO')
    def test_legacy_database_constraint(self):
        candidate=self.stage_file('previsao_').rows.first()
        with self.assertRaises(DatabaseError),transaction.atomic(): Candidate.objects.filter(pk=candidate.pk).update(billable=True)
    def test_zero_quantity_and_future_standard(self):
        order=self.prepare();adjust(self.user,order.pk,Decimal(0),'Sem produção hoje')
        self.assertEqual(production(Order.objects.all()),[])
        self.rule.refresh_from_db();self.assertEqual(self.rule.quantity,10)
    def test_ui_login_csrf_and_scope(self):
        self.assertEqual(self.client.get('/').status_code,302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get('/').status_code,200)
        self.assertEqual(self.client.get('/staging/').status_code,200)
        from django.test import Client as HTTPClient
        secured=HTTPClient(enforce_csrf_checks=True);secured.force_login(self.user)
        self.assertEqual(secured.post('/',{'action':'prepare'}).status_code,403)
    def test_price_specific_and_overlap(self):
        Price.objects.create(company=self.co,product=self.product,amount=1,valid_from=self.day)
        Price.objects.create(company=self.co,product=self.product,client=self.client_record,amount=2,valid_from=self.day)
        self.assertEqual(price_for(self.co,self.client_record,self.product,self.day),2)
        Price.objects.create(company=self.co,product=self.product,client=self.client_record,amount=3,valid_from=self.day)
        with self.assertRaises(ValidationError): price_for(self.co,self.client_record,self.product,self.day)
    def test_unauthorized_company(self):
        user=User.objects.create_user('outsider')
        with self.assertRaises(PermissionDenied): activate(user,self.rule,'Teste')
        self.assertTrue(Audit.objects.filter(actor=user,action='ACESSO_NEGADO').exists())

    def test_closed_order_is_not_demoted_by_production(self):
        order,doc=self.released();check_production(self.user,self.day)
        order.refresh_from_db();self.assertEqual(order.status,'LIBERADO_FECHAMENTO')
    def test_document_endpoint_company_scope(self):
        order,doc=self.issued()
        user=User.objects.create_user('foreign')
        self.client.force_login(user)
        self.assertEqual(self.client.get('/documentos/'+str(doc.pk)+'/').status_code,404)
    def test_recurring_extra_items_and_exception(self):
        other=Product.objects.create(company=self.co,name='Segundo produto')
        RuleItem.objects.create(rule=self.rule,product=other,quantity=5)
        order=self.prepare();self.assertEqual(order.items.count(),2)
        self.assertEqual(sum(row['total'] for row in production(Order.objects.all())),15)
    def test_suspension_does_not_create_order(self):
        RuleException.objects.create(rule=self.rule,date=self.day,suspended=True,reason='Feriado teste')
        self.assertEqual(prepare(self.user,self.day),0)
        self.assertEqual(Order.objects.count(),0)
    def test_non_synthetic_finance_blocked(self):
        order=self.prepare();order.synthetic=False;order.save()
        with self.assertRaises(ValidationError):workflow.issue(self.user,order.pk)
    def test_cancelled_never_closes(self):
        order,doc=self.released();workflow.cancel(self.user,order.pk,'Teste')
        self.assertEqual(workflow.eligible(self.user,self.co,self.client_record,self.day.replace(day=1)).count(),0)
    def test_duplicate_and_incomplete_reconciliation_blocked(self):
        batch=self.stage_file('auditoria_');a,b=list(batch.rows.all()[:2])
        review(self.user,a,'Revisão');review(self.user,b,'Revisão')
        workflow.reconcile(self.user,a,'NOTA-1','Evidência teste','Conciliação teste')
        with self.assertRaises(ValidationError):workflow.reconcile(self.user,b,'NOTA-1','Evidência teste','Conciliação teste')
    def test_manual_order_ui_multiple_items_idempotent(self):
        import uuid
        self.client.force_login(self.user)
        key=str(uuid.uuid4())
        data={'company':str(self.co.pk),'client':str(self.client_record.pk),'date':str(self.day),'time':'06:00','slot':'EXTRA','shift':'DIURNO','baker':'TESTE','driver':'','notes':'','key':key,'form-TOTAL_FORMS':'2','form-INITIAL_FORMS':'0','form-MIN_NUM_FORMS':'0','form-MAX_NUM_FORMS':'100','form-0-product':str(self.product.pk),'form-0-quantity':'3','form-1-product':str(self.product.pk),'form-1-quantity':'4'}
        response=self.client.post('/novo-pedido/',data)
        self.assertEqual(response.status_code,302)
        response=self.client.post('/novo-pedido/',data)
        self.assertEqual(response.status_code,302)
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(Order.objects.get().items.count(),2)
    def test_all_operator_pages_render(self):
        order=self.prepare();self.client.force_login(self.user)
        for url in ['/ajuda/','/cadastros/empresas/','/cadastros/clientes/','/cadastros/produtos/','/cadastros/precos/','/cadastros/recorrencias/','/fechamento/','/auditoria/','/pedidos/'+str(order.pk)+'/','/novo-pedido/']:
            self.assertEqual(self.client.get(url).status_code,200,url)
    def test_upload_staging_is_private_and_nonbillable(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.user)
        response=self.client.post('/staging/',{'file':SimpleUploadedFile('previsao_teste.csv',b'client,qty\nARTIFICIAL,12\n',content_type='text/csv')})
        self.assertEqual(response.status_code,302)
        self.assertEqual(Candidate.objects.count(),1)
        self.assertEqual(Order.objects.count(),0)
        self.assertEqual(Candidate.objects.get().category,'PREVISAO')
    def test_upload_rejects_malformed_csv(self):
        with self.assertRaises(ValidationError):stage_bytes(b'one,two\n1,2,3\n','teste.csv')

    def test_cancellation_supersedes_daily_document(self):
        order,doc=self.issued();daily=workflow.daily_document(self.user,self.day,self.co)
        workflow.cancel(self.user,order.pk,'Cancelamento teste')
        daily.refresh_from_db();self.assertTrue(daily.superseded)
    def test_company_documents_and_closures_do_not_mix(self):
        first=self.prepare()
        company=Company.objects.create(code='OTHER',name='OUTRA EMPRESA ARTIFICIAL')
        client=Client.objects.create(company=company,name='OUTRO CLIENTE')
        product=Product.objects.create(company=company,name='OUTRO PRODUTO')
        second=Order.objects.create(company=company,client=client,date=self.day,slot='1',time=time(6),shift='DIURNO',idempotency_key='other-company')
        OrderItem.objects.create(order=second,product=product,product_name=product.name,unit='UN',quantity=10)
        first,d1=self.released(first);second,d2=self.released(second)
        text1=' '.join(p.extract_text() for p in PdfReader(BytesIO(d1.data)).pages)
        text2=' '.join(p.extract_text() for p in PdfReader(BytesIO(d2.data)).pages)
        self.assertNotIn('OUTRA EMPRESA ARTIFICIAL',text1)
        self.assertIn('OUTRA EMPRESA ARTIFICIAL',text2)
        self.assertNotEqual(d1.sha256,d2.sha256)
        closure=workflow.close(self.user,self.co,self.client_record,self.day.replace(day=1))
        self.assertEqual(closure.lines.count(),1);self.assertEqual(closure.total,Decimal('12.50'))
