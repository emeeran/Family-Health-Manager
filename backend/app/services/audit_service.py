"""Audit service."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.base import AuditLog


class AuditService:
    """Audit logging service."""

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def log_action(
        self,
        user_id: UUID,
        action: str,
        resource_type: str,
        resource_id: UUID,
        previous_state: dict | None = None,
        current_state: dict | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        """Log an audit entry."""
        audit = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            previous_state=previous_state,
            current_state=current_state,
            ip_address=ip_address,
        )
        self.db.add(audit)
        await self.db.flush()
        return audit

    async def list_audit_logs(
        self,
        user_id: UUID,
        action: str | None = None,
        resource_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[AuditLog]:
        """List audit log entries with filters."""
        query = select(AuditLog).where(AuditLog.user_id == user_id)

        if action:
            query = query.where(AuditLog.action == action)
        if resource_type:
            query = query.where(AuditLog.resource_type == resource_type)
        if date_from:
            query = query.where(AuditLog.created_at >= date_from)
        if date_to:
            query = query.where(AuditLog.created_at <= date_to)

        query = query.order_by(AuditLog.created_at.desc())
        result = await self.db.execute(query)
        return list(result.scalars().all())
