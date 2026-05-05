import json
import os
import sqlite3
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

load_dotenv()

app = FastAPI()

# Location of Jinja2 templates
templates = Jinja2Templates(directory="templates")

# Telegram
BOT_TOKEN: str = os.getenv("TOKEN", "")
CHAT_ID: str = os.getenv("CHAT_ID", "")

# Settings
TZ = ZoneInfo(os.getenv("TIME_ZONE", ""))

TRBLSH_URL = "http://192.168.56.15:8080"

# LLM
OLLAMA_API = "http://192.168.0.88:11434/api/generate"
OLLAMA_REQUEST_TIMEOUT = 300
SERVER_PARAMS = StdioServerParameters(command="python", args=["./server.py"])


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    con = sqlite3.connect("db.db")
    cur = con.cursor()

    incidents = cur.execute(
        """SELECT incident_id, hostname, ip_address, status, fired_at, failure_count
           FROM incidents
           ORDER BY fired_at DESC""",
    ).fetchall()
    con.close()

    incidents_list: list[dict[str, str]] = []
    for row in incidents:
        incidents_list.append(
            {
                "incident_id": row[0],
                "hostname": row[1],
                "ip_address": row[2],
                "status": row[3],
                "fired_at": row[4],
                "failure_count": row[5],
                "link": f"{TRBLSH_URL}/alert/{row[0]}",
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"incidents": incidents_list},
    )


@app.post("/execute")
async def execute_investigation(request: Request, incident_id: str):
    # TODO(tonytech83): llm to check the last analysis
    pass


@app.get("/alert/{incident_id}", response_class=HTMLResponse)
async def read_incident(request: Request, incident_id: str):
    con = sqlite3.connect("db.db")
    cur = con.cursor()

    incident = cur.execute(
        "SELECT * FROM incidents WHERE incident_id = ?",
        (incident_id,),
    ).fetchone()

    analyses = cur.execute(
        "SELECT * FROM incident_analysis WHERE incident_id = ? ORDER BY created_at DESC",
        (incident_id,),
    ).fetchall()
    con.close()

    # Parse analysis JSON for each row
    analyses_parsed: list[dict[str, str]] = []
    for row in analyses:
        analyses_parsed.append(
            {
                "id": row[0],
                "created_at": row[2],
                "failed_services": json.loads(row[3]),
                "analysis": json.loads(row[4]),
            },
        )

    return templates.TemplateResponse(
        request=request,
        name="alert.html",
        context={
            "incident_id": incident[0],
            "fingerprint": incident[1],
            "hostname": incident[2],
            "ip_address": incident[3],
            "status": incident[4],
            "fired_at": incident[5],
            "failure_count": incident[7],
            "analyses": analyses_parsed,
        },
    )


def prep_message_to_llm(logs: str, host: str, ip: str) -> str:
    msg: list[str] = [
        "You are a Linux systems reliability engineer.",
        f"The following services have SIMULTANEOUSLY failed on host '{host}' ({ip}).",
        "This may indicate a common root cause.",
        "\n",
        "Analyze the logs and respond ONLY with a valid JSON object in this exact structure:",
        "\n",
        "{",
        '  "hostname": "<the name of the host, if applicable>",',
        '  "ip_address": "<the ip address of the server>",',
        '  "failed_services": "<failed services separated with comma>",',
        '  "time": "<current date in format DD/MM/YYYY and time in format HH:MM:SS, strictly follow the formats!>",',
        '  "message": {',
        '    "log_summary": "<brief summary of pattern — frequency, timing, consistency>",',
        '    "likely_cause": "<one or two sentences about the most probable reason>",',
        '    "investigation_steps": [',
        "      {",
        '        "description": "<action description>",',
        '        "command": "<exact command to run>"',
        "	   },",
        "      {",
        '        "description": "<action description>",',
        '        "command": "<exact command to run>"',
        "      }",
        "    ],",
        '    "possible_causes": [',
        '      "<most likely cause>",',
        '      "<second most likely cause>",',
        '      "<third most likely cause>"',
        "    ]",
        "  }",
        "}",
        "\n",
        "Rules:",
        "- Respond with ONLY the JSON object, no text before or after it",
        "- No markdown, no code blocks, no backticks",
        "- All commands must be safe read-only Linux commands",
        "- Commands must be directly executable on the server without modification",
        "\n",
    ]

    logs_dict = json.loads(logs)

    for srv_idx, (service_name, log_text) in enumerate(logs_dict.items(), start=1):
        msg.append(f"=== SERVICE {srv_idx}: {service_name} ===")
        for line in log_text.split("\n"):
            if line.strip():
                msg.append(f"{line}")
        msg.append("\n")

    return "\n".join(msg)


async def json_audit(broken_json: str) -> str:
    prompt: str = "\n".join(
        [
            "The following text is supposed to be a valid JSON object but it contains syntax errors.",
            "Your task is to fix ONLY the JSON syntax errors — do not change any values, do not add new fields, do not remove fields.",
            "Respond with ONLY the corrected JSON object, no explanation, no markdown, no backticks.",
            "\n",
            str(broken_json),
        ],
    )

    async with httpx.AsyncClient(timeout=OLLAMA_REQUEST_TIMEOUT) as client:
        response = await client.post(
            OLLAMA_API,
            json={"model": "qwen2.5:3b", "prompt": prompt, "stream": False},
        )
        raw = response.json()["response"].strip()

        # Strip markdown again in case LLM adds it
        raw = raw.removeprefix("json")

        return raw.strip()


