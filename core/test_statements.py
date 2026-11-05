from datetime import timedelta,time
from decimal import Decimal
from io import BytesIO
import uuid
from pypdf import PdfReader
from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import *
from .statements import create_statement,statement_action
from . import workflow

class StatementTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.company=Company.objects.create(code='TEST',name='Empresa artificial')
        self.customer=Client.objects.create(company=self.company,name='Cliente artificial',email='artificial@example.invalid')
        self.product=Product.objects.create(company=self.company,name='Pão artificial')
        self.today=timezone.localdate()
        self.client.force_login(self.user)

    def order(self,when=None,status='ENTREGUE',synthetic=True):
        order=Order.objects.create(company=self.company,client=self.customer,date=when or self.today,time=time(6),slot='Teste',synthetic=synthetic,
            status=status,delivered_at=timezone.now() if status in ['ENTREGUE','LIBERADO_FECHAMENTO'] else None,
            issued_snapshot={'total':'12.50'},commercial_number='ARTIFICIAL-'+str(uuid.uuid4())[:8],idempotency_key=str(uuid.uuid4()))
        OrderItem.objects.create(order=order,product=self.product,product_name=self.product.name,quantity=10,unit='UN',unit_price_snapshot=Decimal('1.25'))
        return order

    def generate(self,start=None,end=None):
        return create_statement(self.user,self.company,self.customer,start or self.today.replace(day=1),end or self.today)

    def test_selected_period_includes_only_confirmed_deliveries(self):
        self.order();self.order(status='PRE_LANCADO');self.order(when=self.today-timedelta(days=90))
        row=self.generate()
        self.assertEqual(row.total,Decimal('12.5'));self.assertEqual(row.lines.count(),1)
        self.assertEqual(Receivable.objects.count(),0)
        self.assertEqual(Order.objects.count(),3)
        self.assertEqual(row.snapshot['email'],'artificial@example.invalid')

    def test_repeated_generation_is_idempotent_and_overlapping_period_is_blocked(self):
        self.order();row=self.generate()
        self.assertEqual(self.generate().pk,row.pk)
        with self.assertRaises(ValidationError):self.generate(start=self.today-timedelta(days=45))
        self.assertEqual(ClientStatement.objects.count(),1)

    def test_document_is_preserved_when_catalogue_price_changes(self):
        self.order();row=self.generate();original=bytes(row.document.data)
        Price.objects.create(company=self.company,product=self.product,amount=999,valid_from=self.today)
        self.customer.name='Novo nome artificial';self.customer.save()
        row.refresh_from_db()
        self.assertEqual(row.total,Decimal('12.5'));self.assertEqual(row.snapshot['client'],'Cliente artificial')
        self.assertEqual(bytes(row.document.data),original)

    def test_approval_requires_send_and_evidence_then_allows_export(self):
        self.order();row=self.generate()
        with self.assertRaises(ValidationError):statement_action(self.user,row,'approve','Aprovação artificial do cliente')
        self.assertEqual(self.client.get(f'/fechamentos-clientes/{row.pk}/exportar/').status_code,409)
        statement_action(self.user,row,'send','Enviado ao e-mail artificial@example.invalid')
        statement_action(self.user,row,'approve','Cliente artificial aprovou por e-mail, referência TESTE-1')
        row.refresh_from_db();self.assertEqual(row.status,'APROVADO');self.assertIsNotNone(row.approved_at)
        response=self.client.get(f'/fechamentos-clientes/{row.pk}/exportar/')
        self.assertEqual(response.status_code,200);self.assertIn(b'P\xc3\xa3o artificial',response.content)
        self.assertIn(b'NAO EMITIR NOTA REAL',response.content)
        self.assertEqual(Receivable.objects.count(),0)

    def test_cancelled_draft_can_be_rebuilt_but_approved_cannot_be_cancelled(self):
        self.order();row=self.generate()
        statement_action(self.user,row,'cancel','Ajuste artificial para revisão')
        self.assertEqual(self.client.get(f'/fechamentos-clientes/{row.pk}/pdf/').status_code,409)
        new=self.generate();self.assertNotEqual(new.pk,row.pk)
        statement_action(self.user,new,'send','Envio artificial ao cliente')
        statement_action(self.user,new,'approve','Aprovação artificial recebida')
        with self.assertRaises(ValidationError):statement_action(self.user,new,'cancel','Cancelar artificialmente')

    def test_statement_pdf_lists_period_products_and_total(self):
        self.order();row=self.generate()
        response=self.client.get(f'/fechamentos-clientes/{row.pk}/pdf/')
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(response.content)).pages)
        self.assertIn('Pão artificial',text);self.assertIn('12,50',text)
        self.assertIn('1,2500',text);self.assertIn('HOMOLOGAÇÃO',text)
        self.assertEqual(self.client.get(f'/fechamentos-clientes/{row.pk}/').status_code,200)
        self.assertEqual(self.client.get('/fechamentos-clientes/').status_code,200)

    def test_statement_prevents_cancelling_included_order(self):
        order=self.order();self.generate()
        with self.assertRaises(ValidationError):workflow.cancel(self.user,order.pk,'Cancelar pedido artificial')
        order.refresh_from_db();self.assertEqual(order.status,'ENTREGUE')

    def test_preview_does_not_generate_document_or_statement(self):
        self.order()
        response=self.client.post('/fechamentos-clientes/',{'company':str(self.company.pk),'client':str(self.customer.pk),'start':str(self.today.replace(day=1)),'end':str(self.today),'action':'preview'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(len(response.context['preview']),1)
        self.assertEqual(ClientStatement.objects.count(),0)

    def test_missing_prices_and_mixed_real_test_orders_are_rejected(self):
        order=self.order();order.items.update(unit_price_snapshot=None)
        with self.assertRaises(ValidationError):self.generate()
        order.items.update(unit_price_snapshot=1)
        self.order(synthetic=False)
        with self.assertRaises(ValidationError):self.generate()
        self.assertEqual(ClientStatement.objects.count(),0)
