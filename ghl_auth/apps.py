from django.apps import AppConfig


class GhlAuthConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ghl_auth"

    def ready(self):
        from django.db.models.signals import post_migrate

        post_migrate.connect(_ensure_ghl_refresh_periodic_task, sender=self)


def _ensure_ghl_refresh_periodic_task(sender, **kwargs):
    """Keep celery-beat PeriodicTask in sync after migrations (not on every process boot)."""
    try:
        from django_celery_beat.models import IntervalSchedule, PeriodicTask

        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=4,
            period=IntervalSchedule.HOURS,
        )
        PeriodicTask.objects.update_or_create(
            name="refresh-ghl-oauth-tokens",
            defaults={
                "task": "api.tasks.make_api_call",
                "interval": schedule,
                "crontab": None,
                "enabled": True,
                "description": "Refresh GHL OAuth access/refresh tokens every 4 hours",
            },
        )
    except Exception:
        # Beat tables may not exist yet during early migrate.
        pass
