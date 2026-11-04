from rest_framework import serializers

from .models import DataUpdateRun, PriceCatalogItem


class DataUpdateRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataUpdateRun
        fields = ["id", "status", "sources", "results", "log", "error", "started_at", "finished_at"]


class PriceCatalogItemSerializer(serializers.ModelSerializer):
    release_name = serializers.CharField(source="release.__str__", read_only=True)
    period = serializers.SerializerMethodField()

    class Meta:
        model = PriceCatalogItem
        fields = [
            "id",
            "release",
            "release_name",
            "period",
            "name",
            "spec",
            "unit",
            "price",
            "context",
            "page",
            "document",
        ]

    def get_period(self, o):
        return o.release.meta.get("period") or o.release.version
