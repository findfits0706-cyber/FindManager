import os

os.environ["DJANGO_ENVIRONMENT"] = "test"
os.environ.setdefault("DJANGO_LOGIN_THROTTLE_RATE", "1000/min")

from .settings import *  # noqa: E402,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
