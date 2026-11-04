from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.reverse import reverse


@api_view(["GET"])
def api_root(request):
    names = [
        "project-list",
        "revision-list",
        "work-item-list",
        "resource-list",
        "release-list",
        "price-list",
        "rule-pack-list",
        "calculation-run-list",
    ]
    return Response({n: reverse(n, request=request) for n in names})


urlpatterns = [
    path("", api_root, name="api-root"),
    path("auth/token", obtain_auth_token, name="api-token"),
    path("", include("apps.catalog.urls")),
    path("", include("apps.pricebook.urls")),
    path("", include("apps.regulations.urls")),
    path("", include("apps.projects.urls")),
    path("", include("apps.calculation.urls")),
    path("", include("apps.reports.urls")),
    path("", include("apps.datasync.urls")),
]
