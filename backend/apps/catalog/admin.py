from django.contrib import admin

from .models import DatasetRelease, NormComponent, Resource, SourceDocument, WorkItem


class NormInline(admin.TabularInline):
    model = NormComponent
    extra = 0


@admin.register(WorkItem)
class WorkItemAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "unit", "release")
    search_fields = ("code", "name")
    inlines = [NormInline]


admin.site.register([SourceDocument, DatasetRelease, Resource])
