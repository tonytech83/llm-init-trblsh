import json
from pathlib import Path

import asyncssh
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("trblsh")

SSH_USER = "vagrant"
SSH_KEY = "/home/vagrant/.ssh/troubleshooter_key"
IGNORE_LIST_PATH = "./ignore_list.txt"
LOG_LINES = 50


def load_ignore_list() -> set[str]:
    try:
        with Path(IGNORE_LIST_PATH).open("r") as f:
            return {
                line.strip() for line in f if line.strip() and not line.startswith("#")
            }
    except FileNotFoundError:
        return set()


@mcp.tool()
async def get_failed_services(hostname: str, ip_address: str) -> str:
    """
    Returns: JSON string of failed service names.

    SSH into the target host and get all currently failed systemd services.
    Filters out services in the ignore list.
    """
    ignore_list = load_ignore_list()

    async with asyncssh.connect(
        ip_address,
        username=SSH_USER,
        client_keys=[SSH_KEY],
        known_hosts=None,
    ) as conn:
        result = await conn.run(
            "systemctl list-units --state=failed --no-legend --no-pager",
        )

    services = []
    for line in result.stdout.strip().splitlines():
        if line.strip():
            parts = line.strip().split()
            # Skip the bullet character ●
            unit = parts[1] if parts[0] == "●" else parts[0]
            if unit not in ignore_list:
                services.append(unit)

    return json.dumps(services)


@mcp.tool()
async def get_service_logs(hostname: str, ip_address: str, services: str) -> str:
    """
    Returns: JSON string mapping service name to its logs.

    SSH into the target host and fetch the last LOG_LINES lines
    of journalctl output for each service.
    """
    service_list = json.loads(services)
    logs = {}

    async with asyncssh.connect(
        ip_address,
        username=SSH_USER,
        client_keys=[SSH_KEY],
        known_hosts=None,
    ) as conn:
        for unit in service_list:
            result = await conn.run(f"journalctl -u {unit} -n {LOG_LINES} --no-pager")
            logs[unit] = result.stdout

    return json.dumps(logs)


@mcp.tool()
async def restart_service(hostname: str, ip_address: str, services: list[str]):
    """Restart a list of services on the target host."""
    pass


# 4. Resources - Data endpoints
# (Add your resources definitions here using @mcp.resource())
# @mcp.resource()

# 5. Prompts - AI assistance templates
# (Add your prompt definitions here using @mcp.prompt())
# @mcp.prompt()

# 6. run the server
# Run with streamable STDIO transport
if __name__ == "__main__":
    mcp.run(transport="stdio")
