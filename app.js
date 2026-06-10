/* ══════════════════════════════════════════
   HomeSafe — Multi-Camera Dashboard Script
   Monitoring-only. No simulation controls.
   ══════════════════════════════════════════ */

const SERVER = 'http://localhost:5000';
let serverConnected = false;

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// ═══════════════════════════════════════
// CAMERA STATE — fully independent per device
// ═══════════════════════════════════════
const cameraState = {
  cam1: {
    id: 'cam1', name: 'Camera 1 — Front Door', ip: '192.168.137.168',
    connected: false,
    status: 'DISCONNECTED', threat: 'NONE',
    packets: 0, packetSize: 0, destChanges: 0, activityHour: 0,
    healPhase: null,
    healCooldownRemaining: 0, healStableCount: 0, healStableNeeded: 3,
    attackMemoryCount: 0,
    logs: [], chartLabels: [], chartData: [], totalReadings: 0,
  },
  cam2: {
    id: 'cam2', name: 'Camera 2 — Backyard', ip: '192.168.137.139',
    connected: false,
    status: 'DISCONNECTED', threat: 'NONE',
    packets: 0, packetSize: 0, destChanges: 0, activityHour: 0,
    healPhase: null,
    healCooldownRemaining: 0, healStableCount: 0, healStableNeeded: 3,
    attackMemoryCount: 0,
    logs: [], chartLabels: [], chartData: [], totalReadings: 0,
  }
};

let activeCam = 'cam1';
let chart     = null;

// Shared event log — all cameras combined, newest first
const sharedLogs = [];

const STATUS_COLORS = {
  NORMAL:       '#00ff88',
  SUSPICIOUS:   '#ffb300',
  QUARANTINED:  '#ff3d3d',
  HEALING:      '#00d4ff',
  RECOVERING:   '#00e5cc',
  DISCONNECTED: '#2a5068',
};

// ═══════════════════════════════════════
// IoT CATEGORIES
// ═══════════════════════════════════════
const iotCategories = {
  cctv:     { name: 'CCTV',                 icon: '📹', serverDependent: true,  devices: [{ name:'Camera 1 — Front Door', ip:'192.168.137.168' }, { name:'Camera 2 — Backyard', ip:'192.168.137.139' }, { name:'Camera 3 — Garage', ip:'192.168.1.72' }] },
  router:   { name: 'Router / Gateway',     icon: '🌐', serverDependent: false, devices: [{ name:'Main Router', ip:'192.168.1.1' }, { name:'Range Extender', ip:'192.168.1.2' }] },
  laptop:   { name: 'Laptop / Workstation', icon: '💻', serverDependent: false, devices: [{ name:'Dev Laptop', ip:'192.162.1.65' }, { name:'Desktop Workstation', ip:'192.168.1.11' }, { name:'Office PC', ip:'192.168.1.12' }] },
  mobile:   { name: 'Mobile Devices',       icon: '📱', serverDependent: false, devices: [{ name:'Phone — Primary', ip:'192.168.137.139' }, { name:'Phone — Secondary', ip:'192.168.137.139' }, { name:'Tablet', ip:'192.168.1.70' }] },
  smarttv:  { name: 'Smart TV',             icon: '📺', serverDependent: false, devices: [{ name:'Living Room TV', ip:'192.168.1.40' }, { name:'Bedroom TV', ip:'192.168.1.41' }] },
  alexa:    { name: 'Alexa / Speaker',      icon: '🔊', serverDependent: false, devices: [{ name:'Echo Dot — Kitchen', ip:'192.168.1.50' }, { name:'Echo Show — Hall', ip:'192.168.1.51' }, { name:'Google Nest Mini', ip:'192.168.1.52' }] },
  iot:      { name: 'Smart IoT Devices',    icon: '🏠', serverDependent: false, devices: [{ name:'Smart Thermostat', ip:'192.168.1.80' }, { name:'Smart Light Hub', ip:'192.168.1.81' }, { name:'Smart Lock — Front', ip:'192.168.1.82' }, { name:'Motion Sensor', ip:'192.168.1.83' }] },
  server:   { name: 'Servers',              icon: '🖥️', serverDependent: false, devices: [{ name:'NAS Storage', ip:'192.168.1.90' }, { name:'Home Server', ip:'192.168.1.91' }] },
  external: { name: 'External IP Nodes',    icon: '🔗', serverDependent: false, devices: [{ name:'Cloud Gateway', ip:'203.0.113.10' }, { name:'VPN Endpoint', ip:'198.51.100.5' }, { name:'Remote Monitor', ip:'192.0.2.20' }] },
};

