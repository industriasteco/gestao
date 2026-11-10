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
        data={'action':'routine','product':str(self.product.pk),'quantity':'12','weekdays':['1','3','5'],'amount':'1.40','slot':'Pedido fixo','time':'06:00','shift':'NOTURNO','notes':'Instrução artificial'}
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

    def routine_data(self,product,quantity,days):
        return {'action':'routine','product':str(product.pk),'quantity':str(quantity),'weekdays':[str(day) for day in days],'slot':'Pedido fixo','time':'06:00','shift':'NOTURNO'}

    def test_products_follow_their_own_days_and_friday_extras_share_one_order(self):
        self.assertEqual(self.client.post(f'/clientes/{self.customer.pk}/',self.routine_data(self.product,60,[1,3,5])).status_code,302)
        extra=self.routine_data(self.other_product,250,[5]);extra['amount']='1.75'
        self.assertEqual(self.client.post(f'/clientes/{self.customer.pk}/',extra).status_code,302)
        self.assertFalse(Recurrence.objects.filter(follow_client_days=True).exists())
        for offset in range(7):
            day=self.monday+timedelta(days=offset)
            self.client.get(f'/pedidos-dia/?date={day}')
            if offset in (0,2,4):
                order=Order.objects.get(date=day)
                expected={self.product.pk:Decimal(60)}
                if offset==4:expected[self.other_product.pk]=Decimal(250)
                self.assertEqual(dict(order.items.values_list('product_id','quantity')),expected)
            else:self.assertFalse(Order.objects.filter(date=day).exists())
        self.client.get(f'/pedidos-dia/?date={self.monday+timedelta(days=4)}')
        self.assertEqual(Order.objects.count(),3)
        self.assertEqual(price_for(self.company,self.customer,self.other_product,self.monday),Decimal('1.75'))

    def test_same_product_can_have_different_quantities_without_overlapping_days(self):
        url=f'/clientes/{self.customer.pk}/'
        self.client.post(url,self.routine_data(self.product,60,[1,3,5]))
        friday=self.routine_data(self.product,250,[5])
        self.client.post(url,friday);self.client.post(url,friday)
        rules=Recurrence.objects.filter(active=True)
        self.assertEqual(rules.count(),2)
        self.assertEqual(rules.get(quantity=60).weekdays,[1,3])
        self.assertEqual(rules.get(quantity=250).weekdays,[5])
        for offset,quantity in ((0,60),(2,60),(4,250)):
            day=self.monday+timedelta(days=offset);prepare(self.user,day,automatic_only=True)
            self.assertEqual(Order.objects.get(date=day).items.get().quantity,quantity)
        # Uma seleção que cobre várias linhas substitui só os dias selecionados.
        self.client.post(url,self.routine_data(self.product,80,[3,5]))
        self.assertEqual(Recurrence.objects.get(active=True,quantity=60).weekdays,[1])
        self.assertEqual(Recurrence.objects.get(active=True,quantity=80).weekdays,[3,5])
        self.assertEqual(Recurrence.objects.filter(active=True).count(),2)

    def test_client_day_changes_preserve_custom_days_and_update_legacy_followers(self):
        save_recurring_items(self.user,self.customer,[{'product':self.product,'quantity':Decimal(60)}],'Pedido fixo',time(6),'NOTURNO')
        self.client.post(f'/clientes/{self.customer.pk}/',self.routine_data(self.other_product,250,[5]))
        self.client.post(f'/clientes/{self.customer.pk}/',{'action':'edit','name':self.customer.name,'recurring_weekdays':['2','4']})
        self.assertEqual(Recurrence.objects.get(product=self.product).weekdays,[2,4])
        self.assertEqual(Recurrence.objects.get(product=self.other_product).weekdays,[5])
        # Tirar todos os dias gerais mantém a entrega própria de sexta.
        self.client.post(f'/clientes/{self.customer.pk}/',{'action':'edit','name':self.customer.name})
        prepare(self.user,self.monday+timedelta(days=4),automatic_only=True)
        self.assertEqual(Order.objects.get().items.get().quantity,250)

    def test_specific_day_can_be_set_without_client_general_days(self):
        self.customer.recurring_weekdays=[];self.customer.save()
        response=self.client.post(f'/clientes/{self.customer.pk}/',self.routine_data(self.product,60,[5]))
        self.assertEqual(response.status_code,302)
        self.assertEqual(Recurrence.objects.get().weekdays,[5])

    def test_invalid_or_missing_product_days_do_not_save_routine_or_price(self):
        url=f'/clientes/{self.customer.pk}/'
        for days in ([],[0],[8]):
            data=self.routine_data(self.product,60,days);data['amount']='2.50'
            response=self.client.post(url,data)
            self.assertEqual(response.status_code,200)
            self.assertTrue(response.context['routine_form'].errors)
        self.assertEqual(Recurrence.objects.count(),0)
        self.assertFalse(Price.objects.filter(client=self.customer).exists())

    def test_day_specific_changes_preserve_prepared_quantities_and_add_no_duplicate(self):
        url=f'/clientes/{self.customer.pk}/'
        self.client.post(url,self.routine_data(self.product,60,[1,3,5]))
        friday=self.monday+timedelta(days=4);prepare(self.user,friday,automatic_only=True)
        order=Order.objects.get();item=order.items.get();item.quantity=77;item.save()
        self.client.post(url,self.routine_data(self.product,250,[5]))
        self.client.post(url,self.routine_data(self.other_product,250,[5]))
        self.assertEqual(prepare(self.user,friday,automatic_only=True),0)
        self.assertEqual(Order.objects.count(),1)
        item.refresh_from_db();self.assertEqual(item.quantity,77)
        self.assertEqual(order.items.count(),1)
        prepare(self.user,friday+timedelta(days=7),automatic_only=True)
        future=Order.objects.get(date=friday+timedelta(days=7))
        self.assertEqual(dict(future.items.values_list('product_id','quantity')),{self.product.pk:Decimal(250),self.other_product.pk:Decimal(250)})

    def test_editing_product_days_detaches_routine_from_general_days(self):
        rule=save_recurring_items(self.user,self.customer,[{'product':self.product,'quantity':Decimal(60)}],'Pedido fixo',time(6),'NOTURNO')[0]
        data={'quantity':'60','slot':'Pedido fixo','time':'06:00','shift':'NOTURNO','weekdays':['5'],'auto_prepare':'on','valid_from':str(self.today)}
        response=self.client.post(f'/rotinas/{rule.pk}/',data)
        self.assertEqual(response.status_code,302)
        rule.refresh_from_db();self.assertFalse(rule.follow_client_days)
        self.client.post(f'/clientes/{self.customer.pk}/',{'action':'edit','name':self.customer.name,'recurring_weekdays':['2','4']})
        rule.refresh_from_db();self.assertEqual(rule.weekdays,[5])

    def test_non_admin_cannot_change_day_specific_routines(self):
        reader=User.objects.create_user('leitor_rotinas');Membership.objects.create(user=reader,company=self.company)
        self.client.force_login(reader)
        self.assertEqual(self.client.post(f'/clientes/{self.customer.pk}/',self.routine_data(self.product,60,[5])).status_code,403)
        self.assertEqual(Recurrence.objects.count(),0)
