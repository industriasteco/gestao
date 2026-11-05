import uuid
from datetime import time,timedelta
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError,PermissionDenied
from django.test import TestCase
from django.utils import timezone
from .models import Company,Client,Product,Price,Audit,Order,OrderItem,Membership
from .management_services import set_current_price
from .services import price_for,prices_on
from .proposal_services import resolve_lines,save_proposal,generate_proposal
from .statements import create_statement
from . import workflow


class PriceChangesTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.company=Company.objects.create(code='NONA',name='NONA ARTIFICIAL')
        self.customer=Client.objects.create(company=self.company,name='Cliente artificial')
        self.product=Product.objects.create(company=self.company,name='Pão artificial')
        self.today=timezone.localdate()
        self.old=Price.objects.create(company=self.company,product=self.product,amount=2,valid_from=self.today-timedelta(days=10))
        self.client.force_login(self.user)

    def change(self,amount,client=None):
        return set_current_price(self.user,self.company,self.product,Decimal(amount),client)

    def test_same_day_changes_preserve_values_and_resolve_latest_without_duplicates(self):
        first=self.change('2.5');last=self.change('3.25')
        self.old.refresh_from_db();first.refresh_from_db()
        self.assertEqual(self.old.amount,2)
        self.assertEqual(self.old.valid_until,self.today-timedelta(days=1))
        self.assertTrue(first.superseded);self.assertEqual(first.amount,Decimal('2.5'))
        self.assertIsNone(last.valid_until)
        self.assertEqual(price_for(self.company,self.customer,self.product,self.today),Decimal('3.25'))
        self.assertEqual(self.change('3.25').pk,last.pk)
        self.assertEqual(Price.objects.count(),3)
        event=Audit.objects.get(entity=str(first.pk),action='SUBSTITUIR_PRECO')
        self.assertEqual(event.before['amount'],'2.5000')

    def test_price_forms_have_no_dates_and_prices_tab_accepts_repeated_changes(self):
        for url,form_key in [('/cadastros/precos/','form'),(f'/produtos/{self.product.pk}/','form'),(f'/clientes/{self.customer.pk}/','price_form')]:
            response=self.client.get(url)
            self.assertEqual(response.status_code,200)
            for field in ['valid_from','valid_until']:
                self.assertNotIn(field,response.context[form_key].fields)
        data={'company':str(self.company.pk),'client':'','product':str(self.product.pk)}
        for amount in ['2.5','3.75']:
            response=self.client.post('/cadastros/precos/',dict(data,amount=amount))
            self.assertEqual(response.status_code,302)
        self.assertEqual(price_for(self.company,self.customer,self.product,self.today),Decimal('3.75'))
        page=self.client.get('/cadastros/precos/')
        self.assertEqual(list(page.context['rows'].values_list('amount',flat=True)),[Decimal('3.75')])

    def test_edit_price_and_product_form_prefill_and_update_current_amount(self):
        response=self.client.get(f'/precos/{self.old.pk}/')
        self.assertEqual(response.context['form']['amount'].value(),2)
        response=self.client.post(f'/precos/{self.old.pk}/',{'amount':'2.60'})
        self.assertEqual(response.status_code,302)
        response=self.client.get(f'/produtos/{self.product.pk}/')
        self.assertEqual(response.context['form']['amount'].value(),Decimal('2.60'))
        for amount in ['3','4']:
            response=self.client.post(f'/produtos/{self.product.pk}/',{'name':self.product.name,'unit':'UN','production_cost':'1.25','amount':amount})
            self.assertEqual(response.status_code,302)
        self.assertEqual(price_for(self.company,self.customer,self.product,self.today),4)
        self.assertEqual(self.client.get(f'/produtos/{self.product.pk}/').context['profit'],Decimal('2.75'))

    def test_client_price_is_independent_and_proposal_uses_latest_negotiation(self):
        for amount in ['1.5','1.75']:
            response=self.client.post(f'/clientes/{self.customer.pk}/',{'action':'price','product':str(self.product.pk),'amount':amount})
            self.assertEqual(response.status_code,302)
        self.change('3')
        other=Client.objects.create(company=self.company,name='Outro cliente artificial')
        self.assertEqual(price_for(self.company,self.customer,self.product,self.today),Decimal('1.75'))
        self.assertEqual(price_for(self.company,other,self.product,self.today),3)
        lines,total=resolve_lines(self.company,self.customer,self.today,[dict(product=self.product,description='',quantity=Decimal(10),unit='',unit_price=None)])
        self.assertEqual(total,Decimal('17.50'));self.assertEqual(lines[0]['unit_price'],Decimal('1.75'))

    def test_legacy_overlaps_and_future_prices_are_preserved_without_blocking_changes(self):
        duplicate=Price.objects.create(company=self.company,product=self.product,amount=10,valid_from=self.today)
        future=Price.objects.create(company=self.company,product=self.product,amount=99,valid_from=self.today+timedelta(days=7))
        new=self.change('2.75')
        duplicate.refresh_from_db();future.refresh_from_db()
        self.assertTrue(duplicate.superseded);self.assertTrue(future.superseded)
        self.assertEqual(future.amount,99)
        self.assertEqual(price_for(self.company,self.customer,self.product,self.today+timedelta(days=100)),Decimal('2.75'))
        self.assertEqual(price_for(self.company,self.customer,self.product,self.today-timedelta(days=1)),2)
        self.assertEqual(prices_on(self.today).get().pk,new.pk)

    def test_issued_receipt_statement_and_proposal_keep_original_values(self):
        order=Order.objects.create(company=self.company,client=self.customer,date=self.today,time=time(6),slot='1',shift='NOTURNO',baker='Padeiro artificial',status='CONFERIDO',idempotency_key='price-change-test')
        item=OrderItem.objects.create(order=order,product=self.product,product_name=self.product.name,unit='UN',quantity=10)
        receipt=workflow.issue(self.user,order.pk)
        workflow.deliver(self.user,order.pk,'Entrega artificial confirmada')
        statement=create_statement(self.user,self.company,self.customer,self.today.replace(day=1),self.today)
        values=dict(company=self.company,client=self.customer,title='Serviço artificial',summary='',issued_on=self.today,valid_days=60,customer_name=self.customer.name,customer_tax_id='',customer_address='',included_items='',conditions='',notes='',responsible='Responsável artificial')
        proposal=save_proposal(self.user,values,[dict(product=self.product,description='',quantity=Decimal(10),unit='',unit_price=None)],uuid.uuid4())
        document=generate_proposal(self.user,proposal)
        original=[bytes(doc.data) for doc in [receipt,statement.document,document]]
        self.change('5');self.change('6')
        item.refresh_from_db();proposal.refresh_from_db();statement.refresh_from_db()
        self.assertEqual(item.unit_price_snapshot,2)
        self.assertEqual(statement.total,20);self.assertEqual(proposal.total,20)
        for doc,data in zip([receipt,statement.document,document],original):
            doc.refresh_from_db();self.assertEqual(bytes(doc.data),data)
        self.assertEqual(bytes(generate_proposal(self.user,proposal).data),original[2])
        self.assertEqual(price_for(self.company,self.customer,self.product,self.today),6)

    def test_invalid_prices_cross_company_and_unauthorized_changes_do_not_write(self):
        for amount in ['-1','NaN','1000000000000']:
            with self.assertRaises(ValidationError):self.change(amount)
        other=Company.objects.create(code='OTHER',name='Outra empresa artificial')
        other_product=Product.objects.create(company=other,name='Outro produto artificial')
        with self.assertRaises(ValidationError):
            set_current_price(self.user,self.company,other_product,Decimal(1))
        response=self.client.post('/cadastros/precos/',{'company':str(self.company.pk),'product':str(other_product.pk),'amount':'5'})
        self.assertEqual(response.status_code,200)
        reader=User.objects.create_user('leitor');Membership.objects.create(user=reader,company=self.company)
        with self.assertRaises(PermissionDenied):set_current_price(reader,self.company,self.product,Decimal(5))
        self.client.force_login(reader)
        self.assertEqual(self.client.get(f'/precos/{self.old.pk}/').status_code,403)
        self.assertEqual(self.client.post('/cadastros/precos/',{'amount':'5'}).status_code,403)
        self.assertEqual(Price.objects.count(),1)
        self.old.refresh_from_db();self.assertIsNone(self.old.valid_until)

    def test_zero_price_and_blank_product_price_do_not_create_unwanted_versions(self):
        zero=self.change('0')
        response=self.client.post(f'/produtos/{self.product.pk}/',{'name':self.product.name,'unit':'UN','production_cost':'1','amount':''})
        self.assertEqual(response.status_code,302)
        self.assertEqual(price_for(self.company,self.customer,self.product,self.today),0)
        response=self.client.post(f'/precos/{zero.pk}/',{'amount':'0'})
        self.assertEqual(response.status_code,302);self.assertEqual(Price.objects.count(),2)
