# trblsh — Troubleshooter Agent

The Agent component of the LLM Initial Troubleshooting pipeline. It runs on the **troubleshooter VM** (`192.168.56.15`) and is the integration point between Alertmanager, the MCP Server, Ollama, and Telegram.

## Role in the pipeline

```
... → Alertmanager → [Agent (MCP Client)] ↔ [MCP Server] → Ollama → Telegram
                             ↕
                          SQLite DB
                          Web UI
```

When Alertmanager fires a webhook, the Agent:
1. Creates or updates an incident record in SQLite
2. Opens a stdio session with the MCP Server
3. Calls `get_failed_services` — retrieves currently failed systemd units from the target host via SSH
4. Calls `get_service_logs` — fetches the last 50 journal lines per failed service via SSH
5. Builds a structured prompt and sends it to Ollama for LLM analysis
6. Persists the analysis in SQLite
7. Sends a Telegram notification with a link to the incident UI

## Files

```
trblsh/
├── agent.py              # MCP Client + FastAPI web service (webhook receiver, UI, DB)
├── server.py             # MCP Server (SSH tools exposed to the agent)
├── requirements.txt      # Python dependencies
├── .env.example          # Environment variable template
├── ignore_list.txt       # Systemd units to exclude from analysis
└── templates/
    ├── home.html         # Incident list UI
    └── alert.html        # Incident detail UI
```

## Prerequisites

