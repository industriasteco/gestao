from django.test import TestCase,override_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from .models import Audit
class FirstAccessTests(TestCase):
    def setUp(self):cache.clear()
    @override_settings(SETUP_KEY='test-private-invitation')
    def test_bootstrap_requires_key_and_cannot_repeat(self):
        form={'username':'gestor','password1':'Strong-Test-Password-234','password2':'Strong-Test-Password-234','setup_key':'wrong'}
        self.assertEqual(self.client.post('/primeiro-acesso/',form).status_code,200)
        self.assertFalse(User.objects.exists())
        form['setup_key']='test-private-invitation'
        self.assertEqual(self.client.post('/primeiro-acesso/',form).status_code,302)
        self.assertTrue(User.objects.get().is_superuser)
        self.assertTrue(Audit.objects.filter(action='PRIMEIRO_ACESSO').exists())
        self.assertEqual(self.client.get('/primeiro-acesso/').status_code,404)
    @override_settings(SETUP_KEY='')
    def test_no_unprotected_first_access(self):self.assertEqual(self.client.get('/primeiro-acesso/').status_code,404)
