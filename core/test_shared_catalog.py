import uuid
from datetime import time,timedelta
from decimal import Decimal
from unittest.mock import patch
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from .catalog import available_products,products_for_user
from .client_setup import save_recurring_items
from .forms import ManualItemForm,InlinePriceForm,ClientRoutineForm,PriceForm
from .logistics_services import register_production
from .management_services import set_current_price
from .models import Company,Client,Product,Price,Membership,Order,OrderItem,ProductionRecord,Recurrence
from .operations import activate_operation,company_checks
from .proposal_services import resolve_lines
from .receipt_layout import receipt_logo
from .services import price_for,prepare
from . import workflow


class SharedCatalogTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.today=timezone.localdate()
        self.teco=Company.objects.create(code='TECO',name='TECO ARTIFICIAL',legal_name='TECO ARTIFICIAL',cnpj='11111111111111',address='Endereço artificial',phone='Contato artificial')
        self.nona=Company.objects.create(code='NONA',name='NONA ARTIFICIAL',legal_name='NONA ARTIFICIAL',cnpj='22222222222222',address='Endereço artificial',phone='Contato artificial')
        self.other=Company.objects.create(code='OTHER',name='Outra empresa artificial')
        self.bread=Product.objects.create(company=self.teco,name='Pão artificial',production_cost=Decimal('1.25'))
        self.meal=Product.objects.create(company=self.nona,name='Refeição artificial',production_cost=Decimal('4'))
        self.external=Product.objects.create(company=self.other,name='Produto externo artificial')
        self.teco_client=Client.objects.create(company=self.teco,name='Cliente TECO artificial')
        self.nona_client=Client.objects.create(company=self.nona,name='Cliente NONA artificial')
        set_current_price(self.user,self.teco,self.bread,Decimal('3'))
        set_current_price(self.user,self.nona,self.meal,Decimal('10'))
        self.client.force_login(self.user)

    def test_both_companies_use_existing_catalogue_without_copies(self):
        expected={self.bread.pk,self.meal.pk}
        for company in [self.teco,self.nona]:
            self.assertEqual(set(available_products(company).values_list('pk',flat=True)),expected)
        self.assertEqual(list(available_products(self.other)),[self.external])
        self.assertEqual(Product.objects.count(),3)
        self.assertEqual(Order.objects.count(),0)
        self.assertEqual(Recurrence.objects.count(),0)

    def test_new_regular_and_quick_products_are_automatically_available_to_both(self):
        response=self.client.post('/cadastros/produtos/',{'company':str(self.teco.pk),'name':'Novo pão artificial','unit':'UN','production_cost':'1','amount':'2'})
        self.assertEqual(response.status_code,302)
        response=self.client.post('/cadastros/rapidos/produtos/',{'request_key':str(uuid.uuid4()),'quick_product-company':str(self.nona.pk),'quick_product-name':'Nova refeição artificial','quick_product-unit':'UN','quick_product-production_cost':'2','quick_product-amount':'8'})
        self.assertEqual(response.status_code,201)
        for company in [self.teco,self.nona]:
            products=available_products(company)
            self.assertEqual(products.count(),4)
            self.assertEqual(products.filter(name__startswith='Nov').count(),2)
        self.assertEqual(Product.objects.count(),5)
        self.assertEqual(Order.objects.count(),0)

    def test_shared_base_company_override_and_negotiated_prices_have_correct_priority(self):
        self.assertEqual(price_for(self.nona,self.nona_client,self.bread,self.today),3)
        self.assertEqual(price_for(self.teco,self.teco_client,self.meal,self.today),10)
        set_current_price(self.user,self.nona,self.bread,Decimal('4'))
        set_current_price(self.user,self.nona,self.bread,Decimal('2.5'),self.nona_client)
        set_current_price(self.user,self.teco,self.bread,Decimal('1.8'),self.teco_client)
        self.assertEqual(price_for(self.nona,self.nona_client,self.bread,self.today),Decimal('2.5'))
        self.assertEqual(price_for(self.nona,None,self.bread,self.today),4)
        self.assertEqual(price_for(self.teco,self.teco_client,self.bread,self.today),Decimal('1.8'))
        set_current_price(self.user,self.teco,self.bread,Decimal('5'))
        self.assertEqual(price_for(self.nona,self.nona_client,self.bread,self.today),Decimal('2.5'))
        self.assertEqual(price_for(self.nona,None,self.bread,self.today),4)
        self.assertEqual(price_for(self.teco,None,self.bread,self.today),5)

    def test_shared_base_alone_satisfies_product_and_price_activation_checks(self):
        # A company can start even when the only products/prices originated in the other brand.
        Price.objects.filter(product=self.meal).delete();self.meal.delete()
        checks=company_checks(self.nona)
        self.assertTrue(all(bool(ready) for label,ready,url in checks))
        activate_operation(self.user,self.nona)
        self.nona.refresh_from_db();self.assertTrue(self.nona.operational_enabled)

    def test_customer_prices_and_routine_forms_include_shared_products(self):
        for form in [InlinePriceForm(company=self.nona),ClientRoutineForm(company=self.nona),ManualItemForm(user=self.user)]:
            self.assertIn(self.bread,form.fields['product'].queryset)
        response=self.client.post(f'/clientes/{self.nona_client.pk}/',{'action':'price','product':str(self.bread.pk),'amount':'2.25'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(price_for(self.nona,self.nona_client,self.bread,self.today),Decimal('2.25'))

    def test_manual_order_recurs_with_shared_product_and_remains_in_selling_company(self):
        activate_operation(self.user,self.nona)
        tomorrow=self.today+timedelta(days=1)
        self.nona_client.recurring_weekdays=[tomorrow.isoweekday()];self.nona_client.save()
        data={'company':str(self.nona.pk),'client':str(self.nona_client.pk),'date':str(tomorrow),'time':'06:00','slot':'Entrega artificial','shift':'NOTURNO','baker':'Padeiro artificial','key':str(uuid.uuid4()),'repeat_weekly':'on','form-TOTAL_FORMS':'1','form-INITIAL_FORMS':'0','form-0-product':str(self.bread.pk),'form-0-quantity':'10','form-0-client_price':'2.5'}
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,302)
        order=Order.objects.get();self.assertFalse(order.synthetic)
        self.assertEqual(order.company,self.nona);self.assertEqual(order.items.get().product,self.bread)
        rule=Recurrence.objects.get();self.assertEqual(rule.company,self.nona);self.assertTrue(rule.active)
        self.assertEqual(prepare(self.user,tomorrow+timedelta(days=7),automatic_only=True),1)
        scheduled=Order.objects.exclude(pk=order.pk).get()
        self.assertEqual(scheduled.company,self.nona);self.assertEqual(scheduled.items.get().product,self.bread)
        self.assertEqual(price_for(self.nona,self.nona_client,self.bread,scheduled.date),Decimal('2.5'))

    def test_real_receipts_use_selling_company_brand_and_preserve_values(self):
        for company,customer,product in [(self.nona,self.nona_client,self.bread),(self.teco,self.teco_client,self.meal)]:
            with self.subTest(company=company.code):
                activate_operation(self.user,company)
                order=Order.objects.create(company=company,client=customer,date=self.today,time=time(6),slot='Entrega artificial',shift='NOTURNO',baker='Padeiro artificial',synthetic=False,status='CONFERIDO',idempotency_key=str(uuid.uuid4()))
                item=OrderItem.objects.create(order=order,product=product,product_name=product.name,unit=product.unit,quantity=10)
                expected=price_for(company,customer,product,self.today)
                with patch('core.receipt_layout.receipt_logo',wraps=receipt_logo) as logo:
                    document=workflow.issue(self.user,order.pk)
                    self.assertTrue(logo.called)
                    self.assertTrue(all(call.args==(company.code,) for call in logo.call_args_list))
                original=bytes(document.data);order.refresh_from_db();item.refresh_from_db()
                self.assertEqual(document.company,company)
                self.assertEqual(order.issued_snapshot['company_code'],company.code)
                self.assertEqual(item.unit_price_snapshot,expected)
                set_current_price(self.user,product.company,product,Decimal('50'))
                self.assertEqual(bytes(workflow.issue(self.user,order.pk).data),original)

    def test_proposals_resolve_shared_base_and_customer_price(self):
        line=dict(product=self.bread,description='',quantity=Decimal(10),unit='',unit_price=None)
        self.assertEqual(resolve_lines(self.nona,None,self.today,[line])[1],30)
        set_current_price(self.user,self.nona,self.bread,Decimal('2.5'),self.nona_client)
        self.assertEqual(resolve_lines(self.nona,self.nona_client,self.today,[line])[1],25)

    def test_production_uses_shared_cost_but_records_the_selected_company(self):
        record=ProductionRecord(company=self.nona,product=self.bread,date=self.today,shift='NOTURNO',batch='LOTE ARTIFICIAL',quantity=10,losses=0,baker='Padeiro artificial')
        register_production(self.user,record)
        self.assertEqual(record.company,self.nona);self.assertEqual(record.product,self.bread)
        self.assertEqual(record.cost_snapshot,Decimal('1.25'))
        self.assertFalse(ProductionRecord.objects.filter(company=self.teco).exists())

    def test_company_user_sees_shared_catalogue_and_base_without_other_clients_conditions(self):
        private=set_current_price(self.user,self.teco,self.bread,Decimal('0.1'),self.teco_client)
        own=set_current_price(self.user,self.nona,self.bread,Decimal('2.5'),self.nona_client)
        reader=User.objects.create_user('leitor-nona');Membership.objects.create(user=reader,company=self.nona)
        self.client.force_login(reader)
        self.assertEqual(set(products_for_user(reader).values_list('pk',flat=True)),{self.bread.pk,self.meal.pk})
        response=self.client.get(f'/produtos/{self.bread.pk}/')
        self.assertEqual(response.status_code,200);self.assertEqual(response.context['sale'],3)
        self.assertIn(own,response.context['prices']);self.assertNotIn(private,response.context['prices'])
        self.assertNotContains(response,self.teco_client.name)
        self.assertEqual(self.client.get(f'/clientes/{self.teco_client.pk}/').status_code,404)
        self.assertEqual(self.client.get(f'/produtos/{self.external.pk}/').status_code,404)
        response=self.client.get('/cadastros/precos/')
        self.assertNotContains(response,self.teco_client.name)
        self.assertContains(response,'Padrão do catálogo TECO e NONA')

    def test_unrelated_companies_and_clients_still_cannot_be_crossed(self):
        for company,customer,product in [(self.nona,self.nona_client,self.external),(self.other,None,self.bread),(self.nona,self.teco_client,self.bread)]:
            with self.subTest(company=company.code,product=product.name):
                with self.assertRaises(ValidationError):price_for(company,customer,product,self.today)
                with self.assertRaises(ValidationError):set_current_price(self.user,company,product,Decimal(1),customer)
        form=PriceForm({'company':str(self.nona.pk),'client':str(self.teco_client.pk),'product':str(self.bread.pk),'amount':'1'},user=self.user)
        self.assertFalse(form.is_valid())
        self.nona_client.recurring_weekdays=[self.today.isoweekday()];self.nona_client.save()
        with self.assertRaises(ValidationError):save_recurring_items(self.user,self.nona_client,[{'product':self.external,'quantity':Decimal(10)}],'Entrega artificial',time(6),'NOTURNO')