- Python 3.11+
- SSH key deployed to the target host (see [SSH Setup](#ssh-setup))
- Ollama running and reachable with a model pulled
- Telegram bot token and chat ID

## Configuration

### Environment variables

Copy `.env.example` to `.env` and fill in your values:

```env
TOKEN="<telegram bot token>"
CHAT_ID="<telegram chat id>"
```

### Constants in `agent.py`

| Constant | Default | Description |
|----------|---------|-------------|
| `TRBLSH_URL` | `http://192.168.56.15:8080` | Base URL included in Telegram links |
| `OLLAMA_API` | `http://192.168.0.88:11434/api/generate` | Ollama endpoint |
| `OLLAMA_REQUEST_TIMEOUT` | `300` | LLM request timeout in seconds |

### Constants in `server.py`

| Constant | Default | Description |
|----------|---------|-------------|
| `SSH_USER` | `vagrant` | Username for SSH connections to target |
| `SSH_KEY` | `/home/vagrant/.ssh/troubleshooter_key` | Private key for SSH authentication |
| `IGNORE_LIST_PATH` | `./ignore_list.txt` | Path to the service ignore list |
| `LOG_LINES` | `50` | Number of journal lines fetched per service |

### Ignore list

`ignore_list.txt` contains one systemd unit name per line. Units listed here are excluded from analysis even if they appear in a failed state. Lines starting with `#` are treated as comments.

```
# Example
snapd.service
```

## SSH Setup

The MCP Server connects to target hosts as the `vagrant` user using a dedicated SSH key. Generate and deploy it once on the troubleshooter VM:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/troubleshooter_key -N ""
ssh-copy-id -i ~/.ssh/troubleshooter_key.pub vagrant@192.168.56.13
```

## Alertmanager webhook

The Agent expects Alertmanager to POST alerts to `http://192.168.56.15:8080/alert`. Update `/etc/alertmanager/alertmanager.yml` on the monitor VM:

```yaml
receivers:
  - name: webhook
    webhook_configs:
      - url: "http://192.168.56.15:8080/alert"
```

Then restart Alertmanager:
```bash
sudo systemctl restart alertmanager
```

## Installation

```bash
cd /vagrant/trblsh
pip install -r requirements.txt
cp .env.example .env
# edit .env with your Telegram credentials
```

## Running

```bash
uvicorn agent:app --host 0.0.0.0 --port 8080
```

The MCP Server (`server.py`) is launched automatically as a subprocess by the Agent over stdio. It does not need to be started separately.

## API

### `POST /alert`
Webhook receiver for Alertmanager. Expects the standard Alertmanager webhook payload.

**Flow:**
- Extracts `fingerprint`, `status`, `host`, and `ip` from the first alert in the payload
- Ignores `resolved` alerts (returns early)
- Creates a new incident or increments `failure_count` on an existing one (deduplicated by `fingerprint`)
- Runs the MCP tool chain and LLM analysis
- Returns `{"status": "processed"}` on success

### `GET /`
Incident list. Shows all incidents ordered by most recently fired with summary counters by status.

### `GET /alert/{incident_id}`
Incident detail. Shows the latest LLM analysis prominently, with previous analyses collapsed in a history accordion.

## MCP Server tools

The MCP Server (`server.py`) exposes three tools over stdio transport using [FastMCP](https://github.com/jlowin/fastmcp):

### `get_failed_services(hostname, ip_address)`
SSHes into `ip_address` as `SSH_USER` and runs:
```bash
systemctl list-units --state=failed --no-legend --no-pager
```
Filters out any unit present in `ignore_list.txt`.

**Returns:** JSON array of unit names, e.g. `["dummy-fail.service", "nginx.service"]`

### `get_service_logs(hostname, ip_address, services)`
SSHes into `ip_address` and runs `journalctl` for each service:
```bash
journalctl -u <unit> -n 50 --no-pager
```

**Input:** `services` is a JSON string (the raw output of `get_failed_services`).

**Returns:** JSON object mapping unit name to log output:
```json
{
  "dummy-fail.service": "Apr 16 10:00:01 target systemd[1]: ...",
  "nginx.service": "..."
}
```

### `restart_service(hostname, ip_address, services)` *(stub)*
Not yet implemented. Planned for the automated remediation phase.

## Database

SQLite database at `./db.db`, created automatically on first request.

### `incidents`

| Column | Type | Description |
|--------|------|-------------|
| `incident_id` | TEXT PK | UUID |
| `fingerprint` | TEXT UNIQUE | Alertmanager fingerprint, used for deduplication |
| `hostname` | TEXT | Source host label from the alert |
| `ip_address` | TEXT | Source IP label from the alert |
| `status` | TEXT | `PENDING` / `EXECUTING` / `RESOLVED` / `EXPIRED` |
| `fired_at` | TEXT | ISO timestamp of last alert firing |
| `resolved_at` | TEXT | ISO timestamp of resolution (nullable) |
| `failure_count` | INTEGER | How many times this fingerprint has fired |

### `incident_analysis`

| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `incident_id` | TEXT FK | References `incidents.incident_id` |
| `created_at` | TEXT | ISO timestamp of analysis run |
| `failed_services` | TEXT | JSON array of failed unit names |
| `analysis` | TEXT | JSON object — full LLM response (see below) |

## LLM integration

### Model
`qwen2.5:3b` via Ollama. Can be swapped for any model available on the configured Ollama instance.

### Prompt structure
The Agent instructs the LLM to act as a Linux SRE and analyze logs from all simultaneously failed services for a common root cause. The prompt enforces JSON-only output with no markdown.

### Expected output schema
```json
{
  "hostname": "target.concept.lab",
  "ip_address": "192.168.56.13",
  "failed_services": "dummy-fail.service",
  "time": "16/04/2026 10:00:01",
  "message": {
    "log_summary": "Single failure event recorded at boot...",
    "likely_cause": "Service exited immediately with status 1 due to intentional failure in ExecStart.",
    "investigation_steps": [
      {
        "description": "Check the full service definition",
        "command": "systemctl cat dummy-fail.service"
      },
      {
        "description": "View recent journal output",
        "command": "journalctl -u dummy-fail.service -n 50 --no-pager"
      }
    ],
    "possible_causes": [
      "Intentional exit code 1 in ExecStart",
      "Missing dependency not met before start",
      "Misconfigured ExecStart path"
    ]
  }
}
```

### JSON error recovery
If the LLM returns malformed JSON, the Agent makes a second Ollama call (`json_audit`) asking the model to fix only the syntax, leaving values unchanged.

## Telegram notification

On every processed alert the Agent sends a message to the configured chat:

```
💻  target.concept.lab
📡  192.168.56.13
⚙️  dummy-fail.service
⏰  16/04/2026 10:00:01
🌍  http://192.168.56.15:8080/alert/<incident_id>
```

## Known limitations / TODOs

- `restart_service` tool is stubbed — automated remediation not yet implemented
- `POST /execute` endpoint is stubbed — LLM-driven investigation execution is planned
- Resolved alerts from Alertmanager are acknowledged but no status transition is applied to the incident
- `known_hosts` verification is disabled in the SSH client (`known_hosts=None`)
- Ollama model and URL are hardcoded constants, not environment variables
