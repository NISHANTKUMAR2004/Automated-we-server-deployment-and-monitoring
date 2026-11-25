import re
from typing import Any

SERVICE_STATES = {
    0: "OK",
    1: "WARNING",
    2: "CRITICAL",
    3: "UNKNOWN",
}

HOST_STATES = {
    0: "UP",
    1: "DOWN",
    2: "UNREACHABLE",
}


def parse_blocks(content: str, block_name: str) -> list[dict[str, str]]:
    pattern = rf"(?ms)^\s*{re.escape(block_name)}\s*\{{\s*(.*?)^\s*\}}"
    blocks = []

    for match in re.finditer(pattern, content):
        fields = {}
        for line in match.group(1).splitlines():
            if "=" in line:
                key, value = line.strip().split("=", 1)
                fields[key.strip()] = value.strip()
        blocks.append(fields)

    return blocks


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def parse_nagios_status(content: str) -> dict:
    info_blocks = parse_blocks(content, "info")
    host_blocks = parse_blocks(content, "hoststatus")
    service_blocks = parse_blocks(content, "servicestatus")

    created = safe_int(info_blocks[0].get("created")) if info_blocks else 0

    hosts = []
    for item in host_blocks:
        state = safe_int(item.get("current_state"), 3)
        hosts.append({
            "host_name": item.get("host_name", "unknown"),
            "state": state,
            "state_text": HOST_STATES.get(state, "UNKNOWN"),
            "plugin_output": item.get("plugin_output", ""),
            "last_check": safe_int(item.get("last_check")),
            "next_check": safe_int(item.get("next_check")),
        })

    services = []
    for item in service_blocks:
        state = safe_int(item.get("current_state"), 3)
        services.append({
            "host_name": item.get("host_name", "unknown"),
            "service_description": item.get(
                "service_description", "unknown"
            ),
            "state": state,
            "state_text": SERVICE_STATES.get(state, "UNKNOWN"),
            "plugin_output": item.get("plugin_output", ""),
            "last_check": safe_int(item.get("last_check")),
            "next_check": safe_int(item.get("next_check")),
            "check_interval": float(item.get("check_interval", 0) or 0),
        })

    return {
        "created": created,
        "hosts": hosts,
        "services": services,
        "summary": {
            "total_hosts": len(hosts),
            "total_services": len(services),
            "ok": sum(s["state"] == 0 for s in services),
            "warning": sum(s["state"] == 1 for s in services),
            "critical": sum(s["state"] == 2 for s in services),
            "unknown": sum(s["state"] == 3 for s in services),
        },
    }
