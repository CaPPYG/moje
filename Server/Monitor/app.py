import os
import sys
import time
from datetime import datetime, timezone
from flask import Flask, jsonify, request

app = Flask(__name__)

try:
    import psutil
    # Inicializačný hovor pre cpu_percent, aby subsequentné hovory vrátili správnu hodnotu
    psutil.cpu_percent(interval=None)
except ImportError:
    psutil = None

BOOT_TIME = time.time() if not psutil else psutil.boot_time()


# Globálny stav pre výpočet okamžitej prenosovej rýchlosti (delta bytes / delta time)
_last_net_state = {
    "time": 0.0,
    "bytes_sent": 0,
    "bytes_recv": 0,
    "rate_out": 0.0,
    "rate_in": 0.0,
}


def format_speed(bytes_per_sec):
    """Sformátuje bajty za sekundu na čitateľnú rýchlosť (B/s, KB/s, MB/s)."""
    if bytes_per_sec < 1024:
        return f"{int(bytes_per_sec)} B/s"
    elif bytes_per_sec < 1024 * 1024:
        return f"{bytes_per_sec / 1024:.1f} KB/s"
    elif bytes_per_sec < 1024 * 1024 * 1024:
        return f"{bytes_per_sec / (1024 * 1024):.2f} MB/s"
    return f"{bytes_per_sec / (1024 * 1024 * 1024):.2f} GB/s"


