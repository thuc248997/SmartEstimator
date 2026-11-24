from django.contrib import admin

from .models import BoqMatchMemory


@admin.register(BoqMatchMemory)
class BoqMatchMemoryAdmin(admin.ModelAdmin):
    list_display = ["key", "unit_base", "work_item", "hits", "updated_at"]
    search_fields = ["key", "work_item__code"]
    raw_id_fields = ["work_item"]
