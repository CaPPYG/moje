#!/usr/bin/env python3
"""Solar monitor web server (Flask + Gunicorn).

- Prijima data z ESP (batéria) cez POST /api/esp/battery
- Taha data z vendor platformy (panely + siet) cez collector
- Ridi idle/aktívny rezim podla prítomnosti prehliadaca
"""
import json
import logging
import os
import threading
import time
from datetime import datetime

from flask import Flask, jsonify, render_template, request

import db
from collector import VendorCollector
from config import load_config

BASE = os.path.dirname(os.path.abspath(__file__))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("solar")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

cfg = load_config()
db.init()

collector = VendorCollector(cfg)

_lock = threading.Lock()
_fetch_lock = threading.Lock()
_state = {
    "snapshot": {
        "ts": None,
        "connected": False,
        "battery": None,
        "solar": None,
    },
    "last_heartbeat": 0.0,
    "history_esp": [],
    "history_vendor": [],
    "last_esp": None,
    "last_vendor": None,
    "next_vendor_at": None,
}
_MAX_POINTS = int(cfg.get("history", {}).get("max_points", 500))
_IDLE_AFTER = float(cfg.get("polling", {}).get("idle_after_seconds", 20))
_ACTIVE_INT = float(cfg.get("polling", {}).get("active_interval", 15))
_IDLE_INT = float(cfg.get("polling", {}).get("idle_interval", 300))


def now() -> float:
    return time.time()


def is_active() -> bool:
    return (now() - _state["last_heartbeat"]) < _IDLE_AFTER


def _is_num(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False
def validate_esp(data: dict) -> tuple[dict | None, str | None]:
    """Validuje JSON z ESP. Vrati (normalizovany dict | None, chyba | None)."""
    if not isinstance(data, dict):
        return None, "Body musi byt JSON objekt"

    out = {}
    for k in _FLOAT_FIELDS:
        if k in data:
            try:
                out[k] = float(data[k])
            except (TypeError, ValueError):
                out[k] = None
    for k in _BOOL_FIELDS:
        if k in data:
            v = data[k]
            out[k] = bool(v) if isinstance(v, bool) else v
    for k in _INT_FIELDS:
        if k in data:
            try:
                out[k] = int(data[k])
            except (TypeError, ValueError):
                out[k] = None

    if "cells" in data:
        cells = data["cells"]
        if isinstance(cells, list):
            out["cells"] = [float(c) for c in cells if _is_num(c)]
        else:
            out["cells"] = []

    for k in ("voltage", "current", "power", "soc"):
        if k not in out or out[k] is None:
            return None, f"Chyba povinne pole: {k}"
    return out, None


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    with _lock:
        _state["last_heartbeat"] = now()
    return jsonify({"ok": True})


@app.route("/api/esp/battery", methods=["POST"])
def esp_battery():
    key = cfg.get("esp", {}).get("api_key", "")
    if key:
        got = request.headers.get("X-API-Key", "")
        if got != key:
            return jsonify({"status": "error", "message": "forbidden"}), 403

    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"status": "error", "message": "invalid json"}), 400

    clean, err = validate_esp(data)
    if err:
        return jsonify({"status": "error", "message": err}), 400

    with _lock:
        _state["snapshot"]["battery"] = clean
        _state["snapshot"]["ts"] = datetime.now().isoformat()
        _state["snapshot"]["connected"] = True
        _state["last_esp"] = datetime.now().isoformat()
        _state["history_esp"].append({
            "ts": _state["snapshot"]["ts"],
            "soc": clean.get("soc"),
            "power": clean.get("power"),
            "current": clean.get("current"),
            "voltage": clean.get("voltage"),
        })
        _state["history_esp"] = _state["history_esp"][-_MAX_POINTS:]

    db.save("esp", clean)

    interval = cfg["esp"]["interval_active"] if is_active() else cfg["esp"]["interval_idle"]
    return jsonify({"status": "ok", "interval": int(interval)})



_FLOAT_FIELDS = (
    "voltage", "current", "power", "soc", "soh",
    "remaining_capacity_ah", "nominal_capacity_ah", "cycle_count",
    "temp_mos", "temp_1", "temp_2", "balance_current",
)
_BOOL_FIELDS = ("charge_mosfet", "discharge_mosfet")
_INT_FIELDS = ("balancing_action", "errors_bitmask")

