import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, col, select

from app.db import get_session
from app.models.incident import Incident, IncidentAnalysis
from app.utils.config import TRBLSH_URL

router = APIRouter()
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, session: Session = Depends(get_session)):
    incidents = session.exec(
        select(Incident).order_by(col(Incident.fired_at).desc())
    ).all()

    incidents_list = [
        {
            "incident_id": i.incident_id,
            "hostname": i.hostname,
            "ip_address": i.ip_address,
            "status": i.status,
            "fired_at": i.fired_at,
            "failure_count": i.failure_count,
            "link": f"{TRBLSH_URL}/alert/{i.incident_id}",
        }
        for i in incidents
    ]

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"incidents": incidents_list},
    )


@router.get("/alert/{incident_id}", response_class=HTMLResponse)
async def read_incident(
    request: Request,
    incident_id: str,
    session: Session = Depends(get_session),
):
    incident = session.get(Incident, incident_id)

    analyses = session.exec(
        select(IncidentAnalysis)
        .where(IncidentAnalysis.incident_id == incident_id)
        .order_by(col(IncidentAnalysis.created_at).desc())
    ).all()

    analyses_parsed = []
    for a in analyses:
        try:
            analyses_parsed.append(
                {
                    "id": a.id,
                    "created_at": a.created_at,
                    "failed_services": json.loads(a.failed_services),
                    "analysis": json.loads(a.analysis),
                }
            )
        except (json.JSONDecodeError, TypeError):
            continue

    return templates.TemplateResponse(
        request=request,
        name="alert.html",
        context={
            "incident_id": incident.incident_id,
            "fingerprint": incident.fingerprint,
            "hostname": incident.hostname,
            "ip_address": incident.ip_address,
            "status": incident.status,
            "fired_at": incident.fired_at,
            "failure_count": incident.failure_count,
            "analyses": analyses_parsed,
        },
    )
