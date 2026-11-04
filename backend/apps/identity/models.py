from django.conf import settings
from django.db import models


class Role(models.TextChoices):
    ESTIMATOR = "estimator", "Kỹ sư dự toán"
    REVIEWER = "reviewer", "Thẩm định"
    DATA_ADMIN = "data_admin", "Quản trị dữ liệu"


class Membership(models.Model):
    """Vai trò của người dùng trên một dự án (RBAC tối giản cho đợt 1)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=20, choices=Role.choices)

    class Meta:
        unique_together = [("user", "project")]
