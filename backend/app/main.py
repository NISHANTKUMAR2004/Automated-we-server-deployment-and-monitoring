from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import logging

from backend.app.monitoring import (
    fetch_nagios_status,
    NagiosConnectionError,
)
from backend.app.monitoring import (
    fetch_dashboard_data,
    fetch_system_resources,
    fetch_infrastructure_status,
)
from backend.app.deployment import (
    APP_REGISTRY,
    deploy_app,
    delete_app,
    deploy_dummy_app,
    deploy_uploaded_app,
    get_apps_status,
    get_dummy_app_status,
    is_uploaded_app_id,
)

MAX_HTML_CHARACTERS = 256 * 1024


class HtmlUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=MAX_HTML_CHARACTERS)


app = FastAPI(
    title="Automated Web Deployment and Monitoring API",
    description="Deploy demo web apps with Puppet and monitor their server with Nagios Core",
    version="2.0.0",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("automated-server-monitoring")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


def get_monitoring_data():
    try:
        return fetch_nagios_status()
    except NagiosConnectionError as exc:
        logger.warning("Nagios status retrieval failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Unable to retrieve Nagios monitoring data: {exc}",
        ) from exc


@app.get("/")
def root():
    return {
        "project": "Automated Server Monitoring System",
        "backend": "FastAPI",
        "status": "running",
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "service": "monitoring-api",
    }


@app.get("/api/monitor/status")
def monitor_status():
    return get_monitoring_data()


@app.get("/api/dashboard")
def dashboard_data():
    try:
        return fetch_dashboard_data()
    except NagiosConnectionError as exc:
        logger.warning("Dashboard snapshot retrieval failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=f"Unable to retrieve dashboard data: {exc}",
        ) from exc


@app.get("/api/monitor/services")
def monitor_services():
    data = get_monitoring_data()
    return {
        "total": data["summary"]["total_services"],
        "services": data["services"],
    }


@app.get("/api/monitor/alerts")
def monitor_alerts():
    data = get_monitoring_data()
    alerts = [
        service for service in data["services"]
        if service["state"] != 0
    ]
    return {
        "total": len(alerts),
        "alerts": alerts,
    }


@app.get("/api/monitor/summary")
def monitor_summary():
    data = get_monitoring_data()
    return {
        "summary": data["summary"],
        "created": data["created"],
        "hosts": data["hosts"],
    }


@app.get("/api/system/resources")
def system_resources():
    try:
        return fetch_system_resources()
    except NagiosConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to retrieve system resources: {exc}",
        ) from exc


@app.get("/api/infrastructure/status")
def infrastructure_status():
    try:
        return fetch_infrastructure_status()
    except NagiosConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to retrieve infrastructure status: {exc}",
        ) from exc


@app.post("/api/deploy/dummy-app")
def deploy_demo_application():
    try:
        return deploy_dummy_app()
    except NagiosConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to deploy dummy app: {exc}",
        ) from exc


@app.get("/api/deployment/status")
def deployment_status():
    try:
        return get_dummy_app_status()
    except NagiosConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to verify dummy app deployment: {exc}",
        ) from exc


@app.get("/api/deployment/apps")
def deployment_apps():
    try:
        return {"apps": get_apps_status()}
    except NagiosConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to verify deployed applications: {exc}",
        ) from exc


@app.post("/api/deployment/apps/{app_id}")
def deploy_application(app_id: str):
    if app_id not in APP_REGISTRY:
        raise HTTPException(status_code=404, detail="Unknown demo application")
    try:
        return deploy_app(app_id)
    except NagiosConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to deploy application: {exc}",
        ) from exc


@app.delete("/api/deployment/apps/{app_id}")
def remove_application(app_id: str):
    if app_id not in APP_REGISTRY and not is_uploaded_app_id(app_id):
        raise HTTPException(status_code=404, detail="Unknown demo application")
    try:
        return delete_app(app_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NagiosConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to remove application: {exc}",
        ) from exc


@app.post("/api/deployment/upload")
def upload_html_application(request: HtmlUploadRequest):
    try:
        return deploy_uploaded_app(request.filename, request.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NagiosConnectionError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Unable to deploy uploaded HTML: {exc}",
        ) from exc
