from django.core.management.base import BaseCommand

from ghl_auth.token_service import refresh_all_credentials


class Command(BaseCommand):
    help = "Refresh GoHighLevel OAuth access/refresh tokens (safe to run from cron)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Refresh even if the access token is still within the freshness window.",
        )

    def handle(self, *args, **options):
        force = options["force"]
        results = refresh_all_credentials(force=force)
        self.stdout.write(self.style.SUCCESS(f"GHL token refresh complete: {results}"))
        if results["failed"]:
            raise SystemExit(1)
