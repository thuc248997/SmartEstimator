from django.core.management.base import BaseCommand

from apps.datasync.models import DataUpdateRun
from apps.datasync.service import ALL_SOURCES, run_update


class Command(BaseCommand):
    help = "Kiểm tra và cập nhật định mức TT 38/2026 + giá Hà Nội mới nhất (giống nút 'Cập nhật dữ liệu')"

    def add_arguments(self, parser):
        parser.add_argument("--source", action="append", choices=ALL_SOURCES)
        parser.add_argument("--force", action="store_true", help="Nạp lại kể cả khi đã là bản mới nhất")

    def handle(self, *args, **opts):
        run = DataUpdateRun.objects.create(sources=opts.get("source") or [])
        run = run_update(run.id, force=opts["force"])
        self.stdout.write(run.log)
        for r in run.results:
            self.stdout.write(f"[{r['status']}] {r['title']}: {r['message']}")
            for w in r.get("warnings", []):
                self.stdout.write(self.style.WARNING(f"   ! {w}"))
