"""Conversão comercial com quantidades artificiais e sem dados de clientes reais."""
import csv
import uuid
from datetime import date, time
from decimal import Decimal
from io import BytesIO, StringIO
from pypdf import PdfReader
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Company, Client, Product, Price, Order, OrderItem, Recurrence
from .billing import configure_item, item_price, subtotal
from .services import prepare, production, adjust
from .management_services import set_current_price
from .statements import create_statement, statement_action
from . import workflow


class WeightBillingTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor-peso','','test-only')
        self.company=Company.objects.create(code='TECO',name='Empresa artificial')
        self.customer=Client.objects.create(company=self.company,name='Cliente artificial')
        self.day=date(2026,11,1)
        self.bread=Product.objects.create(company=self.company,name='Produto artificial 35g',unit='UN',unit_weight_g=35)
        self.milk=Product.objects.create(company=self.company,name='Produto artificial 65g',unit='UN',unit_weight_g=65)
        for product,amount in [(self.bread,'8.50'),(self.milk,'8.30')]:
            Price.objects.create(company=self.company,client=self.customer,product=product,amount=Decimal(amount),billing_unit='KG',valid_from=self.day)
        self.client.force_login(self.user)

    def order(self,product=None,quantity=100,selection=''):
        order=Order.objects.create(company=self.company,client=self.customer,date=self.day,time=time(6),slot='Artificial',shift='DIURNO',baker='Equipe artificial',status='CONFERIDO',idempotency_key=str(uuid.uuid4()))
        product=product or self.bread
        item=configure_item(OrderItem(order=order,product=product,product_name=product.name,unit=product.unit,quantity=Decimal(quantity)),selection)
        item.full_clean();item.save()
        return order,item

    def post_data(self,product=None,quantity='100',basis=''):
        return dict(company=str(self.company.pk),client=str(self.customer.pk),date=str(self.day),time='06:00',slot='Artificial',shift='DIURNO',baker='Equipe artificial',key=str(uuid.uuid4()),
            **{'form-TOTAL_FORMS':'1','form-INITIAL_FORMS':'0','form-0-product':str((product or self.bread).pk),'form-0-quantity':quantity,'form-0-billing_unit':basis})

    def test_manual_entry_defaults_to_client_condition_and_is_idempotent(self):
        data=self.post_data()
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,302)
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,302)
        item=OrderItem.objects.get()
        self.assertEqual((item.quantity,item.unit,item.billed_quantity,item.billed_unit),(100,'UN',Decimal('3.5'),'KG'))
        self.assertEqual(item.billing_factor,Decimal('.035'))
        self.assertEqual(production(Order.objects.all())[0]['total'],100)
        self.assertContains(self.client.get(f'/pedidos/{item.order_id}/'),'Faturamento')

    def test_exact_weight_money_and_rounding(self):
        _,bread=self.order();_,milk=self.order(self.milk)
        self.assertEqual(subtotal(bread,item_price(bread)),Decimal('29.75'))
        self.assertEqual(subtotal(milk,item_price(milk)),Decimal('53.95'))
        _,one=self.order(quantity=1)
        self.assertEqual(subtotal(one,item_price(one)),Decimal('.30'))

    def test_issue_statement_export_preserve_frozen_factor_and_kg(self):
        order,item=self.order()
        self.bread.unit_weight_g=99;self.bread.save()
        doc=workflow.issue(self.user,order.pk)
        order.refresh_from_db()
        row=order.issued_snapshot['items'][0]
        self.assertEqual((row['quantity'],row['unit'],row['ordered_quantity'],row['billing_factor'],row['total']),('3.5','KG','100','0.035','29.75'))
        text=' '.join(p.extract_text() for p in PdfReader(BytesIO(bytes(doc.data))).pages)
        self.assertIn('KG',text);self.assertIn('100 UN',text)
        workflow.deliver(self.user,order.pk,'Evidência artificial')
        statement=create_statement(self.user,self.company,self.customer,self.day,self.day)
        self.assertEqual(statement.total,Decimal('29.75'))
        set_current_price(self.user,self.company,self.bread,Decimal('20'),self.customer)
        self.assertEqual(Price.objects.get(product=self.bread,superseded=False,valid_until__isnull=True).billing_unit,'KG')
        statement_action(self.user,statement,'send','Registro artificial de envio')
        statement_action(self.user,statement,'approve','Aprovação artificial registrada')
        from django.urls import reverse
        response=self.client.get(reverse('statement_export',args=[statement.pk]))
        self.assertEqual(response.status_code,200)
        exported=list(csv.DictReader(StringIO(response.content.decode('utf-8-sig')),delimiter=';'))[0]
        self.assertEqual((exported['Unidade'],exported['Quantidade'],exported['Valor_total']),('KG','3.5','29.75'))

    def test_other_customer_keeps_unit_pricing(self):
        other=Client.objects.create(company=self.company,name='Outro artificial')
        Price.objects.create(company=self.company,product=self.bread,amount=Decimal('.50'),valid_from=self.day)
        self.customer=other
        _,item=self.order()
        self.assertEqual((item.billed_unit,item.billed_quantity,subtotal(item,item_price(item))),('UN',100,Decimal('50.00')))

    def test_missing_weight_and_fractional_bread_block_without_partial_order(self):
        self.bread.unit_weight_g=None;self.bread.save()
        response=self.client.post('/novo-pedido/',self.post_data(basis='KG'))
        self.assertContains(response,'cadastre o peso')
        self.assertFalse(Order.objects.exists())
        self.bread.unit_weight_g=35;self.bread.save()
        response=self.client.post('/novo-pedido/',self.post_data(quantity='1.5'))
        self.assertContains(response,'quantidade inteira')
        self.assertFalse(Order.objects.exists())

    def test_adjustment_keeps_conversion_and_rejects_fractional_bread(self):
        order,item=self.order();order.status='PRE_LANCADO';order.save()
        adjust(self.user,order.pk,Decimal(200),'Ajuste artificial')
        item.refresh_from_db();self.assertEqual(item.billed_quantity,Decimal(7))
        with self.assertRaises(ValidationError):adjust(self.user,order.pk,Decimal('1.5'),'Ajuste artificial')

    def test_explicit_unit_mismatch_blocks_issue(self):
        order,_=self.order(selection='PRODUCT')
        with self.assertRaises(ValidationError):workflow.issue(self.user,order.pk)
        order.refresh_from_db();self.assertEqual(order.status,'CONFERIDO')
        self.assertFalse(order.issued_snapshot)

    def test_negotiated_price_uses_order_date_and_selected_unit(self):
        data=self.post_data(basis='KG');data['form-0-client_price']='8.60'
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,302)
        item=OrderItem.objects.get()
        self.assertEqual(item_price(item),Decimal('8.60'))
        self.assertEqual(Price.objects.get(product=self.bread,superseded=False).valid_from,self.day)

    def test_recurring_order_copies_client_conversion(self):
        Recurrence.objects.create(company=self.company,client=self.customer,product=self.bread,quantity=100,slot='Artificial',time=time(6),shift='DIURNO',weekdays=[self.day.isoweekday()],valid_from=self.day,active=True)
        self.assertEqual(prepare(self.user,self.day),1)
        item=OrderItem.objects.get();self.assertEqual(item.billed_quantity,Decimal('3.5'))
        self.assertEqual(prepare(self.user,self.day),0)

    def test_legacy_unissued_item_resolves_condition_only_at_first_issue(self):
        order,item=self.order()
        OrderItem.objects.filter(pk=item.pk).update(billing_unit='',billing_factor=1)
        workflow.issue(self.user,order.pk)
        item.refresh_from_db();self.assertEqual(item.billed_quantity,Decimal('3.5'))

    def test_native_kg_product_needs_no_conversion_weight(self):
        product=Product.objects.create(company=self.company,name='Produto artificial a granel',unit='KG')
        Price.objects.create(company=self.company,product=product,amount=Decimal('10'),valid_from=self.day)
        _,item=self.order(product,quantity='1.5')
        self.assertEqual((item.billed_unit,item.billing_factor,item.billed_quantity),('KG',1,Decimal('1.5')))

    def test_price_form_accepts_kg_and_quick_product_returns_weight(self):
        response=self.client.post('/cadastros/precos/',{'company':str(self.company.pk),'client':str(self.customer.pk),'product':str(self.bread.pk),'amount':'9','billing_unit':'KG'})
        self.assertEqual(response.status_code,302)
        current=Price.objects.get(product=self.bread,valid_until__isnull=True,superseded=False)
        self.assertEqual(current.billing_unit,'KG')
        response=self.client.get('/novo-pedido/')
        self.assertContains(response,'Unidade do faturamento / preço')
        self.assertContains(response,'billing-products-data')

    def test_new_client_condition_preserves_inherited_kg_basis(self):
        other=Client.objects.create(company=self.company,name='Outro artificial')
        Price.objects.create(company=self.company,product=self.bread,amount=Decimal('10'),billing_unit='KG',valid_from=self.day)
        price=set_current_price(self.user,self.company,self.bread,Decimal('9'),other)
        self.assertEqual(price.billing_unit,'KG')

    def test_client_factor_overrides_weight_without_changing_other_clients(self):
        set_current_price(self.user,self.company,self.bread,Decimal('9'),self.customer,billing_unit='KG',billing_factor=Decimal('.040'),effective_on=self.day)
        order,item=self.order()
        self.assertEqual(item.billed_quantity,Decimal('4'))
        self.assertEqual(subtotal(item,item_price(item)),Decimal('36.00'))
        other=Client.objects.create(company=self.company,name='Outro cliente artificial')
        Price.objects.create(company=self.company,client=other,product=self.bread,amount=9,billing_unit='KG',valid_from=self.day)
        order.client=other;order.save()
        self.assertEqual(configure_item(item).billing_factor,Decimal('.035'))

    def test_zero_placeholder_can_be_priced_retroactively_with_client_factor(self):
        zero=set_current_price(self.user,self.company,self.bread,Decimal(0),self.customer,billing_unit='PRODUCT',effective_on=self.day)
        order,item=self.order()
        with self.assertRaisesMessage(ValidationError,'Preço zerado'):item_price(item)
        response=self.client.post(f'/precos/{zero.pk}/',{'amount':'8.50','billing_unit':'KG','billing_factor':'0.040','effective_on':str(self.day)})
        self.assertEqual(response.status_code,302)
        item=configure_item(item)
        self.assertEqual(subtotal(item,item_price(item)),Decimal('34.00'))

    def test_invalid_factor_unit_does_not_replace_price(self):
        with self.assertRaises(ValidationError):
            set_current_price(self.user,self.company,self.bread,Decimal(9),self.customer,billing_unit='PRODUCT',billing_factor=Decimal('.035'),effective_on=self.day)
        self.assertEqual(Price.objects.filter(client=self.customer,product=self.bread,superseded=False).count(),1)
