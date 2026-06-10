/* ═══════════════════════════════════════════════════════════
   simulate.js  ·  AEIS Attack Simulator
   Parameter-driven continuous detection loop
   ═══════════════════════════════════════════════════════════ */

const SERVER = 'http://localhost:5000';

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// ── State ─────────────────────────────────────────────────
let selectedDevice = 'cam1';
let simInterval    = null;
let simTimeLeft    = 0;
let iterCount      = 0;
let isRunning      = false;

// ── Preset definitions ────────────────────────────────────
const PRESETS = {
  normal:  { packets: 6000,  size: 1200,  dest: 2,  hour: 14,  label: '▶ Normal' },
  ddos:    { packets: 15000, size: 400,   dest: 2,  hour: 3,   label: '⚡ DDoS' },
  scan:    { packets: 800,   size: 80,    dest: 18, hour: 2,   label: '⬡ Port Scan' },
  exfil:   { packets: 400,   size: 1460,  dest: 2,  hour: 4,   label: '📤 Exfiltration' },
  timing:  { packets: 5000,  size: 500,   dest: 2,  hour: 3,   label: '⏱ Off-Hours' },
  extreme: { packets: 19000, size: 1480,  dest: 22, hour: 1,   label: '☠ Extreme' },
};

// ── Threshold classification helper ──────────────────────
// Must mirror server.py _run_ml() exactly
function classifyLocally(packets, size, dest) {
  if (packets > 12000 || size < 600 || dest > 10)      return 'QUARANTINED';
  if (packets > 9000  || size > 1350 || dest > 5)      return 'SUSPICIOUS';
  return 'NORMAL';
}

function threatFor(status) {
  return status === 'QUARANTINED' ? 'HIGH' : status === 'SUSPICIOUS' ? 'MEDIUM' : 'LOW';
}

// ── Clock ─────────────────────────────────────────────────
function tickClock() {
  const now  = new Date();
  const dd   = String(now.getDate()).padStart(2,'0');
  const mmm  = MONTHS[now.getMonth()];
  const yyyy = now.getFullYear();
  const hh   = String(now.getHours()).padStart(2,'0');
  const mm   = String(now.getMinutes()).padStart(2,'0');
  const ss   = String(now.getSeconds()).padStart(2,'0');
  const el   = document.getElementById('clock');
  if (el) el.textContent = `${dd} ${mmm} ${yyyy}  |  ${hh}:${mm}:${ss}`;
}

// ── Server status ─────────────────────────────────────────
async function checkServer() {
  const dot = document.getElementById('srvDot');
  const lbl = document.getElementById('srvStatus');
  try {
    const r = await fetch(`${SERVER}/status?_=${Date.now()}`);
    const d = await r.json();
    if (d.server_connected) {
      dot.className     = 'srv-dot online';
      lbl.textContent   = 'CONNECTED';
      lbl.style.color   = 'var(--green)';
      return true;
    }
  } catch (_) {}
  dot.className   = 'srv-dot offline';
  lbl.textContent = 'OFFLINE';
  lbl.style.color = 'var(--red)';
  return false;
}

// ── Read current parameter values ─────────────────────────
function readFeatures() {
  return {
    packets_per_window: parseInt(document.getElementById('in-packets').value)  || 0,
    avg_packet_size:    parseFloat(document.getElementById('in-size').value)   || 0,
    dest_count:         parseInt(document.getElementById('in-dest').value)     || 1,
    activity_hour:      parseInt(document.getElementById('in-hour').value)     || 0,
  };
}

// ── Update badge for a single parameter ───────────────────
function updateBadge(id, status) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = status;
  el.className   = `param-badge ${status === 'NORMAL' ? '' : status}`;
}

function updateParamRow(rowId, status) {
  const row = document.getElementById(rowId);
  if (!row) return;
  row.classList.toggle('state-suspicious',  status === 'SUSPICIOUS');
  row.classList.toggle('state-quarantined', status === 'QUARANTINED');
}

