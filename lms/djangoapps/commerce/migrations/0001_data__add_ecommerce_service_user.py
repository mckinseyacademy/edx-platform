# -*- coding: utf-8 -*-


from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from django.db import migrations, models

USERNAME = settings.ECOMMERCE_SERVICE_WORKER_USERNAME
EMAIL = USERNAME + '@fake.email'

def forwards(apps, schema_editor):
    """Add the service user."""
    User = get_user_model()
    user, created = User.objects.get_or_create(username=USERNAME, email=EMAIL)
    if created:
        user.set_unusable_password()
        user.save()

def backwards(apps, schema_editor):
    """Remove the service user."""
    User.objects.get(username=USERNAME, email=EMAIL).delete()

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('user_api', '0002_retirementstate_userretirementstatus'),
        ('user_manager', '0001_initial'),
        ('user_manager', '0002_auto_20180721_1501'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
