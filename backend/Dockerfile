FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system findmanager && adduser --system --ingroup findmanager findmanager

COPY pyproject.toml ./
COPY manage.py ./
COPY config ./config
COPY apps ./apps

RUN python -m pip install --upgrade pip && python -m pip install .
RUN DJANGO_DEBUG=1 DJANGO_SECRET_KEY=container-build-only python manage.py collectstatic --noinput

USER findmanager

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/', timeout=3)"

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