// ── Live param badges + expected classification ───────────
function refreshParamUI() {
  const pkts = parseInt(document.getElementById('in-packets').value) || 0;
  const size = parseFloat(document.getElementById('in-size').value)  || 0;
  const dest = parseInt(document.getElementById('in-dest').value)    || 1;
  const hour = parseInt(document.getElementById('in-hour').value)    || 0;

  const pktSt  = pkts > 12000 ? 'QUARANTINED' : pkts > 8000  ? 'SUSPICIOUS' : 'NORMAL';
  const sizeSt = size > 1450  ? 'QUARANTINED' : size > 1350  ? 'SUSPICIOUS' : 'NORMAL';
  const dstSt  = dest > 10   ? 'QUARANTINED' : dest > 5     ? 'SUSPICIOUS' : 'NORMAL';
  const hourLbl = (hour >= 0 && hour <= 6) ? 'OFF-HOURS' : 'NORMAL';

  updateBadge('badge-packets', pktSt);
  updateBadge('badge-size',    sizeSt);
  updateBadge('badge-dest',    dstSt);

  const hBadge = document.getElementById('badge-hour');
  if (hBadge) {
    hBadge.textContent = hourLbl;
    hBadge.className   = hourLbl === 'OFF-HOURS'
      ? 'param-badge SUSPICIOUS' : 'param-badge badge-info';
  }

  updateParamRow('row-packets', pktSt);
  updateParamRow('row-size',    sizeSt);
  updateParamRow('row-dest',    dstSt);

  const overall = classifyLocally(pkts, size, dest);
  const expBadge  = document.getElementById('exp-badge');
  const expThreat = document.getElementById('exp-threat');
  if (expBadge) { expBadge.textContent = overall; expBadge.className = `exp-badge ${overall}`; }
  if (expThreat) {
    expThreat.textContent = { NORMAL: 'LOW RISK', SUSPICIOUS: 'MEDIUM RISK', QUARANTINED: 'HIGH RISK' }[overall] || '';
    expThreat.style.color = { NORMAL: 'var(--green)', SUSPICIOUS: 'var(--amber)', QUARANTINED: 'var(--red)' }[overall] || '';
  }
}

// ── Sync slider ↔ number input ────────────────────────────
function bindSlider(sliderId, numId, onChangeFn) {
  const slider = document.getElementById(sliderId);
  const num    = document.getElementById(numId);
  if (!slider || !num) return;

  slider.addEventListener('input', () => {
    num.value = slider.value;
    if (onChangeFn) onChangeFn();
  });
  num.addEventListener('input', () => {
    slider.value = num.value;
    if (onChangeFn) onChangeFn();
  });
}

function bindDuration() {
  const sl  = document.getElementById('sl-duration');
  const num = document.getElementById('in-duration');
  const lbl = document.getElementById('dur-val');
  if (!sl || !num) return;
  const sync = () => { if (lbl) lbl.textContent = sl.value; num.value = sl.value; };
  sl.addEventListener('input',  () => { num.value  = sl.value;  sync(); });
  num.addEventListener('input', () => { sl.value   = num.value; sync(); });
}

// ── Device tabs ───────────────────────────────────────────
function setupDeviceTabs() {
  document.querySelectorAll('.dev-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.dev-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedDevice = btn.dataset.dev;
    });
  });
}

// ── Presets ───────────────────────────────────────────────
function setupPresets() {
  document.querySelectorAll('.preset-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      applyPreset(btn.dataset.preset);
    });
  });
}

function applyPreset(key) {
  const p = PRESETS[key];
  if (!p) return;

  const set = (sl, num, val) => {
    const s = document.getElementById(sl);
    const n = document.getElementById(num);
    if (s) s.value = val;
    if (n) n.value = val;
  };

  set('sl-packets', 'in-packets', p.packets);
  set('sl-size',    'in-size',    p.size);
  set('sl-dest',    'in-dest',    p.dest);
  set('sl-hour',    'in-hour',    p.hour);

  refreshParamUI();
}

