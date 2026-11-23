from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import UserSetting
from .roles import ADMIN, ASSIGNEE, REPORTING, STANDARD


def ensure_user_settings(sender, instance, created, **kwargs):
    if created:
        UserSetting.objects.get_or_create(user=instance)


def connect_user_settings():
    post_save.connect(
        ensure_user_settings,
        sender=get_user_model(),
        dispatch_uid="stockroom.user_settings",
    )


@receiver(post_migrate, dispatch_uid="stockroom.ensure_groups")
def ensure_groups(sender, **kwargs):
    if sender.name != "stockroom":
        return
    for name in (STANDARD, ADMIN, REPORTING, ASSIGNEE):
        Group.objects.get_or_create(name=name)
