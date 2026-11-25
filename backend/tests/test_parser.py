from backend.app.nagios_parser import parse_nagios_status


SAMPLE_STATUS = """
info {
    created=1795555829
    version=4.4.6
}

servicestatus {
    host_name=localhost
    service_description=HTTP
    current_state=0
    plugin_output=HTTP OK: HTTP/1.1 200 OK
    last_check=1795555244
    next_check=1795555304
    check_interval=1.000000
}
"""


def test_parse_http_service():
    result = parse_nagios_status(SAMPLE_STATUS)

    assert result["summary"]["total_services"] == 1
    assert result["summary"]["ok"] == 1

    service = result["services"][0]
    assert service["service_description"] == "HTTP"
    assert service["state_text"] == "OK"
    assert service["check_interval"] == 1.0


def test_empty_status():
    result = parse_nagios_status("")

    assert result["summary"]["total_services"] == 0
    assert result["services"] == []


def test_mixed_service_state_counts():
    status = """
    servicestatus {
        host_name=localhost
        service_description=HTTP
        current_state=2
        plugin_output=HTTP CRITICAL
    }
    servicestatus {
        host_name=localhost
        service_description=PING
        current_state=1
        plugin_output=PING WARNING
    }
    servicestatus {
        host_name=localhost
        service_description=SSH
        current_state=3
        plugin_output=UNKNOWN
    }
    """

    result = parse_nagios_status(status)

    assert result["summary"]["critical"] == 1
    assert result["summary"]["warning"] == 1
    assert result["summary"]["unknown"] == 1
    assert result["summary"]["ok"] == 0


def test_dashboard_bundle_parses_resources_infrastructure_and_apps(monkeypatch):
    from backend.app import monitoring

    content = (
        "__AMS_STATUS__\n"
        "servicestatus {\n"
        "    host_name=localhost\n"
        "    service_description=HTTP\n"
        "    current_state=0\n"
        "}\n"
        "__AMS_RESOURCES__\n"
        "memory=1000 500 400\n"
        "disk=2000 1000 900\n"
        "uptime=up 1 hour\n"
        "cpu=12.5\n"
        "__AMS_INFRA__\n"
        "nginx=active\n"
        "puppetserver=active\n"
        "puppet=inactive\n"
        "nagios=active\n"
        "__AMS_APPS__\n"
        "uploaded-hello-12345678123456781234567812345678|aGVsbG8uaHRtbA==|present|200\n"
        "uploaded-broken-12345678123456781234567812345678|YnJva2VuLmh0bWw=|missing|404\n"
    )
    monkeypatch.setattr(monitoring, "run_remote_command", lambda _command: content)

    result = monitoring.fetch_dashboard_data()

    assert result["monitor"]["summary"]["ok"] == 1
    assert result["resources"]["cpu"] == 12.5
    assert result["infrastructure"]["nagios_core"]["status"] == "active"
    apps = {app["id"]: app for app in result["applications"]}
    hello_id = "uploaded-hello-12345678123456781234567812345678"
    broken_id = "uploaded-broken-12345678123456781234567812345678"
    assert apps[hello_id]["name"] == "hello.html"
    assert apps[hello_id]["deployed"] is True
    assert apps[hello_id]["path"] == f"/apps/{hello_id}/"
    assert apps[broken_id]["deployed"] is False