// ── Threat bar ────────────────────────────────────────────
const THREAT_CFG = {
  LOW:    { col: 'var(--green)', n: 1 },
  MEDIUM: { col: 'var(--amber)', n: 2 },
  HIGH:   { col: 'var(--red)',   n: 3 },
  NONE:   { col: 'var(--text-mute)', n: 0 },
};

function setThreat(level) {
  const cfg = THREAT_CFG[level] || THREAT_CFG.LOW;
  const tt  = document.getElementById('threatText');
  if (tt) { tt.textContent = level; tt.style.color = cfg.col; }
  for (let i = 1; i <= 3; i++) {
    const seg = document.getElementById('ts' + i);
    if (seg) seg.style.background = i <= cfg.n ? cfg.col : 'var(--panel2)';
  }
}

// ── Update result panel ───────────────────────────────────
function applyResult(data, features) {
  const status = data.status || 'NORMAL';
  const threat = data.threat || 'LOW';

  // Big status badge
  const badge = document.getElementById('rStatus');
  if (badge) { badge.textContent = status; badge.className = `rs-badge ${status}`; }

  // Threat bar
  setThreat(threat);

  // ML scores
  setText('rRfProb',   data.rf_prob  != null ? data.rf_prob.toFixed(4)  : '—');
  setText('rIsoScore', data.iso_score != null ? data.iso_score.toFixed(4) : '—');

  // Target device
  const devMap = { cam1: 'CAM 1', cam2: 'CAM 2', both: 'BOTH' };
  setText('rDevice', devMap[selectedDevice] || selectedDevice.toUpperCase());

  // Sent features
  if (features) {
    setText('fPackets', features.packets_per_window);
    setText('fSize',    features.avg_packet_size + ' B');
    setText('fDest',    features.dest_count);
    setText('fHour',    features.activity_hour);
  }
}

// ── Log helpers ───────────────────────────────────────────
function addLog(status, msg) {
  const list = document.getElementById('logList');
  if (!list) return;
  const t  = new Date().toLocaleTimeString('en-GB');
  const li = document.createElement('li');
  li.className = `log-item ${status}`;
  li.innerHTML = `<span class="log-time">${t}</span><span>${msg}</span>`;
  list.prepend(li);
  while (list.children.length > 60) list.removeChild(list.lastChild);
}

function addHistory(status, pkts, size, dest, device) {
  const list = document.getElementById('historyList');
  if (!list) return;
  const empty = list.querySelector('.hist-empty');
  if (empty) empty.remove();

  const t  = new Date().toLocaleTimeString('en-GB');
  const li = document.createElement('li');
  li.className = `hist-item ${status}`;
  li.innerHTML =
    `<span class="hist-time">${t}</span>` +
    `<span class="hist-badge ${status}">${status}</span>` +
    `<span>[${device.toUpperCase()}] pkts=${pkts} size=${size}B dest=${dest}</span>`;
  list.prepend(li);
  while (list.children.length > 50) list.removeChild(list.lastChild);
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ── Send one detection pulse ──────────────────────────────
async function sendDetection(features, deviceId) {
  const r = await fetch(`${SERVER}/simulate`, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ device_id: deviceId, features }),
  });
  return r.json();
}

// ── Send to both cameras ──────────────────────────────────
async function sendToBoth(features) {
  const [r1, r2] = await Promise.all([
    sendDetection(features, 'cam1'),
    sendDetection(features, 'cam2'),
  ]);
  return r1; // return cam1 result for display
}

