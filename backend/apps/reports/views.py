import hashlib

from django.core.files.base import ContentFile
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.audit.services import record
from apps.calculation.models import CalculationRun
from apps.projects.models import EstimateRevision

from .excel import TEMPLATE_VERSION, workbook_bytes
from .models import ReportArtifact

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@api_view(["POST"])
def export(request, pk):
    revision = get_object_or_404(EstimateRevision, pk=pk)
    template = request.query_params.get("template", "estimate-xlsx")
    if template != "estimate-xlsx":
        return Response({"detail": f"Template không hỗ trợ: {template}"}, status=status.HTTP_400_BAD_REQUEST)
    run = (
        revision.approved_run
        if revision.is_locked and revision.approved_run_id
        else (
            CalculationRun.objects.filter(revision=revision, status=CalculationRun.Status.DONE).order_by("-id").first()
        )
    )
    if run is None:
        return Response({"detail": "Chưa có lần tính thành công"}, status=status.HTTP_409_CONFLICT)
    data = workbook_bytes(run)
    digest = hashlib.sha256(data).hexdigest()
    name = f"{slugify(revision.project.name) or 'du-toan'}-rev{revision.number}-run{run.id}.xlsx"
    artifact = ReportArtifact(
        revision=revision,
        run=run,
        template=template,
        template_version=TEMPLATE_VERSION,
        sha256=digest,
        created_by=request.user,
    )
    artifact.file.save(name, ContentFile(data), save=True)
    record(request.user, "report.export", artifact, {"run": run.id, "sha256": digest, "template": TEMPLATE_VERSION})
    resp = HttpResponse(data, content_type=XLSX)
    resp["Content-Disposition"] = f'attachment; filename="{name}"'
    resp["X-Artifact-Id"] = str(artifact.id)
    resp["X-Content-SHA256"] = digest
    return resp
