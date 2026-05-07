from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, TextContent

SERVER_PARAMS = StdioServerParameters(command="python", args=["./app/mcp_server.py"])


async def get_failed_services_and_logs(hostname: str, ip_address: str) -> tuple[str, str]:
    async with (
        stdio_client(SERVER_PARAMS) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()

        result: CallToolResult = await session.call_tool(
            "get_failed_services",
            arguments={"hostname": hostname, "ip_address": ip_address},
        )
        print(f"*** get_failed_services isError={result.isError} content={result.content}")

        if result.isError or not isinstance(result.content[0], TextContent):
            return "", ""

        failed_services: str = result.content[0].text

        if not failed_services:
            return "", ""

        result = await session.call_tool(
            "get_service_logs",
            arguments={
                "hostname": hostname,
                "ip_address": ip_address,
                "services": failed_services,
            },
        )
        logs: str = (
            result.content[0].text if isinstance(result.content[0], TextContent) else ""
        )

        return failed_services, logs