// ── Run/Stop ──────────────────────────────────────────────
async function startSimulation() {
  if (isRunning) return;

  const ok = await checkServer();
  if (!ok) {
    addLog('QUARANTINED', '⚠ Server offline — start the Flask server first');
    return;
  }

  const features  = readFeatures();
  const duration  = parseInt(document.getElementById('in-duration').value) || 30;
  const INTERVAL  = 2500; // ms between each detection

  isRunning    = true;
  simTimeLeft  = duration;
  iterCount    = 0;

  // UI: running state
  const runBtn  = document.getElementById('runBtn');
  const stopBtn = document.getElementById('stopBtn');
  if (runBtn)  { runBtn.textContent = '⏳ Running…'; runBtn.disabled = true; runBtn.classList.add('running'); }
  if (stopBtn) { stopBtn.disabled = false; }
  const pulse = document.getElementById('logPulse');
  if (pulse) pulse.classList.add('active');

  setText('timerVal', simTimeLeft + 's');
  setText('iterVal',  '0');

  // Helper: fire one pulse, update UI
  async function pulse_() {
    try {
      let data;
      if (selectedDevice === 'both') {
        data = await sendToBoth(features);
      } else {
        data = await sendDetection(features, selectedDevice);
      }

      if (!data.ok) {
        addLog('QUARANTINED', `❌ Server error: ${data.error || 'unknown'}`);
        return;
      }

      iterCount++;
      setText('iterVal', iterCount);
      applyResult(data, features);

      const status = data.status || 'NORMAL';
      const icons  = { NORMAL: '🟢', SUSPICIOUS: '🟡', QUARANTINED: '🔴' };
      addLog(status,
        `${icons[status] || '●'} ${status}  |  RF=${data.rf_prob?.toFixed(3)}  ISO=${data.iso_score?.toFixed(3)}  ` +
        `pkts=${features.packets_per_window} size=${features.avg_packet_size}B dest=${features.dest_count}`);

      if (status === 'QUARANTINED' || iterCount === 1) {
        addHistory(status, features.packets_per_window, features.avg_packet_size, features.dest_count, selectedDevice);
      }
    } catch (e) {
      addLog('QUARANTINED', `⚠ Network error: ${e.message}`);
    }
  }

  // Fire immediately
  await pulse_();

  // Continuous loop
  simInterval = setInterval(async () => {
    simTimeLeft -= Math.round(INTERVAL / 1000);
    if (simTimeLeft <= 0) {
      stopSimulation('✅ Simulation complete');
      return;
    }
    setText('timerVal', simTimeLeft + 's');
    await pulse_();
  }, INTERVAL);
}

function stopSimulation(reason) {
  if (simInterval) { clearInterval(simInterval); simInterval = null; }
  isRunning = false;

  const runBtn  = document.getElementById('runBtn');
  const stopBtn = document.getElementById('stopBtn');
  if (runBtn)  { runBtn.textContent = '⚡ Start Simulation'; runBtn.disabled = false; runBtn.classList.remove('running'); }
  if (stopBtn) { stopBtn.disabled = true; }

  const pulse = document.getElementById('logPulse');
  if (pulse) pulse.classList.remove('active');

  setText('timerVal', '—');
  if (reason) addLog('NORMAL', reason);
}

// ── Real capture helpers ──────────────────────────────────
let captureRunning = false;

async function apiStartCapture() {
  const ip  = (document.getElementById('realDeviceIp')?.value  || '').trim() || null;
  const win = parseInt(document.getElementById('realWindowNum')?.value) || 5;
  const ifc = (document.getElementById('realInterface')?.value  || '').trim() || 'Wi-Fi';
  try {
    const r = await fetch(`${SERVER}/start_capture`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ device_ip: ip, window_sec: win, interface: ifc }),
    });
    const d = await r.json();
    if (d.ok && d.started) {
      captureRunning = true;
      setCaptureUI(true);
      addLog('NORMAL', `📡 Real capture started — device=${ip||'ALL'}  window=${win}s`);
      addHistory('NORMAL', '—', '—', '—', 'cam1');
    } else {
      addLog('QUARANTINED', `⚠ Capture failed — ${d.scapy_ok === false ? 'Scapy not installed' : 'already running or permission error'}`);
    }
  } catch(e) { addLog('QUARANTINED', `Capture error: ${e.message}`); }
}

