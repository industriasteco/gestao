from datetime import date,time
from decimal import Decimal
from io import BytesIO
from openpyxl import Workbook
from pypdf import PdfReader
from django.test import TestCase
from django.contrib.auth.models import User,Permission
from django.core.exceptions import ValidationError
from .models import *
from .day_finalization import finalize_day,assign_shift_responsibles
from .print_reference import load_company_reference
from . import pdf


class PrintingFlowTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('admin','', 'test-only')
        self.day=date(2026,11,5)
        self.teco=Company.objects.create(code='TECO',name='TECO ARTIFICIAL',cnpj='11111111111111',address='Endereço artificial TECO',phone='Telefone artificial',email='test@example.invalid')
        self.nona=Company.objects.create(code='NONA',name='NONA ARTIFICIAL',cnpj='22222222222222')
        self.client.force_login(self.user)

    def make_order(self,company,name='Cliente artificial'):
        customer=Client.objects.create(company=company,name=name,address='Entrega artificial')
        product=Product.objects.create(company=company,name='Produto artificial')
        Price.objects.create(company=company,product=product,amount=Decimal('1.25'),valid_from=self.day)
        order=Order.objects.create(company=company,client=customer,date=self.day,time=time(6),slot='Entrega 1',shift='NOTURNO',status='CONFERIDO',baker='Padeiro artificial',separator='Separador artificial',idempotency_key=str(customer.pk))
        OrderItem.objects.create(order=order,product=product,product_name=product.name,quantity=10,unit='UN')
        return order

    def test_finalize_generates_single_mixed_pdf_and_three_production_pages(self):
        self.make_order(self.teco);self.make_order(self.nona)
        docs=finalize_day(self.user,self.day)
        reader=PdfReader(BytesIO(docs[0].data));text=reader.pages[0].extract_text()
        self.assertEqual(len(reader.pages),1)
        self.assertIn('TECO ARTIFICIAL',text);self.assertIn('NONA ARTIFICIAL',text)
        self.assertEqual(text.count('VIA EMPRESA'),2);self.assertEqual(text.count('VIA CLIENTE'),2)
        self.assertIn('Padeiro artificial',text);self.assertIn('Separador artificial',text)
        self.assertIn('Endereço artificial TECO',text)
        self.assertEqual(len(PdfReader(BytesIO(docs[1].data)).pages),3)
        self.assertEqual(Order.objects.count(),2)
        count=Document.objects.count()
        again=finalize_day(self.user,self.day)
        self.assertEqual([d.pk for d in docs],[d.pk for d in again]);self.assertEqual(Document.objects.count(),count)

    def test_mixed_company_pdf_requires_all_memberships(self):
        self.make_order(self.teco);self.make_order(self.nona)
        doc=finalize_day(self.user,self.day)[0]
        viewer=User.objects.create_user('viewer');Membership.objects.create(user=viewer,company=doc.company)
        viewer.user_permissions.add(Permission.objects.get(codename='issue_document',content_type__app_label='core'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(f'/documentos/{doc.pk}/').status_code,403)

    def test_batch_failure_rolls_back_every_issued_order(self):
        a=self.make_order(self.teco);b=self.make_order(self.nona)
        Price.objects.filter(company=self.nona).delete()
        with self.assertRaises(ValidationError):finalize_day(self.user,self.day)
        a.refresh_from_db();b.refresh_from_db()
        self.assertEqual((a.status,b.status),('CONFERIDO','CONFERIDO'));self.assertEqual(Document.objects.count(),0)

    def test_batch_requires_checked_turns_and_cnpj(self):
        order=self.make_order(self.teco);order.status='PRE_LANCADO';order.save()
        with self.assertRaises(ValidationError):finalize_day(self.user,self.day)
        order.status='CONFERIDO';order.save();self.teco.cnpj=None;self.teco.save()
        with self.assertRaises(ValidationError):finalize_day(self.user,self.day)
        self.assertEqual(Document.objects.count(),0)

    def test_zero_items_are_omitted_and_responsibles_are_applied_by_shift(self):
        a=self.make_order(self.teco);b=self.make_order(self.nona)
        b.items.update(quantity=0)
        assign_shift_responsibles(self.user,self.day,'Novo padeiro artificial','','Separador teste')
        a.refresh_from_db();self.assertEqual(a.baker,'Novo padeiro artificial')
        docs=finalize_day(self.user,self.day)
        b.refresh_from_db();self.assertEqual(b.status,'CONFERIDO')
        self.assertNotIn('NONA ARTIFICIAL',PdfReader(BytesIO(docs[0].data)).pages[0].extract_text())

    def test_more_than_ten_items_keeps_every_item_and_totals_per_part(self):
        snapshot={'company_code':'TECO','company_name':'Empresa artificial','client_name':'Cliente artificial','cnpj':None,'date':str(self.day),'number':'TESTE','time':'06:00','slot':'1','ibis':False,'total':'55','items':[{'name':f'Produto artificial {i}','quantity':'1','unit':'UN','price':'5','total':'5'} for i in range(11)]}
        reader=PdfReader(BytesIO(pdf.receipts([snapshot])))
        self.assertEqual(len(reader.pages),1)
        text=reader.pages[0].extract_text()
        self.assertIn('Produto artificial 10',text)
        self.assertIn('50,00',text);self.assertIn('5,00',text)
        self.assertEqual(text.count('TOTAL DESTA FOLHA'),2)

    def test_reference_only_fills_company_metadata_and_never_imports_orders(self):
        book=Workbook();sheet=book.active;sheet.title='EMPRESAS'
        sheet.append([])
        for col,value in enumerate(['TECO','TECO ARTIFICIAL','Razão artificial',None,'Outro endereço artificial','Outro telefone','other@example.invalid'],1):sheet.cell(8,col,value)
        for col,value in enumerate(['NONA CECÍLIA','NONA ARTIFICIAL',None,None,'Endereço NONA artificial',None,None],1):sheet.cell(9,col,value)
        stream=BytesIO();book.save(stream)
        self.assertEqual(load_company_reference(self.user,stream.getvalue()),2)
        self.teco.refresh_from_db();self.nona.refresh_from_db()
        self.assertEqual(self.teco.address,'Endereço artificial TECO')
        self.assertEqual(self.teco.legal_name,'Razão artificial')
        self.assertEqual(self.nona.address,'Endereço NONA artificial')
        self.assertEqual(self.teco.cnpj,'11111111111111')
        self.assertEqual(Order.objects.count(),0)
        self.assertEqual(Client.objects.count(),0)