@app.route("/api/status")
def api_status():
    with _lock:
        snap = dict(_state["snapshot"])
        hist = _state["history_esp"][-96:] + _state["history_vendor"][-96:]
        last_esp = _state["last_esp"]
        last_vendor = _state["last_vendor"]
        nv = _state.get("next_vendor_at")
    next_vendor_in = max(0, int(round(nv - now()))) if nv is not None else None
    return jsonify({
        "data": snap,
        "active": is_active(),
        "last_esp": last_esp,
        "last_vendor": last_vendor,
        "next_vendor_in": next_vendor_in,
        "history": hist,
    })


@app.route("/api/history")
def api_history():
    with _lock:
        esp = _state["history_esp"][-96:]
        vendor = _state["history_vendor"][-96:]
    return jsonify({"esp": esp, "vendor": vendor})


@app.route("/api/health")
def api_health():
    with _lock:
        connected = bool(_state["snapshot"].get("connected"))
        last_esp = _state["last_esp"]
        last_vendor = _state["last_vendor"]
    return jsonify({"ok": connected, "active": is_active(), "last_esp": last_esp, "last_vendor": last_vendor})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    """Vynúti okamžitý vendor fetch (na testovanie / manuálne obnovenie)."""
    if not collector.enabled:
        return jsonify({"ok": True, "refreshed": False, "reason": "vendor disabled"})
    with _fetch_lock:
        data = collector.fetch()
    if data is None:
        return jsonify({"ok": True, "refreshed": False})
    nows = datetime.now().isoformat()
    with _lock:
        _state["snapshot"]["solar"] = data
        _state["snapshot"]["ts"] = nows
        _state["last_vendor"] = nows
        _state["history_vendor"].append({"ts": nows, "pv": _extract_pv(data)})
        _state["history_vendor"] = _state["history_vendor"][-_MAX_POINTS:]
    db.save("vendor", data)
    return jsonify({"ok": True, "refreshed": True})


def vendor_loop():
    if not collector.enabled:
        log.info("Vendor collector vypnuty (vendor.enabled=false)")
        return
    while True:
        with _fetch_lock:
            data = collector.fetch()
        if data is not None:
            with _lock:
                _state["snapshot"]["solar"] = data
                _state["snapshot"]["ts"] = datetime.now().isoformat()
                _state["last_vendor"] = datetime.now().isoformat()
                _state["history_vendor"].append({
                    "ts": _state["last_vendor"],
                    "pv": _extract_pv(data),
                })
                _state["history_vendor"] = _state["history_vendor"][-_MAX_POINTS:]
            db.save("vendor", data)
        interval = _ACTIVE_INT if is_active() else _IDLE_INT
        with _lock:
            _state["next_vendor_at"] = time.time() + interval
        time.sleep(interval)


def _extract_pv(data) -> float | None:
    if isinstance(data, dict):
        raw = data.get("raw") if isinstance(data.get("raw"), dict) else data
        for k in ("pv_total_power", "pvPower", "pv", "solarPower", "totalPower"):
            if k in raw and _is_num(raw[k]):
                try:
                    return float(raw[k])
                except (TypeError, ValueError):
                    return None
    return None


def pruner_loop():
    while True:
        time.sleep(3600)
        try:
            db.prune(days=30)
        except Exception as e:  # noqa: BLE001
            log.error("prune chyba: %s", e)


_THREADS_STARTED = False


def start_threads():
    global _THREADS_STARTED
    if _THREADS_STARTED:
        return
    _THREADS_STARTED = True
    threading.Thread(target=vendor_loop, daemon=True).start()
    threading.Thread(target=pruner_loop, daemon=True).start()
    log.info("Background threads started")


start_threads()


if __name__ == "__main__":
    start_threads()
    web = cfg.get("web", {})
    host = web.get("host", "0.0.0.0")
    port = int(web.get("port", 8000))
    print(f"Solar monitor: http://{web.get('public_url') or '127.0.0.1'}")
    app.run(host=host, port=port, debug=False, threaded=True)
