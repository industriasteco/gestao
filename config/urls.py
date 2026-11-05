from django.contrib import admin
from django.urls import path,include
from core.views import daily,staging
from core import operator_views as op
from core import management_views as mg
from core import logistics_views as lg
from core import statement_views as st
from core import payables_views as ap
from core.access import first_access
urlpatterns=[
    path('empresas/<uuid:pk>/',mg.company_detail,name='company_detail'),
    path('contas-a-pagar/',ap.payables,name='payables'),
    path('contas-a-pagar/<uuid:pk>/',ap.payable_detail,name='payable_detail'),
    path('fornecedores/',ap.suppliers,name='suppliers'),
    path('fornecedores/<uuid:pk>/',ap.supplier_detail,name='supplier_detail'),
    path('notas-de-compra/',ap.invoices,name='purchase_invoices'),
    path('notas-de-compra/<uuid:pk>/',ap.invoice_detail,name='invoice_detail'),
    path('notas-de-compra/<uuid:pk>/xml/',ap.invoice_xml,name='invoice_xml'),
    path('fiscal/',ap.fiscal_overview,name='fiscal_overview'),

    path('modelo-impressao/',op.print_reference,name='print_reference'),
    path('fechamentos-clientes/',st.statements,name='statements'),
    path('fechamentos-clientes/<uuid:pk>/',st.statement_detail,name='statement_detail'),
    path('fechamentos-clientes/<uuid:pk>/pdf/',st.statement_document,name='statement_document'),
    path('fechamentos-clientes/<uuid:pk>/exportar/',st.statement_export,name='statement_export'),

    path('equipe/',lg.team,name='team'),
    path('producao/realizada/',lg.production_actual,name='production_actual'),
    path('rotas/',lg.routes,name='routes'),
    path('rotas/<uuid:pk>/',lg.route_detail,name='route_detail'),
    path('motoristas/<uuid:pk>/',lg.driver_detail,name='driver_detail'),
    path('romaneios/',lg.manifests,name='manifests'),
    path('romaneios/<uuid:pk>/',lg.manifest_detail,name='manifest_detail'),
    path('romaneios/<uuid:pk>/pdf/',lg.manifest_pdf,name='manifest_pdf'),
    path('entregas/<uuid:pk>/',lg.manifest_line,name='manifest_line'),

    path('painel/',mg.dashboard,name='dashboard'),
    path('clientes/<uuid:pk>/',mg.client_detail,name='client_detail'),
    path('produtos/<uuid:pk>/',mg.product_detail,name='product_detail'),
    path('financeiro/',mg.finance,name='finance'),
    path('financeiro/<uuid:pk>/receber/',mg.payment,name='payment'),
    path('estoque/',mg.stock,name='stock'),
    path('rotinas/',mg.routines,name='routines'),
    path('rotinas/importar/',mg.routines_import,name='routines_import'),
    path('rotinas/<uuid:pk>/',mg.routine_detail,name='routine_detail'),
path('iniciar-demonstracao/',op.start_demo,name='start_demo'),path('novo-pedido/',op.new_order,name='new_order'),path('primeiro-acesso/',first_access,name='first_access'),path('ajuda/',op.guide,name='guide'),path('cadastros/<str:kind>/',op.records,name='records'),path('pedidos/<uuid:pk>/',op.order_detail,name='order'),path('documentos/<uuid:pk>/',op.document,name='document'),path('fechamento/',op.monthly,name='monthly'),path('auditoria/',op.audit,name='audit'),path('documentos-dia/',op.daily_pdf,name='daily_pdf'),path('admin/',admin.site.urls),path('accounts/',include('django.contrib.auth.urls')),path('pedidos-dia/',daily,name='daily'),path('',mg.home,name='home'),path('staging/',staging,name='staging')]
