import uuid
from datetime import time,timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from .models import Company,Client,Product,Price,Recurrence,Order,Membership,Document
from .services import price_for,prepare
from .client_setup import save_recurring_items


class ClientScheduleTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.company=Company.objects.create(code='NONA',name='NONA ARTIFICIAL')
        self.product=Product.objects.create(company=self.company,name='Pão artificial')
        self.other_product=Product.objects.create(company=self.company,name='Outro produto artificial')
        self.customer=Client.objects.create(company=self.company,name='Cliente artificial',recurring_weekdays=[1,3,5])
        self.today=timezone.localdate()
        self.monday=self.today+timedelta(days=(1-self.today.isoweekday())%7)
        Price.objects.create(company=self.company,product=self.product,amount=2,valid_from=self.today)
        self.client.force_login(self.user)

    def order_data(self):
        return {'company':str(self.company.pk),'client':str(self.customer.pk),'date':str(self.monday),'time':'06:00','slot':'Pedido fixo','shift':'NOTURNO','baker':'Padeiro artificial','notes':'Embalagem artificial','key':str(uuid.uuid4()),'repeat_weekly':'on','form-TOTAL_FORMS':'2','form-INITIAL_FORMS':'0','form-0-product':str(self.product.pk),'form-0-quantity':'10','form-0-client_price':'1.50','form-1-product':str(self.other_product.pk),'form-1-quantity':'5','form-1-client_price':'2.75'}

    def test_client_registration_saves_weekdays_and_negotiated_prices_atomically(self):
        response=self.client.post('/cadastros/clientes/',{'company':str(self.company.pk),'name':'Novo cliente artificial','recurring_weekdays':['2','4'],'client_prices-TOTAL_FORMS':'2','client_prices-INITIAL_FORMS':'0','client_prices-0-product':str(self.product.pk),'client_prices-0-amount':'1.25'})
        self.assertEqual(response.status_code,302)
        customer=Client.objects.get(name='Novo cliente artificial')
        self.assertEqual(customer.recurring_weekdays,[2,4])
        self.assertEqual(price_for(self.company,customer,self.product,self.today),Decimal('1.25'))
        self.assertEqual(Price.objects.get(client__isnull=True).amount,2)
        self.assertEqual(Order.objects.count(),0);self.assertEqual(Recurrence.objects.count(),0)

    def test_quick_registration_saves_days_and_prices_without_duplication(self):
        data={'request_key':str(uuid.uuid4()),'quick_client-company':str(self.company.pk),'quick_client-name':'Cliente artificial na caixa','quick_client-recurring_weekdays':['1','3','5'],'quick_client_prices-TOTAL_FORMS':'2','quick_client_prices-INITIAL_FORMS':'0','quick_client_prices-0-product':str(self.product.pk),'quick_client_prices-0-amount':'1.75'}
        first=self.client.post('/cadastros/rapidos/clientes/',data)
        self.assertEqual(first.status_code,201)
        self.assertEqual(first.json()['record']['weekdays'],[1,3,5])
        customer=Client.objects.get(pk=first.json()['record']['id'])
        self.assertEqual(price_for(self.company,customer,self.product,self.today),Decimal('1.75'))
        self.assertEqual(self.client.post('/cadastros/rapidos/clientes/',data).status_code,200)
        self.assertEqual(Price.objects.filter(client=customer).count(),1)

    def test_first_order_creates_weekly_routine_and_daily_view_repeats_without_duplicates(self):
        data=self.order_data();response=self.client.post('/novo-pedido/',data)
        self.assertEqual(response.status_code,302)
        origin=Order.objects.get();rules=Recurrence.objects.filter(client=self.customer)
        self.assertEqual(rules.count(),2);self.assertTrue(all(rule.active and rule.auto_prepare for rule in rules))
        self.assertEqual(len(origin.preparation_rules),2)
        self.assertEqual(self.client.get(f'/pedidos-dia/?date={self.monday}').status_code,200)
        self.assertEqual(Order.objects.count(),1)
        following=self.monday+timedelta(days=7)
        response=self.client.get(f'/pedidos-dia/?date={following}')
        self.assertEqual(response.status_code,200);self.assertEqual(Order.objects.count(),2)
        repeated=Order.objects.get(date=following)
        self.assertEqual(list(repeated.items.order_by('quantity').values_list('quantity',flat=True)),[Decimal(5),Decimal(10)])
        self.assertEqual(repeated.status,'PRE_LANCADO');self.assertEqual(Document.objects.count(),0)
        self.assertEqual(price_for(self.company,self.customer,self.product,following),Decimal('1.50'))
        self.client.get(f'/pedidos-dia/?date={following}');self.assertEqual(Order.objects.count(),2)
        self.client.get(f'/pedidos-dia/?date={following+timedelta(days=1)}');self.assertEqual(Order.objects.count(),2)
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,302);self.assertEqual(Order.objects.count(),2)

    def test_weekday_edits_update_auto_rules_and_preserve_prepared_orders_and_manual_rules(self):
        self.client.post('/novo-pedido/',self.order_data());origin=Order.objects.get()
        manual=Recurrence.objects.create(company=self.company,client=self.customer,product=self.product,quantity=1,slot='Outra entrega',time=time(9),shift='DIURNO',weekdays=[6],valid_from=self.today,active=True)
        paused=Recurrence.objects.filter(auto_prepare=True,product=self.other_product).get();paused.active=False;paused.save()
        payload={'action':'edit','name':self.customer.name,'recurring_weekdays':['2','4']}
        response=self.client.post(f'/clientes/{self.customer.pk}/',payload)
        self.assertEqual(response.status_code,302)
        self.assertTrue(all(rule.weekdays==[2,4] for rule in Recurrence.objects.filter(auto_prepare=True)))
        manual.refresh_from_db();paused.refresh_from_db()
        self.assertEqual(manual.weekdays,[6]);self.assertFalse(paused.active)
        origin.refresh_from_db();self.assertEqual(origin.items.get(product=self.product).quantity,10)
        payload.pop('recurring_weekdays');self.client.post(f'/clientes/{self.customer.pk}/',payload)
        day=self.monday+timedelta(days=8);self.client.get(f'/pedidos-dia/?date={day}')
        self.assertEqual(Order.objects.count(),1)
        payload['recurring_weekdays']=['3'];self.client.post(f'/clientes/{self.customer.pk}/',payload)
        self.client.get(f'/pedidos-dia/?date={self.monday+timedelta(days=9)}')
        self.assertEqual(Order.objects.count(),2)

    def test_history_legacy_rules_and_unprivileged_visits_do_not_generate_orders(self):
        rule=Recurrence.objects.create(company=self.company,client=self.customer,product=self.product,quantity=1,slot='Fixo',time=time(6),shift='NOTURNO',weekdays=list(range(1,8)),valid_from=self.today-timedelta(days=20),active=True)
        self.client.get(f'/pedidos-dia/?date={self.today}');self.assertEqual(Order.objects.count(),0)
        rule.auto_prepare=True;rule.save()
        self.client.get(f'/pedidos-dia/?date={self.today-timedelta(days=1)}');self.assertEqual(Order.objects.count(),0)
        reader=User.objects.create_user('leitor');Membership.objects.create(user=reader,company=self.company)
        self.client.force_login(reader);self.client.get(f'/pedidos-dia/?date={self.today}');self.assertEqual(Order.objects.count(),0)
        self.client.force_login(self.user)
        self.customer.active=False;self.customer.save()
        self.client.get(f'/pedidos-dia/?date={self.today}');self.assertEqual(Order.objects.count(),0)

    def test_client_page_can_add_products_quantities_and_prices_to_routine(self):
        data={'action':'routine','product':str(self.product.pk),'quantity':'12','amount':'1.40','slot':'Pedido fixo','time':'06:00','shift':'NOTURNO','notes':'Instrução artificial'}
        self.assertEqual(self.client.post(f'/clientes/{self.customer.pk}/',data).status_code,302)
        data['product']=str(self.other_product.pk);data['quantity']='5';data['amount']='2.25'
        self.assertEqual(self.client.post(f'/clientes/{self.customer.pk}/',data).status_code,302)
        self.assertEqual(Recurrence.objects.filter(active=True,auto_prepare=True).count(),2)
        self.assertEqual(Price.objects.filter(client=self.customer).count(),2)
        self.assertEqual(Order.objects.count(),0)
        self.client.get(f'/pedidos-dia/?date={self.monday}');self.assertEqual(Order.objects.count(),1)

    def test_invalid_days_or_incomplete_routine_do_not_save_prices_or_order(self):
        data=self.order_data();data['shift']=''
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,200)
        self.customer.recurring_weekdays=[];self.customer.save();data['shift']='NOTURNO'
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,200)
        self.assertEqual(Order.objects.count(),0);self.assertEqual(Recurrence.objects.count(),0)
        self.assertEqual(Price.objects.filter(client=self.customer).count(),0)
        response=self.client.post('/cadastros/clientes/',{'company':str(self.company.pk),'name':'Dias inválidos','recurring_weekdays':['9']})
        self.assertEqual(response.status_code,200);self.assertFalse(Client.objects.filter(name='Dias inválidos').exists())

    def test_foreign_product_or_invalid_price_rolls_back_new_client(self):
        other=Company.objects.create(code='OTHER',name='Outra artificial')
        product=Product.objects.create(company=other,name='Produto de outra empresa')
        data={'request_key':str(uuid.uuid4()),'quick_client-company':str(self.company.pk),'quick_client-name':'Cliente inválido','quick_client_prices-TOTAL_FORMS':'1','quick_client_prices-INITIAL_FORMS':'0','quick_client_prices-0-product':str(product.pk),'quick_client_prices-0-amount':'1'}
        self.assertEqual(self.client.post('/cadastros/rapidos/clientes/',data).status_code,400)
        data['quick_client_prices-0-product']=str(self.product.pk);data['quick_client_prices-0-amount']='-1'
        response=self.client.post('/cadastros/rapidos/clientes/',data)
        self.assertEqual(response.status_code,400);self.assertTrue(response.json()['price_errors'])
        self.assertFalse(Client.objects.filter(name='Cliente inválido').exists())

    def test_updating_weekly_quantity_preserves_prepared_adjustments(self):
        self.client.post('/novo-pedido/',self.order_data())
        following=self.monday+timedelta(days=7);prepare(self.user,following,automatic_only=True)
        prepared=Order.objects.get(date=following);item=prepared.items.get(product=self.product);item.quantity=77;item.save()
        save_recurring_items(self.user,self.customer,[{'product':self.product,'quantity':Decimal(20)}],'Pedido fixo',time(6),'NOTURNO',replace=True)
        self.assertEqual(prepare(self.user,following,automatic_only=True),0)
        item.refresh_from_db();self.assertEqual(item.quantity,77)
        next_day=following+timedelta(days=7);prepare(self.user,next_day,automatic_only=True)
        self.assertEqual(Order.objects.get(date=next_day).items.get().quantity,20)
