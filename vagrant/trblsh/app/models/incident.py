from typing import Optional

from sqlmodel import Field, SQLModel


class Incident(SQLModel, table=True):
    __tablename__ = "incidents"

    incident_id: str = Field(primary_key=True)
    fingerprint: str = Field(unique=True)
    hostname: str
    ip_address: str
    status: str
    fired_at: str
    resolved_at: Optional[str] = None
    failure_count: int = 1


class IncidentAnalysis(SQLModel, table=True):
    __tablename__ = "incident_analysis"

    id: str = Field(primary_key=True)
    incident_id: str = Field(foreign_key="incidents.incident_id")
    created_at: str
    failed_services: str
    analysis: str
