import base64
import io
import re
import subprocess
import tarfile
import unicodedata
from pathlib import Path
from uuid import uuid4
import time

from backend.app import config
from backend.app.monitoring import NagiosConnectionError

MAX_HTML_BYTES = 256 * 1024
LOCAL_TUNNEL_PORT = 8081
PUPPET_APPLY_TIMEOUT_SECONDS = 120
UPLOADED_APP_ID_PATTERN = re.compile(
    r"^uploaded-[a-z0-9-]{1,48}-(?:[a-f0-9]{8}|[a-f0-9]{32})$"
)

APP_REGISTRY = {
    "portfolio": {
        "name": "Cloud Portfolio",
        "description": "A polished project landing page running on Nginx.",
        "file": "portfolio/index.html",
        "path": "/portfolio/",
    },
    "cloud-console": {
        "name": "Cloud Console",
        "description": "A compact cloud infrastructure operations console.",
        "file": "cloud-console/index.html",
        "path": "/cloud-console/",
    },
    "storefront": {
        "name": "Mini Storefront",
        "description": "A responsive sample product storefront.",
        "file": "storefront/index.html",
        "path": "/storefront/",
    },
    "custom-demo": {
        "name": "Puppet Live Demo",
        "description": "A tiny interactive page you can replace by uploading an HTML file.",
        "file": "custom-demo.html",
        "path": "/custom-demo/",
    },
    "habit-tracker": {
        "name": "Habit Tracker",
        "description": "Track daily habits and watch your progress update.",
        "file": "habit-tracker.html",
        "path": "/habit-tracker/",
    },
    "quiz-game": {
        "name": "Quick Quiz",
        "description": "Answer three questions and see your score.",
        "file": "quiz-game.html",
        "path": "/quiz-game/",
    },
    "mini-calculator": {
        "name": "Mini Calculator",
        "description": "A working four-operation calculator in one HTML file.",
        "file": "mini-calculator.html",
        "path": "/mini-calculator/",
    },
    "launch-timer": {
        "name": "Launch Timer",
        "description": "Start and reset an interactive launch countdown.",
        "file": "launch-timer.html",
        "path": "/launch-timer/",
    },
}


def _ssh_command() -> list[str]:
    key_path = Path(config.SSH_KEY_PATH)
    if not key_path.is_file():
        raise NagiosConnectionError(f"SSH private key not found: {key_path}")

    return [
        "ssh",
        "-i", str(key_path),
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{config.EC2_USER}@{config.EC2_HOST}",
    ]


