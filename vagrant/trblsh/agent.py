import json
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import FastAPI, Request
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

app = FastAPI()

LLM_API = "http://192.168.0.88:11434/api/generate"
LLM_TIMEOUT = 300
SERVER_PARAMS = StdioServerParameters(command="python", args=["./server.py"])

# Set of active alerts
active_alerts = set()


def logs_to_str(logs):
    logs_dict = json.loads(logs)
    result = []

    for service, log_text in logs_dict.items():
        result.append(f"=== {service} ===")
        for line in log_text.split("\n"):
            if line.strip():
                result.append(f"    {line}")

    return "\n".join(result)


def prep_message_to_llm(logs: str, host: str, ip: str) -> str:
    msg = [
        "You are a Linux systems reliability engineer.",
        f"The following services have SIMULTANEOUSLY failed on host '{host}' ({ip}).",
        "This may indicate a common root cause.",
        "\n",
        "Analyze the logs and respond ONLY with a valid JSON object in this exact structure:",
        "\n",
        "{",
        '  "likely_cause": "<one or two sentences about the most probable reason>",',
        '  "log_summary": "<brief summary of pattern — frequency, timing, consistency>",',
        '  "investigation_steps": [',
        '    {"description": "<action description>", "command": "<exact command to run>"},',
        '    {"description": "<action description>", "command": "<exact command to run>"}',
        "  ],",
        '  "possible_causes": [',
        '    "<most likely cause>",',
        '    "<second most likely cause>",',
        '    "<third most likely cause>"',
        "  ]",
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


# 1. LISTEN: Receive the Webhook from Alertmanager
@app.post("/alert")
async def handle_alert(request: Request):
    data = await request.json()
    alert = data["alerts"][0]

    fingerprint = alert["fingerprint"]
    status = alert["status"]

    hostname = alert["labels"].get("host", "unknown")
    ip_address = alert["labels"].get("ip", "unknown")

    if status == "resolved":
        active_alerts.discard(fingerprint)
        print(f"Alert {fingerprint} resolved, cleared from tracking.")
        return {"status": "ok"}

    if fingerprint in active_alerts:
        print(f"Alert {fingerprint} already being handled, skipping")
        return {"status": "ok"}

    active_alerts.add(fingerprint)
    print(
        f"Alert {fingerprint} added to active alerts. Host: {hostname} | IP: {ip_address}"
    )

    async with stdio_client(SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # Step 1: Get failed services (ignore list filtering happens inside)
            result = await session.call_tool(
                "get_failed_services",
                arguments={"hostname": hostname, "ip_address": ip_address},
            )
            failed_services = result.content[0].text
            print(f"Failed services: {failed_services}")

            if not failed_services:
                print("No failed services outside ignore list, nothing to analyze.")
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
            logs = result.content[0].text
            print("=" * 80)
            msg = prep_message_to_llm(logs, hostname, ip_address)
            print(f"*** Logs fetched successfully")
            print("=" * 80)

    # 3. ANALYZE: Send logs to Ollama for analysis
    analysis = await ask_ollama(msg)
    print("=== LLM ANALYSIS ===")
    print(json.dumps(analysis, indent=2))
    print("====================")

    # Step 4: Send to Telegram (coming next)
    # send_telegram(analysis)

    return {"status": "processed"}


async def fetch_logs_from_loki(host: str, minutes: int = 10) -> list[str]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(minutes=minutes)

    start_ns = int(start.timestamp() * 1e9)
    end_ns = int(now.timestamp() * 1e9)

    query = f'{{job="journald", host="{host}", level=~"err|crit|alert|emerg"}}'

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": query,
                "start": start_ns,
                "end": end_ns,
                "limit": 100,
            },
        )
        response.raise_for_status()
        result = response.json()

    logs = []
    for stream in result.get("data", {}).get("result", []):
        unit = stream.get("stream", {}).get("unit", "unknown")
        for timestamp, line in stream.get("values", []):
            # Convert nanosecond timestamp to readable time
            ts = datetime.fromtimestamp(int(timestamp) / 1e9, tz=timezone.utc)
            logs.append(
                {
                    "time": ts.strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "unit": unit,
                    "message": line,
                }
            )

    return logs


async def ask_ollama(msg):
    async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
        llm_response = await client.post(
            LLM_API, json={"model": "qwen2.5:3b", "prompt": msg, "stream": False}
        )
        raw = llm_response.json()["response"]

        # Strip markdown code blocks if LLM adds them despite instructions
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()

        return json.loads(clean)


def send_telegram(message):
    print(f"Sending to Telegram: {message}")
    # Add your telegram bot code here...


# Run with: uvicorn agent:app --host 0.0.0.0 --port 8080
