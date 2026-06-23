import os

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.constants import ROLE_CHOICES
from apps.accounts.models import User
from apps.accounts.services import ensure_roles
from apps.operations.services import seed_operations

DEFAULT_PASSWORD = "DevPassword123!"


class Command(BaseCommand):
    help = "Create development seed data."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_dev can only be used when DEBUG is enabled.")

        seed_password = os.getenv("DEV_SEED_PASSWORD")
        if not seed_password:
            seed_password = DEFAULT_PASSWORD
            self.stdout.write(
                self.style.WARNING("DEV_SEED_PASSWORD is not set. The default development password will be used.")
            )

        ensure_roles()
        reset_passwords = os.getenv("DEV_SEED_RESET_PASSWORDS", "0") == "1"
        seeded_users = {}
        for role in ROLE_CHOICES:
            username = role
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "display_name": f"{role} user",
                    "employee_code": f"EMP-{role.upper()}",
                    "must_change_password": role != "system_admin",
                    "is_staff": role == "system_admin",
                    "is_superuser": role == "system_admin",
                },
            )
            user.display_name = f"{role} user"
            user.employee_code = f"EMP-{role.upper()}"
            user.employment_status = User.EmploymentStatus.ACTIVE
            user.is_active = True
            if role == "system_admin":
                user.is_staff = True
                user.is_superuser = True
            if created or reset_passwords:
                user.set_password(seed_password)
            user.save()
            user.groups.set(Group.objects.filter(name=role))
            seeded_users[role] = user
            label = "created" if created else "updated"
            self.stdout.write(f"{label}: {username}")

        seed_operations(seeded_users)
        self.stdout.write(self.style.SUCCESS("Development seed data has been created."))
