from django.contrib import admin
from django import forms
from django.core.exceptions import ValidationError
from .models import Company,Client,Product,Price,Recurrence,Membership,Audit
from .services import companies

class CompanyForm(forms.ModelForm):
    class Meta:
        fields='__all__'
    def clean(self):
        data=super().clean()
        company=data.get('company')
        for field in ('client','product'):
            linked=data.get(field)
            if linked and company and linked.company_id!=company.pk:
                raise ValidationError('Cliente/produto deve pertencer à empresa selecionada.')
        return data

class ScopedAdmin(admin.ModelAdmin):
    form=CompanyForm
    def get_readonly_fields(self,request,obj=None):
        return ['active'] if self.model is Recurrence else []
    def get_queryset(self,request):
        qs=super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(company__in=companies(request.user))
    def has_add_permission(self,request): return request.user.is_superuser
    def has_change_permission(self,request,obj=None): return request.user.is_superuser and not (self.model is Price and obj is not None)
    def has_delete_permission(self,request,obj=None): return False
    def save_model(self,request,obj,form,change):
        before={}
        if change:
            old=type(obj).objects.get(pk=obj.pk)
            before={f:str(getattr(old,f)) for f in form.changed_data}
        obj.full_clean();super().save_model(request,obj,form,change)
        Audit.objects.create(actor=request.user,entity=str(obj.pk),action='ALTERAR' if change else 'CRIAR',before=before,after={f:str(getattr(obj,f)) for f in form.changed_data})
for model in [Client,Product,Price,Recurrence]: admin.site.register(model,ScopedAdmin)
class CompanyAdmin(ScopedAdmin):
    def get_queryset(self,request): return companies(request.user)
admin.site.register(Company,CompanyAdmin)
class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self,r): return False
    def has_change_permission(self,r,obj=None): return False
    def has_delete_permission(self,r,obj=None): return False
    def has_view_permission(self,r,obj=None): return r.user.is_superuser
admin.site.register(Audit,ReadOnly)
class MembershipAdmin(admin.ModelAdmin):
    def has_module_permission(self,r): return r.user.is_superuser
    def has_view_permission(self,r,obj=None): return r.user.is_superuser
    def has_add_permission(self,r): return r.user.is_superuser
    def has_change_permission(self,r,obj=None): return r.user.is_superuser
    def has_delete_permission(self,r,obj=None): return r.user.is_superuser
admin.site.register(Membership,MembershipAdmin)
