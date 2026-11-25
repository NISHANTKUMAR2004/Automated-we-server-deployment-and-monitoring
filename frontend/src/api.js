const BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

async function get(path) {
  const response = await fetch(`${BASE_URL}${path}`);
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Keep the HTTP status fallback.
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function post(path, body) {
  const response = await fetch(`${BASE_URL}${path}`, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const responseBody = await response.json();
      detail = responseBody.detail || detail;
    } catch {
      // Keep the HTTP status fallback.
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

async function remove(path) {
  const response = await fetch(`${BASE_URL}${path}`, { method: "DELETE" });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      detail = body.detail || detail;
    } catch {
      // Keep the HTTP status fallback.
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

export const api = {
  dashboard: () => get("/api/dashboard"),
  health: () => get("/api/health"),
  status: () => get("/api/monitor/status"),
  services: () => get("/api/monitor/services"),
  alerts: () => get("/api/monitor/alerts"),
  resources: () => get("/api/system/resources"),
  infrastructure: () => get("/api/infrastructure/status"),
  deployDummyApp: () => post("/api/deploy/dummy-app"),
  deploymentStatus: () => get("/api/deployment/status"),
  applications: () => get("/api/deployment/apps"),
  deployApplication: (appId) => post(`/api/deployment/apps/${encodeURIComponent(appId)}`),
  deleteApplication: (appId) => remove(`/api/deployment/apps/${encodeURIComponent(appId)}`),
  uploadApplication: (filename, content) => post("/api/deployment/upload", { filename, content }),
};
