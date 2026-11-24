import json

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.calculation.serializers import CalculationRunSerializer
from apps.calculation.services import start_calculation
from apps.projects.models import EstimateRevision

from .parser import FIELDS, BoqParseError, parse_workbook
from .prices import auto_apply_catalog_prices
from .service import build_preview, commit

MAX_UPLOAD = 10 * 1024 * 1024


def _int(v):
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


@api_view(["POST"])
@parser_classes([MultiPartParser])
def preview(request, pk):
    """Đọc file BoQ (multipart: file, tùy chọn sheet, header_row, columns={"name": 3, ...}) và gợi ý mã.
    Không ghi gì vào CSDL."""
    revision = get_object_or_404(EstimateRevision.objects.select_related("project"), pk=pk)
    f = request.FILES.get("file")
    if f is None:
        return Response({"detail": "Chưa chọn file"}, status=status.HTTP_400_BAD_REQUEST)
    if f.size > MAX_UPLOAD:
        return Response({"detail": "File lớn hơn 10 MB"}, status=status.HTTP_400_BAD_REQUEST)
    columns = None
    if request.data.get("columns"):
        try:
            raw = json.loads(request.data["columns"])
            columns = {k: _int(raw.get(k)) for k in FIELDS if k in raw}
        except (ValueError, AttributeError):
            return Response({"detail": "columns không hợp lệ"}, status=status.HTTP_400_BAD_REQUEST)
    try:
        parsed = parse_workbook(
            f.read(),
            sheet=request.data.get("sheet") or None,
            header_row=_int(request.data.get("header_row")),
            columns=columns,
        )
    except BoqParseError as e:
        return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    data = build_preview(parsed, revision.project.norm_release_id)
    data["filename"] = f.name
    return Response(data)


@api_view(["POST"])
@parser_classes([JSONParser])
def commit_view(request, pk):
    """Ghi BoQ đã duyệt vào revision rồi tính dự toán (calculate=true, mặc định)."""
    revision = get_object_or_404(EstimateRevision.objects.select_related("project"), pk=pk)
    result = commit(revision, request.data if isinstance(request.data, dict) else {}, request.user)
    if request.data.get("auto_prices", True):
        result["prices"] = auto_apply_catalog_prices(revision, request.user)
    if request.data.get("calculate", True):
        run_obj = start_calculation(revision)
        result["run"] = CalculationRunSerializer(run_obj).data
    return Response(result, status=status.HTTP_201_CREATED)


@api_view(["POST"])
def auto_prices(request, pk):
    """Tự áp giá vật liệu từ công bố giá cho các vật liệu chưa có giá, rồi tính lại."""
    revision = get_object_or_404(EstimateRevision.objects.select_related("project"), pk=pk)
    if revision.is_locked:
        return Response(
            {"detail": f"Revision đã {revision.status}, không được sửa."}, status=status.HTTP_400_BAD_REQUEST
        )
    result = auto_apply_catalog_prices(revision, request.user)
    run_obj = start_calculation(revision)
    result["run"] = CalculationRunSerializer(run_obj).data
    return Response(result)
