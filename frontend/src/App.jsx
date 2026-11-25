import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  Bell,
  CheckCircle2,
  ChevronRight,
  CircleGauge,
  Cpu,
  HardDrive,
  Info,
  LayoutDashboard,
  Menu,
  RefreshCw,
  Server,
  Settings,
  ShieldCheck,
  X,
  XCircle,
  AlertTriangle,
  Network,
  Rocket,
  ArrowUpRight,
  Upload,
  Trash2,
} from "lucide-react";
import { api } from "./api";

const MAX_HTML_BYTES = 256 * 1024;

const navItems = [
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "services", label: "Services", icon: Server },
  { id: "deploy", label: "Deploy applications", icon: Rocket },
  { id: "alerts", label: "Alerts", icon: Bell },
  { id: "system", label: "System Information", icon: CircleGauge },
  { id: "settings", label: "Settings", icon: Settings },
  { id: "about", label: "About Project", icon: Info },
];

function formatBytes(bytes) {
  if (!bytes) return "Unavailable";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** index).toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatTimestamp(seconds) {
  if (!seconds) return "Unavailable";
  return new Date(seconds * 1000).toLocaleString();
}

function StatusBadge({ stateText }) {
  const state = (stateText || "UNKNOWN").toUpperCase();
  return <span className={`status-badge status-${state.toLowerCase()}`}><span />{state}</span>;
}

function StatCard({ icon: Icon, label, value, tone }) {
  return (
    <article className={`stat-card tone-${tone}`}>
      <div className="stat-icon"><Icon size={22} /></div>
      <div>
        <p>{label}</p>
        <strong>{value}</strong>
      </div>
    </article>
  );
}

function Donut({ summary }) {
  const total = summary.total_services || 0;
  const ok = summary.ok || 0;
  const warning = summary.warning || 0;
  const critical = summary.critical || 0;
  const unknown = summary.unknown || 0;
  const pct = (value) => total ? (value / total) * 100 : 0;
  const parts = [
    { label: "OK", value: ok, color: "#36dfc1" },
    { label: "Warning", value: warning, color: "#f8c74d" },
    { label: "Critical", value: critical, color: "#ff5d78" },
    { label: "Unknown", value: unknown, color: "#8390a7" },
  ];
  let cursor = 0;
  const stops = parts.map((part) => {
    const start = cursor;
    cursor += pct(part.value);
    return `${part.color} ${start}% ${cursor}%`;
  }).join(", ");
  const style = total ? { background: `conic-gradient(${stops})` } : undefined;

  return (
    <div className="health-layout">
      <div className="donut" style={style}>
        <div className="donut-hole">
          <strong>{total ? Math.round(pct(ok)) : 0}%</strong>
          <span>Healthy</span>
        </div>
      </div>
      <div className="health-legend">
        {parts.map((part) => (
          <div key={part.label}>
            <span className="legend-dot" style={{ background: part.color }} />
            <span>{part.label}</span>
            <strong>{part.value}</strong>
          </div>
        ))}
      </div>
    </div>
  );
}

