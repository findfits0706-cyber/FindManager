from django.db.models.signals import m2m_changed, post_migrate
from django.dispatch import receiver

from .models import User
from .services import ensure_roles


@receiver(post_migrate)
def create_role_groups(sender, **kwargs):
    ensure_roles()


@receiver(m2m_changed, sender=User.groups.through)
def clear_role_cache(sender, instance, **kwargs):
    instance.__dict__.pop("_role_keys_cache", None)
