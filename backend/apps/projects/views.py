from django.db import transaction
from django.db.models import F, Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.audit.services import record

from .models import EquipmentCost, EstimateLine, EstimateRevision, Project, ProjectItem, ResourceOverride
from .serializers import (
    EquipmentCostSerializer,
    EstimateLineSerializer,
    EstimateRevisionSerializer,
    ProjectItemSerializer,
    ProjectSerializer,
    ResourceOverrideSerializer,
)


class LockedRevision(ValidationError):
    pass


def _assert_unlocked(revision: EstimateRevision):
    if revision.is_locked:
        raise ValidationError({"detail": f"Revision đã {revision.status}, không được sửa. Tạo revision mới."})


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.all().order_by("-id")
    serializer_class = ProjectSerializer

    def perform_create(self, serializer):
        project = serializer.save(created_by=self.request.user)
        record(self.request.user, "project.create", project)

    def perform_update(self, serializer):
        before = ProjectSerializer(serializer.instance).data
        project = serializer.save()
        after = ProjectSerializer(project).data
        record(
            self.request.user,
            "project.update",
            project,
            {k: [before[k], after[k]] for k in after if before.get(k) != after[k]},
        )

    @action(detail=True, methods=["get", "post"])
    def revisions(self, request, pk=None):
        project = self.get_object()
        if request.method == "GET":
            return Response(EstimateRevisionSerializer(project.revisions.all(), many=True).data)
        number = (project.revisions.aggregate(m=Max("number"))["m"] or 0) + 1
        rev = EstimateRevision.objects.create(project=project, number=number, title=request.data.get("title", ""))
        source_id = request.data.get("copy_from")
        if source_id:
            _copy_revision(get_object_or_404(EstimateRevision, pk=source_id, project=project), rev)
        record(request.user, "revision.create", rev, {"copy_from": source_id})
        return Response(EstimateRevisionSerializer(rev).data, status=status.HTTP_201_CREATED)


@transaction.atomic
def _copy_revision(src: EstimateRevision, dst: EstimateRevision):
    for item in src.items.all():
        new_item = ProjectItem.objects.create(revision=dst, order=item.order, name=item.name)
        for ln in item.lines.all():
            ln.pk = None
            ln.item = new_item
            ln.version = 1
            ln.save()
    for ov in src.overrides.all():
        ov.pk = None
        ov.revision = dst
        ov.save()
    for eq in src.equipment.all():
        eq.pk = None
        eq.revision = dst
        eq.save()


