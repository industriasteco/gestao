from datetime import time
from decimal import Decimal
from io import BytesIO
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from pypdf import PdfReader
from .models import Company,Client,Product,Price,Order,OrderItem,Document,Driver,DeliveryRoute,RouteStop
from . import workflow
from .day_finalization import finalize_day
from .statements import create_statement,statement_action
from .logistics_services import build_manifest


class CustomerPurchaseOrderTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.company=Company.objects.create(code='NONA',name='NONA ARTIFICIAL',cnpj='11111111111111')
        self.customer=Client.objects.create(company=self.company,name='Cliente artificial',requires_purchase_order=True)
        self.product=Product.objects.create(company=self.company,name='Produto artificial')
        self.day=timezone.localdate()
        Price.objects.create(company=self.company,product=self.product,amount=Decimal('1.25'),valid_from=self.day)
        self.order=Order.objects.create(company=self.company,client=self.customer,date=self.day,time=time(6),slot='1',shift='NOTURNO',baker='Padeiro artificial',status='CONFERIDO',idempotency_key='purchase-order-test')
        OrderItem.objects.create(order=self.order,product=self.product,product_name=self.product.name,unit='UN',quantity=10)
        self.client.force_login(self.user)

    def issue(self,reference='OC-ART-456'):
        self.order.purchase_order=reference;self.order.save()
        doc=workflow.issue(self.user,self.order.pk)
        self.order.refresh_from_db()
        return doc

    def test_required_po_blocks_single_and_day_issue_without_creating_documents(self):
        with self.assertRaises(ValidationError):workflow.issue(self.user,self.order.pk)
        with self.assertRaises(ValidationError):finalize_day(self.user,self.day)
        self.assertEqual(Document.objects.count(),0)
        self.order.refresh_from_db();self.assertEqual(self.order.status,'CONFERIDO')

    def test_reference_is_printed_on_both_copies_and_frozen_at_issue(self):
        doc=self.issue()
        text=PdfReader(BytesIO(doc.data)).pages[0].extract_text()
        self.assertEqual(text.count('OC DO CLIENTE: OC-ART-456'),2)
        self.assertEqual(self.order.issued_snapshot['purchase_order'],'OC-ART-456')
        original=bytes(doc.data)
        with self.assertRaises(ValidationError):workflow.update_info(self.user,self.order.pk,{'purchase_order':'OUTRA-OC'},'Tentativa artificial após emissão')
        self.order.refresh_from_db();doc.refresh_from_db()
        self.assertEqual(self.order.purchase_order,'OC-ART-456');self.assertEqual(bytes(doc.data),original)

    def test_ibis_keeps_reference_and_four_portrait_pages(self):
        self.customer.name='IBIS';self.customer.save()
        doc=self.issue()
        reader=PdfReader(BytesIO(doc.data))
        self.assertEqual(len(reader.pages),4)
        for page in reader.pages:
            self.assertIn('OC DO CLIENTE: OC-ART-456',page.extract_text())
            self.assertLess(float(page.mediabox.width),float(page.mediabox.height))

    def test_order_edit_form_saves_purchase_order_before_issue(self):
        response=self.client.get(f'/pedidos/{self.order.pk}/')
        self.assertContains(response,'name="purchase_order"')
        response=self.client.post(f'/pedidos/{self.order.pk}/',{'action':'info','purchase_order':'CLIENTE-OC-007','shift':'NOTURNO','baker':'Padeiro artificial','separator':'','driver':'','notes':'','reason':'OC recebida do cliente artificial'})
        self.assertEqual(response.status_code,302)
        self.order.refresh_from_db();self.assertEqual(self.order.purchase_order,'CLIENTE-OC-007')
        self.assertEqual(self.client.get('/novo-pedido/').status_code,200)
        self.assertContains(self.client.get('/novo-pedido/'),'name="purchase_order"')

    def test_statement_and_approved_export_keep_the_frozen_reference(self):
        self.issue();workflow.deliver(self.user,self.order.pk,'Entrega artificial confirmada')
        statement=create_statement(self.user,self.company,self.customer,self.day.replace(day=1),self.day)
        self.assertEqual(statement.snapshot['items'][0]['purchase_order'],'OC-ART-456')
        text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(statement.document.data)).pages)
        self.assertIn('OC-ART-456',text)
        statement_action(self.user,statement,'send','Envio artificial ao cliente')
        statement_action(self.user,statement,'approve','Cliente artificial aprovou o fechamento')
        response=self.client.get(f'/fechamentos-clientes/{statement.pk}/exportar/')
        self.assertEqual(response.status_code,200)
        self.assertIn(b'Ordem_de_compra',response.content);self.assertIn(b'OC-ART-456',response.content)

    def test_romaneio_keeps_the_order_reference(self):
        self.issue()
        driver=Driver.objects.create(company=self.company,name='Motorista artificial')
        route=DeliveryRoute.objects.create(company=self.company,driver=driver,name='Rota artificial')
        RouteStop.objects.create(route=route,client=self.customer,sequence=1)
        manifest=build_manifest(self.user,route,self.day)
        self.assertIn('OC DO CLIENTE: OC-ART-456',manifest.lines.get().instructions)
        response=self.client.get(f'/romaneios/{manifest.pk}/pdf/')
        text='\n'.join(p.extract_text() for p in PdfReader(BytesIO(response.content)).pages)
        self.assertIn('OC-ART-456',text)

    def test_purchase_order_is_optional_when_customer_does_not_require_it(self):
        self.customer.requires_purchase_order=False;self.customer.save()
        document=workflow.issue(self.user,self.order.pk)
        self.assertTrue(bytes(document.data).startswith(b'%PDF'))

    def test_po_can_be_entered_only_at_monthly_billing_without_changing_receipts(self):
        self.customer.requires_purchase_order=False;self.customer.save()
        receipt=workflow.issue(self.user,self.order.pk);original=bytes(receipt.data)
        workflow.deliver(self.user,self.order.pk,'Entrega artificial anterior à OC mensal')
        statement=create_statement(self.user,self.company,self.customer,self.day.replace(day=1),self.day,purchase_order='OC-FECHAMENTO-789')
        self.assertEqual(statement.purchase_order,'OC-FECHAMENTO-789')
        self.assertEqual(statement.snapshot['items'][0]['purchase_order'],'OC-FECHAMENTO-789')
        text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(statement.document.data)).pages)
        self.assertIn('OC-FECHAMENTO-789',text)
        receipt.refresh_from_db();self.assertEqual(bytes(receipt.data),original)
        self.assertNotIn('OC-FECHAMENTO-789',PdfReader(BytesIO(receipt.data)).pages[0].extract_text())

    def test_monthly_reference_does_not_replace_a_purchase_order_already_on_the_order(self):
        self.issue('OC-PEDIDO-123');workflow.deliver(self.user,self.order.pk,'Entrega artificial confirmada')
        statement=create_statement(self.user,self.company,self.customer,self.day.replace(day=1),self.day,purchase_order='OC-GERAL-789')
        self.assertEqual(statement.purchase_order,'OC-GERAL-789')
        self.assertEqual(statement.snapshot['items'][0]['purchase_order'],'OC-PEDIDO-123')
