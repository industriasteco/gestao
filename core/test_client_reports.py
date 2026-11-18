import hashlib
import uuid
from datetime import time,timedelta
from decimal import Decimal
from io import BytesIO
from pypdf import PdfReader
from django.test import TestCase
from django.contrib.auth.models import User,Permission
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from .models import Company,Client,Product,Price,Order,OrderItem,Audit,Document,Receivable,Membership
from .billing import configure_item
from .client_reports import create_client_report,orders_snapshot


class ClientReportTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor-relatorio','','test-only')
        self.company=Company.objects.create(code='TECO',name='Empresa artificial',operational_enabled=True)
        self.customer=Client.objects.create(company=self.company,name='Cliente artificial')
        self.day=timezone.localdate()-timedelta(days=1)
        self.product=Product.objects.create(company=self.company,name='Produto artificial',unit='UN',unit_weight_g=65)
        Price.objects.create(company=self.company,client=self.customer,product=self.product,amount=Decimal('8.30'),billing_unit='KG',valid_from=self.day)
        self.client.force_login(self.user)

    def order(self,quantity=450,synthetic=False,status='PRE_LANCADO'):
        order=Order.objects.create(company=self.company,client=self.customer,date=self.day,time=time(0),slot='Pedido artificial',idempotency_key=str(uuid.uuid4()),synthetic=synthetic,status=status)
        item=configure_item(OrderItem(order=order,product=self.product,product_name=self.product.name,unit='UN',quantity=Decimal(quantity)))
        item.save();return order

    def test_real_draft_orders_report_without_confirming_delivery_or_creating_debt(self):
        first=self.order();self.order();self.order(synthetic=True);self.order(status='CANCELADO')
        doc=create_client_report(self.user,self.customer,self.day,self.day)
        text=' '.join(p.extract_text() for p in PdfReader(BytesIO(bytes(doc.data))).pages)
        self.assertIn('485,56',text)  # Duas linhas de 450 UN, arredondadas individualmente.
        self.assertIn('58,5 KG',text);self.assertIn('900 UN',text)
        self.assertNotIn('HOMOLOG',text.upper());self.assertNotIn('NAO COBRAR',text.upper())
        first.refresh_from_db();self.assertEqual(first.status,'PRE_LANCADO');self.assertIsNone(first.delivered_at)
        self.assertFalse(Receivable.objects.exists())
        self.assertEqual(doc.sha256,hashlib.sha256(bytes(doc.data)).hexdigest())

    def test_idempotence_and_changed_quantities_create_preserved_revision(self):
        order=self.order()
        doc=create_client_report(self.user,self.customer,self.day,self.day)
        self.assertEqual(create_client_report(self.user,self.customer,self.day,self.day).pk,doc.pk)
        self.assertEqual(Audit.objects.filter(action='GERAR_RELATORIO_PEDIDOS').count(),1)
        order.items.update(quantity=500)
        updated=create_client_report(self.user,self.customer,self.day,self.day)
        self.assertNotEqual(updated.pk,doc.pk)
        self.assertEqual(Document.objects.count(),2)
        self.assertEqual(bytes(Document.objects.get(pk=doc.pk).data),bytes(doc.data))

    def test_two_daily_deliveries_remain_distinct_and_morning_comes_first(self):
        afternoon=self.order(quantity=30);afternoon.slot='Tarde';afternoon.save()
        morning=self.order(quantity=35);morning.slot='Manhã';morning.save()
        snapshot=orders_snapshot(self.customer,self.day,self.day,[afternoon,morning])
        self.assertEqual([row['period'] for row in snapshot['items']],['Manhã','Tarde'])
        self.assertEqual(snapshot['orders'],2)
        document=create_client_report(self.user,self.customer,self.day,self.day)
        text=' '.join(page.extract_text() for page in PdfReader(BytesIO(bytes(document.data))).pages)
        self.assertIn('Entrega',text);self.assertIn('Manhã',text);self.assertIn('Tarde',text)
        self.assertIn('35,07',text)

    def test_report_saved_in_client_history_and_pdf_route_requires_scope(self):
        self.order()
        response=self.client.post(reverse('client_report_generate',args=[self.customer.pk]),{'start':str(self.day),'end':str(self.day)})
        self.assertEqual(response.status_code,302)
        doc=Document.objects.get();self.assertIn(str(doc.pk),response.url)
        self.assertContains(self.client.get(reverse('client_detail',args=[self.customer.pk])),'Abrir relatório')
        response=self.client.get(response.url)
        self.assertEqual(response['Content-Type'],'application/pdf');self.assertIn('no-store',response['Cache-Control'])
        other=Company.objects.create(code='OUTRA',name='Empresa artificial outra',operational_enabled=True)
        user=User.objects.create_user('leitor-relatorio');Membership.objects.create(user=user,company=other)
        user.user_permissions.add(Permission.objects.get(codename='view_clientstatement'))
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('client_report_document',args=[self.customer.pk,doc.pk])).status_code,404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse('client_report_document',args=[self.customer.pk,doc.pk])).status_code,302)

    def test_invalid_period_and_test_only_orders_block_generation(self):
        self.order(synthetic=True)
        with self.assertRaises(ValidationError):create_client_report(self.user,self.customer,self.day,self.day)
        self.order()
        with self.assertRaises(ValidationError):create_client_report(self.user,self.customer,self.day,self.day-timedelta(days=1))
        with self.assertRaises(ValidationError):create_client_report(self.user,self.customer,self.day,timezone.localdate()+timedelta(days=1))
        self.assertFalse(Document.objects.exists())

    def test_download_rejects_wrong_client_and_corrupted_pdf(self):
        self.order();doc=create_client_report(self.user,self.customer,self.day,self.day)
        other=Client.objects.create(company=self.company,name='Outro cliente artificial')
        self.assertEqual(self.client.get(reverse('client_report_document',args=[other.pk,doc.pk])).status_code,404)
        Document.objects.filter(pk=doc.pk).update(data=b'corrompido')
        self.assertEqual(self.client.get(reverse('client_report_document',args=[self.customer.pk,doc.pk])).status_code,409)

    def test_operational_context_and_new_orders_remain_real(self):
        response=self.client.get('/novo-pedido/')
        self.assertTrue(response.context['operational_mode'])
        self.assertNotContains(response,'Novo pedido de teste')
        self.order();self.company.operational_enabled=False;self.company.save()
        with self.assertRaises(ValidationError):create_client_report(self.user,self.customer,self.day,self.day)
