from fastapi.testclient import TestClient
import pytest
from pathlib import Path
from backend.app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_alert_filter(monkeypatch):
    from backend.app import main

    def fake_status():
        return {
            "created": 123,
            "hosts": [],
            "services": [
                {
                    "host_name": "localhost",
                    "service_description": "HTTP",
                    "state": 2,
                    "state_text": "CRITICAL",
                    "plugin_output": "HTTP CRITICAL",
                    "last_check": 123,
                    "next_check": 183,
                    "check_interval": 1.0,
                },
                {
                    "host_name": "localhost",
                    "service_description": "PING",
                    "state": 0,
                    "state_text": "OK",
                    "plugin_output": "PING OK",
                    "last_check": 123,
                    "next_check": 183,
                    "check_interval": 1.0,
                },
            ],
            "summary": {
                "total_hosts": 1,
                "total_services": 2,
                "ok": 1,
                "warning": 0,
                "critical": 1,
                "unknown": 0,
            },
        }

    monkeypatch.setattr(main, "get_monitoring_data", lambda: fake_status())
    response = client.get("/api/monitor/alerts")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["alerts"][0]["service_description"] == "HTTP"


def test_monitoring_error(monkeypatch):
    from backend.app import main
    from backend.app.monitoring import NagiosConnectionError

    def fail():
        raise NagiosConnectionError("SSH unavailable")

    monkeypatch.setattr(main, "fetch_nagios_status", fail)
    response = client.get("/api/monitor/status")

    assert response.status_code == 503
    assert "SSH unavailable" in response.json()["detail"]


def test_dummy_app_deployment(monkeypatch):
    from backend.app import main

    monkeypatch.setattr(
        main,
        "deploy_dummy_app",
        lambda: {
            "deployed": True,
            "status_code": 200,
            "url": "http://15.135.200.112:8080",
            "host": "15.135.200.112",
            "port": 8080,
            "public_access_depends_on_security_group": True,
            "source": "EC2 Nginx deployment",
        },
    )

    response = client.post("/api/deploy/dummy-app")

    assert response.status_code == 200
    assert response.json()["deployed"] is True
    assert response.json()["status_code"] == 200


def test_named_application_deployment(monkeypatch):
    from backend.app import main

    monkeypatch.setattr(
        main,
        "deploy_app",
        lambda app_id: {
            "id": app_id,
            "name": "Cloud Console",
            "deployed": True,
            "status_code": 200,
            "url": "http://example.test:8080/cloud-console/",
        },
    )

    response = client.post("/api/deployment/apps/cloud-console")

    assert response.status_code == 200
    assert response.json()["id"] == "cloud-console"
    assert response.json()["deployed"] is True


def test_unknown_application_is_rejected():
    response = client.post("/api/deployment/apps/not-allowed")

    assert response.status_code == 404


