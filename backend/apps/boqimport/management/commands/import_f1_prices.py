from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.boqimport.f1 import F1Error, import_f1_file


class Command(BaseCommand):
    help = "Nạp giá vật tư (sheet Vật liệu) từ file dự toán xuất bởi phần mềm F1 thành bảng giá tham khảo"

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--label", required=True, help="Tên công trình nguồn, vd 'THPT Thiên Lộc'")
        parser.add_argument("--region", default="Hà Nội")

    def handle(self, path, label, region, **_):
        try:
            rel, info = import_f1_file(Path(path), label, region)
        except (F1Error, OSError) as e:
            raise CommandError(str(e)) from e
        state = "đã nạp" if info["created"] else "đã có sẵn (cùng file), không nạp lại"
        self.stdout.write(
            f"Bảng giá #{rel.id} “{rel.name}” {state}: {info['items']} vật tư có giá, "
            f"bỏ {info['skipped']} dòng giá 0 / %; kỳ {info['period'] or '?'}"
        )
