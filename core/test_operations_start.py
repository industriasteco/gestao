import importlib
import uuid
from datetime import time,timedelta
from decimal import Decimal
from io import BytesIO
from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError,PermissionDenied
from django.test import TestCase
from django.utils import timezone
from pypdf import PdfReader
from .models import *
from .operations import activate_operation,reset_routines
from .services import prepare,check_production,activate
from .day_finalization import finalize_day,assign_shift_responsibles
from .statements import create_statement,statement_action
from .logistics_services import build_manifest,report_delivery,check_cash_bag
from .team import TeamForm,create_member
from . import workflow


class OperationsStartTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('gestor','', 'test-only')
        self.co=Company.objects.create(code='NONA',name='NONA ARTIFICIAL',legal_name='RAZÃO ARTIFICIAL',cnpj='11111111111111',address='Endereço artificial',phone='Contato artificial')
        self.today=timezone.localdate()
        self.customer=Client.objects.create(company=self.co,name='CLIENTE ARTIFICIAL',recurring_weekdays=[self.today.isoweekday()])
        self.product=Product.objects.create(company=self.co,name='PRODUTO ARTIFICIAL',production_cost=1)
        self.price=Price.objects.create(company=self.co,product=self.product,amount=2,valid_from=self.today)
        self.client.force_login(self.user)

    def enable(self):activate_operation(self.user,self.co);self.co.refresh_from_db()

    def rule(self,automatic=False):
        return Recurrence.objects.create(company=self.co,client=self.customer,product=self.product,quantity=10,slot='Fixo',time=time(6),shift='NOTURNO',weekdays=[self.today.isoweekday()],valid_from=self.today,active=True,auto_prepare=automatic)

    def order(self,synthetic=False,status='CONFERIDO',quantity=10):
        order=Order.objects.create(company=self.co,client=self.customer,date=self.today,time=time(6),slot='Entrega',shift='NOTURNO',baker='Padeiro artificial',synthetic=synthetic,status=status,idempotency_key=str(uuid.uuid4()))
        OrderItem.objects.create(order=order,product=self.product,product_name=self.product.name,unit='UN',quantity=quantity)
        return order

    def text(self,document):return '\n'.join(page.extract_text() for page in PdfReader(BytesIO(document.data)).pages)

    def test_migration_retires_preloaded_rules_without_deleting_confirmed_rules_or_records(self):
        old=self.rule();new=self.rule(automatic=True)
        order=self.order(synthetic=True);order.recurrence=old;order.save()
        importlib.import_module('core.migrations.0021_retire_preloaded_routines').retire_preloaded(apps,None)
        old.refresh_from_db();new.refresh_from_db();order.refresh_from_db()
        self.assertTrue(old.archived);self.assertFalse(old.active)
        self.assertFalse(new.archived);self.assertTrue(new.active)
        self.assertEqual(order.recurrence_id,old.pk)
        self.assertEqual(Client.objects.count(),1);self.assertEqual(Product.objects.count(),1);self.assertEqual(Order.objects.count(),1)

    def test_full_reset_preserves_catalogue_prices_orders_and_blocks_old_rule_activation(self):
        rule=self.rule();order=self.order(synthetic=True);order.recurrence=rule;order.save()
        self.assertEqual(reset_routines(self.user),1)
        rule.refresh_from_db();self.customer.refresh_from_db()
        self.assertTrue(rule.archived);self.assertEqual(self.customer.recurring_weekdays,[])
        self.assertEqual(prepare(self.user,self.today),0)
        with self.assertRaises(ValidationError):activate(self.user,rule,'Tentativa de reativação artificial')
        self.assertEqual(self.client.get(f'/rotinas/{rule.pk}/').status_code,404)
        self.assertEqual(Order.objects.count(),1);self.assertEqual(Price.objects.count(),1)

    def test_reset_retry_does_not_remove_a_new_routine_created_after_first_response(self):
        self.rule();key=str(uuid.uuid4());data={'action':'reset','confirm':'yes','key':key}
        self.assertEqual(self.client.post('/comecar/',data).status_code,302)
        new=self.rule(automatic=True)
        self.assertEqual(self.client.post('/comecar/',data).status_code,302)
        new.refresh_from_db();self.assertFalse(new.archived);self.assertTrue(new.active)

    def test_activation_checks_missing_data_and_is_idempotent(self):
        self.co.legal_name='';self.co.save()
        with self.assertRaises(ValidationError):activate_operation(self.user,self.co)
        self.co.legal_name='RAZÃO ARTIFICIAL';self.co.save()
        self.price.delete()
        with self.assertRaises(ValidationError):activate_operation(self.user,self.co)
        Price.objects.create(company=self.co,product=self.product,amount=2,valid_from=self.today)
        self.enable();activate_operation(self.user,self.co)
        self.assertTrue(self.co.operational_enabled)
        self.assertEqual(Audit.objects.filter(action='ATIVAR_OPERACAO_GERENCIAL').count(),1)

    def test_start_page_and_activation_require_admin_and_explicit_action(self):
        self.assertEqual(self.client.get('/comecar/').status_code,200)
        self.assertEqual(self.client.post('/comecar/',{'action':'activate','company':str(self.co.pk)}).status_code,302)
        self.co.refresh_from_db();self.assertFalse(self.co.operational_enabled)
        self.client.post('/comecar/',{'action':'activate','company':str(self.co.pk),'confirm':'yes'})
        self.co.refresh_from_db();self.assertTrue(self.co.operational_enabled)
        reader=User.objects.create_user('leitor');Membership.objects.create(user=reader,company=self.co)
        self.client.force_login(reader)
        self.assertEqual(self.client.get('/comecar/').status_code,403)
        with self.assertRaises(PermissionDenied):reset_routines(reader)

    def test_manual_order_is_operational_and_keeps_selected_tomorrow_date(self):
        self.enable();tomorrow=self.today+timedelta(days=1)
        response=self.client.get(f'/novo-pedido/?date={tomorrow}')
        self.assertEqual(response.context['form']['date'].value(),tomorrow)
        data={'company':str(self.co.pk),'client':str(self.customer.pk),'date':str(tomorrow),'time':'06:00','slot':'Entrega','shift':'NOTURNO','baker':'Padeiro artificial','key':str(uuid.uuid4()),'form-TOTAL_FORMS':'1','form-INITIAL_FORMS':'0','form-0-product':str(self.product.pk),'form-0-quantity':'10'}
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,302)
        order=Order.objects.get();self.assertFalse(order.synthetic);self.assertEqual(order.date,tomorrow)
        self.assertEqual(timezone.localtime(order.created_at).date(),self.today)
        self.assertEqual(self.client.post('/novo-pedido/',data).status_code,302);self.assertEqual(Order.objects.count(),1)

    def test_real_receipt_requires_activation_and_remains_immutable_after_price_change(self):
        order=self.order()
        with self.assertRaises(ValidationError):workflow.issue(self.user,order.pk)
        self.enable();order.company=self.co
        document=workflow.issue(self.user,order.pk);original=bytes(document.data)
        text=self.text(document)
        self.assertIn('COMPROVANTE DE ENTREGA',text);self.assertIn('DOCUMENTO NAO FISCAL',text)
        self.assertNotIn('HOMOLOG',text);self.assertNotIn('NAO COBRAR',text)
        order.refresh_from_db();self.assertFalse(order.issued_snapshot['synthetic']);self.assertNotIn('TESTE',order.commercial_number)
        self.price.amount=10;self.price.save()
        self.assertEqual(bytes(workflow.issue(self.user,order.pk).data),original)

    def test_missing_company_data_or_item_price_blocks_real_emission(self):
        self.enable();order=self.order();self.co.cnpj=None;self.co.save()
        with self.assertRaises(ValidationError):workflow.issue(self.user,order.pk)
        self.co.cnpj='11111111111111';self.co.save();self.price.delete()
        with self.assertRaises(ValidationError):workflow.issue(self.user,order.pk)
        self.assertEqual(Document.objects.count(),0)

    def test_real_ibis_keeps_four_portrait_pages_and_non_fiscal_identification(self):
        self.enable();self.customer.name='IBIS';self.customer.save()
        document=workflow.issue(self.user,self.order().pk);reader=PdfReader(BytesIO(document.data))
        self.assertEqual(len(reader.pages),4)
        for page in reader.pages:
            self.assertLess(page.mediabox.width,page.mediabox.height)
            self.assertIn('DOCUMENTO NAO FISCAL',page.extract_text());self.assertNotIn('HOMOLOG',page.extract_text())

    def test_finalization_excludes_old_tests_and_produces_real_documents_once(self):
        self.enable();old=self.order(synthetic=True,status='PRE_LANCADO',quantity=999);real=self.order(status='PRE_LANCADO')
        assign_shift_responsibles(self.user,self.today,'Padeiro artificial','','Separação artificial');check_production(self.user,self.today)
        old.refresh_from_db();self.assertEqual(old.status,'PRE_LANCADO')
        docs=finalize_day(self.user,self.today)
        self.assertEqual([doc.pk for doc in docs],[doc.pk for doc in finalize_day(self.user,self.today)])
        self.assertNotIn('HOMOLOG',self.text(docs[1]));self.assertNotIn('999',self.text(docs[1]))
        real.refresh_from_db();self.assertEqual(real.status,'EMITIDO')
        self.assertEqual(self.client.get(f'/pedidos-dia/?date={self.today}').context['orders'].count(),1)

    def test_real_delivery_statement_and_dashboard_preserve_values_without_auto_debt(self):
        self.enable();order=self.order();workflow.issue(self.user,order.pk);workflow.deliver(self.user,order.pk,'Entrega artificial confirmada')
        statement=create_statement(self.user,self.co,self.customer,self.today.replace(day=1),self.today)
        self.assertFalse(statement.snapshot['synthetic']);self.assertEqual(statement.total,20)
        self.assertNotIn('HOMOLOG',self.text(statement.document))
        statement_action(self.user,statement,'send','Envio artificial de conferência');statement_action(self.user,statement,'approve','Aprovação artificial de conferência')
        self.assertEqual(self.client.get(f'/fechamentos-clientes/{statement.pk}/exportar/').status_code,200)
        self.assertEqual(self.client.get('/painel/').context['revenue'],20)
        self.assertEqual(Receivable.objects.count(),0)

    def test_real_manifest_delivery_and_matching_cash_bag_register_receipt_once(self):
        self.enable();order=self.order();workflow.issue(self.user,order.pk)
        driver=Driver.objects.create(company=self.co,name='Motorista artificial')
        route=DeliveryRoute.objects.create(company=self.co,name='Rota artificial',driver=driver)
        RouteStop.objects.create(route=route,client=self.customer,sequence=1)
        manifest=build_manifest(self.user,route,self.today)
        account=Receivable.objects.create(company=self.co,client=self.customer,reference='Conta artificial',issued_on=self.today,due_on=self.today,amount=20)
        report_delivery(self.user,manifest.lines.get(),{'delivery_status':'ENTREGUE','reported_amount':Decimal(10),'payment_method':'DINHEIRO','receivable':account,'evidence':'Entrega e dinheiro artificiais para conferência'})
        order.refresh_from_db();self.assertEqual(order.status,'ENTREGUE')
        check_cash_bag(self.user,manifest,'Malote artificial',Decimal(10),'Conferência artificial')
        self.assertEqual(Payment.objects.get().amount,10)

    def test_production_role_can_prepare_own_real_routines_without_financial_permissions(self):
        self.enable();self.rule(automatic=True)
        form=TeamForm({'username':'producao','company':str(self.co.pk),'role':'PRODUCAO','password1':'Artificial-Password-1248!','password2':'Artificial-Password-1248!'},user=self.user)
        self.assertTrue(form.is_valid(),form.errors)
        user=create_member(form,self.user)
        self.assertEqual(prepare(user,self.today,automatic_only=True),1)
        order=Order.objects.get();self.assertFalse(order.synthetic)
        self.assertFalse(user.has_perm('core.add_receivable'))
        with self.assertRaises(PermissionDenied):workflow.issue(user,order.pk)

    def test_future_delivery_can_be_printed_today_but_not_confirmed_before_delivery_date(self):
        self.enable();order=self.order();order.date=self.today+timedelta(days=1);order.save()
        workflow.issue(self.user,order.pk)
        self.assertFalse(self.client.get(f'/pedidos/{order.pk}/').context['can_confirm_delivery'])
        with self.assertRaises(ValidationError):workflow.deliver(self.user,order.pk,'Tentativa de confirmar entrega futura')
        order.refresh_from_db();self.assertEqual(order.status,'EMITIDO');self.assertIsNone(order.delivered_at)

    def test_produced_today_for_tomorrow_compares_to_tomorrows_orders(self):
        self.enable();tomorrow=self.today+timedelta(days=1)
        order=self.order(status='PRE_LANCADO');order.date=tomorrow;order.save()
        data={'company':str(self.co.pk),'product':str(self.product.pk),'date':str(self.today),'planned_for':str(tomorrow),'shift':'NOTURNO','batch':'LOTE-ARTIFICIAL','quantity':'11','losses':'1','baker':'Padeiro artificial','notes':'Perda artificial registrada'}
        self.assertEqual(self.client.post(f'/producao/realizada/?date={tomorrow}',data).status_code,302)
        record=ProductionRecord.objects.get();self.assertEqual(record.date,self.today);self.assertEqual(record.planned_for,tomorrow)
        response=self.client.get(f'/producao/realizada/?date={tomorrow}')
        comparison=list(response.context['comparison'])[0]
        self.assertEqual(comparison['planned'],10);self.assertEqual(comparison['produced'],11);self.assertEqual(comparison['good'],10);self.assertEqual(comparison['gap'],0)
        data['date']=str(tomorrow);data['batch']='FUTURO-INVALIDO'
        self.assertEqual(self.client.post('/producao/realizada/',data).status_code,200)
        self.assertEqual(ProductionRecord.objects.count(),1)

    def test_operational_preparation_is_not_blocked_by_a_previous_test_for_same_client_and_date(self):
        self.rule(automatic=True)
        self.assertEqual(prepare(self.user,self.today),1)
        old=Order.objects.get();self.assertTrue(old.synthetic)
        self.enable()
        self.assertEqual(prepare(self.user,self.today),1)
        self.assertEqual(Order.objects.count(),2)
        self.assertEqual(Order.objects.filter(synthetic=False).count(),1)
        old.refresh_from_db();self.assertTrue(old.synthetic)