def format_uptime(seconds):
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def get_network_io():
    """Získa sieťové I/O výhradne z externých rozhraní (vynechá loopback 'lo')."""
    if not psutil:
        return {"bytes_sent": 125829120, "bytes_recv": 245366784}

    try:
        per_nic = psutil.net_io_counters(pernic=True)
        # Hľadáme ens4, eth0 alebo rozhranie, ktoré nie je loopback
        sent = 0
        recv = 0
        found_external = False
        for nic_name, stats in per_nic.items():
            if nic_name.lower() in ("lo", "loopback"):
                continue
            sent += stats.bytes_sent
            recv += stats.bytes_recv
            found_external = True

        if found_external:
            return {"bytes_sent": sent, "bytes_recv": recv}

        # Fallback na globálne počítadlo
        total = psutil.net_io_counters()
        return {"bytes_sent": total.bytes_sent, "bytes_recv": total.bytes_recv}
    except Exception:
        return {"bytes_sent": 0, "bytes_recv": 0}


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/api/system-status", methods=["GET"])
def system_status():
    global _last_net_state
    now = time.time()
    uptime_sec = int(now - BOOT_TIME)

    if not psutil:
        # Graceful fallback pre lokálne testovanie bez knižnice psutil
        return jsonify({
            "status": "ok",
            "online": True,
            "mock": True,
            "cpu": {
                "percent": 12.5,
                "cores": 2
            },
            "memory": {
                "total_gb": 1.0,
                "used_gb": 0.45,
                "percent": 45.0
            },
            "disk": {
                "total_gb": 30.0,
                "used_gb": 8.5,
                "percent": 28.3
            },
            "network": {
                "bytes_sent": 125829120,
                "bytes_recv": 245366784,
                "egress_mb": 120.0,
                "egress_gb": 0.12,
                "ingress_mb": 234.0,
                "ingress_gb": 0.23,
                "rate_out_bps": 12500.0,
                "rate_in_bps": 45200.0,
                "rate_out_human": "12.2 KB/s",
                "rate_in_human": "44.1 KB/s",
                "rate_summary": "↑ 12.2 KB/s | ↓ 44.1 KB/s"
            },
            "uptime": {
                "seconds": uptime_sec,
                "human": format_uptime(uptime_sec)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    # CPU
    cpu_percent = psutil.cpu_percent(interval=None)
    cpu_cores = psutil.cpu_count(logical=True) or 1

    # RAM
    vmem = psutil.virtual_memory()
    mem_total_gb = round(vmem.total / (1024 ** 3), 2)
    mem_used_gb = round(vmem.used / (1024 ** 3), 2)
    mem_percent = round(vmem.percent, 1)

    # Disk (koreňový oddiel)
    disk_path = "/" if os.name != "nt" else "C:\\"
    try:
        disk = psutil.disk_usage(disk_path)
        disk_total_gb = round(disk.total / (1024 ** 3), 1)
        disk_used_gb = round(disk.used / (1024 ** 3), 1)
        disk_percent = round(disk.percent, 1)
    except Exception:
        disk_total_gb = 0.0
        disk_used_gb = 0.0
        disk_percent = 0.0

    # Sieť (Network I/O)
    net_data = get_network_io()
    bytes_sent = net_data["bytes_sent"]
    bytes_recv = net_data["bytes_recv"]

    # Výpočet okamžitej prenosovej rýchlosti
    dt = now - _last_net_state["time"] if _last_net_state["time"] > 0 else 0
    if dt >= 0.5:
        d_sent = max(0, bytes_sent - _last_net_state["bytes_sent"])
        d_recv = max(0, bytes_recv - _last_net_state["bytes_recv"])
        rate_out = d_sent / dt
        rate_in = d_recv / dt
        _last_net_state["time"] = now
        _last_net_state["bytes_sent"] = bytes_sent
        _last_net_state["bytes_recv"] = bytes_recv
        _last_net_state["rate_out"] = rate_out
        _last_net_state["rate_in"] = rate_in
    elif _last_net_state["time"] == 0:
        _last_net_state["time"] = now
        _last_net_state["bytes_sent"] = bytes_sent
        _last_net_state["bytes_recv"] = bytes_recv
        rate_out = 0.0
        rate_in = 0.0
    else:
        rate_out = _last_net_state.get("rate_out", 0.0)
        rate_in = _last_net_state.get("rate_in", 0.0)

    rate_out_human = format_speed(rate_out)
    rate_in_human = format_speed(rate_in)
    rate_summary = f"↑ {rate_out_human} | ↓ {rate_in_human}"

    egress_mb = round(bytes_sent / (1024 ** 2), 1)
    egress_gb = round(bytes_sent / (1024 ** 3), 2)
    ingress_mb = round(bytes_recv / (1024 ** 2), 1)
    ingress_gb = round(bytes_recv / (1024 ** 3), 2)

    return jsonify({
        "status": "ok",
        "online": True,
        "mock": False,
        "cpu": {
            "percent": round(cpu_percent, 1),
            "cores": cpu_cores
        },
        "memory": {
            "total_gb": mem_total_gb,
            "used_gb": mem_used_gb,
            "percent": mem_percent
        },
        "disk": {
            "total_gb": disk_total_gb,
            "used_gb": disk_used_gb,
            "percent": disk_percent
        },
        "network": {
            "bytes_sent": bytes_sent,
            "bytes_recv": bytes_recv,
            "egress_mb": egress_mb,
            "egress_gb": egress_gb,
            "ingress_mb": ingress_mb,
            "ingress_gb": ingress_gb,
            "rate_out_bps": round(rate_out, 1),
            "rate_in_bps": round(rate_in, 1),
            "rate_out_human": rate_out_human,
            "rate_in_human": rate_in_human,
            "rate_summary": rate_summary
        },
        "uptime": {
            "seconds": uptime_sec,
            "human": format_uptime(uptime_sec)
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "hub-monitor"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("MONITOR_PORT", 5070))
    host = os.environ.get("MONITOR_HOST", "0.0.0.0")
    debug = os.environ.get("MONITOR_DEBUG") == "1"
    print("=" * 55)
    print("  📊 GarcArzP HUB – System & Network Monitor")
    print(f"  Lokálna URL:  http://127.0.0.1:{port}")
    print("  Endpoint:     /api/system-status")
    print("=" * 55)
    app.run(host=host, port=port, debug=debug)