function isCatConnected(key) {
  return iotCategories[key].serverDependent && serverConnected;
}

// ═══════════════════════════════════════
// SPA ROUTING
// ═══════════════════════════════════════
function navigateTo(screenId, data) {
  document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
  const bc = document.getElementById('breadcrumb');

  if (screenId === 'screen-home') {
    bc.innerHTML = '<span class="bc-current">Home</span>';
  } else if (screenId === 'screen-category') {
    const key = data.categoryKey;
    bc.innerHTML = `<span class="bc-link" onclick="navigateTo('screen-home')">Home</span><span class="bc-sep"> › </span><span class="bc-current">${iotCategories[key].name}</span>`;
    renderDeviceList(key);
  } else if (screenId === 'screen-cctv') {
    bc.innerHTML = `<span class="bc-link" onclick="navigateTo('screen-home')">Home</span><span class="bc-sep"> › </span><span class="bc-link" onclick="navigateTo('screen-category',{categoryKey:'cctv'})">CCTV</span><span class="bc-sep"> › </span><span class="bc-current">Dashboard</span>`;
    renderCameraSidebar();
    switchCamera(activeCam);
  }

  document.getElementById(screenId).classList.add('active');
}

// ═══════════════════════════════════════
// HOME SCREEN
// ═══════════════════════════════════════
function renderHomeCategories() {
  const grid = document.getElementById('categoryGrid');
  grid.innerHTML = '';
  for (const [key, cat] of Object.entries(iotCategories)) {
    const connected = isCatConnected(key);
    const card = document.createElement('div');
    card.className = `category-card ${connected ? 'clickable' : 'disabled'}`;
    card.id = `cat-card-${key}`;
    card.innerHTML = `
      <span class="cat-icon">${cat.icon}</span>
      <div class="cat-name">${cat.name}</div>
      <div class="cat-count">${cat.devices.length} Device${cat.devices.length !== 1 ? 's' : ''}</div>
      <div class="cat-status ${connected ? 'online' : 'offline'}">${connected ? '● Connected' : '○ Disconnected'}</div>`;
    if (connected) {
      card.onclick = () => key === 'cctv'
        ? navigateTo('screen-cctv')
        : navigateTo('screen-category', { categoryKey: key });
    }
    grid.appendChild(card);
  }
}

// ═══════════════════════════════════════
// DEVICE LIST
// ═══════════════════════════════════════
function renderDeviceList(key) {
  const cat = iotCategories[key];
  document.getElementById('categoryTitle').textContent = cat.name + ' — Devices';
  const grid      = document.getElementById('deviceGrid');
  grid.innerHTML  = '';
  const connected = isCatConnected(key);
  cat.devices.forEach(dev => {
    const card = document.createElement('div');
    card.className = `device-card ${connected ? 'connected' : 'disconnected'}`;
    card.innerHTML = `
      <div class="dev-status-dot"></div>
      <div class="dev-name">${dev.name}</div>
      <div class="dev-ip">${dev.ip}</div>
      <div class="dev-status-text">${connected ? '● Connected' : '○ Disconnected'}</div>`;
    grid.appendChild(card);
  });
}