# Receive the Webhook from Alertmanager
@app.post("/alert")
async def handle_alert(request: Request) -> dict[str, str]:
    # ==== DB ===========================
    con = sqlite3.connect("db.db")
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS incidents(
            incident_id TEXT PRIMARY KEY,
            fingerprint TEXT UNIQUE,
            hostname TEXT,
            ip_address TEXT,
            status TEXT,
            fired_at TEXT,
            resolved_at TEXT,
            failure_count INTEGER
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS incident_analysis(
            id TEXT PRIMARY KEY,
            incident_id TEXT,
            created_at TEXT,
            failed_services TEXT,
            analysis TEXT,
            FOREIGN KEY(incident_id) REFERENCES incidents(incident_id)
        )
    """)
    con.commit()

    # ==== Alert =========================================
    data = await request.json()
    alert_data = data["alerts"][0]
    fingerprint = alert_data["fingerprint"]
    status = alert_data["status"]
    hostname = alert_data["labels"].get("host", "unknown")
    ip_address = alert_data["labels"].get("ip", "unknown")
    # =====================================================

    print("=" * 80)
    if status == "resolved":
        print(
            f"*** {datetime.now(tz=TZ)} - RESOLVED by Loki rule (check loki rule) ...",
        )
        return {"status": "ok"}

    print(
        f"*** {datetime.now(tz=TZ)} - Alert {fingerprint} added to active alerts. Host: {hostname} | IP: {ip_address} ...",
    )

    row = cur.execute(
        "SELECT incident_id FROM incidents WHERE fingerprint = ?",
        (fingerprint,),
    ).fetchone()
    incident_id = row[0] if row else None

    if incident_id:
        cur.execute(
            """UPDATE incidents
                SET failure_count = failure_count + 1,
                    fired_at = ?,
                    status = 'PENDING'
                WHERE fingerprint = ?
            """,
            (datetime.now(tz=TZ), fingerprint),
        )
        con.commit()
        print(
            f"*** {datetime.now(tz=TZ)} - Update the incident (already exists in DB) ...",
        )
    else:
        incident_id = str(uuid.uuid4())
        cur.execute(
            """INSERT INTO incidents(incident_id, fingerprint, hostname, ip_address, status, fired_at, resolved_at, failure_count)
                    VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                incident_id,
                fingerprint,
                hostname,
                ip_address,
                "PENDING",
                datetime.now(tz=TZ).isoformat(),
                None,
                1,
            ),
        )
        con.commit()
        print(f"*** {datetime.now(tz=TZ)} - Create an incident ...")

    async with (
        stdio_client(SERVER_PARAMS) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        # Step 1: Get failed services (ignore list filtering happens inside)
        result: CallToolResult = await session.call_tool(
            "get_failed_services",
            arguments={"hostname": hostname, "ip_address": ip_address},
        )

        failed_services: str = (
            result.content[0].text if isinstance(result.content[0], TextContent) else ""
        )
        print(f"*** {datetime.now(tz=TZ)} - Failed services:")
        [print(f"    - {s}") for s in json.loads(failed_services)]

        if not failed_services:
            # TODO: Change status from PENDING to RESOLVED
            return {"status": "ok"}

        # Step 2: Get logs for each failed service
        result = await session.call_tool(
            "get_service_logs",
            arguments={
                "hostname": hostname,
                "ip_address": ip_address,
                "services": failed_services,
            },
        )
        print(f"*** {datetime.now(tz=TZ)} - Logs fetched successfully ...")

        # Failed services logs_dict
        logs: str = (
            result.content[0].text if isinstance(result.content[0], TextContent) else ""
        )

        msg: str = prep_message_to_llm(logs, hostname, ip_address)
        print(
            f"*** {datetime.now(tz=TZ)} - Prepare message to llm with all needed information for analysis ...",
        )

        # Step 3: llm to execute steps provided by himself
        # TODO: How and where to be implemented this step

    # ==== Send message with logs to Ollama for analysis =============
    llm_analysis = await ask_ollama(msg)
    print(
        f"*** {datetime.now(tz=TZ)} - Send message to llm and receive the response ...",
    )

    # ==== Add analysis in db ========================================
    cur.execute(
        """INSERT INTO incident_analysis(id, incident_id, created_at, failed_services, analysis)
                VALUES(?,?,?,?,?)
        """,
        (
            str(uuid.uuid4()),
            incident_id,
            datetime.now(tz=TZ).isoformat(),
            failed_services,
            json.dumps(llm_analysis),
        ),
    )
    con.commit()
    con.close()
    print(f"*** {datetime.now(tz=TZ)} - Save llm analysis into DB ...")

    # ==== Send to Telegram ==========================
    send_telegram(llm_analysis, incident_id)

    return {"status": "processed"}


async def ask_ollama(msg: str) -> Any:
    async with httpx.AsyncClient(timeout=OLLAMA_REQUEST_TIMEOUT) as client:
        llm_response = await client.post(
            OLLAMA_API,
            json={"model": "qwen2.5:3b", "prompt": msg, "stream": False},
        )
        raw = llm_response.json()["response"]
        clean: str = raw.strip().removeprefix("```").removeprefix("json").strip()

        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            # First attempt failed — ask LLM to fix only the JSON structure
            print("*** JSON parse failed, asking LLM to fix structure ...")
            fixed = await json_audit(clean)
            return json.loads(fixed)


def send_telegram(message: Any, incident_id: str) -> None:
    print(f"*** {datetime.now(tz=TZ)} - Sending llm analysis to Telegram")

    telegram_msg = [
        f"💻  {message['hostname']}",
        f"📡  {message['ip_address']}",
        f"⚙️  {message['failed_services']}",
        f"⏰  {message['time']}",
        f"🌍  {TRBLSH_URL}/alert/{incident_id}",
    ]

    print("-" * 80)
    print("\n".join(telegram_msg))
    print("-" * 80)

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": "\n".join(telegram_msg),
    }

    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()


# Run with: uvicorn agent:app --host 0.0.0.0 --port 8080
