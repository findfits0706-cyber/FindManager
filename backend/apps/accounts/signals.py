from django.db.models.signals import post_migrate
from django.dispatch import receiver

from .services import ensure_roles


@receiver(post_migrate)
def create_role_groups(sender, **kwargs):
    ensure_roles()
