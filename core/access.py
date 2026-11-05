from django import forms
from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection,transaction
from django.http import Http404,HttpResponse
from django.shortcuts import render,redirect
from django.utils.crypto import constant_time_compare
from .models import Audit

class ERPLoginView(LoginView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['setup_available'] = bool(settings.SETUP_KEY) and not User.objects.filter(is_superuser=True, is_active=True).exists()
        return context

class FirstAccessForm(UserCreationForm):
    setup_key=forms.CharField(label='Chave de primeiro acesso',widget=forms.PasswordInput)
    class Meta:
        model=User;fields=['username','password1','password2','setup_key']

def first_access(request):
    if not settings.SETUP_KEY or User.objects.filter(is_superuser=True,is_active=True).exists():raise Http404
    form=FirstAccessForm(request.POST or None)
    if request.method=='POST':
        key='setup-rate:'+request.META.get('REMOTE_ADDR','unknown')
        attempts=cache.get(key,0)
        if attempts>=5:return HttpResponse('Aguarde alguns minutos antes de tentar novamente.',status=429)
        cache.set(key,attempts+1,300)
        if form.is_valid():
            if not constant_time_compare(form.cleaned_data['setup_key'],settings.SETUP_KEY):form.add_error('setup_key','Chave inválida. Confira a chave nas configurações da hospedagem.')
            else:
                with transaction.atomic():
                    with connection.cursor() as cursor:cursor.execute('SELECT pg_advisory_xact_lock(49881001)')
                    if User.objects.filter(is_superuser=True,is_active=True).exists():raise Http404
                    user=form.save(commit=False);user.is_staff=True;user.is_superuser=True;user.save()
                    Audit.objects.create(actor=user,entity=str(user.pk),action='PRIMEIRO_ACESSO',reason='Conta criada com chave de instalação')
                login(request,user);return redirect('guide')
    return render(request,'core/first_access.html',{'form':form})
