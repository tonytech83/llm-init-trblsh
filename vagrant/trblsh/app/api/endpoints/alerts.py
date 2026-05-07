import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models.incident import Incident, IncidentAnalysis
from app.schemas.alert import AlertmanagerWebhook
from app.services.llm import ask_ollama, prep_message_to_llm
from app.services.mcp_client import get_failed_services_and_logs
from app.services.telegram import send_telegram
from app.utils.config import TZ

router = APIRouter()


@router.post("/execute")
async def execute_investigation(incident_id: str):
    # TODO(tonytech83): llm to check and execute the last analysis
    pass


@router.post("/alert")
async def handle_alert(
    payload: AlertmanagerWebhook,
    session: Session = Depends(get_session),
) -> dict[str, str]:
    alert_data = payload.alerts[0]

    fingerprint = alert_data.fingerprint
    status = alert_data.status
    hostname = alert_data.labels.get("host", "unknown")
    ip_address = alert_data.labels.get("ip", "unknown")

    print("=" * 80)
    if status == "resolved":
        print(
            f"*** {datetime.now(tz=TZ)} - RESOLVED by Loki rule (check loki rule) ..."
        )
        return {"status": "ok"}

    print(
        f"*** {datetime.now(tz=TZ)} - Alert {fingerprint} added to active alerts."
        f" Host: {hostname} | IP: {ip_address} ...",
    )

    existing = session.exec(
        select(Incident).where(Incident.fingerprint == fingerprint),
    ).first()

    if existing:
        existing.failure_count += 1
        existing.fired_at = datetime.now(tz=TZ).isoformat()
        existing.status = "PENDING"
        session.add(existing)
        session.commit()
        incident_id = existing.incident_id
        print(f"*** {datetime.now(tz=TZ)} - Updated existing incident ...")
    else:
        incident_id = str(uuid.uuid4())
        session.add(
            Incident(
                incident_id=incident_id,
                fingerprint=fingerprint,
                hostname=hostname,
                ip_address=ip_address,
                status="PENDING",
                fired_at=datetime.now(tz=TZ).isoformat(),
                failure_count=1,
            )
        )
        session.commit()
        print(f"*** {datetime.now(tz=TZ)} - Created incident ...")

    failed_services, logs = await get_failed_services_and_logs(hostname, ip_address)

    if not failed_services:
        return {"status": "ok"}

    print(f"*** {datetime.now(tz=TZ)} - Failed services:")
    try:
        [print(f"    - {s}") for s in json.loads(failed_services)]
    except json.JSONDecodeError:
        return {"status": "ok"}
    print(f"*** {datetime.now(tz=TZ)} - Logs fetched successfully ...")

    msg = prep_message_to_llm(logs, hostname, ip_address)
    print(f"*** {datetime.now(tz=TZ)} - Prepared message for LLM ...")

    llm_analysis = await ask_ollama(msg)
    print(f"*** {datetime.now(tz=TZ)} - Received LLM response ...")

    session.add(
        IncidentAnalysis(
            id=str(uuid.uuid4()),
            incident_id=incident_id,
            created_at=datetime.now(tz=TZ).isoformat(),
            failed_services=failed_services,
            analysis=json.dumps(llm_analysis),
        )
    )
    session.commit()
    print(f"*** {datetime.now(tz=TZ)} - Saved LLM analysis to DB ...")

    send_telegram(llm_analysis, incident_id)

    return {"status": "processed"}
