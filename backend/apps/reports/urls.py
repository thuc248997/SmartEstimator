from django.urls import path

from .views import export

urlpatterns = [path("revisions/<int:pk>/export", export, name="revision-export")]
