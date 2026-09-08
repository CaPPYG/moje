// Solar monitor - frontend logika
const API_BASE = "/solar";
const fmt = (v, suffix = "", dec = 1) => {
  if (v === null || v === undefined) return "—";
  const n = typeof v === "number" ? (Math.round(v * 10 ** dec) / 10 ** dec) : v;
  return n + suffix;
};
const fmtPad = (v, suffix = "", dec = 2) => {
  if (v === null || v === undefined) return "—";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return "—";
  return n.toFixed(dec) + suffix;
};
const set = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };
const fmtPower = (w) => {
  if (w == null) return { v: "—", u: "W" };
  const n = Number(w);
  if (Math.abs(n) >= 1000) return { v: fmt(n / 1000, "", 2), u: "kW" };
  return { v: fmt(n, "", 0), u: "W" };
};

const badge = (el, cls, txt) => { el.textContent = txt; el.className = "badge " + cls; };

// ---------- hodiny ----------
function tickClock() {
  const el = document.getElementById("clock");
  if (el) el.textContent = new Date().toLocaleTimeString();
}
setInterval(tickClock, 1000); tickClock();

// ---------- SOC gauge ----------
const lerp = (a, b, t) => Math.round(a + (b - a) * t);
const hexRGB = (h) => { const n = parseInt(h.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; };
const mixCol = (c1, c2, t) => { const a = hexRGB(c1), b = hexRGB(c2); return `rgb(${lerp(a[0], b[0], t)}, ${lerp(a[1], b[1], t)}, ${lerp(a[2], b[2], t)})`; };
const socColor = (soc) => soc >= 50 ? mixCol("#34e39b", "#ffb020", (100 - soc) / 50) : mixCol("#ffb020", "#ff5c72", (50 - soc) / 50);
function updateGauge(soc) {
  const bar = document.getElementById("soc-bar");
  if (!bar || soc == null) return;
  const r = 52, C = 2 * Math.PI * r;
  bar.style.strokeDasharray = C;
  bar.style.strokeDashoffset = C * (1 - clamp(soc, 0, 100) / 100);
  bar.style.stroke = socColor(clamp(soc, 0, 100));
}
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

// ---------- články (cells) ----------
function renderCells(cells) {
  const box = document.getElementById("cells");
  if (!box) return;
  if (!Array.isArray(cells) || !cells.length) {
    box.innerHTML = "<div class='cell-battery-pod'><span class='c-name'>—</span><span class='c-volt num-font'>—</span><div class='cell-tank'><div class='cell-tank-fill' style='height:0%'></div></div><span class='c-bolt'>⚡</span></div>";
    set("cell-range", "—");
    return;
  }
  const avg = cells.reduce((a, b) => a + b, 0) / cells.length;
  const min = Math.min(...cells), max = Math.max(...cells);
  set("cell-range", `${(max - min).toFixed(3)} V`);
  const lo = min, span = (max - min) || 1;
  const pct = v => Math.max(38, Math.min(96, 50 + ((v - lo) / span) * 46));
  box.innerHTML = cells.map((v, i) => {
    const cls = (v > avg + 0.01) ? "cell-battery-pod hi" : (v < avg - 0.01) ? "cell-battery-pod low" : "cell-battery-pod";
    return `<div class="${cls}"><span class="c-name">C${String(i + 1).padStart(2, "0")}</span><span class="c-volt num-font">${v.toFixed(3)}</span><div class="cell-tank"><div class="cell-tank-fill" style="height:${pct(v).toFixed(0)}%"></div></div><span class="c-bolt">⚡</span></div>`;
  }).join("");
}

// ---------- graf ----------
function drawChart(history) {
  const canvas = document.getElementById("chart");
  if (!canvas || !history || !history.length) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width = canvas.offsetWidth * 2;
  const h = canvas.height = 300;
  ctx.clearRect(0, 0, w, h);
  const pad = 28;

  const pvPoints = history.filter(p => p && p.pv != null);
  const socPoints = history.filter(p => p && p.soc != null);
  if (pvPoints.length < 2 && socPoints.length < 2) return;

  const maxPv = Math.max(100, ...pvPoints.map(p => Number(p.pv) || 0));
  const draw = (pts, getY, color) => {
    if (pts.length < 2) return;
    ctx.strokeStyle = color; ctx.lineWidth = 2.5; ctx.beginPath();
    pts.forEach((p, i) => {
      const x = pad + (i / (pts.length - 1)) * (w - pad * 2);
      const y = h - pad - getY(p) * (h - pad * 2);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();
  };
  draw(pvPoints, p => (Number(p.pv) || 0) / maxPv, "#ffb020");
  draw(socPoints, p => (Number(p.soc) || 0) / 100, "#34e39b");
}

// ---------- refresh ----------
async function refresh() {
  await post(`${API_BASE}/api/heartbeat`);
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    const json = await res.json();
    const d = json.data || {};
    const b = d.battery || {};
    const s = d.solar || {};

    badge(document.getElementById("status-badge"), (d.esp_online ?? d.connected) ? "online" : "offline", (d.esp_online ?? d.connected) ? "Online" : "Offline");
    badge(document.getElementById("mode-badge"), json.active ? "active" : "idle", json.active ? "live" : "idle");

    // Hero „Panely & Dom" flow hodnoty sa plnia v bloku „Tok energie" nižšie.

    updateGauge(b.soc);
    const socN = Number(b.soc);
    set("bat-soc", (b.soc == null || Number.isNaN(socN) || !isFinite(socN)) ? "—" : (Number.isInteger(socN) ? String(socN) : socN.toFixed(1)));
    set("bat-voltage", fmtPad(b.voltage, " V", 2));
    const bp = document.getElementById("bat-power");
    if (bp) {
      const bpw = b.power;
      if (bpw == null || Number.isNaN(Number(bpw))) { bp.textContent = "—"; bp.className = "stat-power"; }
      else if (Math.abs(bpw) < 0.05) { bp.textContent = "· Kľud"; bp.className = "stat-power idle"; }
      else if (bpw < 0) { bp.textContent = `· ${fmtPad(Math.abs(bpw), " W", 2)} vybíja`; bp.className = "stat-power discharge"; }
      else { bp.textContent = `· ${fmtPad(bpw, " W", 2)} nabíja`; bp.className = "stat-power charge"; }
    }

    set("daily-kwh", fmt(s.daily_kwh, "", 2));
    set("daily-sub", fmt(s.total_kwh, " kWh", 0));

    // nabíjanie
    const chip = document.getElementById("charge-chip");
    if (chip) {
      const cur = b.current;
      chip.textContent = cur == null ? "—" : Math.abs(cur) < 0.05 ? "Kľud" : cur < 0 ? "Vybíja" : "Nabíja";
    }

    set("b-voltage", fmt(b.voltage, " V"));
    set("b-current", fmt(b.current, " A"));
    set("b-power", fmt(b.power, " W"));
    set("b-soh", fmt(b.soh, " %", 0));
    set("b-rem", fmt(b.remaining_capacity_ah, " Ah"));
    set("b-nom", fmt(b.nominal_capacity_ah, " Ah"));
    set("b-cycles", fmt(b.cycle_count, "", 0));
    set("b-tmos", fmt(b.temp_mos, " °C"));
    set("b-t1", fmt(b.temp_1, " °C"));
    set("b-t2", fmt(b.temp_2, " °C"));
    set("b-balcur", fmt(b.balance_current, " A"));
    set("b-balact", b.balancing_action > 0 ? "Aktívne" : "—");
    set("b-chg", b.charge_mosfet === true ? "ON" : (b.charge_mosfet === false ? "OFF" : "—"));
    set("b-dchg", b.discharge_mosfet === true ? "ON" : (b.discharge_mosfet === false ? "OFF" : "—"));
    set("b-err", b.errors_bitmask ? ("0x" + Number(b.errors_bitmask).toString(16).toUpperCase().padStart(4, "0")) : "OK (0x0000)");

    set("pv-detail", fmt(s.pv_total_power ?? null, " W"));
    set("pv-cap", fmt(s.installed_kw, " kW"));
    set("pv-daily", fmt(s.daily_kwh, " kWh"));
    set("pv-monthly", fmt(s.monthly_kwh, " kWh"));
    set("pv-yearly", fmt(s.yearly_kwh, " kWh"));
    set("pv-total", fmt(s.total_kwh, " kWh"));
    set("devices", fmt(s.device_total, "", 0));
    set("vendor-ts", json.last_vendor ? json.last_vendor.replace("T", " ").slice(0, 19) : "—");
    set("pv-status", s.status || "—");
    const invKw = s.inverter_producing_power;
    const invStr = (invKw == null || Number.isNaN(Number(invKw))) ? "—" : (() => { const f = fmtPower(Number(invKw) * 1000); return `${f.v} ${f.u}`; })();
    set("inv-power", invStr);
    set("inv-online", s.inverter_online === true ? "ON" : (s.inverter_online === false ? "OFF" : "—"));
    set("inv-ts", s.inverter_last_data_at ? String(s.inverter_last_data_at).replace("T", " ").slice(0, 19) : "—");
    set("inv-name", s.inverter_name || "—");
    set("inv-state", s.inverter_state || "—");
    set("inv-alarm", s.inverter_is_alarmed === true ? "ÁNO" : (s.inverter_is_alarmed === false ? "nie" : "—"));
    set("inv-daily", s.inverter_daily_kwh == null ? "—" : `${fmtPad(s.inverter_daily_kwh, " kWh", 2)}`);
    set("inv-total", s.inverter_total_kwh == null ? "—" : `${fmtPad(s.inverter_total_kwh, " kWh", 1)}`);

    // Veľký energy hub – tok + dolná lišta (v kW / V, podľa nového designu)
    const pvKW = (s.pv_active_kw != null) ? Number(s.pv_active_kw)
      : (s.pv_power_kw != null) ? Number(s.pv_power_kw)
      : (s.pv_total_power != null) ? Number(s.pv_total_power) / 1000 : null;
    const fkV = (kw) => (kw == null || Number.isNaN(Number(kw))) ? "—" : (() => { const f = fmtPower(Number(kw) * 1000); return `${f.v} ${f.u}`; })();
    const kWn = (kw) => (kw == null || Number.isNaN(Number(kw))) ? "—" : fmt(Number(kw), "", 2);
    const kWs = (kw) => (kw == null || Number.isNaN(Number(kw))) ? "—" : (Number(kw) > 0 ? "+" + fmt(Number(kw), "", 2) : fmt(Number(kw), "", 2));

    set("f-pv-kw", fkV(s.pv_active_kw));
    set("f-load-kw", fkV(s.load_power_kw));
    set("hero-pv-v", fmtPad(s.flow_pvVoltage, " V", 1));
    set("hero-load-v", fmtPad(s.flow_loadVoltage, " V", 1));

    set("hero-pv-w", kWn(pvKW));
    set("hero-load-w", kWn(s.load_power_kw));
    set("b-voltage-mini", fmt(b.voltage, "", 1));
    set("flow-time", s.flow_time_ms ? new Date(Number(s.flow_time_ms)).toLocaleTimeString() : "—");

    // LIVE passthrough (1 s) z vendor API: batéria cez napätie (24-28V -> 0-100%) + vendor %, solár
    const lv = d.live || {};
    const bv = Number(lv.battery_voltage);
    if (Number.isFinite(bv) && bv > 0) {
      const vpct = Math.max(0, Math.min(100, (bv - 24.0) / (28.0 - 24.0) * 100));
      updateGauge(vpct);
      set("bat-soc", String(Math.round(vpct)));
      set("bat-voltage", fmtPad(bv, " V", 1));
      set("b-voltage-mini", fmt(bv, "", 1));
      const vs = Number(lv.battery_soc);
      const vnd = document.getElementById("bat-soc-vendor");
      if (vnd) vnd.textContent = Number.isFinite(vs) ? Math.round(vs) + " %" : "—";
    }
    // Solár + dom z LIVE passthrough (namiesto pomalého / rate-limitovaného vendor flow)
    if (lv.pv_power_w != null) {
      const pvKw = Number(lv.pv_power_w) / 1000;
      set("f-pv-kw", fkV(pvKw));
      set("hero-pv-w", kWn(pvKw));
    }
    if (lv.pv_voltage != null) set("hero-pv-v", fmtPad(lv.pv_voltage, " V", 1));
    if (lv.load_w != null) {
      const loKw = Number(lv.load_w) / 1000;
      set("f-load-kw", fkV(loKw));
      set("hero-load-w", kWn(loKw));
    }
    if (lv.grid_voltage != null) set("hero-load-v", fmtPad(lv.grid_voltage, " V", 1));


    renderCells(b.cells || []);
    drawChart(json.history);

    set("last-update", `Aktualizované: ${(d.ts || "").replace("T", " ").slice(0, 19) || "—"}`);
    set("error-msg", "");
  } catch (e) {
    set("error-msg", "Chyba načítania dát");
  }
}

async function post(url) { try { await fetch(url, { method: "POST" }); } catch (e) {} }

let timer = null, visible = true;
function schedule() { clearInterval(timer); timer = setInterval(() => { if (visible) refresh(); }, 1000); }
document.addEventListener("visibilitychange", () => { visible = !document.hidden; if (visible) { refresh(); schedule(); } });
refresh(); schedule();

const refreshBtn = document.getElementById("refresh-btn");
if (refreshBtn) {
  refreshBtn.addEventListener("click", async () => {
    refreshBtn.disabled = true;
    refreshBtn.classList.add("spinning");
    try {
      await post(`${API_BASE}/api/refresh`);
      await refresh();
    } finally {
      refreshBtn.disabled = false;
      refreshBtn.classList.remove("spinning");
    }
  });
}
