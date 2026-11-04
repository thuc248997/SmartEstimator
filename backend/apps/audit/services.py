from .models import AuditEvent


def record(actor, action: str, target, diff: dict | None = None, reason: str = "") -> AuditEvent:
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        target_type=type(target).__name__,
        target_id=str(getattr(target, "pk", target)),
        diff=diff or {},
        reason=reason,
    )
