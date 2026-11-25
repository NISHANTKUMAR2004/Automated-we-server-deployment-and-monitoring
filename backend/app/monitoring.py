import subprocess
from pathlib import Path
import shlex

from backend.app import config
from backend.app.nagios_parser import parse_nagios_status


class NagiosConnectionError(Exception):
    pass


def run_remote_command(command: str) -> str:
    key_path = Path(config.SSH_KEY_PATH)
    if not key_path.is_file():
        raise NagiosConnectionError(f"SSH private key not found: {key_path}")

    ssh_command = [
        "ssh",
        "-i", str(key_path),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{config.EC2_USER}@{config.EC2_HOST}",
        command,
    ]
    try:
        result = subprocess.run(
            ssh_command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.SSH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise NagiosConnectionError("SSH connection timed out") from exc
    except FileNotFoundError as exc:
        raise NagiosConnectionError("OpenSSH client was not found") from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or "Unknown SSH error"
        raise NagiosConnectionError(detail)
    return result.stdout.strip()


def fetch_nagios_status() -> dict:
    key_path = Path(config.SSH_KEY_PATH)

    if not key_path.is_file():
        raise NagiosConnectionError(
            f"SSH private key not found: {key_path}"
        )

    command = [
        "ssh",
        "-i", str(key_path),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{config.EC2_USER}@{config.EC2_HOST}",
        f"sudo -n cat {config.NAGIOS_STATUS_PATH}",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=config.SSH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise NagiosConnectionError(
            "SSH connection timed out while fetching Nagios data"
        ) from exc
    except FileNotFoundError as exc:
        raise NagiosConnectionError(
            "OpenSSH client was not found on this computer"
        ) from exc

    if result.returncode != 0:
        detail = result.stderr.strip() or "Unknown SSH error"
        raise NagiosConnectionError(detail)

    if "servicestatus {" not in result.stdout:
        raise NagiosConnectionError(
            "Nagios status file did not contain service status data"
        )

    return parse_nagios_status(result.stdout)


def fetch_system_resources() -> dict:
    memory_output = run_remote_command(
        "free -b | awk 'NR==2 {print $2, $3, $7}'"
    )
    disk_output = run_remote_command(
        "df -B1 / | awk 'NR==2 {print $2, $3, $4}'"
    )
    uptime_output = run_remote_command("uptime -p")
    cpu_output = run_remote_command(
        "awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5}' /proc/stat;"
        " sleep 1;"
        " awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5}' /proc/stat"
    )

    memory_parts = memory_output.split()
    disk_parts = disk_output.split()

    memory_total = int(memory_parts[0]) if len(memory_parts) == 3 else 0
    memory_used = int(memory_parts[1]) if len(memory_parts) == 3 else 0
    memory_available = int(memory_parts[2]) if len(memory_parts) == 3 else 0
    disk_total = int(disk_parts[0]) if len(disk_parts) == 3 else 0
    disk_used = int(disk_parts[1]) if len(disk_parts) == 3 else 0
    disk_available = int(disk_parts[2]) if len(disk_parts) == 3 else 0

    cpu = None
    cpu_samples = [line.split() for line in cpu_output.splitlines() if line.strip()]
    if len(cpu_samples) == 2:
        try:
            total_before, idle_before = map(float, cpu_samples[0])
            total_after, idle_after = map(float, cpu_samples[1])
            total_delta = total_after - total_before
            idle_delta = idle_after - idle_before
            if total_delta > 0:
                cpu = round(max(0.0, min(100.0,
                    (total_delta - idle_delta) * 100.0 / total_delta)), 1)
        except (TypeError, ValueError, ZeroDivisionError):
            cpu = None

    return {
        "memory": {
            "total_bytes": memory_total,
            "used_bytes": memory_used,
            "available_bytes": memory_available,
        },
        "disk": {
            "total_bytes": disk_total,
            "used_bytes": disk_used,
            "available_bytes": disk_available,
        },
        "uptime": uptime_output,
        "cpu": cpu,
        "source": "EC2 read-only SSH commands",
    }


def fetch_infrastructure_status() -> dict:
    output = run_remote_command(
        "printf 'nginx='; systemctl is-active nginx 2>/dev/null || true;"
        " printf '\\npuppetserver='; systemctl is-active puppetserver 2>/dev/null || true;"
        " printf '\\npuppet='; systemctl is-active puppet 2>/dev/null || true;"
        " nagios_state=$(systemctl is-active nagios 2>/dev/null || true);"
        " if [ \"$nagios_state\" != active ]; then"
        " nagios_state=$(systemctl is-active nagios4 2>/dev/null || true); fi;"
        " printf '\\nnagios=%s' \"${nagios_state:-unknown}\""
    )

    statuses = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.strip().split("=", 1)
            statuses[key] = value.strip()

    def verified_status(key: str) -> dict:
        value = statuses.get(key, "unknown")
        return {
            "status": value if value in ("active", "inactive", "failed") else "unknown",
            "verified": value in ("active", "inactive", "failed"),
        }

    return {
        "puppet_server": verified_status("puppetserver"),
        "puppet_agent": verified_status("puppet"),
        "nagios_core": verified_status("nagios"),
        "nginx": verified_status("nginx"),
        "monitoring_server": {
            "host": config.EC2_HOST,
            "user": config.EC2_USER,
            "status": "reachable",
            "verified": True,
        },
    }


def fetch_dashboard_data() -> dict:
    from backend.app.deployment import _uploaded_apps_command, parse_uploaded_apps

    status_path = shlex.quote(config.NAGIOS_STATUS_PATH)
    command = (
        "printf '\\n__AMS_STATUS__\\n'; "
        f"sudo -n cat {status_path}; "
        "printf '\\n__AMS_RESOURCES__\\n'; "
        "memory=$(free -b | awk 'NR==2 {print $2, $3, $7}'); "
        "disk=$(df -B1 / | awk 'NR==2 {print $2, $3, $4}'); "
        "uptime_value=$(uptime -p); "
        "cpu_before=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5}' /proc/stat); "
        "sleep 0.3; "
        "cpu_after=$(awk '/^cpu /{print $2+$3+$4+$5+$6+$7+$8, $5}' /proc/stat); "
        "cpu_value=$(awk -v before=\"$cpu_before\" -v after=\"$cpu_after\" "
        "'BEGIN {split(before,a,\" \"); split(after,b,\" \"); d=b[1]-a[1]; "
        "if (d > 0) printf \"%.1f\", ((d-(b[2]-a[2]))*100/d); else print \"unknown\"}'); "
        "printf 'memory=%s\\ndisk=%s\\nuptime=%s\\ncpu=%s\\n' "
        "\"$memory\" \"$disk\" \"$uptime_value\" \"$cpu_value\"; "
        "printf '__AMS_INFRA__\\n'; "
        "for svc in nginx puppetserver puppet; do "
        "value=$(systemctl is-active \"$svc\" 2>/dev/null || true); "
        "printf '%s=%s\\n' \"$svc\" \"${value:-unknown}\"; done; "
        "nagios_state=$(systemctl is-active nagios 2>/dev/null || true); "
        "if [ \"$nagios_state\" != active ]; then "
        "nagios_state=$(systemctl is-active nagios4 2>/dev/null || true); fi; "
        "printf 'nagios=%s\\n' \"${nagios_state:-unknown}\"; "
        "printf '__AMS_APPS__\\n'; "
        f"{_uploaded_apps_command()}"
    )
    output = run_remote_command(command)
    sections = output.split("__AMS_RESOURCES__\n", 1)
    if len(sections) != 2 or "__AMS_STATUS__\n" not in sections[0]:
        raise NagiosConnectionError("Combined monitoring response was incomplete")

    status_text = sections[0].split("__AMS_STATUS__\n", 1)[1]
    if "servicestatus {" not in status_text:
        raise NagiosConnectionError("Nagios status data was missing from response")
    resources_and_more = sections[1]
    if "__AMS_INFRA__\n" not in resources_and_more or "__AMS_APPS__\n" not in resources_and_more:
        raise NagiosConnectionError("Combined server information was incomplete")
    resources_text, infra_and_apps = resources_and_more.split("__AMS_INFRA__\n", 1)
    infra_text, apps_text = infra_and_apps.split("__AMS_APPS__\n", 1)

    def parse_key_values(text: str) -> dict[str, str]:
        values = {}
        for line in text.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        return values

    resource_values = parse_key_values(resources_text)
    infra_values = parse_key_values(infra_text)
    memory = resource_values.get("memory", "").split()
    disk = resource_values.get("disk", "").split()

    if len(memory) != 3 or len(disk) != 3:
        raise NagiosConnectionError("EC2 resource metrics were incomplete")

    try:
        memory_total, memory_used, memory_available = map(int, memory)
        disk_total, disk_used, disk_available = map(int, disk)
        cpu = float(resource_values["cpu"])
    except (KeyError, TypeError, ValueError) as exc:
        raise NagiosConnectionError("EC2 resource metrics could not be parsed") from exc

    return {
        "monitor": parse_nagios_status(status_text),
        "resources": {
            "memory": {
                "total_bytes": memory_total,
                "used_bytes": memory_used,
                "available_bytes": memory_available,
            },
            "disk": {
                "total_bytes": disk_total,
                "used_bytes": disk_used,
                "available_bytes": disk_available,
            },
            "uptime": resource_values.get("uptime", "Unavailable"),
            "cpu": cpu,
            "source": "EC2 read-only SSH commands",
        },
        "infrastructure": {
            "puppet_server": {
                "status": infra_values.get("puppetserver", "unknown"),
                "verified": infra_values.get("puppetserver") in ("active", "inactive", "failed"),
            },
            "puppet_agent": {
                "status": infra_values.get("puppet", "unknown"),
                "verified": infra_values.get("puppet") in ("active", "inactive", "failed"),
            },
            "nagios_core": {
                "status": infra_values.get("nagios", "unknown"),
                "verified": infra_values.get("nagios") in ("active", "inactive", "failed"),
            },
            "nginx": {
                "status": infra_values.get("nginx", "unknown"),
                "verified": infra_values.get("nginx") in ("active", "inactive", "failed"),
            },
            "monitoring_server": {
                "host": config.EC2_HOST,
                "user": config.EC2_USER,
                "status": "reachable",
                "verified": True,
            },
        },
        "applications": parse_uploaded_apps(apps_text),
    }
