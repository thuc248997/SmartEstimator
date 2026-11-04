from rest_framework.routers import DefaultRouter

from .views import DatasetReleaseViewSet, ResourceViewSet, SourceDocumentViewSet, WorkItemViewSet

router = DefaultRouter(trailing_slash=False)
router.register("catalog/sources", SourceDocumentViewSet, basename="source")
router.register("catalog/releases", DatasetReleaseViewSet, basename="release")
router.register("catalog/resources", ResourceViewSet, basename="resource")
router.register("catalog/work-items", WorkItemViewSet, basename="work-item")
urlpatterns = router.urls
