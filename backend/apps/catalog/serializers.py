from rest_framework import serializers

from .models import DatasetRelease, NormComponent, Resource, SourceDocument, WorkItem


class SourceDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SourceDocument
        fields = "__all__"


class DatasetReleaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetRelease
        fields = "__all__"


class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = "__all__"


class NormComponentSerializer(serializers.ModelSerializer):
    resource_code = serializers.CharField(source="resource.code", read_only=True, default=None)
    resource_name = serializers.CharField(source="resource.name", read_only=True, default=None)
    resource_unit = serializers.CharField(source="resource.unit", read_only=True, default=None)

    class Meta:
        model = NormComponent
        fields = [
            "id",
            "kind",
            "resource",
            "resource_code",
            "resource_name",
            "resource_unit",
            "quantity",
            "is_other_pct",
            "condition",
        ]


class WorkItemSerializer(serializers.ModelSerializer):
    release_name = serializers.CharField(source="release.name", read_only=True)
    is_sample = serializers.BooleanField(source="release.is_sample", read_only=True)

    class Meta:
        model = WorkItem
        fields = ["id", "release", "release_name", "is_sample", "code", "name", "unit", "group_code", "notes"]


class WorkItemDetailSerializer(WorkItemSerializer):
    components = NormComponentSerializer(many=True, read_only=True)

    class Meta(WorkItemSerializer.Meta):
        fields = WorkItemSerializer.Meta.fields + ["components"]