class EstimateRevisionViewSet(mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet):
    queryset = EstimateRevision.objects.select_related("project").prefetch_related(
        "items__lines__work_item", "overrides__resource", "equipment"
    )
    serializer_class = EstimateRevisionSerializer

    def perform_update(self, serializer):
        _assert_unlocked(self.get_object())
        serializer.save()

    @action(detail=True, methods=["post"])
    def items(self, request, pk=None):
        rev = self.get_object()
        _assert_unlocked(rev)
        ser = ProjectItemSerializer(data={**request.data, "revision": rev.id})
        ser.is_valid(raise_exception=True)
        item = ser.save()
        return Response(ProjectItemSerializer(item).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"items/(?P<item_id>\d+)")
    def item(self, request, pk=None, item_id=None):
        rev = self.get_object()
        _assert_unlocked(rev)
        item = get_object_or_404(ProjectItem, pk=item_id, revision=rev)
        if request.method == "DELETE":
            record(request.user, "item.delete", item, {"name": item.name})
            item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        ser = ProjectItemSerializer(item, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save()
        record(request.user, "item.update", item, dict(request.data))
        return Response(ProjectItemSerializer(item).data)

    @action(detail=True, methods=["post"])
    def lines(self, request, pk=None):
        """Thêm một hoặc nhiều dòng: body là object hoặc list."""
        rev = self.get_object()
        _assert_unlocked(rev)
        many = isinstance(request.data, list)
        ser = EstimateLineSerializer(data=request.data, many=many)
        ser.is_valid(raise_exception=True)
        payload = ser.validated_data if many else [ser.validated_data]
        for d in payload:
            if d["item"].revision_id != rev.id:
                raise ValidationError({"item": "Hạng mục không thuộc revision này"})
        created = ser.save()
        for ln in created if many else [created]:
            record(request.user, "line.create", ln, {"code": ln.code, "quantity": str(ln.quantity)})
        return Response(ser.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"lines/(?P<line_id>\d+)")
    def line(self, request, pk=None, line_id=None):
        rev = self.get_object()
        _assert_unlocked(rev)
        ln = get_object_or_404(EstimateLine, pk=line_id, item__revision=rev)
        if request.method == "DELETE":
            record(request.user, "line.delete", ln, {"code": ln.code})
            ln.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        expected = request.data.get("version")
        if expected is not None and int(expected) != ln.version:
            return Response(
                {"detail": "Dòng đã bị người khác sửa", "version": ln.version}, status=status.HTTP_409_CONFLICT
            )
        before = EstimateLineSerializer(ln).data
        ser = EstimateLineSerializer(ln, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        new_item = ser.validated_data.get("item")
        if new_item is not None and new_item.revision_id != rev.id:
            raise ValidationError({"item": "Hạng mục không thuộc revision này"})
        with transaction.atomic():
            ser.save()
            EstimateLine.objects.filter(pk=ln.pk).update(version=F("version") + 1)
        ln.refresh_from_db()
        after = EstimateLineSerializer(ln).data
        record(request.user, "line.update", ln, {k: [before[k], after[k]] for k in after if before.get(k) != after[k]})
        return Response(after)

    @action(detail=True, methods=["post"], url_path=r"items/(?P<item_id>\d+)/reorder")
    def reorder(self, request, pk=None, item_id=None):
        """Sắp xếp lại / chuyển dòng vào hạng mục: body {"line_ids": [...]} theo thứ tự mới."""
        rev = self.get_object()
        _assert_unlocked(rev)
        item = get_object_or_404(ProjectItem, pk=item_id, revision=rev)
        ids = request.data.get("line_ids")
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            raise ValidationError({"line_ids": "Cần danh sách id dòng"})
        lines = {ln.id: ln for ln in EstimateLine.objects.filter(pk__in=ids, item__revision=rev)}
        if len(lines) != len(set(ids)):
            raise ValidationError({"line_ids": "Có dòng không thuộc revision này"})
        with transaction.atomic():
            for order, lid in enumerate(ids, 1):
                EstimateLine.objects.filter(pk=lid).update(item=item, order=order, version=F("version") + 1)
        record(request.user, "item.reorder", item, {"line_ids": ids})
        return Response(ProjectItemSerializer(ProjectItem.objects.get(pk=item.pk)).data)

    @action(detail=True, methods=["post"])
    def equipment(self, request, pk=None):
        rev = self.get_object()
        _assert_unlocked(rev)
        ser = EquipmentCostSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        eq = ser.save(revision=rev)
        record(request.user, "equipment.create", eq, {"name": eq.name})
        return Response(EquipmentCostSerializer(eq).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch", "delete"], url_path=r"equipment/(?P<eq_id>\d+)")
    def equipment_item(self, request, pk=None, eq_id=None):
        rev = self.get_object()
        _assert_unlocked(rev)
        eq = get_object_or_404(EquipmentCost, pk=eq_id, revision=rev)
        if request.method == "DELETE":
            record(request.user, "equipment.delete", eq, {"name": eq.name})
            eq.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        ser = EquipmentCostSerializer(eq, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        # Chỉ ghi các trường được gửi: hai ô sửa liên tiếp (số lượng, đơn giá) không ghi đè lẫn nhau
        EquipmentCost.objects.filter(pk=eq.pk).update(**ser.validated_data)
        eq.refresh_from_db()
        record(request.user, "equipment.update", eq, {k: str(v) for k, v in request.data.items()})
        return Response(EquipmentCostSerializer(eq).data)

    @action(detail=True, methods=["post"])
    def overrides(self, request, pk=None):
        rev = self.get_object()
        _assert_unlocked(rev)
        ser = ResourceOverrideSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ov, _ = ResourceOverride.objects.update_or_create(
            revision=rev,
            resource=ser.validated_data["resource"],
            defaults={
                "price": ser.validated_data["price"],
                "reason": ser.validated_data["reason"],
                "created_by": request.user,
            },
        )
        record(
            request.user,
            "override.upsert",
            ov,
            {"resource": ov.resource.code, "price": str(ov.price)},
            reason=ov.reason,
        )
        return Response(ResourceOverrideSerializer(ov).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def review(self, request, pk=None):
        rev = self.get_object()
        _assert_unlocked(rev)
        rev.status = EstimateRevision.Status.REVIEW
        rev.save(update_fields=["status"])
        record(request.user, "revision.review", rev)
        return Response(EstimateRevisionSerializer(rev).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        """Khóa revision: snapshot + hash lấy từ lần tính gần nhất (phải DONE và không có lỗi chặn)."""
        from apps.calculation.models import CalculationRun
        from apps.calculation.services import BLOCKING_WARNINGS

        rev = self.get_object()
        _assert_unlocked(rev)
        run = CalculationRun.objects.filter(revision=rev, status=CalculationRun.Status.DONE).order_by("-id").first()
        if run is None:
            raise ValidationError({"detail": "Chưa có lần tính thành công. Gọi /calculate trước."})
        blocking = [w for w in run.warnings if w.get("code") in BLOCKING_WARNINGS]
        if blocking and not request.data.get("force"):
            return Response(
                {"detail": "Có cảnh báo chặn phê duyệt", "warnings": blocking}, status=status.HTTP_409_CONFLICT
            )
        rev.status = EstimateRevision.Status.APPROVED
        rev.snapshot = run.snapshot
        rev.content_hash = run.output_hash
        rev.approved_run = run
        rev.approved_by = request.user
        rev.approved_at = timezone.now()
        rev.save()
        record(
            request.user,
            "revision.approve",
            rev,
            {"run": run.id, "output_hash": run.output_hash},
            reason=request.data.get("reason", ""),
        )
        return Response(EstimateRevisionSerializer(rev).data)