// ═══════════════════════════════════════
// CAMERA SIDEBAR — monitoring only
// ═══════════════════════════════════════
function _dotClass(cam, offline) {
  if (offline) return 'dot-offline';
  const hp = cam.healPhase;
  if (hp === 'HEALING')   return 'dot-healing';
  if (hp === 'RECOVERING') return 'dot-recovering';
  if (cam.status === 'QUARANTINED') return 'dot-quarantined';
  if (cam.status === 'SUSPICIOUS')  return 'dot-suspicious';
  return 'dot-normal';
}
function _badgeClass(cam, offline) {
  if (offline) return 'badge-offline';
  const hp = cam.healPhase;
  if (hp === 'HEALING')   return 'badge-healing';
  if (hp === 'RECOVERING') return 'badge-recovering';

  if (cam.status === 'QUARANTINED') return 'badge-quarantined';
  if (cam.status === 'SUSPICIOUS')  return 'badge-suspicious';
  return 'badge-normal';
}
function _badgeText(cam, offline) {
  if (offline) return 'NO DATA';
  if (cam.healPhase === 'HEALING')   return 'HEALING';
  if (cam.healPhase === 'RECOVERING') return 'RECOVR';
  return cam.status;
}

function renderCameraSidebar() {
  const list = document.getElementById('camList');
  list.innerHTML = '';

  Object.values(cameraState).forEach(cam => {
    const st      = cam.status;
    const offline = !serverConnected || !cam.connected;
    const rowExtra = cam.healPhase === 'HEALING' || cam.healPhase === 'RECOVERING'
      ? '' : st === 'QUARANTINED' ? 'cam-quarantined' : st === 'SUSPICIOUS' ? 'cam-suspicious' : '';

    const item = document.createElement('div');
    item.className = `cam-item ${cam.id === activeCam ? 'active' : ''} ${rowExtra}`;
    item.id = `sidebar-${cam.id}`;
    item.innerHTML = `
      <div class="cam-dot ${_dotClass(cam, offline)}"></div>
      <span class="cam-label">${cam.name.split('—')[0].trim()}</span>
      <span class="cam-status-badge ${_badgeClass(cam, offline)}">${_badgeText(cam, offline)}</span>`;
    item.onclick = () => switchCamera(cam.id);
    list.appendChild(item);
  });
}

// ═══════════════════════════════════════
// SWITCH ACTIVE CAMERA
// ═══════════════════════════════════════
function switchCamera(camId) {
  activeCam = camId;
  const cam = cameraState[camId];

  document.querySelectorAll('.cam-item').forEach(el => {
    el.classList.toggle('active', el.id === `sidebar-${camId}`);
  });

  document.getElementById('metaDevice').textContent = cam.name;
  document.getElementById('metaCamIP').textContent  = cam.ip;

  renderCamMetrics(cam);
  renderCamLogs();
  updateChartForCam(cam);
}


