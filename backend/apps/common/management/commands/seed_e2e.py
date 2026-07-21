from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.constants import ROLE_CHOICES
from apps.accounts.models import User


class Command(BaseCommand):
    help = "Create deterministic seed users and masters in a dedicated development/test E2E database."

    def handle(self, *args, **options):
        if not settings.DEBUG or settings.ENVIRONMENT not in {"development", "test"}:
            raise CommandError("seed_e2e is restricted to DEBUG development/test environments.")
        call_command("seed_dev", stdout=self.stdout)
        User.objects.filter(username__in=ROLE_CHOICES).update(must_change_password=False)
        self.stdout.write(self.style.SUCCESS("E2E seed data has been created."))
