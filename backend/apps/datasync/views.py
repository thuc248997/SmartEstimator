from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.audit.services import record
from apps.catalog.models import DatasetRelease

from .models import DataUpdateRun, PriceCatalogItem
from .serializers import DataUpdateRunSerializer, PriceCatalogItemSerializer
from .service import ALL_SOURCES, run_update


class DataUpdateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = DataUpdateRun.objects.all()
    serializer_class = DataUpdateRunSerializer

    def get_permissions(self):
        if self.action == "create":
            return [permissions.IsAdminUser()]
        return super().get_permissions()

    def create(self, request):
        """Kiểm tra và cập nhật dữ liệu mới nhất (chạy nền). Đang có lượt chạy → trả về lượt đó."""
        busy = DataUpdateRun.objects.filter(
            status__in=["queued", "running"], started_at__gte=timezone.now() - timedelta(hours=1)
        ).first()
        if busy:
            return Response(DataUpdateRunSerializer(busy).data, status=status.HTTP_200_OK)
        sources = (
            [s for s in request.data.get("sources", []) if s in ALL_SOURCES] if isinstance(request.data, dict) else []
        )
        force = bool(request.data.get("force")) if isinstance(request.data, dict) else False
        run = DataUpdateRun.objects.create(triggered_by=request.user, sources=sources)
        record(request.user, "data.update.start", run, {"sources": sources, "force": force})
        if settings.CELERY_TASK_ALWAYS_EAGER:
            run_update(run.id, force=force)
            run.refresh_from_db()
        else:
            from .tasks import run_update_task

            res = run_update_task.delay(run.id, force)
            DataUpdateRun.objects.filter(pk=run.pk).update(celery_task_id=res.id)
        return Response(DataUpdateRunSerializer(run).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def data_status(request):
    """Bản dữ liệu đang có (mới nhất mỗi loại) + lượt kiểm tra gần nhất."""
    rels = (
        DatasetRelease.objects.filter(status="published")
        .select_related("source")
        .annotate(
            n_items=Count("work_items", distinct=True),
            n_prices=Count("prices", distinct=True),
            n_catalog=Count("catalog_items", distinct=True),
        )
        .order_by("-id")
    )
    out = []
    for r in rels:
        out.append(
            {
                "id": r.id,
                "kind": r.kind,
                "name": r.name,
                "version": r.version,
                "region": r.region,
                "is_sample": r.is_sample,
                "effective_from": r.effective_from,
                "created_at": r.created_at,
                "source": {
                    "number": r.source.number,
                    "issuer": r.source.issuer,
                    "url": r.source.url,
                    "issued_on": r.source.issued_on,
                }
                if r.source
                else None,
                "counts": {"work_items": r.n_items, "prices": r.n_prices, "catalog_items": r.n_catalog},
                "meta": {k: v for k, v in r.meta.items() if k != "report"},
                "report": {
                    k: v
                    for k, v in r.meta.get("report", {}).items()
                    if k not in ("skipped_tables", "unmatched_machines")
                },
            }
        )
    last = DataUpdateRun.objects.order_by("-id").first()
    return Response(
        {
            "releases": out,
            "last_run": DataUpdateRunSerializer(last).data if last else None,
            "can_update": request.user.is_staff,
        }
    )


class PriceCatalogViewSet(viewsets.ReadOnlyModelViewSet):
    """Tra giá vật liệu công bố: ?query=xi măng,PC40&release=<id> (mặc định bản mới nhất)."""

    serializer_class = PriceCatalogItemSerializer

    def get_queryset(self):
        qs = PriceCatalogItem.objects.select_related("release")
        rel = self.request.query_params.get("release")
        if rel:
            qs = qs.filter(release_id=rel)
        else:
            latest = DatasetRelease.objects.filter(kind="CATALOG", status="published").order_by("-id").first()
            qs = qs.filter(release=latest) if latest else qs.none()
        q = (self.request.query_params.get("query") or "").strip()
        for term in [t.strip() for t in q.split(",") if t.strip()]:
            qs = qs.filter(Q(name__icontains=term) | Q(spec__icontains=term) | Q(context__icontains=term))
        unit = self.request.query_params.get("unit")
        if unit:
            qs = qs.filter(unit__iexact=unit)
        return qs.order_by("name", "price")
