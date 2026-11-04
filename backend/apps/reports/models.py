from django.conf import settings
from django.db import models


class ReportArtifact(models.Model):
    revision = models.ForeignKey("projects.EstimateRevision", on_delete=models.CASCADE, related_name="artifacts")
    run = models.ForeignKey("calculation.CalculationRun", on_delete=models.PROTECT, related_name="artifacts")
    template = models.CharField(max_length=50)
    template_version = models.CharField(max_length=20)
    file = models.FileField(upload_to="reports/%Y/%m/")
    sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
