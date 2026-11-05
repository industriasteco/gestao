import uuid
from io import BytesIO
from datetime import date, time, timedelta
from decimal import Decimal
from openpyxl import Workbook
from django.test import TestCase
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import *
from .excel_import import read_workbook, inferred_patterns, import_workbook
from .management_services import set_price, receive, balances, move_stock
from .services import price_for, prepare


def workbook():
    book=Workbook();book.remove(book.active)
    for day,qty in [(1,10),(8,10),(15,10),(29,20)]:
        sheet=book.create_sheet(f'{day}-outubro-26_MD')
        sheet.cell(5,4,date(2026,10,day))
        sheet.cell(6,1,'Cliente:');sheet.cell(6,2,'CLIENTE ARTIFICIAL')
        for column in (1,7):
            sheet.cell(8,column,qty);sheet.cell(8,column+1,'P. ÁGUA')
            sheet.cell(9,column,5);sheet.cell(9,column+1,'P. LEITE')
            sheet.cell(10,column+1,'EMBALAR SEPARADO E ENTREGAR NA PORTARIA')
    old=book.create_sheet('SEGUNDA');old.cell(1,1,'MODELO ANTIGO')
    out=BytesIO();book.save(out);return out.getvalue()


class ManagementTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.co=Company.objects.create(code='TEST',name='Empresa artificial')
        self.customer=Client.objects.create(company=self.co,name='Cliente artificial')
        self.product=Product.objects.create(company=self.co,name='Pão artificial')
        self.today=timezone.localdate()
        self.client.force_login(self.user)

    def test_import_creates_only_catalogue_and_routines_idempotently(self):
        data=workbook()
        batch,created,analysis=import_workbook(self.user,self.co,data,'ARTIFICIAL.xlsm',date(2026,11,1))
        self.assertTrue(created)
        self.assertEqual(Order.objects.count(),0)
        self.assertEqual(Receivable.objects.count(),0)
        self.assertEqual(Recurrence.objects.filter(active=True).count(),2)
        self.assertEqual(analysis['clients'],1)
        self.assertEqual(analysis['products'],2)
        self.assertEqual(len(analysis['orders']),4)
        self.assertEqual(Price.objects.count(),0)
        Candidate.objects.create(batch=batch,row_number=999,category='ITEM_A_CONFERIR',raw={'reason':'Aviso de teste'})
        self.assertEqual(self.client.get('/rotinas/').status_code,200)
        self.assertEqual(self.client.get(f'/clientes/{self.customer.pk}/').status_code,200)
        self.assertIn('EMBALAR',Client.objects.get(name__iexact='CLIENTE ARTIFICIAL').notes)
        _,created,_=import_workbook(self.user,self.co,data,'ARTIFICIAL.xlsm',date(2026,11,1))
        self.assertFalse(created)
        self.assertEqual(Recurrence.objects.count(),2)

    def test_weekday_mode_ignores_missing_sheets_but_counts_absence_in_available_dates(self):
        analysis=read_workbook(workbook())
        pattern=next(p for p in inferred_patterns(analysis) if p['product']=='P. ÁGUA')
        self.assertEqual((pattern['quantity'],pattern['matches'],pattern['samples']),('10',3,4))
        self.assertTrue(pattern['stable'])
        # Item present once among four available Thursdays is not a routine.
        for order in analysis['orders'][1:]:order['items']=[]
        self.assertFalse(inferred_patterns(analysis)[0]['stable'])

    def test_future_preparation_groups_products_and_keeps_adjustments(self):
        import_workbook(self.user,self.co,workbook(),'ARTIFICIAL.xlsm',date(2026,11,1))
        self.assertEqual(prepare(self.user,date(2026,11,5)),1)
        order=Order.objects.get()
        self.assertEqual(order.items.count(),2)
        line=order.items.first();line.quantity=99;line.save()
        self.assertEqual(prepare(self.user,date(2026,11,5)),0)
        line.refresh_from_db();self.assertEqual(line.quantity,99)
        self.assertIn('EMBALAR',order.notes)

    def test_negotiated_prices_and_history_do_not_overwrite(self):
        start=date(2026,1,1)
        first=set_price(self.user,self.co,self.product,Decimal('2'),start)
        set_price(self.user,self.co,self.product,Decimal('3'),date(2026,2,1))
        first.refresh_from_db();self.assertEqual(first.valid_until,date(2026,1,31))
        set_price(self.user,self.co,self.product,Decimal('1.5'),start,self.customer)
        self.assertEqual(price_for(self.co,self.customer,self.product,date(2026,2,5)),Decimal('1.5'))
        with self.assertRaises(ValidationError):set_price(self.user,self.co,self.product,Decimal('4'),date(2026,2,1))

    def test_product_price_can_be_entered_directly_in_product_form(self):
        response=self.client.post('/cadastros/produtos/',{'company':str(self.co.pk),'name':'Novo pão','unit':'UN','amount':'2.50','valid_from':str(self.today)})
        self.assertEqual(response.status_code,302)
        product=Product.objects.get(name='Novo pão')
        self.assertEqual(Price.objects.get(product=product).amount,Decimal('2.5'))

    def account(self):
        return Receivable.objects.create(company=self.co,client=self.customer,reference='TESTE',issued_on=self.today-timedelta(days=15),due_on=self.today-timedelta(days=10),amount=100)

    def test_partial_payment_updates_balance_and_status_and_is_idempotent(self):
        row=self.account()
        receive(self.user,row,Decimal('30'),self.today,'payment-1')
        receive(self.user,row,Decimal('30'),self.today,'payment-1')
        self.assertEqual(Payment.objects.count(),1)
        current=balances(self.user)[0]
        self.assertEqual((current.balance,current.days_late),(70,10))
        self.assertContains(self.client.get(f'/clientes/{self.customer.pk}/'),'Inadimplente')
        receive(self.user,row,Decimal('70'),self.today,'payment-2')
        self.assertEqual(balances(self.user)[0].days_late,0)
        self.assertContains(self.client.get(f'/clientes/{self.customer.pk}/'),'Adimplente')

    def test_overpayment_and_future_payment_rejected(self):
        row=self.account()
        with self.assertRaises(ValidationError):receive(self.user,row,Decimal('101'),self.today,'too-much')
        with self.assertRaises(ValidationError):receive(self.user,row,Decimal('1'),self.today+timedelta(days=1),'future')
        self.assertEqual(Payment.objects.count(),0)

    def test_stock_cannot_be_negative_and_retries_do_not_duplicate(self):
        item=StockItem.objects.create(company=self.co,name='Farinha artificial',minimum=5)
        key=uuid.uuid4()
        move_stock(self.user,item,Decimal('10'),self.today,'Entrada',key)
        move_stock(self.user,item,Decimal('10'),self.today,'Entrada',key)
        with self.assertRaises(ValidationError):move_stock(self.user,item,Decimal('-11'),self.today,'Saída',uuid.uuid4())
        self.assertEqual(item.movements.count(),1)
        with self.assertRaises(ValidationError):move_stock(self.user,item,Decimal('-2'),self.today-timedelta(days=1),'Saída retroativa',uuid.uuid4())

    def test_tenant_cannot_see_other_company_clients_stock_or_finance(self):
        self.account()
        viewer=User.objects.create_user('leitor')
        other=Company.objects.create(code='OTHER',name='Outra empresa')
        Membership.objects.create(user=viewer,company=other)
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(f'/clientes/{self.customer.pk}/').status_code,404)
        self.assertEqual(self.client.get('/financeiro/').status_code,403)
        self.assertEqual(self.client.post('/financeiro/',{}).status_code,403)
        self.assertEqual(self.client.get('/rotinas/importar/').status_code,403)

    def test_dashboard_does_not_count_test_orders_as_revenue(self):
        order=Order.objects.create(company=self.co,client=self.customer,date=self.today,time=time(6),slot='Teste',status='EMITIDO',synthetic=True,idempotency_key='test')
        OrderItem.objects.create(order=order,product=self.product,product_name=self.product.name,unit='UN',quantity=10,unit_price_snapshot=2)
        response=self.client.get('/')
        self.assertEqual(response.context['revenue'],0)
        self.assertEqual(response.context['test_orders'],1)
        order.synthetic=False;order.save()
        response=self.client.get('/')
        self.assertEqual(response.context['revenue'],20)
        self.assertEqual(response.context['units'][0]['quantity'],10)

    def test_all_new_pages_render_and_legacy_date_link_still_works(self):
        for url in ['/', '/painel/', '/?date=2026-11-05','/pedidos-dia/','/rotinas/','/rotinas/importar/','/financeiro/','/estoque/',f'/clientes/{self.customer.pk}/',f'/produtos/{self.product.pk}/','/cadastros/clientes/','/cadastros/produtos/']:
            with self.subTest(url=url):self.assertEqual(self.client.get(url).status_code,200)
        row=self.account();self.assertEqual(self.client.get(f'/financeiro/{row.pk}/receber/').status_code,200)

    def test_company_mismatch_rejected_in_financial_and_price_forms(self):
        other=Company.objects.create(code='OTHER',name='Outra')
        other_client=Client.objects.create(company=other,name='Cliente outra')
        response=self.client.post('/financeiro/',{'company':str(self.co.pk),'client':str(other_client.pk),'reference':'wrong','issued_on':str(self.today),'due_on':str(self.today),'amount':'10'})
        self.assertEqual(response.status_code,200)
        self.assertFalse(Receivable.objects.exists())
        with self.assertRaises(ValidationError):set_price(self.user,self.co,self.product,Decimal('1'),self.today,other_client)

    def test_divergent_copies_are_flagged_instead_of_guessed(self):
        book=Workbook()
        sheet=book.active;sheet.title='1-outubro-26_MD'
        sheet.cell(5,4,date(2026,10,1));sheet.cell(6,1,'Cliente:');sheet.cell(6,2,'Artificial')
        sheet.cell(8,2,'P. ÁGUA');sheet.cell(8,7,140);sheet.cell(8,8,'P. ÁGUA')
        stream=BytesIO();book.save(stream)
        analysis=read_workbook(stream.getvalue())
        self.assertEqual(analysis['orders'][0]['items'],[])
        self.assertIn('Vias divergentes',analysis['orders'][0]['problems'][0]['reason'])

    def test_unverified_input_cannot_be_backdated_as_routine(self):
        with self.assertRaises(ValidationError):
            import_workbook(self.user,self.co,workbook(),'ARTIFICIAL.xlsm',date(2026,10,1))
        self.assertFalse(ImportBatch.objects.exists())

    def test_editing_imported_time_does_not_duplicate_prepared_order(self):
        import_workbook(self.user,self.co,workbook(),'ARTIFICIAL.xlsm',date(2026,11,1))
        prepare(self.user,date(2026,11,5))
        Recurrence.objects.update(time=time(5))
        self.assertEqual(prepare(self.user,date(2026,11,5)),0)
        self.assertEqual(Order.objects.count(),1)

    def test_manually_registered_rules_group_like_the_excel_automation(self):
        from datetime import time
        Recurrence.objects.create(company=self.co,client=self.customer,product=self.product,quantity=10,slot='1',time=time(6),shift='NOTURNO',weekdays=[4],valid_from=date(2026,11,1),active=True)
        other=Product.objects.create(company=self.co,name='Outro produto artificial')
        Recurrence.objects.create(company=self.co,client=self.customer,product=other,quantity=5,slot='1',time=time(6),shift='NOTURNO',weekdays=[4],valid_from=date(2026,11,1),active=True)
        self.assertEqual(prepare(self.user,date(2026,11,5)),1)
        self.assertEqual(Order.objects.get().items.count(),2)
        self.assertEqual(prepare(self.user,date(2026,11,5)),0)
