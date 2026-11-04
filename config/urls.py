from django.contrib import admin
from django.urls import path,include
from core.views import daily,staging
from core import operator_views as op
from core.access import first_access
urlpatterns=[path('iniciar-demonstracao/',op.start_demo,name='start_demo'),path('novo-pedido/',op.new_order,name='new_order'),path('primeiro-acesso/',first_access,name='first_access'),path('ajuda/',op.guide,name='guide'),path('cadastros/<str:kind>/',op.records,name='records'),path('pedidos/<uuid:pk>/',op.order_detail,name='order'),path('documentos/<uuid:pk>/',op.document,name='document'),path('fechamento/',op.monthly,name='monthly'),path('auditoria/',op.audit,name='audit'),path('documentos-dia/',op.daily_pdf,name='daily_pdf'),path('admin/',admin.site.urls),path('accounts/',include('django.contrib.auth.urls')),path('',daily,name='daily'),path('staging/',staging,name='staging')]
