from django.apps import AppConfig


class BoqImportConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.boqimport"
    verbose_name = "Nhập BoQ từ Excel"
