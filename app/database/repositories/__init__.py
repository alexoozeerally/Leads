"""Repository pattern — one repository per aggregate."""

from app.database.repositories.audit_repo import AuditRepository
from app.database.repositories.business_repo import BusinessRepository
from app.database.repositories.lead_repo import LeadRepository, SuppressionRepository

__all__ = [
    "AuditRepository",
    "BusinessRepository",
    "LeadRepository",
    "SuppressionRepository",
]
