import json

import httpx
from fastapi import FastAPI, Request
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

app = FastAPI()

LOKI_URL = "http://192.168.56.14:3100"
SERVER_PARAMS = StdioServerParameters(command="python", args=["./server.py"])

# Set of active alerts
active_alerts: set[str] = set()


def logs_to_str(logs) -> str:
    logs_dict = json.loads(logs)
    result: list[str] = []

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
        "Analyze the logs for each service and:",
        "1. Identify the most likely root cause for each service",
        "2. Determine if the failures are related",
        "3. Suggest troubleshooting steps in order of priority",
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
            # logs_to_str(logs)
            msg = prep_message_to_llm(logs, hostname, ip_address)
            print(msg)
            print(f"*** Logs fetched successfully")
            print("=" * 80)

    # 3. ANALYZE: Send logs to Ollama for analysis
    analysis = await ask_ollama(msg)

    # Step 4: Send to Telegram (coming next)
    # send_telegram(analysis)

    return {"status": "processed"}


async def ask_ollama(msg: srt):
    async with httpx.AsyncClient() as client:
        llm_response = await client.post(
            "http://localhost:11434/api/generate",
            json={"model": "qwen2.5:3b", "prompt": msg, "stream": False},
        )
        return resp.llm_response()["response"]


def send_telegram(message: str):
    print(f"Sending to Telegram: {message}")
    # Add your telegram bot code here...


# Run with: uvicorn agent:app --host 0.0.0.0 --port 8080
