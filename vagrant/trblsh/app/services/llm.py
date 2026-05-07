import json
from typing import Any

import httpx

from app.utils.config import OLLAMA_API, OLLAMA_REQUEST_TIMEOUT


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


async def _json_audit(broken_json: str) -> str:
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
        raw = response.json()["response"].strip().removeprefix("json")
        return raw.strip()


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
            print("*** JSON parse failed, asking LLM to fix structure ...")
            fixed = await _json_audit(clean)
            return json.loads(fixed)
