"""Seed SAMPLE catalog/prices, the TT 36/2026 rule pack, and a demo user+token."""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from rest_framework.authtoken.models import Token

from apps.catalog.loader import load_catalog
from apps.regulations.loader import load_rule_pack

FIXTURES = Path(settings.BASE_DIR) / "fixtures"


class Command(BaseCommand):
    help = "Nạp dữ liệu MẪU (không phải số liệu chính thức) + rule pack TT 36/2026 + user demo"

    def add_arguments(self, parser):
        parser.add_argument("--no-user", action="store_true")

    def handle(self, *args, **opts):
        pack = load_rule_pack(FIXTURES / "rule_pack_tt36_2026.json")
        norm_rel, price_rel = load_catalog(FIXTURES / "sample_catalog.json")
        self.stdout.write(self.style.SUCCESS(f"Rule pack: {pack} (approved={pack.is_approved})"))
        self.stdout.write(self.style.SUCCESS(f"Norm release: {norm_rel} | Price release: {price_rel}"))
        if not opts["no_user"]:
            User = get_user_model()
            user, created = User.objects.get_or_create(
                username="demo", defaults={"is_staff": True, "is_superuser": True}
            )
            if created:
                user.set_password("demo12345")
                user.save()
            token, _ = Token.objects.get_or_create(user=user)
            self.stdout.write(self.style.SUCCESS(f"Demo user 'demo' / 'demo12345' — API token: {token.key}"))
        self.stdout.write(self.style.WARNING("⚠ Dữ liệu catalog/giá là SAMPLE — không dùng cho hồ sơ thật."))