def test_html_upload_deployment(monkeypatch):
    from backend.app import main

    monkeypatch.setattr(
        main,
        "deploy_uploaded_app",
        lambda filename, content: {
            "id": "custom-demo",
            "deployed": True,
            "status_code": 200,
            "path": "/custom-demo/",
        },
    )

    response = client.post(
        "/api/deployment/upload",
        json={"filename": "demo.html", "content": "<html><body>Live</body></html>"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == "custom-demo"
    assert response.json()["status_code"] == 200


def test_html_upload_validates_before_remote_deployment(monkeypatch):
    from backend.app import deployment

    def reject_deployment(*_args):
        raise AssertionError("must not deploy invalid files")

    monkeypatch.setattr(deployment, "_deploy_html", reject_deployment)

    with pytest.raises(ValueError, match=r"\.html"):
        deployment.deploy_uploaded_app("not-html.txt", "<html>demo</html>")
    with pytest.raises(ValueError, match="complete HTML page"):
        deployment.deploy_uploaded_app("snippet.html", "plain text")
    with pytest.raises(ValueError, match="256 KB"):
        deployment.deploy_uploaded_app("large.html", "<html>" + "x" * deployment.MAX_HTML_BYTES)
    with pytest.raises(ValueError, match="not a path"):
        deployment.deploy_uploaded_app("../page.html", "<html>demo</html>")


def test_each_uploaded_html_gets_a_distinct_route(monkeypatch):
    from backend.app import deployment

    generated_ids = iter([
        "11111111aaaaaaaa11111111aaaaaaaa",
        "22222222bbbbbbbb22222222bbbbbbbb",
    ])
    deployed = []
    monkeypatch.setattr(
        deployment,
        "uuid4",
        lambda: type("FakeUuid", (), {"hex": next(generated_ids)})(),
    )
    monkeypatch.setattr(
        deployment,
        "_deploy_uploaded_html",
        lambda app_id, filename, html: deployed.append((app_id, filename, html)) or {
            "id": app_id,
            "name": filename,
            "path": f"/apps/{app_id}/",
        },
    )

    first = deployment.deploy_uploaded_app("My Demo.html", "<html>one</html>")
    second = deployment.deploy_uploaded_app("My Demo.html", "<html>two</html>")

    assert first["id"] != second["id"]
    assert first["path"] != second["path"]
    assert deployed[0][1:] == ("My Demo.html", "<html>one</html>")


def test_uploaded_app_delete_removes_only_that_upload(monkeypatch):
    from backend.app import deployment

    app_id = "uploaded-sample-12345678123456781234567812345678"
    app = {
        "id": app_id,
        "name": "sample.html",
        "path": f"/apps/{app_id}/",
        "deployed": True,
    }
    staged = {}
    invoked = {}
    monkeypatch.setattr(deployment, "get_uploaded_apps", lambda: [app])
    monkeypatch.setattr(
        deployment,
        "_stage_archive",
        lambda staged_id, files: staged.update(id=staged_id, files=files),
    )
    monkeypatch.setattr(
        deployment,
        "_run_uploaded_manifest",
        lambda staged_id, path, expected_status: invoked.update(
            id=staged_id, path=path, expected_status=expected_status
        ) or expected_status,
    )

    result = deployment.delete_app(app_id)

    assert result["deleted"] is True
    assert result["deployed"] is False
    assert staged["id"] == app_id
    assert f"/var/www/ams-demo/{app_id}" in staged["files"]["manifest.pp"]
    assert "ensure => absent" in staged["files"]["manifest.pp"]
    assert invoked == {
        "id": app_id,
        "path": f"/apps/{app_id}/",
        "expected_status": "404",
    }


def test_named_application_deletion(monkeypatch):
    from backend.app import main

    monkeypatch.setattr(
        main,
        "delete_app",
        lambda app_id: {
            "id": app_id,
            "deployed": False,
            "deleted": True,
            "status_code": 403,
        },
    )

    response = client.delete("/api/deployment/apps/habit-tracker")

    assert response.status_code == 200
    assert response.json()["deleted"] is True
    assert response.json()["deployed"] is False


def test_unknown_application_delete_is_rejected():
    response = client.delete("/api/deployment/apps/not-allowed")

    assert response.status_code == 404


def test_delete_manifest_targets_only_selected_demo(monkeypatch):
    from backend.app import deployment

    applied = {}
    scheduled_checks = []
    monkeypatch.setattr(
        deployment,
        "_apply_manifest",
        lambda path, manifest: applied.update(path=path, manifest=manifest),
    )
    monkeypatch.setattr(deployment, "_schedule_nagios_check", scheduled_checks.append)
    monkeypatch.setattr(
        deployment,
        "get_app_status",
        lambda app_id: {
            "id": app_id,
            "deployed": False,
            "status_code": 403,
        },
    )

    result = deployment.delete_app("habit-tracker")

    assert applied["path"] == "/tmp/ams-remove-demo-app.pp"
    assert "'/var/www/ams-demo/habit-tracker'" in applied["manifest"]
    assert "ensure => absent" in applied["manifest"]
    assert "force  => true" in applied["manifest"]
    assert result["deleted"] is True
    assert scheduled_checks == ["habit-tracker"]


def test_nagios_checks_cover_every_demo_app():
    from backend.app.deployment import APP_REGISTRY

    config_path = Path(__file__).resolve().parents[2] / "nagios" / "services" / "demo-apps.cfg"
    nagios_config = config_path.read_text(encoding="utf-8")

    assert "command_line    /usr/lib/nagios/plugins/check_http" in nagios_config
    for app_id, app in APP_REGISTRY.items():
        assert f"service_description     APP - {app_id}" in nagios_config
        assert f"check_command           check_ams_demo_http!{app['path']}" in nagios_config


def test_dashboard_bundle_returns_live_sections(monkeypatch):
    from backend.app import main

    sample = {
        "monitor": {
            "summary": {
                "total_hosts": 1,
                "total_services": 1,
                "ok": 1,
                "warning": 0,
                "critical": 0,
                "unknown": 0,
            },
            "services": [],
            "hosts": [],
            "created": 123,
        },
        "resources": {"cpu": 4.2, "memory": {}, "disk": {}, "uptime": "up 1 hour"},
        "infrastructure": {"nginx": {"status": "active", "verified": True}},
        "applications": [{"id": "portfolio", "deployed": True}],
    }
    monkeypatch.setattr(main, "fetch_dashboard_data", lambda: sample)

    response = client.get("/api/dashboard")

    assert response.status_code == 200
    assert response.json()["monitor"]["summary"]["ok"] == 1
    assert response.json()["resources"]["cpu"] == 4.2
    assert response.json()["applications"][0]["deployed"] is True
