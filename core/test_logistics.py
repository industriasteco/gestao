import uuid
from datetime import timedelta, time
from decimal import Decimal
from io import BytesIO
from pypdf import PdfReader
from django.test import TestCase
from django.contrib.auth.models import User, Permission
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils import timezone
from .models import *
from .logistics_services import register_production,build_manifest,report_delivery,check_cash_bag
from .logistics_views import line_status
from .management_services import balances
from .team import TeamForm,create_member


class OperationsTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('admin','', 'test-only')
        self.company=Company.objects.create(code='ART',name='Empresa artificial')
        self.customer=Client.objects.create(company=self.company,name='Cliente artificial',address='Endereço artificial')
        self.product=Product.objects.create(company=self.company,name='Pão artificial',unit='UN',production_cost=Decimal('1.2'))
        self.driver=Driver.objects.create(company=self.company,name='Motorista artificial',vehicle='Veículo artificial')
        self.route=DeliveryRoute.objects.create(company=self.company,name='Rota artificial',driver=self.driver)
        RouteStop.objects.create(route=self.route,client=self.customer,sequence=1,instructions='Entregar na portaria artificial')
        self.today=timezone.localdate()
        Price.objects.create(company=self.company,product=self.product,amount=2,valid_from=self.today)
        self.client.force_login(self.user)

    def make_order(self,synthetic=True):
        order=Order.objects.create(company=self.company,client=self.customer,date=self.today,time=time(6),slot='1',synthetic=synthetic,status='EMITIDO',issued_snapshot={'total':'20'},idempotency_key=str(uuid.uuid4()))
        OrderItem.objects.create(order=order,product=self.product,product_name=self.product.name,quantity=10,unit='UN',unit_price_snapshot=2)
        return order

    def report(self,line,amount='20',account=None,method='DINHEIRO',delivery='ENTREGUE'):
        return report_delivery(self.user,line,{'reported_amount':Decimal(amount),'payment_method':method,'receivable':account,'delivery_status':delivery,'evidence':'Conferência artificial da entrega e dinheiro.'})

    def account(self):
        return Receivable.objects.create(company=self.company,client=self.customer,reference='ARTIFICIAL',issued_on=self.today,due_on=self.today,amount=20)

    def test_production_preserves_cost_and_measures_losses(self):
        record=ProductionRecord(company=self.company,product=self.product,date=self.today,shift='DIURNO',batch='LOTE-1',quantity=100,losses=5,baker='Padeiro artificial',notes='Perda artificial no forno')
        register_production(self.user,record)
        self.product.production_cost=9;self.product.save()
        record.refresh_from_db()
        self.assertEqual(record.cost_snapshot,Decimal('1.2'))
        self.assertEqual(record.quantity-record.losses,95)
        self.assertEqual(record.actor,self.user)
        response=self.client.get('/producao/realizada/')
        self.assertEqual(response.status_code,200)
        self.assertEqual(list(response.context['comparison'])[0]['good'],95)

    def test_invalid_losses_and_future_production_rejected(self):
        for losses,day in [(11,self.today),(1,self.today+timedelta(days=1))]:
            with self.assertRaises(ValidationError):
                register_production(self.user,ProductionRecord(company=self.company,product=self.product,date=day,shift='DIURNO',batch='INVALID',quantity=10,losses=losses,baker='Teste',notes='Teste'))
        self.assertEqual(ProductionRecord.objects.count(),0)

    def test_production_compares_per_company_not_just_product_name(self):
        self.make_order()
        register_production(self.user,ProductionRecord(company=self.company,product=self.product,date=self.today,shift='DIURNO',batch='LOTE',quantity=9,losses=1,baker='Teste',notes='Perda teste'))
        row=list(self.client.get('/producao/realizada/').context['comparison'])[0]
        self.assertEqual((row['planned'],row['good'],row['shortage']),(10,8,2))

    def test_product_profit_uses_current_cost_and_sale_price(self):
        response=self.client.get(f'/produtos/{self.product.pk}/')
        self.assertEqual(response.context['profit'],Decimal('.8'))
        self.assertEqual(response.context['margin'],40)
        self.assertContains(response,'Lucro bruto')

    def test_manifest_is_idempotent_and_preserves_snapshot(self):
        order=self.make_order()
        manifest=build_manifest(self.user,self.route,self.today)
        self.assertEqual(manifest.lines.count(),1)
        self.assertEqual(manifest.lines.get().amount_due,20)
        self.assertEqual(build_manifest(self.user,self.route,self.today).pk,manifest.pk)
        self.product.name='Nome modificado';self.product.save()
        self.driver.name='Outro nome';self.driver.save()
        manifest.refresh_from_db()
        self.assertEqual(manifest.driver_name,'Motorista artificial')
        self.assertEqual(manifest.lines.get().items_snapshot[0]['product'],'Pão artificial')
        self.assertEqual(Order.objects.count(),1)

    def test_one_order_cannot_be_sent_in_two_routes(self):
        self.make_order();build_manifest(self.user,self.route,self.today)
        other=DeliveryRoute.objects.create(company=self.company,name='Outra rota',driver=self.driver)
        RouteStop.objects.create(route=other,client=self.customer,sequence=1)
        with self.assertRaises(ValidationError):build_manifest(self.user,other,self.today)
        self.assertEqual(DeliveryManifest.objects.count(),1)

    def test_cash_report_does_not_pay_account_until_bag_matches(self):
        self.make_order(synthetic=False)
        manifest=build_manifest(self.user,self.route,self.today);line=manifest.lines.get();account=self.account()
        self.report(line,'10',account)
        self.assertEqual(balances(self.user)[0].balance,20)
        bag=check_cash_bag(self.user,manifest,'BAG-1',Decimal('9'),'Diferença artificial para conferência')
        self.assertEqual(bag.status,'DIVERGENTE');self.assertEqual(Payment.objects.count(),0)
        bag=check_cash_bag(self.user,manifest,'BAG-1',Decimal('10'),'Reconferência: valor correto localizado')
        self.assertEqual(bag.status,'CONFERIDO');self.assertEqual(balances(self.user)[0].balance,10)
        check_cash_bag(self.user,manifest,'BAG-1',Decimal('10'),'Repetição')
        self.assertEqual(Payment.objects.count(),1)
        line.refresh_from_db();self.assertIn('Parcial',line_status(line,bag))

    def test_cash_bag_difference_requires_explanation(self):
        self.make_order();manifest=build_manifest(self.user,self.route,self.today);self.report(manifest.lines.get())
        with self.assertRaises(ValidationError):check_cash_bag(self.user,manifest,'BAG',Decimal('19'),'')
        self.assertEqual(CashBag.objects.count(),0)

    def test_test_orders_cannot_pay_real_accounts(self):
        self.make_order();manifest=build_manifest(self.user,self.route,self.today);line=manifest.lines.get()
        with self.assertRaises(ValidationError):self.report(line,account=self.account())
        self.report(line)
        bag=check_cash_bag(self.user,manifest,'BAG',Decimal('20'),'Simulação')
        self.assertEqual(bag.status,'CONFERIDO');self.assertEqual(Payment.objects.count(),0)

    def test_bag_requires_report_for_every_client_and_preserves_closed_reports(self):
        self.make_order();manifest=build_manifest(self.user,self.route,self.today);line=manifest.lines.get()
        with self.assertRaises(ValidationError):check_cash_bag(self.user,manifest,'BAG',Decimal('0'),'')
        self.report(line,'0',method='PRAZO')
        check_cash_bag(self.user,manifest,'BAG',Decimal('0'),'Sem recebimento')
        with self.assertRaises(ValidationError):self.report(line,'10')
        with self.assertRaises(ValidationError):check_cash_bag(self.user,manifest,'BAG',Decimal('1'),'')

    def test_electronic_payment_is_not_mistaken_for_cash(self):
        self.make_order();manifest=build_manifest(self.user,self.route,self.today);line=manifest.lines.get()
        with self.assertRaises(ValidationError):self.report(line,'20',method='PIX')
        self.report(line,'0',method='PIX')
        bag=check_cash_bag(self.user,manifest,'BAG',Decimal('0'),'Comprovante precisa de conferência bancária')
        line.refresh_from_db();self.assertIn('PIX',line_status(line,bag));self.assertEqual(Payment.objects.count(),0)

    def test_manifest_pdf_includes_payment_status_and_bag(self):
        self.make_order();manifest=build_manifest(self.user,self.route,self.today);line=manifest.lines.get();self.report(line)
        check_cash_bag(self.user,manifest,'BAG-ARTIFICIAL',Decimal('20'),'Teste')
        response=self.client.get(f'/romaneios/{manifest.pk}/pdf/')
        self.assertEqual(response.status_code,200)
        text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
        self.assertIn('malote conferido',text)
        self.assertIn('BAG-ARTIFICIAL',text)
        self.assertIn('HOMOLOGAÇÃO',text)
        self.assertIn('Cliente artificial',text)

    def test_logistics_and_production_are_company_scoped(self):
        order=self.make_order();manifest=build_manifest(self.user,self.route,self.today)
        other=Company.objects.create(code='OTHER',name='Outra')
        viewer=User.objects.create_user('viewer');Membership.objects.create(user=viewer,company=other)
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(f'/romaneios/{manifest.pk}/').status_code,404)
        self.assertEqual(self.client.get(f'/romaneios/{manifest.pk}/pdf/').status_code,404)
        self.assertEqual(self.client.get(f'/rotas/{self.route.pk}/').status_code,404)

    def test_all_new_operational_pages_render_with_populated_records(self):
        self.make_order();manifest=build_manifest(self.user,self.route,self.today)
        for url in ['/producao/realizada/','/rotas/',f'/rotas/{self.route.pk}/',f'/motoristas/{self.driver.pk}/','/romaneios/',f'/romaneios/{manifest.pk}/',f'/entregas/{manifest.lines.get().pk}/','/equipe/']:
            with self.subTest(url=url):self.assertEqual(self.client.get(url).status_code,200)

    def test_employee_roles_separate_production_from_cash_counting(self):
        form=TeamForm({'username':'padeiro','first_name':'Padeiro artificial','company':str(self.company.pk),'role':'PRODUCAO','password1':'Password-Artificial-9843!','password2':'Password-Artificial-9843!'},user=self.user)
        self.assertTrue(form.is_valid(),form.errors)
        employee=create_member(form,self.user)
        self.assertTrue(employee.has_perm('core.add_productionrecord'))
        self.assertFalse(employee.has_perm('core.add_cashbag'))
        self.assertFalse(employee.is_staff)
        self.client.force_login(employee)
        self.assertContains(self.client.get('/'),'Produção realizada')
        self.assertEqual(self.client.get('/financeiro/').status_code,403)
        response=self.client.post('/producao/realizada/',{'company':str(self.company.pk),'product':str(self.product.pk),'date':str(self.today),'shift':'DIURNO','batch':'FUNCIONARIO','quantity':'5','losses':'0','baker':'Padeiro artificial','notes':''})
        self.assertEqual(response.status_code,302)
        self.assertEqual(ProductionRecord.objects.get().actor,employee)
