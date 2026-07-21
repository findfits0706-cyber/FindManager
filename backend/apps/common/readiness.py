from dataclasses import dataclass

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@dataclass(frozen=True)
class ReadinessResult:
    database: bool
    migrations: bool
    settings: bool

    @property
    def ready(self) -> bool:
        return self.database and self.migrations and self.settings


def database_is_ready() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return False
    return True


def migrations_are_current() -> bool:
    try:
        executor = MigrationExecutor(connection)
        return not executor.migration_plan(executor.loader.graph.leaf_nodes())
    except Exception:
        return False


def required_settings_are_ready() -> bool:
    basic = bool(settings.SECRET_KEY and settings.ALLOWED_HOSTS and settings.STATIC_ROOT and settings.MEDIA_ROOT)
    if settings.ENVIRONMENT != "production":
        return basic
    return bool(
        basic
        and not settings.DEBUG
        and settings.CSRF_TRUSTED_ORIGINS
        and settings.SESSION_COOKIE_SECURE
        and settings.CSRF_COOKIE_SECURE
        and settings.SECURE_SSL_REDIRECT
        and settings.SECURE_HSTS_SECONDS > 0
    )


def check_readiness() -> ReadinessResult:
    database = database_is_ready()
    return ReadinessResult(
        database=database,
        migrations=database and migrations_are_current(),
        settings=required_settings_are_ready(),
    )