// ═══════════════════════════════════════
// RENDER CAM METRICS
// ═══════════════════════════════════════
function renderCamMetrics(cam) {
  const banner    = document.getElementById('statusBanner');
  const bannerTxt = document.getElementById('bannerStatus');
  if (!banner || !bannerTxt) return;

  const disconnected = !cam.connected;
  // Effective display state — healing phases override raw status for UI
  let displaySt = disconnected ? 'DISCONNECTED' : cam.status;
  if (!disconnected && cam.healPhase === 'HEALING')   displaySt = 'HEALING';
  if (!disconnected && cam.healPhase === 'RECOVERING') displaySt = 'RECOVERING';

  banner.className    = displaySt;
  bannerTxt.className = displaySt;
  const statusLabels = { HEALING: 'HEALING', RECOVERING: 'RECOVERING',
    DISCONNECTED: 'NO DATA', ISOLATED: 'ISOLATED' };
  bannerTxt.textContent = disconnected ? 'NO DATA' : (statusLabels[displaySt] || displaySt);

  // During healing/recovering, show threat as NONE (zero bars) — device is being remediated
  const displayThreat = (disconnected || cam.healPhase) ? 'NONE' : cam.threat;
  setThreat(displayThreat);

  setText('mPackets',      disconnected ? '—' : cam.packets);
  setText('mPacketSize',   disconnected ? '—' : cam.packetSize);
  setText('mDestChanges',  disconnected ? '—' : cam.destChanges);
  setText('mActivityHour', disconnected ? '—' : cam.activityHour);

  const pct = (v, max) => disconnected ? 0 : Math.min(100, (v / max) * 100);
  const pktCol  = cam.packets    > 12000 ? '#ef4444' : cam.packets    > 9000 ? '#f59e0b' : '#10b981';
  const sizeCol = cam.packetSize < 600   ? '#ef4444' : cam.packetSize > 1450 ? '#ef4444' : cam.packetSize > 1350 ? '#f59e0b' : '#10b981';
  const dstCol  = cam.destChanges > 10   ? '#ef4444' : cam.destChanges > 5   ? '#f59e0b' : '#10b981';
  setBar('barPackets',     pct(cam.packets,     20000), pktCol);
  setBar('barPacketSize',  pct(cam.packetSize,   1600), sizeCol);
  setBar('barDestChanges', pct(cam.destChanges,    30), dstCol);
  setBar('barActivityHour',pct(cam.activityHour,   24), '#00d4ff');

  // ── Healing panel ────────────────────────────────────────────────────────
  renderHealPanel(cam);
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ═══════════════════════════════════════
// RENDER CAM LOGS — shared across all cameras
// ═══════════════════════════════════════
function renderCamLogs() {
  const list = document.getElementById('logList');
  if (!list) return;
  list.innerHTML = '';
  sharedLogs.slice(0, 50).forEach(entry => {
    const li = document.createElement('li');
    li.className = `log-item ${entry.status}`;
    li.innerHTML = `<span class="log-time">${entry.time}</span><span class="log-cam-tag">${entry.camTag}</span><span>${entry.msg}</span>`;
    list.appendChild(li);
  });
}

function addCamLog(camId, status, msg) {
  const cam    = cameraState[camId];
  const t      = new Date().toLocaleTimeString('en-GB');
  const camTag = cam ? cam.name.split('—')[0].trim() : camId;
  sharedLogs.unshift({ status, time: t, msg, camTag });
  if (sharedLogs.length > 80) sharedLogs.pop();
  // Re-render whenever CCTV screen is active
  if (document.getElementById('screen-cctv')?.classList.contains('active')) {
    renderCamLogs();
  }
}

// ═══════════════════════════════════════
// CHART
// ═══════════════════════════════════════
function initChart() {
  const ctx = document.getElementById('trafficChart');
  if (!ctx) return;
  chart = new Chart(ctx.getContext('2d'), {
    type: 'line',
    data: {
      labels: [],
      datasets: [{
        label: 'Packets / Window', data: [],
        borderColor: '#00ff88', backgroundColor: 'rgba(0,255,136,0.06)',
        fill: true, tension: 0.45, pointRadius: 3,
        pointBackgroundColor: '#00ff88', pointBorderColor: '#020b14', pointBorderWidth: 2,
      }]
    },
    options: {
      animation: false, responsive: true,
      interaction: { intersect: false, mode: 'index' },
      plugins: { legend: { labels: { color: '#2a5068', font: { family: 'JetBrains Mono', size: 10 } } } },
      scales: {
        x: { ticks: { color: '#2a5068', font: { family: 'JetBrains Mono', size: 9 } }, grid: { color: 'rgba(14,58,90,0.5)' } },
        y: { ticks: { color: '#2a5068', font: { family: 'JetBrains Mono', size: 9 } }, grid: { color: 'rgba(14,58,90,0.5)' }, beginAtZero: true },
      }
    }
  });
}

function updateChartForCam(cam) {
  if (!chart) return;
  chart.data.labels            = [...cam.chartLabels];
  chart.data.datasets[0].data = [...cam.chartData];
  const col = STATUS_COLORS[cam.connected ? cam.status : 'DISCONNECTED'] || '#2a5068';
  chart.data.datasets[0].borderColor          = col;
  chart.data.datasets[0].backgroundColor      = col + '11';
  chart.data.datasets[0].pointBackgroundColor = col;
  chart.update();
}

function pushChartPoint(camId, t, packets) {
  const cam = cameraState[camId];
  cam.chartLabels.push(t);
  cam.chartData.push(packets);
  if (cam.chartLabels.length > 20) { cam.chartLabels.shift(); cam.chartData.shift(); }
  if (activeCam === camId) updateChartForCam(cam);
}

// ═══════════════════════════════════════
// THREAT BAR
// ═══════════════════════════════════════
function setThreat(level) {
  const colors = {
    LOW:    { col: '#00ff88', n: 1 },
    MEDIUM: { col: '#ffb300', n: 2 },
    HIGH:   { col: '#ff3d3d', n: 3 },
    NONE:   { col: '#2a5068', n: 0 },
  };
  const cfg = colors[level] || colors.LOW;
  const tt  = document.getElementById('threatText');
  if (tt) { tt.textContent = level; tt.style.color = cfg.col; }
  for (let i = 1; i <= 3; i++) {
    const seg = document.getElementById('ts' + i);
    if (seg) seg.style.background = i <= cfg.n ? cfg.col : 'var(--border)';
  }
}

function setBar(id, pct, color) {
  const el = document.getElementById(id);
  if (!el) return;
  el.style.width      = Math.min(100, Math.max(0, pct)) + '%';
  el.style.background = color;
}

// ═══════════════════════════════════════
// CLOCK & UPTIME
// ═══════════════════════════════════════
function tickClock() {
  const now  = new Date();
  const dd   = String(now.getDate()).padStart(2, '0');
  const mmm  = MONTHS[now.getMonth()];
  const yyyy = now.getFullYear();
  const hh   = String(now.getHours()).padStart(2, '0');
  const mm   = String(now.getMinutes()).padStart(2, '0');
  const ss   = String(now.getSeconds()).padStart(2, '0');
  document.getElementById('clock').textContent = `${dd} ${mmm} ${yyyy}  |  ${hh}:${mm}:${ss}`;
}

const startTime = Date.now();
function updateUptime() {
  const el = document.getElementById('metaUptime');
  if (!el) return;
  const s   = Math.floor((Date.now() - startTime) / 1000);
  const h   = String(Math.floor(s / 3600)).padStart(2, '0');
  const m   = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
  const sec = String(s % 60).padStart(2, '0');
  el.textContent = `${h}:${m}:${sec}`;
}

// ═══════════════════════════════════════
// APPLY DATA → Camera State
// ═══════════════════════════════════════
function applyDeviceData(camId, alertData, metricsData) {
  const cam        = cameraState[camId];
  const prevStatus = cam.status;
  const prevPhase  = cam.healPhase;
  const t          = new Date().toLocaleTimeString('en-GB');

  cam.connected    = true;
  cam.status       = alertData.status    || 'NORMAL';
  cam.threat       = alertData.threat    || 'LOW';
  cam.healPhase    = alertData.heal_phase || null;
  cam.healCooldownRemaining = alertData.heal_cooldown_remaining || 0;
  cam.healStableCount       = alertData.heal_stable_count       || 0;
  cam.healStableNeeded      = alertData.heal_stable_needed      || 3;
  cam.attackMemoryCount     = alertData.attack_memory_count     || 0;
  cam.packets      = metricsData.no_of_packets         || 0;
  cam.packetSize   = metricsData.packet_size           || 0;
  cam.destChanges  = metricsData.dest_ip_changes       || 0;
  cam.activityHour = metricsData.activity_hour_pattern || 0;
  cam.totalReadings++;

  pushChartPoint(camId, t, cam.packets);

  // Log significant transitions
  if (cam.status !== prevStatus) {
    addCamLog(camId, cam.status,
      `${cam.name.split('\u2014')[0].trim()} → ${cam.status}  |  Threat: ${cam.threat}`);
    if (cam.status === 'QUARANTINED') {
      addCamLog(camId, 'QUARANTINED', `🚫 ${cam.name.split('\u2014')[0].trim()} — ISOLATED · Feed cut off`);
    }
    // Show user-friendly popup when status turns SUSPICIOUS
    if (cam.status === 'SUSPICIOUS' && prevStatus !== 'SUSPICIOUS') {
      showSuspiciousAlert(camId);
    }
  }
  if (cam.healPhase !== prevPhase) {
    if (cam.healPhase === 'HEALING')    addCamLog(camId, 'NORMAL', `💙 ${cam.name.split('\u2014')[0].trim()} — HEALING phase started`);
    if (cam.healPhase === 'RECOVERING') addCamLog(camId, 'SUSPICIOUS', `🔵 ${cam.name.split('\u2014')[0].trim()} — RECOVERING (SUSPICIOUS)`);
    if (!cam.healPhase && prevPhase)    addCamLog(camId, 'NORMAL', `✅ ${cam.name.split('\u2014')[0].trim()} — Fully RECOVERED → NORMAL`);
  }

  if (activeCam === camId) {
    renderCamMetrics(cam);
    document.getElementById('metaTime').textContent = t;
  }

  refreshSidebarDot(camId);
}

function markDeviceDisconnected(camId) {
  const cam     = cameraState[camId];
  const wasConn = cam.connected;

  cam.connected    = false;
  cam.status       = 'DISCONNECTED';
  cam.threat       = 'NONE';
  cam.packets      = 0;
  cam.packetSize   = 0;
  cam.destChanges  = 0;
  cam.activityHour = 0;

  if (wasConn) {
    addCamLog(camId, 'NORMAL',
      `📷 ${cam.name.split('—')[0].trim()} — No Data / Disconnected`);
  }

  if (activeCam === camId) renderCamMetrics(cam);
  refreshSidebarDot(camId);
}

function renderHealPanel(cam) {
  const panel = document.getElementById('healPanel');
  if (!panel) return;
  const show = cam.connected && (cam.status === 'QUARANTINED' || cam.healPhase);
  panel.style.display = show ? 'flex' : 'none';
  if (!show) return;

  const label   = document.getElementById('healLabel');
  const phInfo  = document.getElementById('healPhaseInfo');
  const barFill = document.getElementById('healBarFill');
  const coolEl  = document.getElementById('healCooldown');
  const coolVal = document.getElementById('healCooldownVal');
  const memEl   = document.getElementById('healMemCount');

  if (memEl) memEl.textContent = cam.attackMemoryCount || 0;

  if (cam.status === 'QUARANTINED' && !cam.healPhase) {
    // Waiting for cooldown
    panel.className = 'heal-panel';
    if (label)  { label.textContent = '⏳ QUARANTINED — Cooldown Active'; label.className = 'heal-label'; }
    if (phInfo) phInfo.textContent = `Healing begins after cooldown expires…`;
    if (barFill){ barFill.style.width = '0%'; barFill.className = 'heal-bar-fill'; }
    if (coolEl) coolEl.style.display = 'flex';
    if (coolVal && cam.healCooldownRemaining > 0) coolVal.textContent = Math.ceil(cam.healCooldownRemaining);
  } else if (cam.healPhase === 'HEALING') {
    panel.className = 'heal-panel healing';
    if (label)  { label.textContent = '💙 HEALING'; label.className = 'heal-label'; }
    const pct = cam.healStableNeeded > 0 ? Math.round((cam.healStableCount / cam.healStableNeeded) * 100) : 0;
    if (phInfo) phInfo.textContent = `Stable readings: ${cam.healStableCount} / ${cam.healStableNeeded}`;
    if (barFill){ barFill.style.width = pct + '%'; barFill.className = 'heal-bar-fill'; }
    if (coolEl) coolEl.style.display = 'none';
  } else if (cam.healPhase === 'RECOVERING') {
    panel.className = 'heal-panel recovering';
    if (label)  { label.textContent = '🔵 RECOVERING'; label.className = 'heal-label recovering'; }
    const pct = cam.healStableNeeded > 0 ? Math.round((cam.healStableCount / cam.healStableNeeded) * 100) : 0;
    if (phInfo) phInfo.textContent = `Verifying stability: ${cam.healStableCount} / ${cam.healStableNeeded}`;
    if (barFill){ barFill.style.width = pct + '%'; barFill.className = 'heal-bar-fill recovering'; }
    if (coolEl) coolEl.style.display = 'none';
  }
}

function refreshSidebarDot(camId) {
  const item = document.getElementById(`sidebar-${camId}`);
  if (!item) return;
  const cam     = cameraState[camId];
  const dot     = item.querySelector('.cam-dot');
  const badge   = item.querySelector('.cam-status-badge');
  const offline = !serverConnected || !cam.connected;

  if (dot)   dot.className   = `cam-dot ${_dotClass(cam, offline)}`;
  if (badge) {
    badge.className   = `cam-status-badge ${_badgeClass(cam, offline)}`;
    badge.textContent = _badgeText(cam, offline);
  }

  item.classList.remove('cam-quarantined', 'cam-suspicious');
  if (!offline && !cam.healPhase) {
    if (cam.status === 'QUARANTINED') item.classList.add('cam-quarantined');
    if (cam.status === 'SUSPICIOUS')  item.classList.add('cam-suspicious');
  }
}

function updateConnStatus(ok) {
  const cs = document.getElementById('connStatus');
  if (!cs) return;
  cs.textContent = ok ? 'CONNECTED' : 'OFFLINE';
  cs.className   = ok ? '' : 'err';
}

// ═══════════════════════════════════════
// POLL — per-device independent fetching
// ═══════════════════════════════════════
async function pollDevice(camId) {
  const cam = cameraState[camId];

  if (!cam.connected) {
    // Already marked disconnected by poll() — just ensure UI is right
    if (activeCam === camId) renderCamMetrics(cam);
    refreshSidebarDot(camId);
    return;
  }

  try {
    const [aRes, mRes] = await Promise.all([
      fetch(`${SERVER}/alert?device_id=${camId}&_=${Date.now()}`),
      fetch(`${SERVER}/metrics?device_id=${camId}&_=${Date.now()}`),
    ]);
    const alertData   = await aRes.json();
    const metricsData = await mRes.json();

    if (alertData.connected === false || metricsData.connected === false) {
      markDeviceDisconnected(camId);
      return;
    }

    applyDeviceData(camId, alertData, metricsData);
  } catch (_) {
    // Server is up but this device poll failed — leave state as-is
  }
}

async function poll() {
  try {
    const sRes      = await fetch(`${SERVER}/status?_=${Date.now()}`);
    const statusData = await sRes.json();

    const wasConnected = serverConnected;
    serverConnected    = statusData.server_connected;

    if (!wasConnected && serverConnected) {
      // Just came online
      renderHomeCategories();
      renderCameraSidebar();
      addCamLog('cam1', 'NORMAL', '🟢 Server connected — monitoring active');
    }

    updateConnStatus(true);

    // Update per-device connected flags from /status
    const devices = statusData.devices || {};
    Object.entries(devices).forEach(([id, info]) => {
      if (cameraState[id]) {
        cameraState[id].connected = info.connected;
        if (!info.connected) markDeviceDisconnected(id);
      }
    });

    // Poll each device independently
    await Promise.all(['cam1', 'cam2'].map(id => pollDevice(id)));

    // Refresh sidebar badges
    renderCameraSidebar();

  } catch (_) {
    if (serverConnected) {
      serverConnected = false;
      Object.keys(cameraState).forEach(id => markDeviceDisconnected(id));
      renderHomeCategories();
      renderCameraSidebar();
      addCamLog('cam1', 'QUARANTINED', '🔴 Server disconnected — all devices offline');
    }
    updateConnStatus(false);
  }
}

// ═══════════════════════════════════════
// CAM 1 — SERVER OVERRIDE (demo)
// ═══════════════════════════════════════
async function forceStatus(status) {
  try {
    const r = await fetch(`${SERVER}/force/${status}`);
    const d = await r.json();
    if (d.ok) addCamLog('cam1', status, `🎮 Manual override → ${status}`);
    await poll();
  } catch (e) {
    addCamLog('cam1', 'QUARANTINED', `Override failed: ${e.message}`);
  }
}



// ═══════════════════════════════════════
// SUSPICIOUS ALERT POPUP
// ═══════════════════════════════════════
function showSuspiciousAlert(camId) {
  const cam  = cameraState[camId];
  const name = cam ? cam.name.split('—')[0].trim() : camId;
  
  document.getElementById('susCamName').textContent = name;
  
  const titleEl = document.querySelector('#suspiciousAlert .sus-title');
  const bodyEl  = document.querySelector('#suspiciousAlert .sus-body');
  
  titleEl.textContent = 'Unusual Activity Detected';
  titleEl.style.color = 'var(--amber)';
  document.querySelector('#suspiciousAlert .sus-box').style.borderColor = 'var(--amber)';
  document.querySelector('#suspiciousAlert .sus-icon').textContent = '⚠️';
  bodyEl.innerHTML = `We noticed some unusual network activity on <strong id="susCamName">${name}</strong>. This could be suspicious traffic. We're keeping a close eye on it and will alert you if things get worse.`;
  
  document.getElementById('suspiciousAlert').style.display = 'flex';
}

function dismissSuspiciousAlert() {
  document.getElementById('suspiciousAlert').style.display = 'none';
}


// ═══════════════════════════════════════
let captureActive = false;

async function startRealCapture(deviceIp, windowSec, iface) {
  try {
    const r = await fetch(`${SERVER}/start_capture`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ device_ip: deviceIp, window_sec: windowSec || 5, interface: iface || 'Wi-Fi' }),
    });
    const d = await r.json();
    if (d.ok && d.started) {
      captureActive = true;
      addCamLog('cam1', 'NORMAL', `🟢 Real capture started — device=${deviceIp || 'ALL'}  window=${windowSec || 5}s`);
    } else {
      addCamLog('cam1', 'QUARANTINED', `⚠ Capture failed: ${d.scapy_ok ? 'already running?' : 'Scapy not installed'}`);
    }
    return d;
  } catch (e) {
    addCamLog('cam1', 'QUARANTINED', `Capture error: ${e.message}`);
  }
}

async function stopRealCapture() {
  try {
    const r = await fetch(`${SERVER}/stop_capture`, { method: 'POST' });
    const d = await r.json();
    captureActive = false;
    addCamLog('cam1', 'NORMAL', '⏹ Real capture stopped');
    return d;
  } catch (e) {
    addCamLog('cam1', 'QUARANTINED', `Stop error: ${e.message}`);
  }
}


// ═══════════════════════════════════════
// BOOT
// ═══════════════════════════════════════
document.addEventListener('DOMContentLoaded', () => {
  renderHomeCategories();
  initChart();

  tickClock();
  setInterval(tickClock, 1000);
  setInterval(updateUptime, 1000);

  addCamLog('cam1', 'NORMAL', '🟢 HomeSafe Dashboard — Waiting for server…');
  addCamLog('cam2', 'NORMAL', '🟢 Camera 2 — Awaiting simulation data…');

  poll();
  setInterval(poll, 3000);

  navigateTo('screen-home');
});
