from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """Append-only application-level audit log."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=50)  # line.update, override.create, revision.approve, report.export ...
    target_type = models.CharField(max_length=50)
    target_id = models.CharField(max_length=50)
    diff = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=500, blank=True)
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["target_type", "target_id"])]
