from rest_framework import serializers

from .models import CalculationLine, CalculationRun


class CalculationLineSerializer(serializers.ModelSerializer):
    code = serializers.CharField(source="line.code", read_only=True)
    name = serializers.CharField(source="line.name", read_only=True)
    unit = serializers.CharField(source="line.unit", read_only=True)
    item = serializers.IntegerField(source="line.item_id", read_only=True)

    class Meta:
        model = CalculationLine
        fields = [
            "breakdown",
            "line",
            "item",
            "code",
            "name",
            "unit",
            "quantity",
            "unit_vl",
            "unit_nc",
            "unit_m",
            "vl",
            "nc",
            "m",
            "direct",
            "warnings",
        ]


class CalculationRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalculationRun
        fields = [
            "id",
            "revision",
            "status",
            "engine_version",
            "input_hash",
            "output_hash",
            "result",
            "warnings",
            "error",
            "created_at",
            "finished_at",
        ]


class CalculationRunDetailSerializer(CalculationRunSerializer):
    lines = CalculationLineSerializer(many=True, read_only=True)

    class Meta(CalculationRunSerializer.Meta):
        fields = CalculationRunSerializer.Meta.fields + ["lines"]
