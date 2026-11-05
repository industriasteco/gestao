from .models import Company


def operating_context(request):
    if not request.user.is_authenticated:return {'operational_mode':False}
    scope=Company.objects.all() if request.user.is_superuser else Company.objects.filter(membership__user=request.user)
    return {'operational_mode':scope.filter(operational_enabled=True).exists()}
