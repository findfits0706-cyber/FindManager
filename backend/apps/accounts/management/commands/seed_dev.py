import os

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.constants import ROLE_CHOICES
from apps.accounts.models import User
from apps.accounts.services import ensure_roles

DEFAULT_PASSWORD = "DevPassword123!"


class Command(BaseCommand):
    help = "Create development seed data."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("本番環境では seed_dev を実行できません。")

        seed_password = os.getenv("DEV_SEED_PASSWORD")
        if not seed_password:
            seed_password = DEFAULT_PASSWORD
            self.stdout.write(
                self.style.WARNING("DEV_SEED_PASSWORD が未設定のため、既定の開発用パスワードを使用します。")
            )

        ensure_roles()
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
            user.set_password(seed_password)
            user.save()
            user.groups.set(Group.objects.filter(name=role))
            label = "created" if created else "updated"
            self.stdout.write(f"{label}: {username}")
        self.stdout.write(self.style.SUCCESS("開発用ユーザーの投入が完了しました。"))