function App() {
  const [status, setStatus] = useState(null);
  const [services, setServices] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [resources, setResources] = useState(null);
  const [infrastructure, setInfrastructure] = useState(null);
  const [applications, setApplications] = useState([]);
  const [selectedHtmlFile, setSelectedHtmlFile] = useState(null);
  const [uploadingHtml, setUploadingHtml] = useState(false);
  const [uploadFeedback, setUploadFeedback] = useState(null);
  const [deletingApp, setDeletingApp] = useState("");
  const [deploymentNotice, setDeploymentNotice] = useState(null);
  const uploadInputRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [nagiosPopupOpen, setNagiosPopupOpen] = useState(false);
  const refreshInFlight = useRef(false);
  const [refreshSeconds, setRefreshSeconds] = useState(() => {
    const stored = Number(window.localStorage.getItem("monitor-refresh-seconds"));
    return [15, 30, 60].includes(stored) ? stored : 30;
  });
  const [activeNav, setActiveNav] = useState("dashboard");

  const loadData = useCallback(async (showLoading = false) => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    if (showLoading) setLoading(true);
    setError("");
    try {
      const data = await api.dashboard();
      const statusData = data.monitor;
      setStatus(statusData);
      setServices(statusData.services || []);
      setAlerts((statusData.services || []).filter((service) => service.state !== 0));
      setResources(data.resources);
      setInfrastructure(data.infrastructure);
      setApplications(data.applications || []);
      setLastUpdated(new Date());
      setError("");
    } catch (err) {
      setError(err.status === 503
        ? "SSH connection unavailable. The dashboard could not retrieve current EC2 monitoring data."
        : err.message);
    } finally {
      refreshInFlight.current = false;
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(true);
    const timer = window.setInterval(() => loadData(false), refreshSeconds * 1000);
    return () => window.clearInterval(timer);
  }, [loadData, refreshSeconds]);

  const navigate = (id) => {
    setMobileOpen(false);
    setActiveNav(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const updateRefreshSeconds = (event) => {
    const value = Number(event.target.value);
    setRefreshSeconds(value);
    window.localStorage.setItem("monitor-refresh-seconds", String(value));
  };

  const selectHtmlFile = (event) => {
    const file = event.currentTarget.files?.[0];
    setUploadFeedback(null);
    if (!file) {
      setSelectedHtmlFile(null);
      return;
    }
    if (!file.name.toLowerCase().endsWith(".html")) {
      setSelectedHtmlFile(null);
      setUploadFeedback({ type: "error", text: "Choose an .html file." });
      event.currentTarget.value = "";
      return;
    }
    if (file.size > MAX_HTML_BYTES) {
      setSelectedHtmlFile(null);
      setUploadFeedback({ type: "error", text: "The HTML file must be 256 KB or smaller." });
      event.currentTarget.value = "";
      return;
    }
    setSelectedHtmlFile(file);
  };

  const uploadAndDeployHtml = async () => {
    if (!selectedHtmlFile) return;
    setUploadingHtml(true);
    setUploadFeedback(null);
    try {
      const result = await api.uploadApplication(
        selectedHtmlFile.name,
        await selectedHtmlFile.text(),
      );
      setApplications((current) => [...current, result].sort(
        (left, right) => left.name.localeCompare(right.name)
      ));
      setUploadFeedback(result.deployed
        ? { type: "success", text: `${selectedHtmlFile.name} is live at ${result.path} (HTTP ${result.status_code}).` }
        : { type: "error", text: `Puppet applied the file, but the live check returned HTTP ${result.status_code || "unavailable"}.` });
      setSelectedHtmlFile(null);
      if (uploadInputRef.current) uploadInputRef.current.value = "";
      await loadData(false);
    } catch (err) {
      setUploadFeedback({ type: "error", text: err.message });
    } finally {
      setUploadingHtml(false);
    }
  };

  const deleteApplication = async (app) => {
    if (!window.confirm(`Delete ${app.name} from EC2? This cannot be undone.`)) return;
    setDeletingApp(app.id);
    setDeploymentNotice(null);
    try {
      const result = await api.deleteApplication(app.id);
      if (result.deleted) {
        setApplications((current) => current.filter((item) => item.id !== app.id));
        setDeploymentNotice({ type: "success", text: `${app.name} was deleted from EC2.` });
      } else {
        setDeploymentNotice({ type: "error", text: `Could not confirm deletion of ${app.name}.` });
      }
      await loadData(false);
    } catch (err) {
      setDeploymentNotice({ type: "error", text: `Could not remove ${app.name}: ${err.message}` });
    } finally {
      setDeletingApp("");
    }
  };

  const deploymentBusy = Boolean(deletingApp || uploadingHtml);
  const summary = status?.summary || {
    total_hosts: 0, total_services: 0, ok: 0, warning: 0, critical: 0, unknown: 0,
  };
  const host = status?.hosts?.[0];

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><Activity size={22} /></div>
          <div><strong>Server Monitor</strong><span>AWS · Nagios</span></div>
        </div>
        <nav>
          {navItems.map(({ id, label, icon: Icon }) => (
            <button key={id} className={activeNav === id ? "active" : ""} onClick={() => navigate(id)}>
              <Icon size={18} /><span>{label}</span>
              {id === "alerts" && alerts.length > 0 && <b>{alerts.length}</b>}
            </button>
          ))}
        </nav>
        <div className="sidebar-status">
          <div>
            <span className={`connection-dot ${!status || error || summary.critical > 0 ? "offline" : ""}`} />
            {error ? "Data unavailable" : !status ? "Connecting to EC2" : summary.critical > 0 ? "Critical issue detected" : "EC2 connected"}
          </div>
          <small>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Waiting for data"}</small>
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-backdrop" aria-label="Close menu" onClick={() => setMobileOpen(false)} />}

      <main>
        <header id="dashboard" className="topbar">
          <button className="menu-button" aria-label="Open menu" onClick={() => setMobileOpen(true)}><Menu size={20} /></button>
          <div className="title-block">
            <p>Infrastructure deployment & monitoring</p>
            <h1>Automated Web Application Deployment and Monitoring</h1>
            <div className="host-line">
              <Server size={14} /> EC2 {status ? "15.135.200.112" : "AWS server"} <span>•</span>
              <i className={host?.state === 0 ? "up" : ""}>{host ? host.state_text : "Awaiting host data"}</i>
            </div>
          </div>
          <div className="header-actions">
            <div className="refresh-indicator"><span />Auto refresh {refreshSeconds}s</div>
            <button className="icon-button" aria-label="Refresh data" onClick={() => loadData(true)} disabled={loading}>
              <RefreshCw size={18} className={loading ? "spin" : ""} />
            </button>
            <div className="avatar">U</div>
          </div>
        </header>

        {error && (
          <section className="error-banner">
            <XCircle size={20} />
            <div><strong>Unable to refresh monitoring data</strong><span>{error}</span></div>
            <button onClick={() => loadData(true)}>Try again</button>
          </section>
        )}

        {loading && !status ? (
          <div className="loading-state"><RefreshCw className="spin" size={28} /><p>Connecting to Nagios status data...</p></div>
        ) : (
          <>
            <section className="summary-grid">
              <StatCard icon={Server} label="Monitored hosts" value={summary.total_hosts} tone="blue" />
              <StatCard icon={ShieldCheck} label="Total services" value={summary.total_services} tone="purple" />
              <StatCard icon={CheckCircle2} label="Services OK" value={summary.ok} tone="green" />
              <StatCard icon={AlertTriangle} label="Warning alerts" value={summary.warning} tone="yellow" />
              <StatCard icon={XCircle} label="Critical alerts" value={summary.critical} tone="red" />
            </section>

            <section id="deploy" className="deployment-section">
              <div className="section-title">
                <div><p>Release management</p><h2>HTML application deployment</h2><span>Puppet deploys an application only after you upload an HTML file.</span></div>
                <div className="section-tools">
                  <button className="nagios-popup-trigger" onClick={() => { setNagiosPopupOpen(true); loadData(false); }}>
                    <Activity size={14} /> Nagios app checks
                    <span>{services.filter((service) => service.service_description.startsWith("APP - ")).length}</span>
                  </button>
                  <span className="deployment-target"><Server size={14} /> EC2 · Nginx · port 8080</span>
                </div>
              </div>
              <div className="deployment-hint">
                EC2 port 8080 stays private. Jenkins also uses local port 8080, so this demo tunnel uses 8081 instead.
                <code>ssh -i D:\aws-keys\automated-server-monitoring-key.pem -N -L 8081:127.0.0.1:8080 ubuntu@15.135.200.112</code>
              </div>
              <div className="upload-deploy-panel">
                <div className="upload-deploy-copy">
                  <strong>Deploy an HTML application</strong>
                  <span>Select a self-contained .html file (up to 256 KB). Every upload gets its own name, URL, Nagios check, and card; it stays here until you delete it.</span>
                </div>
                <div className="upload-deploy-controls">
                  <input
                    ref={uploadInputRef}
                    type="file"
                    accept=".html,text/html"
                    aria-label="Choose an HTML file to deploy"
                    onChange={selectHtmlFile}
                    disabled={deploymentBusy}
                  />
                  <button
                    className="deploy-button upload-deploy-button"
                    onClick={uploadAndDeployHtml}
                    disabled={!selectedHtmlFile || deploymentBusy}
                  >
                    {uploadingHtml ? <RefreshCw className="spin" size={15} /> : <Upload size={15} />}
                    {uploadingHtml ? "Uploading and deploying..." : "Deploy selected HTML"}
                  </button>
                </div>
                {uploadFeedback && <span className={`upload-feedback ${uploadFeedback.type}`}>{uploadFeedback.text}</span>}
              </div>
              {deploymentNotice && <div className={`deployment-notice ${deploymentNotice.type}`}>{deploymentNotice.text}</div>}
              <div className="application-grid">
                {applications.map((app, index) => (
                  <article className="application-card uploaded-app-card" key={app.id}>
                    <div className="application-card-top">
                      <div className="application-icon"><Upload size={20} /></div>
                      <span className={`app-state ${app.deployed ? "deployed" : ""}`}>
                        <i />{app.deployed ? "DEPLOYED" : "CHECK FAILED"}
                      </span>
                    </div>
                    <span className="app-sequence">UPLOADED HTML · {String(index + 1).padStart(2, "0")}</span>
                    <h3 title={app.name}>{app.name}</h3>
                    <p>Static HTML page deployed with Puppet and served by Nginx.</p>
                    <div className="app-route"><code>{app.path}</code><span>{app.status_code ? `HTTP ${app.status_code}` : "Check unavailable"}</span></div>
                    <div className="app-actions">
                      <button
                        className="delete-app-button"
                        onClick={() => deleteApplication(app)}
                        disabled={deploymentBusy}
                        aria-label={`Delete ${app.name} from EC2`}
                        title={deletingApp === app.id ? "Deleting with Puppet..." : `Delete ${app.name} from EC2`}
                      >
                        {deletingApp === app.id ? <RefreshCw className="spin" size={15} /> : <Trash2 size={15} />}
                        <span>{deletingApp === app.id ? "Deleting" : "Delete"}</span>
                      </button>
                      {app.deployed && (
                        <a href={app.tunnel_url} target="_blank" rel="noreferrer" aria-label={`Open ${app.name} through the SSH tunnel`}>
                          <ArrowUpRight size={17} />
                        </a>
                      )}
                    </div>
                  </article>
                ))}
                {!applications.length && (
                  <div className="application-empty">
                    <Upload size={22} />
                    <strong>Your app workspace is empty</strong>
                    <span>Upload an HTML file above. Each deployment gets its own URL and card.</span>
                  </div>
                )}
              </div>
            </section>

            <section className="dashboard-grid">
              <article className="panel health-panel">
                <div className="panel-heading"><div><p>Live health</p><h2>Service Status</h2></div><span className="live-pill">LIVE</span></div>
                <Donut summary={summary} />
              </article>
              <article id="system" className="panel resource-panel">
                <div className="panel-heading"><div><p>EC2 live readings</p><h2>System Resources</h2></div></div>
                {resources ? (
                  <div className="resource-list">
                    <div className="resource-row"><div className="resource-icon blue"><Cpu size={19} /></div><div><span>CPU</span><strong>{resources.cpu === null || resources.cpu === undefined ? "Not available" : `${resources.cpu}%`}</strong></div></div>
                    <div className="resource-row"><div className="resource-icon purple"><Activity size={19} /></div><div><span>Memory</span><strong>{formatBytes(resources.memory?.used_bytes)} / {formatBytes(resources.memory?.total_bytes)}</strong></div></div>
                    <div className="resource-row"><div className="resource-icon cyan"><HardDrive size={19} /></div><div><span>Root disk</span><strong>{formatBytes(resources.disk?.used_bytes)} / {formatBytes(resources.disk?.total_bytes)}</strong></div></div>
                    <div className="resource-row"><div className="resource-icon green"><Network size={19} /></div><div><span>Uptime</span><strong>{resources.uptime || "Unavailable"}</strong></div></div>
                  </div>
                ) : <p className="muted">System resource data unavailable.</p>}
              </article>
            </section>

            <section id="services" className="panel table-panel">
              <div className="panel-heading">
                <div><p>Nagios Core</p><h2>Monitored Services</h2></div>
                <span className="count-pill">{services.length} services</span>
              </div>
              {services.length ? (
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Host</th><th>Service Name</th><th>Status</th><th>Plugin Output</th><th>Last Check</th><th>Interval</th></tr></thead>
                    <tbody>
                      {services.map((service) => (
                        <tr key={`${service.host_name}-${service.service_description}`}>
                          <td><span className="host-cell"><Server size={14} />{service.host_name}</span></td>
                          <td><strong>{service.service_description}</strong></td>
                          <td><StatusBadge stateText={service.state_text} /></td>
                          <td className="output-cell">{service.plugin_output || "No plugin output"}</td>
                          <td>{formatTimestamp(service.last_check)}</td>
                          <td>{service.check_interval ? `${service.check_interval} min` : "Unavailable"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <div className="empty-state"><Server size={32} /><strong>No monitored services</strong><span>No service status data was returned.</span></div>}
            </section>

            <section className="bottom-grid">
              <article id="alerts" className="panel alerts-panel">
                <div className="panel-heading"><div><p>Notifications</p><h2>Recent Alerts</h2></div><span className="count-pill">{alerts.length} active</span></div>
                {alerts.length ? alerts.map((alert) => (
                  <div className="alert-item" key={`${alert.host_name}-${alert.service_description}`}>
                    <div className={`alert-icon ${alert.state_text?.toLowerCase()}`}><AlertTriangle size={18} /></div>
                    <div><strong>{alert.service_description}</strong><span>{alert.host_name} · {alert.plugin_output}</span></div>
                    <StatusBadge stateText={alert.state_text} />
                  </div>
                )) : (
                  <div className="empty-alert"><div><CheckCircle2 size={26} /></div><strong>All systems operational</strong><span>No active alerts.</span></div>
                )}
              </article>

              <article className="panel infrastructure-panel">
                <div className="panel-heading"><div><p>Configuration stack</p><h2>Infrastructure</h2></div></div>
                {infrastructure ? (
                  <div className="infra-list">
                    {[
                      ["Nagios Core", infrastructure.nagios_core],
                      ["Nginx", infrastructure.nginx],
                      ["Puppet Server", infrastructure.puppet_server],
                      ["Puppet Agent", infrastructure.puppet_agent],
                    ].map(([name, item]) => (
                      <div key={name}><span>{name}</span><strong className={item.verified && item.status === "active" ? "ok" : ""}>
                        {item.verified ? item.status : "Not checked"}
                      </strong></div>
                    ))}
                  </div>
                ) : <p className="muted">Infrastructure status unavailable.</p>}
              </article>
            </section>

            <section id="settings" className="panel settings-panel">
              <div className="panel-heading">
                <div><p>Dashboard preferences</p><h2>Settings</h2></div>
              </div>
              <div className="settings-row">
                <div><strong>Automatic refresh</strong><span>Changes are saved in this browser.</span></div>
                <select value={refreshSeconds} onChange={updateRefreshSeconds} aria-label="Automatic refresh interval">
                  <option value={15}>Every 15 seconds</option>
                  <option value={30}>Every 30 seconds</option>
                  <option value={60}>Every 60 seconds</option>
                </select>
              </div>
              <div className="settings-row">
                <div><strong>Monitoring target</strong><span>Backend reads Nagios and resource data over SSH.</span></div>
                <span className="settings-value">AWS EC2 · ap-southeast-2</span>
              </div>
            </section>

            <footer id="about">
              <span><ShieldCheck size={15} /> Automated Web Application Deployment and Monitoring</span>
              <span>FastAPI · Nagios Core · Puppet · AWS EC2</span>
              {lastUpdated && <span>Last updated {lastUpdated.toLocaleTimeString()}</span>}
            </footer>
          </>
        )}
      </main>
      {nagiosPopupOpen && (
        <div
          className="nagios-modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setNagiosPopupOpen(false);
          }}
        >
          <section className="nagios-modal" role="dialog" aria-modal="true" aria-labelledby="nagios-modal-title">
            <header className="nagios-modal-header">
              <div><p>NAGIOS CORE · LIVE SERVICE DATA</p><h2 id="nagios-modal-title">Application monitoring</h2></div>
              <button className="icon-button" aria-label="Close Nagios app checks" onClick={() => setNagiosPopupOpen(false)}><X size={18} /></button>
            </header>
            <p className="nagios-modal-intro">Nagios runs an HTTP check against each EC2 app route on port 8080. Results below come from Nagios <code>status.dat</code>.</p>
            <div className="nagios-app-check-list">
              {applications.map((app) => {
                const check = services.find((service) => service.service_description === `APP - ${app.id}`);
                return (
                  <article key={app.id} className="nagios-app-check">
                    <div className="nagios-app-check-top">
                      <strong>{app.name}</strong>
                      {check
                        ? <StatusBadge stateText={check.state_text} />
                        : <span className="status-badge status-unknown"><span />NOT CONFIGURED</span>}
                    </div>
                    <code>{app.path}</code>
                    <p>{check?.plugin_output || "Nagios has not reported a check for this app yet."}</p>
                    <small>
                      {app.deployed ? `Deployment HTTP ${app.status_code}` : "App not deployed"}
                      {check ? ` · Last check ${formatTimestamp(check.last_check)} · every ${check.check_interval} min` : ""}
                    </small>
                  </article>
                );
              })}
            </div>
            <footer className="nagios-modal-footer">Each uploaded app has its own HTTP check. Deleting an app also removes its Nagios check.</footer>
          </section>
        </div>
      )}
    </div>
  );
}

export default App;
