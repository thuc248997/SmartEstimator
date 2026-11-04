from django.contrib import admin

from .models import EstimateLine, EstimateRevision, Project, ProjectItem, ResourceOverride

admin.site.register([Project, EstimateRevision, ProjectItem, EstimateLine, ResourceOverride])
