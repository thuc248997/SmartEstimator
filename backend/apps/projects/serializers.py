from decimal import ROUND_HALF_UP, Decimal

from rest_framework import serializers

from apps.calculation.engine.quantity import QuantityError, evaluate, sum_details

from .models import EquipmentCost, EstimateLine, EstimateRevision, Project, ProjectItem, ResourceOverride


class ProjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Project
        fields = "__all__"
        read_only_fields = ["created_by", "created_at"]


class EstimateLineSerializer(serializers.ModelSerializer):
    code = serializers.CharField(read_only=True)

    class Meta:
        model = EstimateLine
        fields = [
            "id",
            "item",
            "order",
            "work_item",
            "custom_code",
            "code",
            "name",
            "unit",
            "quantity_expr",
            "quantity",
            "k_nc",
            "k_m",
            "note",
            "details",
            "manual_vl",
            "manual_nc",
            "manual_m",
            "version",
        ]
        read_only_fields = ["version"]
        extra_kwargs = {"name": {"required": False}, "unit": {"required": False}}

    def validate(self, attrs):
        wi = attrs.get("work_item", getattr(self.instance, "work_item", None))
        if wi is None and not attrs.get("custom_code", getattr(self.instance, "custom_code", "")):
            raise serializers.ValidationError("Cần work_item hoặc custom_code (mã tạm tính)")
        name = attrs.get("name", getattr(self.instance, "name", ""))
        unit = attrs.get("unit", getattr(self.instance, "unit", ""))
        if wi is not None:
            if not name:
                attrs["name"] = wi.name
            if not unit:
                attrs["unit"] = wi.unit
        elif not name or not unit:
            raise serializers.ValidationError("Mã tạm tính cần có name và unit")
        if "details" in attrs:
            details = attrs["details"] or []
            if not isinstance(details, list) or len(details) > 500:
                raise serializers.ValidationError({"details": "Diễn giải phải là danh sách tối đa 500 dòng"})
            try:
                total, norm = sum_details(details)
            except QuantityError as e:
                raise serializers.ValidationError({"details": str(e)}) from e
            attrs["details"] = norm
            if norm:
                attrs["quantity"] = total
                attrs["quantity_expr"] = ""
                return attrs
        has_details = bool(attrs.get("details", getattr(self.instance, "details", None)))
        if has_details and ("quantity" in attrs or "quantity_expr" in attrs) and "details" not in attrs:
            raise serializers.ValidationError(
                {"quantity": "Khối lượng đang lấy từ diễn giải; sửa các dòng diễn giải hoặc xóa diễn giải trước"}
            )
        expr = attrs.get("quantity_expr", getattr(self.instance, "quantity_expr", "") or "")
        if expr.strip():
            try:
                attrs["quantity"] = evaluate(expr)
            except QuantityError as e:
                raise serializers.ValidationError({"quantity_expr": str(e)}) from e
        return attrs


class EquipmentCostSerializer(serializers.ModelSerializer):
    amount = serializers.SerializerMethodField()
    vat = serializers.SerializerMethodField()
    amount_after_tax = serializers.SerializerMethodField()

    class Meta:
        model = EquipmentCost
        fields = [
            "id",
            "revision",
            "order",
            "name",
            "unit",
            "quantity",
            "unit_price",
            "vat_rate",
            "note",
            "amount",
            "vat",
            "amount_after_tax",
        ]
        read_only_fields = ["revision"]

    @staticmethod
    def _r(v) -> Decimal:
        return Decimal(str(v)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    @classmethod
    def _amounts(cls, o) -> tuple[Decimal, Decimal]:
        a = cls._r(Decimal(str(o.quantity)) * Decimal(str(o.unit_price)))
        return a, cls._r(a * Decimal(str(o.vat_rate)))

    def get_amount(self, o):
        return str(self._amounts(o)[0])

    def get_vat(self, o):
        return str(self._amounts(o)[1])

    def get_amount_after_tax(self, o):
        a, v = self._amounts(o)
        return str(a + v)

    def validate_vat_rate(self, v):
        if v < 0 or v > 1:
            raise serializers.ValidationError("Thuế suất là tỷ lệ 0–1 (vd 0.10)")
        return v


class ProjectItemSerializer(serializers.ModelSerializer):
    lines = EstimateLineSerializer(many=True, read_only=True)

    class Meta:
        model = ProjectItem
        fields = ["id", "revision", "order", "name", "lines"]


class ResourceOverrideSerializer(serializers.ModelSerializer):
    resource_code = serializers.CharField(source="resource.code", read_only=True)

    class Meta:
        model = ResourceOverride
        fields = ["id", "revision", "resource", "resource_code", "price", "reason", "created_by", "created_at"]
        read_only_fields = ["revision", "created_by", "created_at"]


class EstimateRevisionSerializer(serializers.ModelSerializer):
    items = ProjectItemSerializer(many=True, read_only=True)
    overrides = ResourceOverrideSerializer(many=True, read_only=True)
    equipment = EquipmentCostSerializer(many=True, read_only=True)
    is_locked = serializers.BooleanField(read_only=True)

    class Meta:
        model = EstimateRevision
        fields = [
            "id",
            "project",
            "number",
            "title",
            "status",
            "is_locked",
            "content_hash",
            "approved_run",
            "approved_by",
            "approved_at",
            "created_at",
            "items",
            "overrides",
            "equipment",
        ]
        read_only_fields = ["project", "number", "status", "content_hash", "approved_run", "approved_by", "approved_at"]
