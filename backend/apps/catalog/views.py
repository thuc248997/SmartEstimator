from django.db.models import Q
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import DatasetRelease, Resource, SourceDocument, WorkItem
from .serializers import (
    DatasetReleaseSerializer,
    NormComponentSerializer,
    ResourceSerializer,
    SourceDocumentSerializer,
    WorkItemDetailSerializer,
    WorkItemSerializer,
)

# Tên chương theo cấu trúc mã hiệu định mức dự toán xây dựng (tham khảo, dùng để lọc nhanh)
CHAPTERS = {
    "AA": "Công tác chuẩn bị mặt bằng xây dựng",
    "AB": "Công tác đào, đắp đất, đá, cát",
    "AC": "Công tác đóng cọc, ép cọc, nhổ cọc, khoan tạo lỗ",
    "AD": "Công tác làm đường",
    "AE": "Công tác xây gạch đá",
    "AF": "Công tác bê tông tại chỗ, cốt thép, ván khuôn",
    "AG": "Công tác sản xuất và lắp dựng cấu kiện bê tông đúc sẵn",
    "AH": "Công tác sản xuất, lắp dựng cấu kiện gỗ",
    "AI": "Công tác sản xuất, lắp dựng cấu kiện sắt thép",
    "AK": "Công tác làm mái, làm trần và các công tác hoàn thiện",
    "AL": "Các công tác khác",
    "BA": "Lắp đặt hệ thống điện trong công trình",
    "BB": "Lắp đặt hệ thống mạng, viễn thông, camera (điện nhẹ)",
}


class SourceDocumentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SourceDocument.objects.all()
    serializer_class = SourceDocumentSerializer


class DatasetReleaseViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DatasetRelease.objects.select_related("source").order_by("is_sample", "-id")
    serializer_class = DatasetReleaseSerializer
    filterset_fields = ["kind", "status", "region", "is_sample"]

    def get_queryset(self):
        qs = super().get_queryset()
        # Mặc định chỉ bản đã phát hành (bản nháp / bị gỡ không được chọn cho dự toán mới)
        if self.action == "list" and "status" not in self.request.query_params:
            qs = qs.filter(status=DatasetRelease.Status.PUBLISHED)
        return qs


class ResourceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Resource.objects.all()
    serializer_class = ResourceSerializer
    filterset_fields = ["kind"]

    def get_queryset(self):
        qs = super().get_queryset()
        q = self.request.query_params.get("query")
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        return qs


class WorkItemViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WorkItem.objects.select_related("release").all()
    filterset_fields = ["release", "group_code"]

    def get_serializer_class(self):
        return WorkItemDetailSerializer if self.action == "retrieve" else WorkItemSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        q = (self.request.query_params.get("query") or "").strip()
        # "Trát,75" → mọi từ khóa đều phải khớp (mã bắt đầu bằng, hoặc tên chứa)
        for term in [t.strip() for t in q.split(",") if t.strip()]:
            qs = qs.filter(Q(code__istartswith=term) | Q(name__icontains=term))
        return qs

    @action(detail=False, methods=["get"])
    def groups(self, request):
        """Danh mục chương (2 ký tự đầu mã) để lọc nhanh khi tra mã."""
        qs = WorkItem.objects.all()
        release = request.query_params.get("release")
        if release:
            qs = qs.filter(release_id=release)
        counts: dict[str, int] = {}
        for code in qs.values_list("code", flat=True):
            ch = code[:2].upper()
            counts[ch] = counts.get(ch, 0) + 1
        return Response(
            [{"code": ch, "name": CHAPTERS.get(ch, f"Chương {ch}"), "count": n} for ch, n in sorted(counts.items())]
        )

    @action(detail=True, methods=["get"])
    def norms(self, request, pk=None):
        wi = self.get_object()
        return Response(NormComponentSerializer(wi.components.select_related("resource"), many=True).data)