def _run(
    command: list[str],
    input_text: str | bytes | None = None,
    timeout_seconds: int | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=not isinstance(input_text, bytes),
            encoding="utf-8" if not isinstance(input_text, bytes) else None,
            errors="replace" if not isinstance(input_text, bytes) else None,
            timeout=timeout_seconds or config.SSH_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise NagiosConnectionError("SSH deployment timed out") from exc
    except FileNotFoundError as exc:
        raise NagiosConnectionError("OpenSSH client was not found") from exc
    if isinstance(input_text, bytes):
        return subprocess.CompletedProcess(
            result.args,
            result.returncode,
            result.stdout.decode("utf-8", errors="replace"),
            result.stderr.decode("utf-8", errors="replace"),
        )
    return result


def _remote(command: str) -> str:
    result = _run(_ssh_command() + [command])
    if result.returncode != 0:
        detail = result.stderr.strip() or "Unknown remote deployment error"
        raise NagiosConnectionError(detail)
    return result.stdout.strip()


def deploy_dummy_app() -> dict:
    return deploy_app("portfolio")


def deploy_app(app_id: str) -> dict:
    app = APP_REGISTRY.get(app_id)
    if app is None:
        raise ValueError(f"Unknown demo application: {app_id}")

    html_path = Path(__file__).resolve().parents[2] / "demo-apps" / app["file"]
    if not html_path.is_file():
        raise NagiosConnectionError(f"Demo application file not found: {html_path}")

    html = html_path.read_text(encoding="utf-8")
    return _deploy_html(app_id, html)


def deploy_uploaded_app(filename: str, html: str) -> dict:
    if filename != filename.replace("\\", "/").rsplit("/", 1)[-1]:
        raise ValueError("Choose a single .html file, not a path")
    if not filename.lower().endswith(".html"):
        raise ValueError("Choose a single .html file")
    if not html.strip():
        raise ValueError("The selected HTML file is empty")
    if "<html" not in html.lower():
        raise ValueError("The selected file must contain a complete HTML page")
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        raise ValueError("HTML files must be 256 KB or smaller")
    if any(ord(character) < 32 for character in filename):
        raise ValueError("The filename contains unsupported control characters")

    stem = Path(filename).stem
    slug = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", slug).strip("-").lower()[:40] or "page"
    app_id = f"uploaded-{slug}-{uuid4().hex}"
    return _deploy_uploaded_html(app_id, filename, html)


def is_uploaded_app_id(app_id: str) -> bool:
    return UPLOADED_APP_ID_PATTERN.fullmatch(app_id) is not None


def _uploaded_apps_command() -> str:
    return (
        "for app_dir in /var/www/ams-demo/uploaded-*; do "
        "[ -d \"$app_dir\" ] || continue; "
        "[ -f \"$app_dir/.display-name\" ] || continue; "
        "app_id=${app_dir##*/}; "
        "app_name=$(base64 -w0 \"$app_dir/.display-name\"); "
        "if [ -f \"$app_dir/index.html\" ]; then file_state=present; "
        "else file_state=missing; fi; "
        "http_code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "
        "http://127.0.0.1:8080/apps/$app_id/ 2>/dev/null || true); "
        "printf '%s|%s|%s|%s\\n' \"$app_id\" \"$app_name\" "
        "\"$file_state\" \"$http_code\"; done"
    )


def parse_uploaded_apps(output: str) -> list[dict]:
    apps = []
    for line in output.splitlines():
        parts = line.strip().split("|")
        if len(parts) != 4:
            continue
        app_id, encoded_name, file_state, status_code = parts
        if not is_uploaded_app_id(app_id):
            continue
        try:
            name = base64.b64decode(encoded_name, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        deployed = file_state == "present" and status_code == "200"
        apps.append({
            "id": app_id,
            "name": name,
            "description": "Uploaded HTML application",
            "deployed": deployed,
            "status_code": int(status_code) if status_code.isdigit() else None,
            "url": f"http://{config.EC2_HOST}:8080/apps/{app_id}/",
            "tunnel_url": f"http://localhost:{LOCAL_TUNNEL_PORT}/apps/{app_id}/",
            "path": f"/apps/{app_id}/",
            "port": 8080,
            "public_access_depends_on_security_group": True,
        })
    return sorted(apps, key=lambda app: app["name"].casefold())


def get_uploaded_apps() -> list[dict]:
    return parse_uploaded_apps(_remote(_uploaded_apps_command()))


def _nagios_config(apps: list[dict]) -> str:
    lines = [
        "define command {",
        "    command_name    check_ams_demo_http",
        "    command_line    /usr/lib/nagios/plugins/check_http -H '$HOSTADDRESS$' -I '$HOSTADDRESS$' -p 8080 -u '$ARG1$'",
        "}",
    ]
    for app in apps:
        lines.extend([
            "",
            "define service {",
            "    use                     generic-service",
            "    host_name               localhost",
            f"    service_description     APP - {app['id']}",
            f"    check_command           check_ams_demo_http!{app['path']}",
            "    check_interval          1",
            "    retry_interval          1",
            "    max_check_attempts     1",
            "}",
        ])
    return "\n".join(lines) + "\n"


def _upload_manifest(app_id: str) -> str:
    app_dir = f"/var/www/ams-demo/{app_id}"
    stage_dir = f"/tmp/ams-upload-{app_id}"
    return f"""file {{ '/var/www/ams-demo':
  ensure => directory,
  owner  => 'root',
  group  => 'root',
  mode   => '0755',
}}

file {{ '{app_dir}':
  ensure  => directory,
  owner   => 'root',
  group   => 'root',
  mode    => '0755',
  require => File['/var/www/ams-demo'],
}}

file {{ '{app_dir}/index.html':
  ensure  => file,
  owner   => 'root',
  group   => 'root',
  mode    => '0644',
  source  => 'file://{stage_dir}/index.html',
  require => File['{app_dir}'],
}}

file {{ '{app_dir}/.display-name':
  ensure  => file,
  owner   => 'root',
  group   => 'root',
  mode    => '0644',
  source  => 'file://{stage_dir}/display-name',
  require => File['{app_dir}'],
}}

file {{ '/etc/nginx/conf.d/ams-demo-apps.conf':
  ensure  => file,
  owner   => 'root',
  group   => 'root',
  mode    => '0644',
  source  => 'file://{stage_dir}/ams-demo-apps.conf',
  notify  => Service['nginx'],
}}

file {{ '/etc/nagios4/conf.d/ams-demo-apps.cfg':
  ensure  => file,
  owner   => 'root',
  group   => 'root',
  mode    => '0644',
  source  => 'file://{stage_dir}/ams-demo-apps.cfg',
}}

file {{ '/etc/nginx/conf.d/dummy-app.conf':
  ensure => absent,
}}

exec {{ 'validate-ams-demo-app-checks':
  command     => '/usr/sbin/nagios4 -v /etc/nagios4/nagios.cfg',
  refreshonly => true,
  subscribe   => File['/etc/nagios4/conf.d/ams-demo-apps.cfg'],
  require     => File['{app_dir}/index.html'],
}}

exec {{ 'reload-ams-demo-app-checks':
  command     => '/bin/systemctl reload nagios4',
  refreshonly => true,
  subscribe   => Exec['validate-ams-demo-app-checks'],
  require     => Service['nagios4'],
}}

service {{ 'nagios4':
  ensure => running,
  enable => true,
}}

service {{ 'nginx':
  ensure => running,
  enable => true,
}}
"""


def _delete_manifest(app_id: str) -> str:
    return f"""file {{ '/var/www/ams-demo/{app_id}':
  ensure => absent,
  force  => true,
}}

file {{ '/etc/nagios4/conf.d/ams-demo-apps.cfg':
  ensure  => file,
  owner   => 'root',
  group   => 'root',
  mode    => '0644',
  source  => 'file:///tmp/ams-upload-{app_id}/ams-demo-apps.cfg',
}}

exec {{ 'validate-ams-demo-app-checks':
  command     => '/usr/sbin/nagios4 -v /etc/nagios4/nagios.cfg',
  refreshonly => true,
  subscribe   => File['/etc/nagios4/conf.d/ams-demo-apps.cfg'],
}}

service {{ 'nagios4':
  ensure => running,
  enable => true,
}}

exec {{ 'reload-ams-demo-app-checks':
  command     => '/bin/systemctl reload nagios4',
  refreshonly => true,
  subscribe   => Exec['validate-ams-demo-app-checks'],
  require     => Service['nagios4'],
}}
"""


def _archive_for_upload(
    app_id: str,
    files: dict[str, str],
) -> bytes:
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as tar:
        for filename, content in files.items():
            payload = content.encode("utf-8")
            member_names = [f"ams-upload-{app_id}/{filename}"]
            if filename == "ams-demo-apps.conf":
                member_names.append(filename)
            for member_name in member_names:
                member = tarfile.TarInfo(member_name)
                member.size = len(payload)
                member.mode = 0o600
                tar.addfile(member, io.BytesIO(payload))
    return archive.getvalue()


def _stage_archive(app_id: str, files: dict[str, str]) -> None:
    result = _run(
        _ssh_command() + ["sudo -n tar -x -C /tmp"],
        _archive_for_upload(app_id, files),
        timeout_seconds=PUPPET_APPLY_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "Could not stage deployment files on EC2"
        raise NagiosConnectionError(detail)


def _run_uploaded_manifest(
    app_id: str,
    url_path: str,
    expected_status: str = "200",
) -> str:
    stage_dir = f"/tmp/ams-upload-{app_id}"
    command = (
        f"sudo -n puppet apply {stage_dir}/manifest.pp --detailed-exitcodes; "
        "puppet_status=$?; "
        "if [ \"$puppet_status\" -ne 0 ] && [ \"$puppet_status\" -ne 2 ]; "
        "then exit \"$puppet_status\"; fi; "
        "sudo -n nginx -t && "
        "sudo -n nagios4 -v /etc/nagios4/nagios.cfg >/dev/null && "
        f"curl -sS -o /dev/null -w '%{{http_code}}' --max-time 10 "
        f"http://127.0.0.1:8080{url_path}; "
        "result=$?; "
        f"sudo -n rm -rf {stage_dir}; "
        "exit \"$result\""
    )
    result = _run(
        _ssh_command() + [command],
        timeout_seconds=PUPPET_APPLY_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise NagiosConnectionError(detail or "Puppet deployment failed")
    status_code = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""
    if status_code != expected_status:
        raise NagiosConnectionError(
            f"Deployment health check returned HTTP {status_code or 'unavailable'}"
        )
    return status_code


def _deploy_uploaded_html(app_id: str, filename: str, html: str) -> dict:
    existing_apps = get_uploaded_apps()
    app = {
        "id": app_id,
        "name": filename,
        "description": "Uploaded HTML application",
        "deployed": True,
        "status_code": 200,
        "path": f"/apps/{app_id}/",
        "url": f"http://{config.EC2_HOST}:8080/apps/{app_id}/",
        "tunnel_url": f"http://localhost:{LOCAL_TUNNEL_PORT}/apps/{app_id}/",
        "port": 8080,
        "public_access_depends_on_security_group": True,
    }
    nginx_config_path = Path(__file__).resolve().parents[2] / "puppet" / "files" / "ams-demo-apps.conf"
    files = {
        "index.html": html,
        "display-name": filename,
        "ams-demo-apps.conf": nginx_config_path.read_text(encoding="utf-8"),
        "ams-demo-apps.cfg": _nagios_config([*existing_apps, app]),
        "manifest.pp": _upload_manifest(app_id),
    }
    _stage_archive(app_id, files)
    status_code = _run_uploaded_manifest(app_id, app["path"])
    app["status_code"] = int(status_code)
    return app


def _deploy_html(app_id: str, html: str) -> dict:
    nginx_config_path = Path(__file__).resolve().parents[2] / "puppet" / "files" / "ams-demo-apps.conf"
    nginx_config = nginx_config_path.read_text(encoding="utf-8")
    nagios_config_path = Path(__file__).resolve().parents[2] / "nagios" / "services" / "demo-apps.cfg"
    nagios_config = nagios_config_path.read_text(encoding="utf-8")
    manifest = _manifest_for(app_id)
    _remote("sudo -n mkdir -p /var/www/ams-demo /tmp/ams-demo")
    _write_remote(f"/tmp/ams-demo-{app_id}.html", html)
    _write_remote("/tmp/ams-demo-apps.conf", nginx_config)
    _write_remote("/tmp/ams-demo-apps-nagios.cfg", nagios_config)
    _apply_manifest("/tmp/ams-demo-app.pp", manifest)
    _schedule_nagios_check(app_id)

    return get_app_status(app_id)


def delete_app(app_id: str) -> dict:
    if is_uploaded_app_id(app_id):
        uploaded_apps = get_uploaded_apps()
        app = next((item for item in uploaded_apps if item["id"] == app_id), None)
        if app is None:
            raise ValueError(f"Unknown uploaded application: {app_id}")

        remaining_apps = [item for item in uploaded_apps if item["id"] != app_id]
        files = {
            "ams-demo-apps.cfg": _nagios_config(remaining_apps),
            "manifest.pp": _delete_manifest(app_id),
        }
        _stage_archive(app_id, files)
        _run_uploaded_manifest(app_id, app["path"], expected_status="404")
        app.update(deployed=False, status_code=404, deleted=True)
        return app

    app = APP_REGISTRY.get(app_id)
    if app is None:
        raise ValueError(f"Unknown demo application: {app_id}")

    manifest_path = "/tmp/ams-remove-demo-app.pp"
    manifest = f"""file {{ '/var/www/ams-demo/{app_id}':
  ensure => absent,
  force  => true,
}}
"""
    _apply_manifest(manifest_path, manifest)
    _schedule_nagios_check(app_id)
    result = get_app_status(app_id)
    result["deleted"] = not result["deployed"]
    return result


def _schedule_nagios_check(app_id: str) -> None:
    timestamp = int(time.time())
    _remote(
        f"printf '[{timestamp}] SCHEDULE_FORCED_SVC_CHECK;localhost;"
        f"APP - {app_id};{timestamp}\\n' | "
        "sudo -n tee /var/lib/nagios4/rw/nagios.cmd >/dev/null"
    )


def _apply_manifest(manifest_path: str, manifest: str) -> None:
    _write_remote(manifest_path, manifest)
    puppet_result = _run(
        _ssh_command() + [
            f"sudo -n puppet apply {manifest_path} --detailed-exitcodes"
        ],
        timeout_seconds=PUPPET_APPLY_TIMEOUT_SECONDS,
    )
    if puppet_result.returncode not in (0, 2):
        detail = puppet_result.stderr.strip() or puppet_result.stdout.strip()
        raise NagiosConnectionError(detail or "Puppet configuration failed")
    _remote("sudo -n nginx -t && sudo -n systemctl reload nginx")


def _write_remote(path: str, content: str) -> None:
    result = _run(
        _ssh_command() + [f"sudo -n tee {path} >/dev/null"],
        content,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"Could not stage deployment file {path}"
        raise NagiosConnectionError(detail)


def _manifest_for(app_id: str) -> str:
    destination = f"/var/www/ams-demo/{app_id}"
    source = f"file:///tmp/ams-demo-{app_id}.html"
    return f"""file {{ '/var/www/ams-demo':
  ensure => directory,
  owner  => 'root',
  group  => 'root',
  mode   => '0755',
}}

file {{ '{destination}':
  ensure => directory,
  owner  => 'root',
  group  => 'root',
  mode   => '0755',
  require => File['/var/www/ams-demo'],
}}

file {{ '{destination}/index.html':
  ensure  => file,
  owner   => 'root',
  group   => 'root',
  mode    => '0644',
  source  => '{source}',
  require => File['{destination}'],
}}

file {{ '/etc/nginx/conf.d/dummy-app.conf':
  ensure => absent,
}}

file {{ '/etc/nginx/conf.d/ams-demo-apps.conf':
  ensure  => file,
  owner   => 'root',
  group   => 'root',
  mode    => '0644',
  source  => 'file:///tmp/ams-demo-apps.conf',
  notify  => Service['nginx'],
}}

file {{ '/etc/nagios4/conf.d/ams-demo-apps.cfg':
  ensure  => file,
  owner   => 'root',
  group   => 'root',
  mode    => '0644',
  source  => 'file:///tmp/ams-demo-apps-nagios.cfg',
}}

service {{ 'nagios4':
  ensure => running,
  enable => true,
}}

exec {{ 'validate-nagios-app-checks':
  command     => '/usr/sbin/nagios4 -v /etc/nagios4/nagios.cfg',
  refreshonly => true,
  subscribe   => File['/etc/nagios4/conf.d/ams-demo-apps.cfg'],
  require     => File['{destination}/index.html'],
}}

exec {{ 'reload-nagios-app-checks':
  command     => '/bin/systemctl reload nagios4',
  refreshonly => true,
  subscribe   => Exec['validate-nagios-app-checks'],
  require     => Service['nagios4'],
}}

service {{ 'nginx':
  ensure => running,
  enable => true,
}}
"""


def get_app_status(app_id: str) -> dict:
    if is_uploaded_app_id(app_id):
        app = next((item for item in get_uploaded_apps() if item["id"] == app_id), None)
        if app is None:
            raise ValueError(f"Unknown uploaded application: {app_id}")
        return app

    app = APP_REGISTRY.get(app_id)
    if app is None:
        raise ValueError(f"Unknown demo application: {app_id}")

    status_result = _remote(
        f"if test -f /var/www/ams-demo/{app_id}/index.html; then "
        "printf 'present'; else printf 'missing'; fi; "
        f"curl -sS -o /dev/null -w ' %{{http_code}}' "
        f"http://127.0.0.1:8080{app['path']}"
    )
    file_state, _, status_code = status_result.partition(" ")
    deployed = file_state == "present" and status_code == "200"
    return {
        "id": app_id,
        "name": app["name"],
        "description": app["description"],
        "deployed": deployed,
        "status_code": int(status_code) if status_code.isdigit() else None,
        "url": f"http://{config.EC2_HOST}:8080{app['path']}",
        "tunnel_url": f"http://localhost:{LOCAL_TUNNEL_PORT}{app['path']}",
        "path": app["path"],
        "port": 8080,
        "public_access_depends_on_security_group": True,
    }


def get_apps_status() -> list[dict]:
    return get_uploaded_apps()


def get_dummy_app_status() -> dict:
    return get_app_status("portfolio")