async function apiStopCapture() {
  try {
    await fetch(`${SERVER}/stop_capture`, { method: 'POST' });
    captureRunning = false;
    setCaptureUI(false);
    addLog('NORMAL', '⏹ Real capture stopped');
  } catch(e) { addLog('QUARANTINED', `Stop error: ${e.message}`); }
}

function setCaptureUI(running) {
  const dot  = document.getElementById('csDot');
  const txt  = document.getElementById('csText');
  const sBtn = document.getElementById('realStartBtn');
  const xBtn = document.getElementById('realStopBtn');
  if (dot)  { dot.className  = running ? 'cs-dot active' : 'cs-dot'; }
  if (txt)  { txt.textContent = running ? 'Capture running — feeding ML pipeline…' : 'Capture stopped'; }
  if (sBtn) { sBtn.disabled = running; }
  if (xBtn) { xBtn.disabled = !running; }
}

// ── Mode toggle ───────────────────────────────────────────
let currentMode = 'synthetic';

function switchMode(mode) {
  currentMode = mode;
  document.querySelectorAll('.mode-tab').forEach(t => t.classList.toggle('active', t.dataset.mode === mode));
  const synth = document.getElementById('syntheticControls');
  const real  = document.getElementById('realControls');
  const desc  = document.getElementById('modeDesc');
  if (mode === 'synthetic') {
    if (synth) synth.style.display = '';
    if (real)  real.style.display  = 'none';
    if (desc)  desc.textContent = 'Synthetic mode — controlled parameter testing. No real network packets.';
    // Stop capture if switching away
    if (captureRunning) apiStopCapture();
  } else {
    if (synth) synth.style.display = 'none';
    if (real)  real.style.display  = '';
    if (desc)  desc.textContent = 'Real Traffic mode — Scapy captures live packets and feeds the ML pipeline.';
    // Stop simulation if switching away
    if (isRunning) stopSimulation('Mode switched to Real Traffic');
  }
}

// ── Boot ──────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  tickClock();
  setInterval(tickClock, 1000);

  setupDeviceTabs();
  setupPresets();

  // Bind sliders ↔ inputs
  bindSlider('sl-packets', 'in-packets', refreshParamUI);
  bindSlider('sl-size',    'in-size',    refreshParamUI);
  bindSlider('sl-dest',    'in-dest',    refreshParamUI);
  bindSlider('sl-hour',    'in-hour',    refreshParamUI);
  bindDuration();

  // Real window slider
  const rwSl  = document.getElementById('realWindowSl');
  const rwNum = document.getElementById('realWindowNum');
  const ribW  = document.getElementById('ribWindow');
  if (rwSl && rwNum) {
    const syncRW = () => { rwNum.value = rwSl.value; if (ribW) ribW.textContent = rwSl.value; };
    rwSl.addEventListener('input', () => { rwNum.value = rwSl.value; syncRW(); });
    rwNum.addEventListener('input',() => { rwSl.value  = rwNum.value; syncRW(); });
  }

  // Initial render
  refreshParamUI();

  // Synthetic buttons
  document.getElementById('runBtn')?.addEventListener('click',  startSimulation);
  document.getElementById('stopBtn')?.addEventListener('click', () => stopSimulation('⏹ Stopped by user'));

  // Real capture buttons
  document.getElementById('realStartBtn')?.addEventListener('click', apiStartCapture);
  document.getElementById('realStopBtn')?.addEventListener('click',  apiStopCapture);

  // Mode tabs
  document.querySelectorAll('.mode-tab').forEach(btn => {
    btn.addEventListener('click', () => switchMode(btn.dataset.mode));
  });

  // Normal preset selected on load
  document.getElementById('preset-normal')?.classList.add('selected');

  // Server health
  checkServer();
  setInterval(checkServer, 5000);
});

