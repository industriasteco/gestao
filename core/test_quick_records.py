import uuid
from datetime import time
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase,Client as HTTPClient
from django.utils import timezone
from .models import Company,Client,Product,Price,Order,OrderItem,Audit,Membership
from .services import price_for


class QuickRecordsTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.company=Company.objects.create(code='NONA',name='NONA ARTIFICIAL')
        self.client.force_login(self.user)

    def customer_data(self,key=None):
        return {'request_key':str(key or uuid.uuid4()),'quick_client-company':str(self.company.pk),'quick_client-name':'Cliente artificial novo','quick_client-legal_name':'Razão social artificial','quick_client-tax_id':'11111111111111','quick_client-email':'cliente@example.invalid','quick_client-phone':'Telefone artificial','quick_client-address':'Endereço artificial','quick_client-notes':'Entregar na portaria artificial','quick_client-requires_purchase_order':'on'}

    def product_data(self,key=None):
        return {'request_key':str(key or uuid.uuid4()),'quick_product-company':str(self.company.pk),'quick_product-name':'Produto artificial novo','quick_product-unit':'KG','quick_product-production_cost':'1.2500','quick_product-amount':'2.7500'}

    def test_customer_is_persisted_with_full_details_without_creating_order(self):
        response=self.client.post('/cadastros/rapidos/clientes/',self.customer_data())
        self.assertEqual(response.status_code,201)
        customer=Client.objects.get(pk=response.json()['record']['id'])
        self.assertEqual(customer.company,self.company)
        self.assertEqual(customer.address,'Endereço artificial')
        self.assertEqual(customer.email,'cliente@example.invalid')
        self.assertEqual(customer.legal_name,'Razão social artificial')
        self.assertTrue(customer.requires_purchase_order)
        self.assertEqual(Order.objects.count(),0)
        self.assertTrue(Audit.objects.filter(entity=str(customer.pk),action='CADASTRO_RAPIDO').exists())

    def test_product_includes_unit_cost_and_sale_price_without_dates(self):
        response=self.client.post('/cadastros/rapidos/produtos/',self.product_data())
        self.assertEqual(response.status_code,201)
        product=Product.objects.get(pk=response.json()['record']['id'])
        self.assertEqual(product.unit,'KG');self.assertEqual(product.production_cost,Decimal('1.25'))
        price=Price.objects.get(product=product)
        self.assertEqual(price.amount,Decimal('2.75'));self.assertIsNone(price.valid_until)
        self.assertEqual(Order.objects.count(),0)

    def test_repeating_saved_request_does_not_duplicate_or_overwrite_record(self):
        for kind,data,model in [('clientes',self.customer_data(),Client),('produtos',self.product_data(),Product)]:
            with self.subTest(kind=kind):
                first=self.client.post(f'/cadastros/rapidos/{kind}/',data)
                second=self.client.post(f'/cadastros/rapidos/{kind}/',data)
                self.assertEqual(first.status_code,201);self.assertEqual(second.status_code,200)
                self.assertEqual(first.json()['record']['id'],second.json()['record']['id'])
                self.assertEqual(model.objects.count(),1)
                prefix='quick_client' if kind=='clientes' else 'quick_product'
                data[prefix+'-name']='Outro nome artificial'
                self.assertEqual(self.client.post(f'/cadastros/rapidos/{kind}/',data).status_code,409)
                self.assertFalse(model.objects.filter(name='Outro nome artificial').exists())
        self.assertEqual(Price.objects.count(),1)

    def test_validation_errors_never_leave_partial_product_price_or_customer(self):
        data=self.product_data();data['quick_product-amount']='-1'
        response=self.client.post('/cadastros/rapidos/produtos/',data)
        self.assertEqual(response.status_code,400);self.assertIn('amount',response.json()['errors'])
        data=self.product_data();data['quick_product-production_cost']='-1'
        self.assertEqual(self.client.post('/cadastros/rapidos/produtos/',data).status_code,400)
        data=self.customer_data();data['quick_client-company']=str(uuid.uuid4())
        self.assertEqual(self.client.post('/cadastros/rapidos/clientes/',data).status_code,400)
        self.assertEqual(Product.objects.count(),0);self.assertEqual(Price.objects.count(),0);self.assertEqual(Client.objects.count(),0)

    def test_new_records_can_be_used_in_same_manual_order_with_entered_details(self):
        customer=self.client.post('/cadastros/rapidos/clientes/',self.customer_data()).json()['record']['id']
        product=self.client.post('/cadastros/rapidos/produtos/',self.product_data()).json()['record']['id']
        data={'company':str(self.company.pk),'client':customer,'purchase_order':'OC-ARTIFICIAL-001','date':str(timezone.localdate()),'time':'06:00','slot':'Entrega artificial','shift':'DIURNO','baker':'Padeiro artificial','driver':'Motorista artificial','notes':'Observação preenchida antes do cadastro','key':str(uuid.uuid4()),'form-TOTAL_FORMS':'4','form-INITIAL_FORMS':'0','form-0-product':product,'form-0-quantity':'12.500'}
        response=self.client.post('/novo-pedido/',data)
        self.assertEqual(response.status_code,302)
        order=Order.objects.get();item=OrderItem.objects.get()
        self.assertEqual(order.client_id,uuid.UUID(customer));self.assertEqual(order.purchase_order,'OC-ARTIFICIAL-001')
        self.assertEqual(order.time,time(6));self.assertEqual(order.notes,data['notes'])
        self.assertEqual(item.product_id,uuid.UUID(product));self.assertEqual(item.quantity,Decimal('12.5'));self.assertEqual(item.unit,'KG')
        self.assertEqual(price_for(self.company,order.client,item.product,order.date),Decimal('2.75'))
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,302)
        self.assertEqual(Order.objects.count(),1);self.assertEqual(Client.objects.count(),1);self.assertEqual(Product.objects.count(),1)

    def test_post_only_csrf_and_catalogue_permissions_are_enforced(self):
        self.assertEqual(self.client.get('/cadastros/rapidos/clientes/').status_code,405)
        secured=HTTPClient(enforce_csrf_checks=True);secured.force_login(self.user)
        self.assertEqual(secured.post('/cadastros/rapidos/clientes/',self.customer_data()).status_code,403)
        reader=User.objects.create_user('leitor');Membership.objects.create(user=reader,company=self.company)
        self.client.force_login(reader)
        self.assertEqual(self.client.post('/cadastros/rapidos/produtos/',self.product_data()).status_code,403)
        self.client.logout()
        self.assertEqual(self.client.post('/cadastros/rapidos/clientes/',self.customer_data()).status_code,302)
        self.assertEqual(Client.objects.count(),0);self.assertEqual(Product.objects.count(),0)
