import uuid
from datetime import time,timedelta
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User,Permission
from django.core.exceptions import PermissionDenied,ValidationError
from django.urls import reverse
from django.utils import timezone
from .models import Company,Client,Product,Price,Order,OrderItem,Receivable,Payment,Document,Membership
from .billing import configure_item
from .sales import recognize_delivered_sales,record_external_invoice
from .management_services import balances,receive
from .statements import create_statement
from . import workflow


class SalesTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor-vendas','','test-only')
        self.co=Company.objects.create(code='TECO',name='Empresa artificial',legal_name='Empresa artificial de teste',cnpj='00000000000000',address='Endereço artificial',phone='Contato artificial',operational_enabled=True)
        self.customer=Client.objects.create(company=self.co,name='Cliente artificial')
        self.day=timezone.localdate()-timedelta(days=1)
        self.product=Product.objects.create(company=self.co,name='Produto artificial 65g',unit='UN',unit_weight_g=65)
        Price.objects.create(company=self.co,client=self.customer,product=self.product,amount=Decimal('8.30'),billing_unit='KG',valid_from=self.day)
        self.client.force_login(self.user)

    def order(self,quantity=450,synthetic=False):
        order=Order.objects.create(company=self.co,client=self.customer,date=self.day,time=time(0),slot='Artificial',synthetic=synthetic,idempotency_key=str(uuid.uuid4()))
        configure_item(OrderItem(order=order,product=self.product,product_name=self.product.name,unit='UN',quantity=Decimal(quantity))).save()
        return order

    def recognize(self):
        return recognize_delivered_sales(self.user,self.customer,self.day,self.day,30,'Usuário confirmou as entregas artificiais.')

    def test_delivered_sales_feed_revenue_history_and_receivable_without_fiscal_document(self):
        order=self.order();self.order();account=self.recognize()
        self.assertEqual(account.amount,Decimal('485.56'));self.assertIsNone(account.due_on);self.assertEqual(account.terms_days,30)
        order.refresh_from_db();self.assertEqual(order.status,'ENTREGUE');self.assertIsNotNone(order.delivered_at)
        self.assertIsNone(order.issued_at);self.assertEqual(order.issued_snapshot,{})
        self.assertFalse(Document.objects.exists());self.assertFalse(Payment.objects.exists())
        response=self.client.get('/')
        self.assertEqual(response.context['revenue'],account.amount)
        self.assertEqual(response.context['open_total'],account.amount)
        self.assertEqual(response.context['awaiting_invoice_total'],account.amount)
        self.assertEqual(response.context['overdue_total'],0)
        self.assertEqual(response.context['sold_count'],2)

    def test_retries_are_idempotent_and_preserve_due_date(self):
        self.order();account=self.recognize();self.assertEqual(self.recognize().pk,account.pk)
        record_external_invoice(self.user,account,'NF-ARTIFICIAL-001',timezone.localdate())
        self.assertEqual(self.recognize().pk,account.pk)
        self.assertEqual(Receivable.objects.count(),1)
        account.refresh_from_db();self.assertEqual(account.due_on,timezone.localdate()+timedelta(days=30))

    def test_overlap_does_not_create_duplicate_receivable(self):
        self.order();self.recognize();self.order()
        with self.assertRaises(ValidationError):self.recognize()
        self.assertEqual(Receivable.objects.count(),1)

    def test_external_invoice_calculates_due_date_and_preserves_payment_balance(self):
        self.order();account=self.recognize()
        self.assertEqual(balances(self.user,timezone.localdate()+timedelta(days=500))[0].days_late,0)
        response=self.client.post(reverse('payment',args=[account.pk]),{'action':'external_invoice','number':'NF-ARTIFICIAL-002','issued_on':str(timezone.localdate())})
        self.assertEqual(response.status_code,302)
        account.refresh_from_db();self.assertEqual(account.due_on,timezone.localdate()+timedelta(days=30))
        self.assertEqual(self.client.get('/').context['awaiting_invoice_total'],0)
        receive(self.user,account,Decimal('42.78'),timezone.localdate(),'PAGAMENTO-ARTIFICIAL')
        self.assertEqual(balances(self.user)[0].balance,Decimal('200'))

    def test_external_invoice_rejects_future_and_conflicting_changes(self):
        self.order();account=self.recognize()
        with self.assertRaises(ValidationError):record_external_invoice(self.user,account,'NF-ART',timezone.localdate()+timedelta(days=1))
        first=record_external_invoice(self.user,account,'NF-ART',timezone.localdate())
        self.assertEqual(record_external_invoice(self.user,account,'NF-ART',timezone.localdate()).pk,first.pk)
        with self.assertRaises(ValidationError):record_external_invoice(self.user,account,'OUTRA',timezone.localdate())

    def test_missing_price_rolls_back_all_sales(self):
        order=self.order();Price.objects.all().update(superseded=True)
        with self.assertRaises(ValidationError):self.recognize()
        order.refresh_from_db();self.assertEqual(order.status,'PRE_LANCADO');self.assertFalse(Receivable.objects.exists())

    def test_test_orders_do_not_become_real_accounts(self):
        self.order(synthetic=True)
        with self.assertRaises(ValidationError):self.recognize()
        self.assertFalse(Receivable.objects.exists())

    def test_linked_orders_cannot_be_cancelled_without_financial_review(self):
        order=self.order();self.recognize()
        with self.assertRaises(ValidationError):workflow.cancel(self.user,order.pk,'Cancelamento artificial')
        order.refresh_from_db();self.assertEqual(order.status,'ENTREGUE')

    def test_confirmed_deliveries_can_be_included_in_statement_without_fake_receipt(self):
        order=self.order();account=self.recognize()
        workflow.release(self.user,order.pk)
        statement=create_statement(self.user,self.co,self.customer,self.day,self.day)
        self.assertEqual(statement.total,account.amount)
        order.refresh_from_db();self.assertIsNone(order.issued_at)

    def test_scope_and_confirmation_required(self):
        self.order()
        response=self.client.post(reverse('client_sales',args=[self.customer.pk]),{'start':str(self.day),'end':str(self.day),'terms_days':'30','evidence':'Confirmação artificial'})
        self.assertEqual(response.status_code,302);self.assertFalse(Receivable.objects.exists())
        user=User.objects.create_user('financeiro-outra')
        co=Company.objects.create(code='OUTRA',name='Outra artificial');Membership.objects.create(user=user,company=co)
        user.user_permissions.add(Permission.objects.get(codename='add_receivable'),Permission.objects.get(codename='confirm_delivery'))
        with self.assertRaises(PermissionDenied):recognize_delivered_sales(user,self.customer,self.day,self.day,30,'Confirmação artificial')

    def test_pending_due_accounts_render_in_finance_and_client_history(self):
        self.order();account=self.recognize()
        for url in ['/financeiro/',reverse('client_detail',args=[self.customer.pk]),reverse('payment',args=[account.pk])]:
            response=self.client.get(url);self.assertEqual(response.status_code,200);self.assertContains(response,'30 dias após emissão')
