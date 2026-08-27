#!/usr/bin/env python3
"""
CaPPy Tools – Toolbox + Planner v jednom súbore
------------------------------------------------
Záložka 1 – Metadata Cleaner:
  • Drag & drop alebo vyber súboru / priečinka
  • Nastav GPS polohu (mapa, adresa, zoznam miest)
  • Randomizačné filtre (saturácia, kontrast, jas, hue, zoom, denoise...)
  • Vymaže metadáta, zapíše GPS, aplikuje filtre, uloží kópiu

Záložka 2 – Reels Downloader:
  • Zoznam linkov -> stiahne všetky cez yt-dlp

Záložky 3-6 – CaPPy Planner:
  • Nahraj originálne videá, pridaj zariadenia (fingerprint / GPS / model)
  • Vygeneruj rozvrh (1-3 videa/deň, každé zariadenie dostane iné video v ten istý deň)
  • Spusti server -> QR kód per zariadenie -> otvor na mobile a stiahni dnešné videá

Záložka 7 – Drive (Google):
  • Vygenerovaný rozvrh nahraje na Google Drive cez rclone
  • Štruktúra: CaPPy/<názov>/<zariadenie>/<dátum>/<video>.mp4

Potrebné nástroje:
  pip install -U yt-dlp tkinterdnd2 tkintermapview qrcode[pil]
  + ffmpeg a exiftool v PATH
  + rclone (https://rclone.org/downloads/) pre Google Drive upload
"""

import os, re, random, importlib, sys, shutil, subprocess, threading, uuid, datetime, socket, json
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse
import webbrowser

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_AVAILABLE = False

try:
    import tkintermapview
    MAP_AVAILABLE = True
except ImportError:
    MAP_AVAILABLE = False

try:
    import qrcode
    from PIL import Image, ImageTk
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

# ─── Constants ────────────────────────────────────────────────────────────────

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff", ".bmp"}

BG       = "#0e0e1a"
CARD_BG  = "#13131f"
ACCENT   = "#2563eb"
ENTRY_BG = "#1a1a2e"
GREEN    = "#22c55e"
RED      = "#dc2626"

SERVER_PORT = 8765

CITIES = [
    ("Custom (klikni na mapu / zadaj ručne)", None,      None),
    ("Los Angeles, CA",    34.0522,  -118.2437),
    ("New York, NY",       40.7128,   -74.0060),
    ("Chicago, IL",        41.8781,   -87.6298),
    ("Houston, TX",        29.7604,   -95.3698),
    ("Miami, FL",          25.7617,   -80.1918),
    ("Seattle, WA",        47.6062,  -122.3321),
    ("London, UK",         51.5074,    -0.1278),
    ("Paris, France",      48.8566,     2.3522),
    ("Berlin, Germany",    52.5200,    13.4050),
    ("Amsterdam, NL",      52.3676,     4.9041),
    ("Madrid, Spain",      40.4168,    -3.7038),
    ("Rome, Italy",        41.9028,    12.4964),
    ("Dubai, UAE",         25.2048,    55.2708),
    ("Tokyo, Japan",       35.6762,   139.6503),
    ("Seoul, Korea",       37.5665,   127.0008),
    ("Sydney, Australia", -33.8688,   151.2093),
    ("Toronto, Canada",    43.6532,   -79.3832),
    ("São Paulo, Brazil", -23.5505,   -46.6333),
]

# (display name, make, model)  –  None = auto/random
DEVICES = [
    ("Auto (náhodné zariadenie)", None, None),
    ("Apple iPhone 16 Pro",       "Apple",   "iPhone 16 Pro"),
    ("Apple iPhone 15 Pro",       "Apple",   "iPhone 15 Pro"),
    ("Apple iPhone 15",           "Apple",   "iPhone 15"),
    ("Apple iPhone 14 Pro",       "Apple",   "iPhone 14 Pro"),
    ("Apple iPhone 14",           "Apple",   "iPhone 14"),
    ("Apple iPhone 13",           "Apple",   "iPhone 13"),
    ("Apple iPhone 12",           "Apple",   "iPhone 12"),
    ("Samsung Galaxy S25 Ultra",  "Samsung", "SM-S938B"),
    ("Samsung Galaxy S24 Ultra",  "Samsung", "SM-S928B"),
    ("Samsung Galaxy S24",        "Samsung", "SM-S921B"),
    ("Samsung Galaxy S23",        "Samsung", "SM-S911B"),
    ("Samsung Galaxy A55",        "Samsung", "SM-A556B"),
    ("Google Pixel 9 Pro",        "Google",  "Pixel 9 Pro"),
    ("Google Pixel 8 Pro",        "Google",  "Pixel 8 Pro"),
    ("Google Pixel 8",            "Google",  "Pixel 8"),
    ("Google Pixel 7",            "Google",  "Pixel 7"),
    ("OnePlus 12",                "OnePlus", "CPH2573"),
    ("Xiaomi 14 Ultra",           "Xiaomi",  "23UF5D0AD"),
    ("Sony Xperia 1 VI",          "Sony",    "XQ-EC72"),
    ("Huawei P60 Pro",            "Huawei",  "MNA-AL00"),
]

# id, display name, ffmpeg type, eq_param,
# has_range, default_min, default_max, abs_min, abs_max, resolution, fmt, enabled_default
FILTER_DEFS = [
    ("saturation", "Saturation",         "eq",          "saturation",  True,  0.98,  1.02,  0.00,  3.00,  0.010, "{:.2f}x",  True),
    ("contrast",   "Contrast",           "eq",          "contrast",    True,  0.98,  1.02,  0.00,  3.00,  0.010, "{:.2f}x",  True),
    ("brightness", "Brightness",         "eq",          "brightness",  True, -0.010, 0.010, -0.50,  0.50,  0.001, "{:+.3f}",  True),
    ("gamma",      "Gamma",              "eq",          "gamma",       True,  0.98,  1.02,  0.10,  3.00,  0.010, "{:.2f}",   True),
    ("color_temp", "Color Temperature",  "colorbalance", None,         True, -0.020, 0.020, -0.50,  0.50,  0.001, "{:+.3f}",  True),
    ("hue",        "Hue Shift",          "hue",          None,         True, -1.50,  1.50, -30.00, 30.00,  0.500, "{:+.1f}°", True),
    ("zoom",       "Zoom",               "zoom",         None,         True,  1.000, 1.010,  1.000,  1.200,  0.001, "{:.3f}x",  True),
    ("sharpen",    "Sharpen",            "unsharp",      None,         True,  0.40,  0.70,  0.00,  2.00,  0.050, "{:.2f}x",  True),
    ("denoise",    "Denoise (hqdn3d)",   "hqdn3d",       None,         True,  2.0,   4.0,   0.0,  10.0,   0.500, "{:.1f}",   True),
    ("deband",     "Deband",             "deband",       None,         False, 0,     0,     0,     0,     0,     "",         True),
    ("noise",      "Noise (film grain)", "noise",        None,         True,  3.0,   8.0,   0.0,  30.0,   1.000, "{:.0f}",   False),
    ("vignette",   "Vignette",           "vignette",     None,         True,  0.30,  0.60,  0.00,  1.50,  0.050, "{:.2f}",   False),
]

# Default filter state (safe preset) pre Planner spoofing
SAFE_FILTERS = {
    "saturation":  {"enabled": True,  "min": 0.98, "max": 1.02},
    "contrast":    {"enabled": True,  "min": 0.98, "max": 1.02},
    "brightness":  {"enabled": True,  "min":-0.010,"max": 0.010},
    "gamma":       {"enabled": True,  "min": 0.98, "max": 1.02},
    "color_temp":  {"enabled": True,  "min":-0.020,"max": 0.020},
    "hue":         {"enabled": True,  "min":-1.5,  "max": 1.5},
    "zoom":        {"enabled": True,  "min": 1.000,"max": 1.010},
    "sharpen":     {"enabled": True,  "min": 0.40, "max": 0.70},
    "denoise":     {"enabled": True,  "min": 2.0,  "max": 4.0},
    "deband":      {"enabled": True,  "min": 0,    "max": 0},
    "noise":       {"enabled": False, "min": 0,    "max": 0},
    "vignette":    {"enabled": False, "min": 0,    "max": 0},
}

# ── Global server state ───────────────────────────────────────────────────────
_srv = {"schedule": [], "devices": [], "output_dir": "", "videos": [], "server": None}

# ─── UI helpers ───────────────────────────────────────────────────────────────

# Plannerský postup – klikateľné kroky (záložky Videá..Drive)
PLAN_STEPS = [("Videá", "🎞"), ("Zariadenia", "📱"), ("Rozvrh", "⚡"), ("Server", "📶"), ("Drive", "☁")]


class StepBar(tk.Frame):
    """Klikateľný stepper s aktuálnym krokom postupu."""
    def __init__(self, parent, current):
        super().__init__(parent, bg=BG)
        self._nav = None
        tk.Label(self, text="Postup:", bg=BG, fg="#666",
                 font=("Segoe UI", 8)).pack(side="left", padx=(0, 8))
        for i, (label, emoji) in enumerate(PLAN_STEPS):
            active = i == current
            chip = tk.Label(self, text=f"{'●' if active else '○'} {emoji} {label}",
                            bg=ACCENT if active else ENTRY_BG,
                            fg="white" if active else "#8899bb",
                            padx=10, pady=4,
                            font=("Segoe UI", 9, "bold" if active else "normal"),
                            cursor="hand2")
            chip.pack(side="left", padx=(0, 6))
            chip.bind("<Button-1>", lambda e, idx=i: self._go(idx))

    def _go(self, idx):
        if self._nav:
            self._nav(idx)

    def set_nav(self, fn):
        self._nav = fn


def tool_badge(parent, name, ok):
    """Zelená/šedá placka signalizujúca dostupnosť externého nástroja."""
    return tk.Label(parent, text=name,
                    bg=GREEN if ok else "#2a2a3a",
                    fg="#062a14" if ok else "#777",
                    padx=9, pady=3, font=("Segoe UI", 8, "bold"))


def _shade(hex_color, factor):
    """Svetlejšia / tmavšia verzia hex farby pre hover efekt."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
        f = factor
        return (f"#{int(max(0, min(255, r*f))):02x}"
                f"{int(max(0, min(255, g*f))):02x}"
                f"{int(max(0, min(255, b*f))):02x}")
    except Exception:
        return hex_color


def btn(parent, text, command=None, **kw):
    """Jednotné tlačidlo appky – ploché, s hover efektom a kurzorom."""
    bg   = kw.pop("bg", ACCENT)
    fg   = kw.pop("fg", "white")
    padx = kw.pop("padx", 12)
    pady = kw.pop("pady", 8)
    font = kw.pop("font", ("Segoe UI", 9))
    kw.pop("relief", None); kw.pop("bd", None)
    kw.pop("borderwidth", None); kw.pop("highlightthickness", None)
    b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                  relief="flat", bd=0, highlightthickness=0,
                  padx=padx, pady=pady, font=font, cursor="hand2",
                  activebackground=_shade(bg, 1.18), activeforeground=fg, **kw)
    b.bind("<Enter>", lambda e: b.config(bg=_shade(bg, 1.18)))
    b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b
# ─── Core: ffmpeg filter builder ──────────────────────────────────────────────

def build_vf(filter_states):
    """Returns (vf_string | None, needs_reencode bool)"""
    eq_params = {}
    other = []
    needs_reencode = False

    for fid, _, ftype, eq_param, has_range, dmin, dmax, *_ in FILTER_DEFS:
        st = filter_states.get(fid, {})
        if not st.get("enabled", False):
            continue
        needs_reencode = True

        if has_range:
            lo = st.get("min", dmin)
            hi = st.get("max", dmax)
            if lo > hi: lo, hi = hi, lo
            val = random.uniform(lo, hi) if lo != hi else lo
        else:
            val = 0

        if ftype == "eq":
            eq_params[eq_param] = val
        elif ftype == "colorbalance":
            other.append(
                f"colorbalance=rs={val:.4f}:gs=0:bs={-val:.4f}"
                f":rm={val/2:.4f}:gm=0:bm={-val/2:.4f}"
                f":rh={val/4:.4f}:gh=0:bh={-val/4:.4f}"
            )
        elif ftype == "hue":
            other.append(f"hue=h={val:.2f}")
        elif ftype == "zoom" and val > 1.0:
            other.append(f"scale=iw*{val:.4f}:ih*{val:.4f},crop=iw/{val:.4f}:ih/{val:.4f}")
        elif ftype == "unsharp":
            other.append(f"unsharp=lx=5:ly=5:la={val:.3f}:cx=5:cy=5:ca=0")
        elif ftype == "hqdn3d":
            other.append(f"hqdn3d={val:.2f}:{val:.2f}:{val*3:.2f}:{val*3:.2f}")
        elif ftype == "deband":
            other.append("deband")
        elif ftype == "noise":
            other.append(f"noise=alls={val:.0f}:allf=t+u")
        elif ftype == "vignette":
            other.append(f"vignette=a={val:.3f}")

    parts = []
    if eq_params:
        parts.append("eq=" + ":".join(f"{k}={v:.5f}" for k, v in eq_params.items()))
    parts.extend(other)
    vf = ",".join(parts) if parts else None
    return vf, needs_reencode


def check_tool(name):
    return shutil.which(name) is not None


def dms_ref(v, pos, neg):
    return pos if v >= 0 else neg


def apply_fingerprint(out_path, fp, log):
    """Write device fingerprint metadata via exiftool."""
    if not fp.get("enabled"):
        return
    if not check_tool("exiftool"):
        raise RuntimeError("exiftool nie je nájdený v PATH.")
    log("Zapisujem device fingerprint (exiftool)...")

    cmd = ["exiftool", "-overwrite_original"]

    # ── Device make / model ──
    make, model = fp.get("make"), fp.get("model")
    if fp.get("mode") == "random":
        # pick a real device at random (skip index 0 = "Auto")
        _, make, model = random.choice(DEVICES[1:])
    if make and model:
        cmd += [f"-Make={make}", f"-Model={model}",
                f"-DeviceMake={make}", f"-DeviceModel={model}"]

    # ── Creation date ──
    if fp.get("random_date"):
        days = max(1, int(fp.get("days_back", 30)))
        delta = datetime.timedelta(
            days=random.randint(0, days),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
            seconds=random.randint(0, 59),
        )
        dt_str = (datetime.datetime.now() - delta).strftime("%Y:%m:%d %H:%M:%S")
        for tag in ("-CreateDate", "-ModifyDate", "-DateTimeOriginal",
                    "-MediaCreateDate", "-TrackCreateDate",
                    "-MediaModifyDate", "-TrackModifyDate"):
            cmd.append(f"{tag}={dt_str}")

    # ── Random UID ──
    if fp.get("random_uid"):
        uid = uuid.uuid4().hex.upper()
        cmd += [f"-ImageUniqueID={uid}", f"-MediaDataOffset=0"]

    # ── Optional text tags ──
    for tag, key in [("-Title", "title"), ("-Artist", "artist"), ("-Comment", "comment")]:
        val = fp.get(key, "").strip()
        if val:
            cmd.append(f"{tag}={val}")

    cmd.append(out_path)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"exiftool (fingerprint) zlyhal:\n{r.stderr[-1000:]}")
def process_file(src_path, lat, lon, use_location, filter_states, fp_settings, log, out_path=None):
    src_path = os.path.abspath(src_path)
    if not os.path.isfile(src_path):
        raise FileNotFoundError(f"Súbor neexistuje: {src_path}")

    root, ext = os.path.splitext(src_path)
    if out_path is None:
        out_path = f"{root}_clean{ext}"
        c = 1
        while os.path.exists(out_path):
            out_path = f"{root}_clean_{c}{ext}"; c += 1

    ext_lower = ext.lower()
    if ext_lower in VIDEO_EXT:
        if not check_tool("ffmpeg"):
            raise RuntimeError("ffmpeg nie je nájdený v PATH.")
        vf_str, needs_reencode = build_vf(filter_states)
        log("Spracúvam video (ffmpeg)...")
        if vf_str:
            log(f"  Filtre: {vf_str[:120]}")
        no_sig = fp_settings.get("no_ffmpeg_sig", True)
        cmd = ["ffmpeg", "-y", "-i", src_path, "-map_metadata", "-1"]
        if no_sig:
            cmd += ["-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
        if vf_str:
            cmd += ["-vf", vf_str]
        if needs_reencode:
            cmd += ["-c:v", "libx264", "-crf", "18", "-preset", "fast", "-c:a", "copy"]
        else:
            cmd += ["-c", "copy"]
        cmd.append(out_path)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg zlyhal:\n{r.stderr[-2000:]}")

    elif ext_lower in IMAGE_EXT:
        log("Kopírujem obrázok a čistím metadáta...")
        shutil.copy2(src_path, out_path)
        if check_tool("exiftool"):
            subprocess.run(["exiftool", "-all=", "-overwrite_original", out_path],
                           capture_output=True)
    else:
        raise RuntimeError(f"Nepodporovaná prípona: {ext}")

    # ── GPS ──
    if use_location and lat is not None and lon is not None:
        if not check_tool("exiftool"):
            raise RuntimeError("exiftool nie je nájdený v PATH.")
        log("Zapisujem GPS súradnice (exiftool)...")
        r = subprocess.run([
            "exiftool", "-overwrite_original",
            f"-GPSLatitude={abs(lat)}",
            f"-GPSLatitudeRef={dms_ref(lat,'N','S')}",
            f"-GPSLongitude={abs(lon)}",
            f"-GPSLongitudeRef={dms_ref(lon,'E','W')}",
            out_path,
        ], capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"exiftool zlyhal:\n{r.stderr[-1500:]}")

    # ── Device fingerprint ──
    apply_fingerprint(out_path, fp_settings, log)

    return out_path


def extract_links(raw):
    seen, result = set(), []
    for line in raw.splitlines():
        l = line.strip()
        if l and re.match(r"^https?://", l) and l not in seen:
            seen.add(l); result.append(l)
    return result


def detect_browsers():
    """Nájde nainštalované prehliadače pre --cookies-from-browser."""
    candidates = {
        "chrome":   os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"),
        "edge":     os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data"),
        "firefox":  os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles"),
        "opera":    os.path.expandvars(r"%APPDATA%\Opera Software\Opera Stable"),
        "brave":    os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data"),
        "chromium": os.path.expandvars(r"%LOCALAPPDATA%\Chromium\User Data"),
        "vivaldi":  os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\User Data"),
    }
    found = [name for name, path in candidates.items() if path and os.path.isdir(path)]
    return found or ["chrome"]
# ── Planner: spoof one video per device ───────────────────────────────────────

def spoof_video(src, out_path, lat, lon, jitter, make, model, log):
    ext = os.path.splitext(src)[1].lower()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    if ext in VIDEO_EXT:
        if not check_tool("ffmpeg"):
            raise RuntimeError("ffmpeg nie je v PATH")
        vf_str, needs_reencode = build_vf(SAFE_FILTERS)
        cmd = ["ffmpeg", "-y", "-i", src, "-map_metadata", "-1",
               "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]
        if vf_str:
            cmd += ["-vf", vf_str]
        cmd += (["-c:v", "libx264", "-crf", "18", "-preset", "fast", "-c:a", "copy"]
                if needs_reencode else ["-c", "copy"])
        cmd.append(out_path)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg zlyhal: {r.stderr[-300:]}")
    else:
        shutil.copy2(src, out_path)
        if check_tool("exiftool"):
            subprocess.run(["exiftool", "-all=", "-overwrite_original", out_path],
                           capture_output=True)

    if lat is not None and check_tool("exiftool"):
        jlat = lat + random.uniform(-jitter, jitter)
        jlon = lon + random.uniform(-jitter, jitter)
        subprocess.run(["exiftool", "-overwrite_original",
                        f"-GPSLatitude={abs(jlat)}", f"-GPSLatitudeRef={dms_ref(jlat,'N','S')}",
                        f"-GPSLongitude={abs(jlon)}", f"-GPSLongitudeRef={dms_ref(jlon,'E','W')}",
                        out_path], capture_output=True)

    if check_tool("exiftool"):
        apply_fingerprint(out_path, {
            "enabled": True, "mode": "random" if make is None else "same",
            "make": make, "model": model,
            "random_date": True, "days_back": 30,
            "random_uid": True, "no_ffmpeg_sig": True,
            "title": "", "artist": "", "comment": "",
        }, log)


def update_original_meta(src, lat, lon, jitter, make, model, log, fp=None):
    """Zmení LEN GPS a metadáta originálu – video stream sa nedotýka, kvalita ostáva rovnaká."""
    if not check_tool("exiftool"):
        raise RuntimeError("exiftool nie je v PATH")
    log("  originál: mažem metadáta, zapisujem GPS + fingerprint (kvalita sa nemení)")
    subprocess.run(["exiftool", "-all=", "-overwrite_original", src],
                   capture_output=True, text=True)
    if lat is not None:
        jlat = lat + random.uniform(-jitter, jitter)
        jlon = lon + random.uniform(-jitter, jitter)
        subprocess.run(["exiftool", "-overwrite_original",
                        f"-GPSLatitude={abs(jlat)}", f"-GPSLatitudeRef={dms_ref(jlat,'N','S')}",
                        f"-GPSLongitude={abs(jlon)}", f"-GPSLongitudeRef={dms_ref(jlon,'E','W')}",
                        src], capture_output=True, text=True)
    if fp is None:
        fp = {
            "enabled": True, "mode": "random" if make is None else "same",
            "make": make, "model": model,
            "random_date": True, "days_back": 30,
            "random_uid": True, "no_ffmpeg_sig": True,
            "title": "", "artist": "", "comment": "",
        }
    apply_fingerprint(src, fp, log)


# ── Schedule algorithm ────────────────────────────────────────────────────────

def make_schedule(n_videos, n_devices, vmin, vmax, start_date):
    """
    Rozvrh s garanciou: v ten istý deň žiadne dve zariadenia nepostujú rovnaké
    originálne video. Každé zariadenie dostane VŠETKY videá presne raz.

    Každý deň sa vyberie spoločný počet videí c (v rozsahu vmin..vmax) a VŠETKY
    zariadenia postujú c videí (lockstep). Fronty zariadení sú rotácie
    spoločného zamiešaného poradia s pevným odstupom >= vmax, takže okná videí
    sa nikdy neprekrývajú (denné okná majú dĺžku c <= vmax a štarty sú od seba
    vzdialené aspoň `offset`).
    Vracia list (date, {dev_idx: [video_indices]}).
    """
    if n_videos < 1 or n_devices < 1:
        return []
    n_devices = min(n_devices, n_videos)
    offset = max(1, n_videos // n_devices)
    # garancia disjunktnosti: vmax_eff nesmie presiahnuť odstup medzi zariadeniami
    vmax_eff = min(vmax, offset)
    vmin_eff = min(vmin, vmax_eff)

    base = list(range(n_videos))
    random.shuffle(base)
    queues = []
    for i in range(n_devices):
        s = (i * offset) % n_videos
        queues.append(base[s:] + base[:s])

    schedule, positions, day_n = [], [0] * n_devices, 0
    while positions[0] < n_videos:  # lockstep: všetky zariadenia majú rovnaký posun
        date = start_date + datetime.timedelta(days=day_n)
        remaining = n_videos - positions[0]
        hi = min(vmax_eff, remaining)
        lo = min(vmin_eff, hi)
        cnt = random.randint(lo, hi)
        day = {}
        for di in range(n_devices):
            p = positions[di]
            day[di] = queues[di][p:p + cnt]
            positions[di] += cnt
        schedule.append((date, day))
        day_n += 1
    return schedule


def schedule_to_json(schedule, devices, videos):
    out = []
    for date, assignments in schedule:
        entry = {"date": date.isoformat(), "devices": {}}
        for di, vid_idxs in assignments.items():
            dev = devices[di]
            entry["devices"][dev["name"]] = [
                os.path.basename(videos[vi]) for vi in vid_idxs if vi < len(videos)
            ]
        out.append(entry)
    return out
# ── HTTP Server ───────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0e0e1a;color:#fff;font-family:system-ui,sans-serif;padding:16px;max-width:480px;margin:auto}}
h1{{font-size:1.25rem;color:#4da3ff;margin-bottom:2px}}
.sub{{color:#444;font-size:.8rem;margin-bottom:18px}}
.card{{background:#13131f;border:1px solid #222240;border-radius:10px;padding:14px;margin-bottom:10px}}
.name{{font-weight:600;margin-bottom:8px;font-size:.95rem}}
.tag{{color:#22c55e;font-size:.78rem;margin-bottom:6px}}
.btn{{display:block;background:#2563eb;color:#fff;padding:11px;border-radius:8px;
      text-align:center;text-decoration:none;font-weight:600}}
.btn:active{{background:#1d4ed8}}
.empty{{color:#444;text-align:center;padding:40px 0;font-size:.9rem}}
.nav a{{color:#2563eb;text-decoration:none;font-size:.85rem}}
.nav{{margin-bottom:14px}}
.date-nav{{display:flex;gap:8px;margin-bottom:14px}}
.date-nav a{{background:#1a1a2e;color:#888;padding:8px 12px;border-radius:8px;
             text-decoration:none;font-size:.82rem;flex:1;text-align:center}}
.date-nav a.today{{background:#2563eb;color:#fff}}
</style></head><body>{body}</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        segs = [s for s in p.split("/") if s]
        if not segs: return self._index()
        if segs[0] == "device" and len(segs) >= 2:
            di = int(segs[1]) if segs[1].isdigit() else -1
            ds = segs[2] if len(segs) >= 3 else None
            return self._device(di, ds)
        if segs[0] == "dl":
            return self._download("/".join(segs[1:]))
        self._404()

    def _index(self):
        devices = _srv["devices"]
        today = datetime.date.today().isoformat()
        rows = "".join(
            f'<div class="card"><div class="name">📱 {d["name"]}</div>'
            f'<a class="btn" href="/device/{i}">Dnes → {today}</a></div>'
            for i, d in enumerate(devices)
        )
        body = f'<h1>CaPPy Planner</h1><div class="sub">Vyber zariadenie</div>{rows or "<div class=empty>Žiadne zariadenia. Generuj rozvrh v appke.</div>"}'
        self._html(HTML.format(title="CaPPy", body=body))

    def _device(self, di, date_str):
        devices, schedule, videos, out_dir = (_srv["devices"], _srv["schedule"],
                                              _srv["videos"], _srv["output_dir"])
        if di < 0 or di >= len(devices): return self._404()
        dev = devices[di]
        try:
            target = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
        except ValueError:
            target = datetime.date.today()

        prev = (target - datetime.timedelta(days=1)).isoformat()
        nxt  = (target + datetime.timedelta(days=1)).isoformat()
        today = datetime.date.today().isoformat()
        tstr = target.isoformat()

        day_vids = None
        for sdate, assignments in schedule:
            if sdate == target:
                day_vids = assignments.get(di, []); break

        dnav = (f'<div class="date-nav">'
                f'<a href="/device/{di}/{prev}">← {prev}</a>'
                f'<a href="/device/{di}" class="{"today" if tstr==today else ""}">Dnes</a>'
                f'<a href="/device/{di}/{nxt}">{nxt} →</a></div>')

        nav = f'<h1>📱 {dev["name"]}</h1><div class="sub">{tstr}</div><div class="nav"><a href="/">← Späť</a></div>{dnav}'

        if day_vids is None:
            body = nav + '<div class="empty">Žiadne videá na tento deň.</div>'
        else:
            items = ""
            for vi in day_vids:
                if vi >= len(videos): continue
                orig = videos[vi]
                stem, ext = os.path.splitext(os.path.basename(orig))
                fname = f"{stem}_x_{di+1}{ext}"
                fpath = os.path.join(out_dir, dev["name"], tstr, fname)
                rel   = urllib.parse.quote(f"{dev['name']}/{tstr}/{fname}")
                if os.path.exists(fpath):
                    items += (f'<div class="card"><div class="tag">Video #{vi+1}</div>'
                              f'<div class="name">{fname}</div>'
                              f'<a class="btn" href="/dl/{rel}">⬇ Stiahnuť</a></div>')
                else:
                    items += f'<div class="card"><div class="name">⏳ {fname} (spracúva sa...)</div></div>'
            body = nav + (items or '<div class="empty">Žiadne videá.</div>')

        self._html(HTML.format(title=dev["name"], body=body))

    def _download(self, rel):
        out_dir = os.path.realpath(_srv["output_dir"])
        path = os.path.realpath(os.path.join(out_dir, urllib.parse.unquote(rel)))
        if not path.startswith(out_dir + os.sep) or not os.path.isfile(path):
            return self._404()
        ext = os.path.splitext(path)[1].lower()
        ct = "video/mp4" if ext in (".mp4", ".mov") else "application/octet-stream"
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(size))
        self.send_header("Content-Disposition", f'attachment; filename="{os.path.basename(path)}"')
        self.end_headers()
        with open(path, "rb") as f:
            while chunk := f.read(65536): self.wfile.write(chunk)

    def _html(self, html):
        d = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html;charset=utf-8")
        self.send_header("Content-Length", str(len(d)))
        self.end_headers(); self.wfile.write(d)

    def _404(self):
        self.send_response(404); self.end_headers(); self.wfile.write(b"404")
def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close(); return ip
    except: return "127.0.0.1"


def start_server():
    srv = HTTPServer(("", SERVER_PORT), Handler)
    _srv["server"] = srv
    srv.serve_forever()


def stop_server():
    if _srv["server"]:
        _srv["server"].shutdown()
        _srv["server"] = None


# ── Device Profile Dialog ─────────────────────────────────────────────────────

class DeviceDialog(tk.Toplevel):
    def __init__(self, parent, existing=None):
        super().__init__(parent)
        self.title("Zariadenie")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.grab_set()
        self.result = None

        pad = {"padx": 12, "pady": 5}

        tk.Label(self, text="Názov zariadenia:", bg=BG, fg="#aaa").grid(row=0, column=0, sticky="e", **pad)
        self.name_var = tk.StringVar(value=existing.get("name", "") if existing else f"Zariadenie {random.randint(1,99)}")
        tk.Entry(self, textvariable=self.name_var, width=26, bg=ENTRY_BG, fg="white",
                 insertbackground="white", relief="flat").grid(row=0, column=1, **pad)

        tk.Label(self, text="Device model:", bg=BG, fg="#aaa").grid(row=1, column=0, sticky="e", **pad)
        self.device_var = tk.StringVar(value=existing.get("device_model", "Auto (náhodné zariadenie)") if existing else "Auto (náhodné zariadenie)")
        ttk.Combobox(self, values=[d[0] for d in DEVICES], textvariable=self.device_var,
                     width=24, state="readonly").grid(row=1, column=1, **pad)

        tk.Label(self, text="Mesto (GPS):", bg=BG, fg="#aaa").grid(row=2, column=0, sticky="e", **pad)
        self.city_var = tk.StringVar(value=existing.get("city", "Los Angeles, CA") if existing else "Los Angeles, CA")
        city_names = [c[0] for c in CITIES]
        ttk.Combobox(self, values=city_names, textvariable=self.city_var,
                     width=24, state="readonly").grid(row=2, column=1, **pad)

        tk.Label(self, text="GPS Jitter (°):", bg=BG, fg="#aaa").grid(row=3, column=0, sticky="e", **pad)
        self.jitter_var = tk.StringVar(value=str(existing.get("jitter", 0.0015)) if existing else "0.0015")
        tk.Entry(self, textvariable=self.jitter_var, width=12, bg=ENTRY_BG, fg="white",
                 insertbackground="white", relief="flat").grid(row=3, column=1, sticky="w", **pad)

        btn_row = tk.Frame(self, bg=BG)
        btn_row.grid(row=4, column=0, columnspan=2, pady=14)
        btn(btn_row, text="Uložiť", command=self._save,
            bg=ACCENT, fg="white", padx=16, pady=6).pack(side="left", padx=6)
        btn(btn_row, text="Zrušiť", command=self.destroy,
            bg=ENTRY_BG, fg="white", padx=16, pady=6).pack(side="left", padx=6)

    def _save(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Chýba názov", "Zadaj názov zariadenia.", parent=self)
            return
        city = self.city_var.get()
        lat = lon = None
        for cname, clat, clon in CITIES:
            if cname == city and clat is not None:
                lat, lon = clat, clon; break
        make = model = None
        for dname, dmake, dmodel in DEVICES:
            if dname == self.device_var.get():
                make, model = dmake, dmodel; break
        try:
            jitter = float(self.jitter_var.get())
        except ValueError:
            jitter = 0.0015
        self.result = {"name": name, "device_model": self.device_var.get(),
                       "city": city, "lat": lat, "lon": lon,
                       "make": make, "model": model, "jitter": jitter}
        self.destroy()
# ─── Filter Card Widget ───────────────────────────────────────────────────────

class FilterCard(tk.Frame):
    def __init__(self, parent, fid, fname, ftype, has_range,
                 dmin, dmax, amin, amax, res, fmt, on_default):
        super().__init__(parent, bg=CARD_BG, padx=8, pady=6,
                         highlightbackground="#222240", highlightthickness=1)
        self.fid = fid
        self.has_range = has_range
        self.fmt = fmt
        self._dmin = dmin
        self._dmax = dmax
        self.enabled_var = tk.BooleanVar(value=on_default)
        self.min_var = tk.DoubleVar(value=dmin)
        self.max_var = tk.DoubleVar(value=dmax)

        # ── Header row ──
        hdr = tk.Frame(self, bg=CARD_BG)
        hdr.pack(fill="x")
        tk.Label(hdr, text=fname, font=("Segoe UI", 9, "bold"),
                 bg=CARD_BG, fg="white").pack(side="left")
        tk.Checkbutton(hdr, variable=self.enabled_var,
                       bg=CARD_BG, activebackground=CARD_BG,
                       selectcolor="#2a2a3a", fg="white").pack(side="right")

        if has_range and res > 0:
            # ── Min slider ──
            mr = tk.Frame(self, bg=CARD_BG)
            mr.pack(fill="x", pady=(3, 0))
            tk.Label(mr, text="Min", width=3, anchor="w", bg=CARD_BG,
                     fg="#555", font=("Segoe UI", 7)).pack(side="left")
            tk.Scale(mr, from_=amin, to=amax, resolution=res, orient="horizontal",
                     variable=self.min_var, bg=CARD_BG, fg="#666",
                     troughcolor="#1e1e30", highlightthickness=0,
                     showvalue=False, bd=0,
                     command=lambda v: self._update_labels()
                     ).pack(side="left", fill="x", expand=True)
            self.min_lbl = tk.Label(mr, text="", width=9, anchor="e",
                                    bg=CARD_BG, fg="#aaa", font=("Segoe UI", 8))
            self.min_lbl.pack(side="right")

            # ── Max slider ──
            mr2 = tk.Frame(self, bg=CARD_BG)
            mr2.pack(fill="x")
            tk.Label(mr2, text="Max", width=3, anchor="w", bg=CARD_BG,
                     fg="#555", font=("Segoe UI", 7)).pack(side="left")
            tk.Scale(mr2, from_=amin, to=amax, resolution=res, orient="horizontal",
                     variable=self.max_var, bg=CARD_BG, fg="#666",
                     troughcolor="#1e1e30", highlightthickness=0,
                     showvalue=False, bd=0,
                     command=lambda v: self._update_labels()
                     ).pack(side="left", fill="x", expand=True)
            self.max_lbl = tk.Label(mr2, text="", width=9, anchor="e",
                                    bg=CARD_BG, fg="#aaa", font=("Segoe UI", 8))
            self.max_lbl.pack(side="right")
            self._update_labels()

    def _update_labels(self):
        if self.has_range and self.fmt:
            try:
                self.min_lbl.config(text=self.fmt.format(self.min_var.get()))
                self.max_lbl.config(text=self.fmt.format(self.max_var.get()))
            except Exception:
                pass

    def get_state(self):
        return {
            "enabled": self.enabled_var.get(),
            "min": self.min_var.get() if self.has_range else 0,
            "max": self.max_var.get() if self.has_range else 0,
        }

    def set_enabled(self, v):
        self.enabled_var.set(v)

    def reset(self):
        self.min_var.set(self._dmin)
        self.max_var.set(self._dmax)
        self._update_labels()

# ─── Location Section ─────────────────────────────────────────────────────────

class LocationSection(tk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text="  📍  Location", bg=BG, fg="white",
                         font=("Segoe UI", 10, "bold"), padx=10, pady=8,
                         relief="flat", highlightbackground="#222240", highlightthickness=1)
        self.lat_var = tk.StringVar(value="34.052200")
        self.lon_var = tk.StringVar(value="-118.243700")
        self.marker = None

        # ── Toggle ──
        tog_row = tk.Frame(self, bg=BG)
        tog_row.pack(fill="x", pady=(0, 8))
        self.enabled_var = tk.BooleanVar(value=True)
        tk.Checkbutton(tog_row, text="Zapísať GPS do výstupu", variable=self.enabled_var,
                       bg=BG, fg="white", selectcolor=ENTRY_BG,
                       activebackground=BG, font=("Segoe UI", 9)).pack(side="left")

        # ── City preset + Reset ──
        city_row = tk.Frame(self, bg=BG)
        city_row.pack(fill="x", pady=(0, 8))
        tk.Label(city_row, text="Mesto:", bg=BG, fg="#888",
                 font=("Segoe UI", 9)).pack(side="left")
        self.city_var = tk.StringVar(value="Los Angeles, CA")
        city_names = [c[0] for c in CITIES]
        self.city_combo = ttk.Combobox(city_row, values=city_names,
                                        textvariable=self.city_var,
                                        width=28, state="readonly")
        self.city_combo.pack(side="left", padx=8)
        self.city_combo.bind("<<ComboboxSelected>>", self._on_city)
        btn(city_row, text="Reset", command=self._on_reset,
            bg=ENTRY_BG, fg="white", padx=8).pack(side="left")

        # ── Map widget (optional) ──
        if MAP_AVAILABLE:
            self.map_widget = tkintermapview.TkinterMapView(
                self, width=520, height=200, corner_radius=4)
            self.map_widget.pack(pady=(0, 8), fill="x")
            self.map_widget.set_position(34.0522, -118.2437)
            self.map_widget.set_zoom(5)
            self.marker = self.map_widget.set_marker(34.0522, -118.2437)
            self.map_widget.add_left_click_map_command(self._on_map_click)
        else:
            mrow = tk.Frame(self, bg=BG)
            mrow.pack(pady=(0, 6))
            tk.Label(mrow, text="(Chýba tkintermapview – interaktívna mapa nebude k dispozícii)",
                     bg=BG, fg="#444", font=("Segoe UI", 8)).pack(side="left")
            btn(mrow, text="⚡ Inštalovať mapu", command=self._install_map,
                bg=ENTRY_BG, fg="#4da3ff", padx=8, pady=3,
                font=("Segoe UI", 8, "bold")).pack(side="left", padx=(8, 0))

        # ── Lat / Lon fields ──
        self.jitter_var = tk.StringVar(value="0.0015")
        coords = tk.Frame(self, bg=BG)
        coords.pack(fill="x")
        for label, var in [("Latitude:", self.lat_var), ("Longitude:", self.lon_var)]:
            tk.Label(coords, text=label, bg=BG, fg="#888",
                     font=("Segoe UI", 9)).pack(side="left")
            e = tk.Entry(coords, textvariable=var, width=14,
                         bg=ENTRY_BG, fg="white", insertbackground="white",
                         relief="flat", font=("Segoe UI", 9))
            e.pack(side="left", padx=(4, 16))

        tk.Label(coords, text="Jitter (°):", bg=BG, fg="#888",
                 font=("Segoe UI", 9)).pack(side="left")
        tk.Entry(coords, textvariable=self.jitter_var, width=8,
                 bg=ENTRY_BG, fg="white", insertbackground="white",
                 relief="flat", font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))

        self.lat_var.trace_add("write", self._on_typed)
        self.lon_var.trace_add("write", self._on_typed)

    def _install_map(self):
        """Rovno doinštaluje tkintermapview a ponúkne reštart pre aktiváciu mapy."""
        root = self.winfo_toplevel()
        ok, _ = install_pip(root, ["tkintermapview"])
        if ok:
            if messagebox.askyesno("Hotovo",
                                   "Interaktívna mapa (tkintermapview) je nainštalovaná.\n"
                                   "Reštartovať appku, aby sa mapa aktivovala?"):
                restart_app()
        else:
            messagebox.showerror("Chyba", "Inštalácia mapy zlyhala.\nSkús ručne:\n"
                                 "pip install tkintermapview")

    def _on_city(self, _=None):
        name = self.city_var.get()
        for cname, lat, lon in CITIES:
            if cname == name and lat is not None:
                jlat = lat + random.uniform(-0.015, 0.015)
                jlon = lon + random.uniform(-0.015, 0.015)
                self.lat_var.set(f"{jlat:.6f}")
                self.lon_var.set(f"{jlon:.6f}")
                self._move_map(jlat, jlon)
                return

    def _on_reset(self):
        self.city_var.set(CITIES[0][0])

    def _on_map_click(self, coords):
        lat, lon = coords
        self.lat_var.set(f"{lat:.6f}")
        self.lon_var.set(f"{lon:.6f}")
        self._move_map(lat, lon)

    def _on_typed(self, *_):
        try:
            lat = float(self.lat_var.get())
            lon = float(self.lon_var.get())
            self._move_map(lat, lon)
        except ValueError:
            pass

    def _move_map(self, lat, lon):
        if MAP_AVAILABLE and hasattr(self, "map_widget"):
            self.map_widget.set_position(lat, lon)
            if self.marker:
                self.marker.delete()
            self.marker = self.map_widget.set_marker(lat, lon)

    def get_coords(self):
        """Returns (enabled, lat, lon, jitter) – base coords without extra jitter applied."""
        if not self.enabled_var.get():
            return False, None, None, 0.0
        try:
            lat = float(self.lat_var.get())
            lon = float(self.lon_var.get())
            jitter = float(self.jitter_var.get())
        except ValueError:
            return True, None, None, 0.0
        return True, lat, lon, jitter
# ─── Filters Section ──────────────────────────────────────────────────────────

class FiltersSection(tk.LabelFrame):
    def __init__(self, parent):
        super().__init__(parent, text="  🎛  Randomization Filters", bg=BG, fg="white",
                         font=("Segoe UI", 10, "bold"), padx=10, pady=8,
                         relief="flat", highlightbackground="#222240", highlightthickness=1)

        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", pady=(0, 6))
        tk.Label(bar, text="Náhodná hodnota z rozsahu Min–Max sa aplikuje pri každom spracovaní.",
                 bg=BG, fg="#555", font=("Segoe UI", 8)).pack(side="left")
        btn(bar, text="All On", command=self._all_on,
            bg=ENTRY_BG, fg="white", padx=8).pack(side="right", padx=2)
        btn(bar, text="Reset", command=self._reset_all,
            bg=ENTRY_BG, fg="white", padx=8).pack(side="right", padx=2)

        grid = tk.Frame(self, bg=BG)
        grid.pack(fill="x")
        self.cards = {}
        for col in range(3):
            grid.columnconfigure(col, weight=1)

        for i, (fid, fname, ftype, eq_param, has_range,
                dmin, dmax, amin, amax, res, fmt, on_def) in enumerate(FILTER_DEFS):
            card = FilterCard(grid, fid, fname, ftype, has_range,
                              dmin, dmax, amin, amax, res, fmt, on_def)
            row, col = divmod(i, 3)
            card.grid(row=row, column=col, sticky="nsew", padx=4, pady=4)
            self.cards[fid] = card

    def _all_on(self):
        for card in self.cards.values():
            card.set_enabled(True)

    def _reset_all(self):
        for fid, *_, on_def in [(f[0], *f[1:]) for f in FILTER_DEFS]:
            if fid in self.cards:
                self.cards[fid].set_enabled(FILTER_DEFS[[f[0] for f in FILTER_DEFS].index(fid)][-1])
                self.cards[fid].reset()

    def get_states(self):
        return {fid: card.get_state() for fid, card in self.cards.items()}

# ─── Device Fingerprint Section ──────────────────────────────────────────────

class DeviceFingerprintSection(tk.LabelFrame):
    MODES = [("Same device", "same"), ("Per copy", "per_copy"), ("Random unique", "random")]

    def __init__(self, parent):
        super().__init__(parent, text="  📱  Device Fingerprint", bg=BG, fg="white",
                         font=("Segoe UI", 10, "bold"), padx=10, pady=8,
                         relief="flat", highlightbackground="#222240", highlightthickness=1)
        self.mode_var = tk.StringVar(value="random")
        self._btn_refs = []

        # ── Info note ──
        tk.Label(self,
                 text="Source metadata is always wiped. Here you pick what gets written onto the clean file.",
                 bg=BG, fg="#555", font=("Segoe UI", 8), wraplength=540, justify="left"
                 ).pack(anchor="w", pady=(0, 8))

        # ── 3 mode buttons ──
        mode_row = tk.Frame(self, bg=BG)
        mode_row.pack(anchor="w", pady=(0, 10))
        for label, val in self.MODES:
            btn = tk.Button(mode_row, text=label, width=13,
                            command=lambda v=val: self._set_mode(v),
                            relief="flat", font=("Segoe UI", 9),
                            bg=ENTRY_BG, fg="#888", pady=5)
            btn.pack(side="left", padx=(0, 4))
            self._btn_refs.append((val, btn))

        # ── Device dropdown ──
        dev_row = tk.Frame(self, bg=BG)
        dev_row.pack(fill="x", pady=(0, 8))
        tk.Label(dev_row, text="Device:", bg=BG, fg="#888",
                 font=("Segoe UI", 9), width=8, anchor="w").pack(side="left")
        self.device_var = tk.StringVar(value=DEVICES[0][0])
        self.device_combo = ttk.Combobox(dev_row,
                                          values=[d[0] for d in DEVICES],
                                          textvariable=self.device_var,
                                          width=28, state="readonly")
        self.device_combo.pack(side="left", padx=(0, 16))
        self._set_mode("random")  # called after device_combo exists

        tk.Label(dev_row, text="Creation date back (days):",
                 bg=BG, fg="#888", font=("Segoe UI", 9)).pack(side="left")
        self.days_var = tk.StringVar(value="30")
        tk.Entry(dev_row, textvariable=self.days_var, width=6,
                 bg=ENTRY_BG, fg="white", insertbackground="white",
                 relief="flat").pack(side="left", padx=(4, 0))

        # ── Optional text tags ──
        tags_row = tk.Frame(self, bg=BG)
        tags_row.pack(fill="x", pady=(0, 8))
        self.title_var  = tk.StringVar()
        self.artist_var = tk.StringVar()
        self.comment_var = tk.StringVar()
        for label, var, w in [("Title", self.title_var, 18),
                               ("Artist", self.artist_var, 18),
                               ("Comment", self.comment_var, 22)]:
            tk.Label(tags_row, text=label+":", bg=BG, fg="#888",
                     font=("Segoe UI", 9)).pack(side="left", padx=(0, 2))
            e = tk.Entry(tags_row, textvariable=var, width=w,
                         bg=ENTRY_BG, fg="white", insertbackground="white",
                         relief="flat")
            e.insert(0, "")
            e.config(fg="#555")
            e.bind("<FocusIn>", lambda ev, v=var, ew=e: (ew.config(fg="white"),))
            e.pack(side="left", padx=(0, 12))

        # ── Checkboxes ──
        chk_row = tk.Frame(self, bg=BG)
        chk_row.pack(anchor="w")
        self.rand_date_var = tk.BooleanVar(value=True)
        self.rand_uid_var  = tk.BooleanVar(value=True)
        self.no_sig_var    = tk.BooleanVar(value=True)
        for text, var in [("Random creation date", self.rand_date_var),
                           ("Random UID",           self.rand_uid_var),
                           ("No ffmpeg signature",  self.no_sig_var)]:
            tk.Checkbutton(chk_row, text=text, variable=var,
                           bg=BG, fg="#aaa", selectcolor=ENTRY_BG,
                           activebackground=BG, font=("Segoe UI", 9)
                           ).pack(side="left", padx=(0, 16))

    def _set_mode(self, val):
        self.mode_var.set(val)
        for v, btn in self._btn_refs:
            if v == val:
                btn.config(bg=ACCENT, fg="white")
            else:
                btn.config(bg=ENTRY_BG, fg="#888")
        state = "disabled" if val == "random" else "readonly"
        self.device_combo.config(state=state)

    def get_settings(self):
        mode = self.mode_var.get()
        make = model = None
        if mode != "random":
            dev_name = self.device_var.get()
            for dname, dmake, dmodel in DEVICES:
                if dname == dev_name:
                    make, model = dmake, dmodel
                    break
        try:
            days_back = int(self.days_var.get())
        except ValueError:
            days_back = 30
        return {
            "enabled":       True,
            "mode":          mode,
            "make":          make,
            "model":         model,
            "days_back":     days_back,
            "random_date":   self.rand_date_var.get(),
            "random_uid":    self.rand_uid_var.get(),
            "no_ffmpeg_sig": self.no_sig_var.get(),
            "title":         self.title_var.get(),
            "artist":        self.artist_var.get(),
            "comment":       self.comment_var.get(),
        }
# ─── Metadata Cleaner Tab ─────────────────────────────────────────────────────

class MetadataTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.selected_path = None

        # Scrollable canvas
        canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=BG)
        self.inner.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)

        def _scroll(e):
            canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")
        canvas.bind("<MouseWheel>", _scroll)
        self.inner.bind("<MouseWheel>", _scroll)

        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self._build(canvas)

    def _build(self, canvas):
        p = self.inner

        tk.Label(p, text="1 · Vyber súbor alebo priečinok     2 · Nastav GPS a filtre     3 · Vyčistiť",
                 bg=BG, fg="#666", font=("Segoe UI", 8)).pack(anchor="w", padx=16, pady=(10, 0))

        # ── Source Media ──
        src = tk.LabelFrame(p, text="  ⬆  Source Media", bg=BG, fg="white",
                            font=("Segoe UI", 10, "bold"), padx=10, pady=8,
                            relief="flat", highlightbackground="#222240", highlightthickness=1)
        src.pack(fill="x", padx=12, pady=(4, 6))

        self.drop_frame = tk.Frame(src, bg="#0a0a16", height=90,
                                    highlightbackground="#333366", highlightthickness=1)
        self.drop_frame.pack(fill="x")
        self.drop_frame.pack_propagate(False)
        dtext = "Pretiahni sem video, foto alebo priečinok" if DND_AVAILABLE else "Vyber súbor alebo priečinok"
        self.drop_label = tk.Label(
            self.drop_frame,
            text=dtext + "\nMP4 · MOV · MKV · WebM · JPG · PNG · WebP",
            bg="#0a0a16", fg="#6666aa",
            font=("Segoe UI", 10), justify="center")
        self.drop_label.pack(expand=True)

        if DND_AVAILABLE:
            self.drop_frame.drop_target_register(DND_FILES)
            self.drop_frame.dnd_bind("<<Drop>>", self.on_drop)

        btn_row = tk.Frame(src, bg=BG)
        btn_row.pack(fill="x", pady=(8, 0))
        btn(btn_row, text="⬆ Vybrať súbor...", command=self.browse_file,
            bg=ENTRY_BG, fg="white", padx=10, pady=4).pack(side="left")
        btn(btn_row, text="⬆ Vybrať priečinok...", command=self.browse_folder,
            bg=ENTRY_BG, fg="white", padx=10, pady=4).pack(side="left", padx=(6, 0))
        self.file_var = tk.StringVar(value="Žiadny súbor")
        tk.Label(btn_row, textvariable=self.file_var, bg=BG, fg="#4da3ff",
                 font=("Segoe UI", 9), wraplength=420).pack(side="left", padx=12)

        # ── Location ──
        self.location = LocationSection(p)
        self.location.pack(fill="x", padx=12, pady=6)

        # ── Filters ──
        self.filters = FiltersSection(p)
        self.filters.pack(fill="x", padx=12, pady=6)

        # ── Device Fingerprint ──
        self.fingerprint = DeviceFingerprintSection(p)
        self.fingerprint.pack(fill="x", padx=12, pady=6)

        # ── Copies + Process button ──
        bottom = tk.Frame(p, bg=BG)
        bottom.pack(fill="x", padx=12, pady=(8, 18))

        copies_row = tk.Frame(bottom, bg=BG)
        copies_row.pack(fill="x", pady=(0, 8))
        tk.Label(copies_row, text="Počet kópií:", bg=BG, fg="#888",
                 font=("Segoe UI", 10)).pack(side="left")
        self.copies_var = tk.IntVar(value=1)
        sb = tk.Spinbox(copies_row, from_=1, to=20, textvariable=self.copies_var,
                        width=4, bg=ENTRY_BG, fg="white", insertbackground="white",
                        buttonbackground=ENTRY_BG, relief="flat",
                        font=("Segoe UI", 11, "bold"))
        sb.pack(side="left", padx=8)
        tk.Label(copies_row,
                 text="Každá kópia: iné GPS (jitter), iný device fingerprint, iné hodnoty filtrov.",
                 bg=BG, fg="#444", font=("Segoe UI", 8)).pack(side="left")

        self.proc_btn = btn(
            bottom, text="⚡  Vyčistiť a spracovať",
            command=self.run_process, state="disabled",
            bg=ACCENT, fg="white",
            font=("Segoe UI", 11, "bold"), padx=20, pady=10)
        self.proc_btn.pack(fill="x")

        self.orig_var = tk.BooleanVar(value=True)
        tk.Checkbutton(bottom, text="Upraviť aj originál (len GPS + metadáta – kvalita sa nemení)",
                       variable=self.orig_var, bg=BG, fg="#aaa", selectcolor=ENTRY_BG,
                       activebackground=BG, font=("Segoe UI", 9)
                       ).pack(anchor="w", pady=(6, 0))

        self.status_var = tk.StringVar(value="")
        tk.Label(bottom, textvariable=self.status_var, bg=BG, fg="#888",
                 wraplength=560, justify="left", font=("Segoe UI", 8)).pack(pady=(6, 0))

        # Progress bar čistenia (aktualizovaný cez poll z hlavného vlákna)
        self._prog_total = 0
        self._prog_done = 0
        self._prog_active = False
        self.prog_var = tk.DoubleVar(value=0)
        self.prog_bar = ttk.Progressbar(bottom, variable=self.prog_var, maximum=100)
        self.prog_bar.pack(fill="x", pady=(6, 0))

        miss = [t for t in ("ffmpeg", "exiftool") if not check_tool(t)]
        if miss:
            self.status_var.set(f"⚠  Chýbajú v PATH: {', '.join(miss)}")

    def on_drop(self, event):
        paths = self._media_paths(event.data)
        if len(paths) == 1:
            self.set_file(paths[0])
        elif paths:
            self.set_file(paths[0])
            self.file_var.set(f"{len(paths)} podporovaných súborov")

    def browse_file(self):
        p = filedialog.askopenfilename(
            filetypes=[("Video/Foto",
                        "*.mp4 *.mov *.mkv *.webm *.avi *.m4v "
                        "*.jpg *.jpeg *.png *.webp *.heic")])
        if p:
            self.set_file(p)

    def browse_folder(self):
        p = filedialog.askdirectory()
        if p:
            self.set_file(p)

    def _media_paths(self, raw_paths):
        paths = []
        path_items = [raw_paths] if os.path.exists(raw_paths) else self.tk.splitlist(raw_paths)
        for path in path_items:
            path = path.strip("{}")
            if os.path.isfile(path) and os.path.splitext(path)[1].lower() in VIDEO_EXT | IMAGE_EXT:
                paths.append(path)
            elif os.path.isdir(path):
                for root, _, names in os.walk(path):
                    paths.extend(os.path.join(root, name) for name in sorted(names)
                                 if os.path.splitext(name)[1].lower() in VIDEO_EXT | IMAGE_EXT)
        return sorted(set(paths))

    def set_file(self, path):
        self.selected_path = path
        if os.path.isdir(path):
            count = len(self._media_paths(path))
            self.file_var.set(f"{os.path.basename(os.path.normpath(path))} ({count} médií)")
        else:
            self.file_var.set(os.path.basename(path))
        self.proc_btn.config(state="normal")
        self.status_var.set("")

    def _log(self, msg):
        self.status_var.set(msg)
        self.update_idletasks()

    def _poll_progress(self):
        """Poll v hlavnom vlákne – bezpečne aktualizuje progress bar počas čistenia."""
        if self._prog_total:
            self.prog_var.set(self._prog_done / self._prog_total * 100)
        if self._prog_active:
            self.after(120, self._poll_progress)

    def run_process(self):
        if not self.selected_path:
            return
        batch_paths = self._media_paths(self.selected_path)
        if not batch_paths:
            messagebox.showwarning("Prázdne", "Priečinok neobsahuje podporované fotky ani videá.")
            return
        use_loc, base_lat, base_lon, jitter = self.location.get_coords()
        if use_loc and (base_lat is None or base_lon is None):
            messagebox.showerror("Chyba", "Zadaj platné GPS súradnice (Latitude / Longitude).")
            return
        if self.orig_var.get() and not check_tool("exiftool"):
            messagebox.showerror("Chýba exiftool",
                                 "Pre úpravu originálov (GPS + metadáta) je potrebný exiftool v PATH.")
            return
        states      = self.filters.get_states()
        fp_settings = self.fingerprint.get_settings()
        n_copies    = max(1, self.copies_var.get())
        total       = len(batch_paths) * n_copies
        if self.orig_var.get():
            total += len(batch_paths)
        self._prog_total = total
        self._prog_done = 0
        self._prog_active = True
        self.prog_var.set(0)
        self._poll_progress()
        self.proc_btn.config(state="disabled")

        def worker():
            is_batch = os.path.isdir(self.selected_path)
            source_root = os.path.abspath(self.selected_path) if is_batch else None
            output_root = f"{source_root}_cleaned" if is_batch else None
            done  = []
            try:
                for file_index, src in enumerate(batch_paths, 1):
                    root, ext = os.path.splitext(src)
                    relative = os.path.relpath(src, source_root) if is_batch else None
                    self._log(f"Súbor {file_index}/{len(batch_paths)}: {os.path.basename(src)}")
                    for i in range(1, n_copies + 1):
                        self._log(f"Kópia {i}/{n_copies}...")

                        # Fresh GPS jitter for every copy
                        if use_loc and base_lat is not None:
                            lat = base_lat + random.uniform(-jitter, jitter)
                            lon = base_lon + random.uniform(-jitter, jitter)
                        else:
                            lat, lon = base_lat, base_lon

                        # Batch output keeps the input folder structure.
                        if is_batch:
                            relative_root, relative_ext = os.path.splitext(relative)
                            out_dir = os.path.join(output_root, os.path.dirname(relative))
                            os.makedirs(out_dir, exist_ok=True)
                            suffix = "_clean" if n_copies == 1 else f"_x_{i}"
                            out_path = os.path.join(out_dir, relative_root + suffix + relative_ext)
                            c = 1
                            base_out = out_path
                            while os.path.exists(out_path):
                                out_path = os.path.join(
                                    out_dir, f"{relative_root}{suffix}_{c}{relative_ext}")
                                c += 1
                        elif n_copies == 1:
                            out_path = f"{root}_clean{ext}"
                            c = 1
                            while os.path.exists(out_path):
                                out_path = f"{root}_clean_{c}{ext}"; c += 1
                        else:
                            out_path = f"{root}_x_{i}{ext}"
                            c = 1
                            while os.path.exists(out_path):
                                out_path = f"{root}_x_{i}_{c}{ext}"; c += 1

                        out = process_file(src, lat, lon, use_loc, states, fp_settings,
                                           self._log, out_path=out_path)
                        done.append(out)
                        self._prog_done += 1
                        self._log(f"  ✓ {os.path.basename(out)}")

                    # Originál: len GPS + metadáta, kvalita sa nemení
                    if self.orig_var.get():
                        o_lat = base_lat if use_loc else None
                        o_lon = base_lon if use_loc else None
                        self._log(f"  originál: GPS + metadáta")
                        update_original_meta(src, o_lat, o_lon, jitter,
                                             fp_settings.get("make"), fp_settings.get("model"),
                                             self._log, fp=fp_settings)
                        self._prog_done += 1

                summary = "\n".join(os.path.basename(p) for p in done)
                self._log(f"✓ Všetko hotovo ({len(done)} kópií).")
                messagebox.showinfo("Hotovo",
                    f"Vytvorených {len(done)} kópií:\n{summary}")
            except Exception as e:
                self._log(f"✗ Chyba: {e}")
                messagebox.showerror("Chyba", str(e))
            finally:
                self._prog_active = False
                self.proc_btn.config(state="normal")

        threading.Thread(target=worker, daemon=True).start()
# ─── Reels Downloader Tab ─────────────────────────────────────────────────────

class DownloaderTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)

        tk.Label(self,
                 text="Vlož linky (jeden na riadok) – Instagram Reels, TikTok, YouTube Shorts...",
                 fg="#888", bg=BG, font=("Segoe UI", 9)).pack(pady=(12, 4), padx=16, anchor="w")

        self.links_box = scrolledtext.ScrolledText(
            self, height=11, width=72,
            bg="#0a0a16", fg="white", insertbackground="white",
            font=("Segoe UI", 9))
        self.links_box.pack(padx=16, pady=(0, 8), fill="x")

        folder_row = tk.Frame(self, bg=BG)
        folder_row.pack(fill="x", padx=16, pady=(0, 6))
        tk.Label(folder_row, text="Priečinok:", bg=BG, fg="#888").pack(side="left")
        default_dl = os.path.join(os.path.expanduser("~"), "Downloads", "reels")
        self.folder_var = tk.StringVar(value=default_dl)
        tk.Entry(folder_row, textvariable=self.folder_var,
                 bg=ENTRY_BG, fg="white", insertbackground="white",
                 relief="flat", width=46).pack(side="left", padx=8, fill="x", expand=True)
        btn(folder_row, text="...", command=self._browse,
            bg=ENTRY_BG, fg="white", padx=6).pack(side="left")

        # ── Cookies: prehliadač alebo súbor ──
        ck = tk.LabelFrame(self, text="  🍪 Cookies (potrebné pre obmedzený obsah)  ",
                           bg=BG, fg="#4da3ff", font=("Segoe UI", 9, "bold"),
                           padx=10, pady=6, relief="flat",
                           highlightbackground="#222240", highlightthickness=1)
        ck.pack(fill="x", padx=16, pady=(0, 8))
        self.cookies_mode = tk.StringVar(value="browser")

        c1 = tk.Frame(ck, bg=BG)
        c1.pack(fill="x", pady=2)
        tk.Radiobutton(c1, text="Cookies z prehliadača:", variable=self.cookies_mode,
                       value="browser", bg=BG, fg="#aaa", selectcolor=ENTRY_BG,
                       activebackground=BG, font=("Segoe UI", 9)).pack(side="left")
        self.browser_var = tk.StringVar(value="chrome")
        browsers = detect_browsers()
        if self.browser_var.get() not in browsers:
            self.browser_var.set(browsers[0])
        self.browser_combo = ttk.Combobox(c1, textvariable=self.browser_var,
                                          values=browsers, width=14, state="readonly")
        self.browser_combo.pack(side="left", padx=(6, 0))
        tk.Label(c1, text="(musí byť prihlásený na Instagram)",
                 bg=BG, fg="#444", font=("Segoe UI", 8)).pack(side="left", padx=(8, 0))

        c2 = tk.Frame(ck, bg=BG)
        c2.pack(fill="x", pady=2)
        tk.Radiobutton(c2, text="Cookies zo súboru (cookies.txt):", variable=self.cookies_mode,
                       value="file", bg=BG, fg="#aaa", selectcolor=ENTRY_BG,
                       activebackground=BG, font=("Segoe UI", 9)).pack(side="left")
        self.cookies_file_var = tk.StringVar()
        tk.Entry(c2, textvariable=self.cookies_file_var,
                 bg=ENTRY_BG, fg="white", insertbackground="white",
                 relief="flat", width=22).pack(side="left", padx=(6, 4))
        btn(c2, text="...", command=self._browse_cookies,
            bg=ENTRY_BG, fg="white", padx=4).pack(side="left")

        # ── Akcie ──
        act = tk.Frame(self, bg=BG)
        act.pack(fill="x", padx=16, pady=(0, 8))
        self.dl_btn = btn(
            act, text="⬇  Stiahnuť všetko", command=self.start_download,
            bg=ACCENT, fg="white", font=("Segoe UI", 11, "bold"),
            padx=20, pady=10)
        self.dl_btn.pack(side="left", fill="x", expand=True)
        self.update_btn = btn(
            act, text="🔄 Aktualizovať yt-dlp", command=self._update_ytdlp,
            bg=ENTRY_BG, fg="white", font=("Segoe UI", 9),
            padx=12, pady=10)
        self.update_btn.pack(side="left", padx=(6, 0))

        tk.Label(self, text="Log:", bg=BG, fg="#555").pack(anchor="w", padx=16)
        self.log_box = scrolledtext.ScrolledText(
            self, height=10, width=72, state="disabled",
            bg="#060610", fg="#00ff88",
            font=("Courier", 8))
        self.log_box.pack(padx=16, pady=(2, 14), fill="x")

        if not check_tool("yt-dlp"):
            self._log("⚠  yt-dlp nie je v PATH. Nainštaluj: pip install -U yt-dlp")

    def _browse(self):
        p = filedialog.askdirectory()
        if p: self.folder_var.set(p)

    def _log(self, msg):
        self.log_box.config(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")
        self.update_idletasks()

    def start_download(self):
        links = extract_links(self.links_box.get("1.0", "end"))
        if not links:
            messagebox.showwarning("Prázdne", "Vlož aspoň jeden platný link.")
            return
        if not check_tool("yt-dlp"):
            messagebox.showerror("Chýba yt-dlp", "Nainštaluj: pip install -U yt-dlp")
            return
        out = self.folder_var.get().strip()
        os.makedirs(out, exist_ok=True)
        self.dl_btn.config(state="disabled")
        threading.Thread(target=self._run, args=(links, out), daemon=True).start()

    def _browse_cookies(self):
        p = filedialog.askopenfilename(
            filetypes=[("Cookies", "*.txt"), ("Všetky súbory", "*.*")])
        if p:
            self.cookies_file_var.set(p)

    def _update_ytdlp(self):
        if not check_tool("yt-dlp"):
            messagebox.showerror("Chýba yt-dlp", "Nainštaluj: pip install -U yt-dlp")
            return
        self._log("Aktualizujem yt-dlp...")
        self.update_btn.config(state="disabled")
        threading.Thread(target=self._update_worker, daemon=True).start()

    def _update_worker(self):
        try:
            r = subprocess.run(["yt-dlp", "-U"], capture_output=True, text=True)
            tail = [l for l in (r.stdout or "").splitlines() if l.strip()]
            self._log("  " + (tail[-1] if tail else f"exit {r.returncode}"))
            if r.returncode != 0:
                err = [l for l in (r.stderr or "").splitlines() if l.strip()]
                self._log("  " + (err[-1] if err else "chýba detail"))
        except Exception as e:
            self._log(f"  ✗ {e}")
        self.update_btn.config(state="normal")

    def _run(self, links, out_folder):
        self._log(f"Spúšťam – {len(links)} linkov → {out_folder}\n")
        mode = self.cookies_mode.get()
        ok = failed = 0
        for i, link in enumerate(links, 1):
            self._log(f"[{i}/{len(links)}]  {link}")
            cmd = ["yt-dlp",
                   "-o", os.path.join(out_folder, "%(uploader)s_%(id)s.%(ext)s"),
                   "--no-playlist"]
            if mode == "browser":
                b = self.browser_var.get().strip()
                if b:
                    cmd += ["--cookies-from-browser", b]
            elif mode == "file":
                cf = self.cookies_file_var.get().strip()
                if cf and os.path.isfile(cf):
                    cmd += ["--cookies", cf]
            cmd.append(link)
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                ok += 1; self._log("  ✓ OK")
            else:
                failed += 1
                last = (r.stderr.strip().splitlines() or ["neznáma chyba"])[-1]
                self._log(f"  ✗ {last}")
                low = last.lower()
                if any(k in low for k in ("isn't available", "audiences", "private",
                                          "not available", "login required")):
                    self._log("  💡 Obsah je obmedzený – prihlás sa na Instagram v prehliadači "
                              "a nastav Cookies vľavo hore.")
                elif "cookies" in low or "decrypt" in low:
                    self._log("  💡 Cookies z prehliadača zlyhali – skús Firefox alebo súbor cookies.txt.")

        self._log(f"\nHotovo — ✓ {ok}  ✗ {failed}")
        self.dl_btn.config(state="normal")
        messagebox.showinfo("Hotovo",
                            f"Stiahnutých: {ok}\nZlyhalo: {failed}\nPriečinok: {out_folder}")
# ─── Planner: Video Tab ───────────────────────────────────────────────────────

class VideoTab(tk.Frame):
    def __init__(self, parent, on_change=None):
        super().__init__(parent, bg=BG)
        self.on_change = on_change
        self.videos = []

        self.step_bar = StepBar(self, 0)
        self.step_bar.pack(fill="x", padx=16, pady=(12, 2))

        tk.Label(self, text="Originálne videá – každé sa skopíruje pre každé zariadenie.",
                 bg=BG, fg="#666", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(2, 4))

        self.summary_var = tk.StringVar(value="Zatiaľ žiadne videá.")
        tk.Label(self, textvariable=self.summary_var, bg=BG, fg="#4da3ff",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(0, 4))

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=(0, 8))
        btn(btn_row, text="＋ Pridať videá", command=self._add,
            bg=ACCENT, fg="white", padx=12, pady=6, font=("Segoe UI", 9, "bold")).pack(side="left")
        btn(btn_row, text="＋ Pridať priečinok", command=self._add_folder,
            bg=ENTRY_BG, fg="white", padx=12, pady=6).pack(side="left", padx=6)
        btn(btn_row, text="Odstrániť vybrané", command=self._remove,
            bg=ENTRY_BG, fg="#f66", padx=12, pady=6).pack(side="right")
        btn(btn_row, text="Vyčistiť zoznam", command=self._clear,
            bg=ENTRY_BG, fg="#f66", padx=12, pady=6).pack(side="right", padx=(0, 6))

        list_frame = tk.Frame(self, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=16, pady=6)
        sb = ttk.Scrollbar(list_frame)
        sb.pack(side="right", fill="y")
        self.listbox = tk.Listbox(list_frame, bg=CARD_BG, fg="white", selectbackground=ACCENT,
                                   relief="flat", font=("Segoe UI", 9),
                                   yscrollcommand=sb.set, selectmode="extended")
        self.listbox.pack(fill="both", expand=True)
        sb.config(command=self.listbox.yview)

    def _add(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Video", "*.mp4 *.mov *.mkv *.webm *.avi *.m4v")])
        for p in paths:
            if p not in self.videos:
                self.videos.append(p)
                self.listbox.insert("end", os.path.basename(p))
        self._update()

    def _add_folder(self):
        folder = filedialog.askdirectory()
        if not folder: return
        for f in sorted(os.listdir(folder)):
            p = os.path.join(folder, f)
            if os.path.isfile(p) and os.path.splitext(f)[1].lower() in VIDEO_EXT:
                if p not in self.videos:
                    self.videos.append(p)
                    self.listbox.insert("end", f)
        self._update()

    def _remove(self):
        for i in reversed(self.listbox.curselection()):
            self.videos.pop(i)
            self.listbox.delete(i)
        self._update()

    def _update(self):
        self.summary_var.set(f"{len(self.videos)} videí")
        if self.on_change: self.on_change()

    def _clear(self):
        self.videos.clear()
        self.listbox.delete(0, "end")
        self._update()

# ─── Planner: Devices Tab ─────────────────────────────────────────────────────

class DevicesTab(tk.Frame):
    def __init__(self, parent, on_change=None):
        super().__init__(parent, bg=BG)
        self.on_change = on_change
        self.devices = []

        self.step_bar = StepBar(self, 1)
        self.step_bar.pack(fill="x", padx=16, pady=(12, 2))

        tk.Label(self, text="Každé zariadenie = iný device fingerprint, GPS poloha, model.",
                 bg=BG, fg="#666", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(2, 4))

        self.summary_var = tk.StringVar(value="Zatiaľ žiadne zariadenia.")
        tk.Label(self, textvariable=self.summary_var, bg=BG, fg="#4da3ff",
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=16, pady=(0, 4))

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=(0, 8))
        btn(btn_row, text="＋ Pridať zariadenie", command=self._add,
            bg=ACCENT, fg="white", padx=12, pady=6, font=("Segoe UI", 9, "bold")).pack(side="left")
        btn(btn_row, text="Upraviť vybrané", command=self._edit,
            bg=ENTRY_BG, fg="white", padx=12, pady=6).pack(side="left", padx=6)
        btn(btn_row, text="Odstrániť vybrané", command=self._remove,
            bg=ENTRY_BG, fg="#f66", padx=12, pady=6).pack(side="left", padx=6)

        list_frame = tk.Frame(self, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=16, pady=(0, 4))
        sb = ttk.Scrollbar(list_frame)
        sb.pack(side="right", fill="y")
        self.listbox = tk.Listbox(list_frame, bg=CARD_BG, fg="white", selectbackground=ACCENT,
                                   relief="flat", font=("Segoe UI", 9), yscrollcommand=sb.set)
        self.listbox.pack(fill="both", expand=True)
        sb.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self._refresh_details())

        self.details_var = tk.StringVar(value="Vyber zariadenie v zozname.")
        tk.Label(self, textvariable=self.details_var, bg=CARD_BG, fg="#aaa",
                 font=("Segoe UI", 9), padx=10, pady=8, anchor="w", justify="left",
                 wraplength=680).pack(fill="x", padx=16, pady=(0, 8))

    def _selected(self):
        sel = self.listbox.curselection()
        return sel[0] if sel else None

    def _refresh_list(self):
        self.listbox.delete(0, "end")
        for dev in self.devices:
            self.listbox.insert("end", dev["name"])
        self._refresh_details()

    def _refresh_details(self):
        i = self._selected()
        if i is None or i >= len(self.devices):
            self.details_var.set("Vyber zariadenie v zozname.")
            return
        dev = self.devices[i]
        gps = f"{dev['lat']}, {dev['lon']}" if dev["lat"] is not None else "—"
        self.details_var.set(
            f"📱  {dev['name']}\n"
            f"Model: {dev['device_model']}   ·   GPS: {dev['city']} ({gps})   ·   jitter {dev['jitter']}°")

    def _add(self):
        dlg = DeviceDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self.devices.append(dlg.result)
            self._refresh_list()
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set("end")
            self._refresh_details()
            if self.on_change: self.on_change()

    def _edit(self):
        i = self._selected()
        if i is None:
            messagebox.showinfo("Výber", "Najprv vyber zariadenie v zozname.")
            return
        dlg = DeviceDialog(self, existing=self.devices[i])
        self.wait_window(dlg)
        if dlg.result:
            self.devices[i] = dlg.result
            self._refresh_list()
            self.listbox.selection_set(i)
            self._refresh_details()
            if self.on_change: self.on_change()

    def _remove(self):
        i = self._selected()
        if i is None:
            messagebox.showinfo("Výber", "Najprv vyber zariadenie v zozname.")
            return
        self.devices.pop(i)
        self._refresh_list()
        if self.on_change: self.on_change()
# ─── Planner: Schedule Tab ────────────────────────────────────────────────────

class ScheduleTab(tk.Frame):
    def __init__(self, parent, get_videos, get_devices):
        super().__init__(parent, bg=BG)
        self.get_videos  = get_videos
        self.get_devices = get_devices
        self._schedule   = []
        self._output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "CaPPy_output"))
        self._cancelled  = False
        self.on_server_start = None

        self.step_bar = StepBar(self, 2)
        self.step_bar.pack(fill="x", padx=16, pady=(12, 2))

        # ── Settings ──
        cfg = tk.LabelFrame(self, text="  Nastavenia rozvrhu  ", bg=BG, fg="#4da3ff",
                            font=("Segoe UI", 9, "bold"), padx=10, pady=6,
                            relief="flat", highlightbackground="#222240", highlightthickness=1)
        cfg.pack(fill="x", padx=16, pady=(8, 6))

        row1 = tk.Frame(cfg, bg=BG)
        row1.pack(fill="x", pady=4)
        tk.Label(row1, text="Výstupný priečinok:", bg=BG, fg="#888").pack(side="left")
        tk.Entry(row1, textvariable=self._output_dir, bg=ENTRY_BG, fg="white",
                 insertbackground="white", relief="flat", width=40).pack(side="left", padx=8, fill="x", expand=True)
        btn(row1, text="...", command=self._browse,
            bg=ENTRY_BG, fg="white", padx=6).pack(side="left")

        row2 = tk.Frame(cfg, bg=BG)
        row2.pack(fill="x", pady=4)
        tk.Label(row2, text="Dátum začiatku:", bg=BG, fg="#888").pack(side="left")
        self._start_var = tk.StringVar(value=datetime.date.today().isoformat())
        tk.Entry(row2, textvariable=self._start_var, width=12,
                 bg=ENTRY_BG, fg="white", insertbackground="white", relief="flat").pack(side="left", padx=8)
        tk.Label(row2, text="Videí/deň min:", bg=BG, fg="#888").pack(side="left", padx=(16, 0))
        self._vmin = tk.IntVar(value=1)
        tk.Spinbox(row2, from_=1, to=5, textvariable=self._vmin, width=3,
                   bg=ENTRY_BG, fg="white", buttonbackground=ENTRY_BG, relief="flat").pack(side="left", padx=4)
        tk.Label(row2, text="max:", bg=BG, fg="#888").pack(side="left")
        self._vmax = tk.IntVar(value=3)
        tk.Spinbox(row2, from_=1, to=5, textvariable=self._vmax, width=3,
                   bg=ENTRY_BG, fg="white", buttonbackground=ENTRY_BG, relief="flat").pack(side="left", padx=4)

        self.orig_var = tk.BooleanVar(value=True)
        tk.Checkbutton(cfg, text="Upraviť aj originálne videá (len GPS + metadáta – kvalita sa nemení)",
                       variable=self.orig_var, bg=BG, fg="#aaa", selectcolor=ENTRY_BG,
                       activebackground=BG, font=("Segoe UI", 9)
                       ).pack(anchor="w", pady=(6, 0))

        self._info_var = tk.StringVar(value="")
        tk.Label(cfg, textvariable=self._info_var, bg=BG, fg="#4da3ff",
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))

        # ── Generate buttons ──
        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=6)
        self._gen_btn = btn(btn_row, text="⚡ Generovať rozvrh",
                            command=self._generate,
                            bg=ACCENT, fg="white", font=("Segoe UI", 11, "bold"),
                            padx=12, pady=10)
        self._gen_btn.pack(side="left", fill="x", expand=True)
        self._gen_btn2 = btn(btn_row, text="⚡ Generovať + Server",
                             command=self._generate_and_serve,
                             bg=GREEN, fg="white", font=("Segoe UI", 11, "bold"),
                             padx=12, pady=10)
        self._gen_btn2.pack(side="left", fill="x", expand=True, padx=(6, 0))
        btn(btn_row, text="Zobraziť rozvrh (preview)", command=self._preview,
            bg=ENTRY_BG, fg="white", pady=6).pack(fill="x", pady=(6, 0))

        # ── Progress ──
        self._prog_var = tk.DoubleVar(value=0)
        self._prog = ttk.Progressbar(self, variable=self._prog_var, maximum=100)
        self._prog.pack(fill="x", padx=16, pady=(4, 0))

        tk.Label(self, text="Log:", bg=BG, fg="#555").pack(anchor="w", padx=16)
        self._log_box = scrolledtext.ScrolledText(self, height=12, state="disabled",
                                                   bg="#060610", fg="#00ff88",
                                                   font=("Courier", 8))
        self._log_box.pack(fill="both", expand=True, padx=16, pady=(2, 12))

    def _browse(self):
        p = filedialog.askdirectory()
        if p: self._output_dir.set(p)

    def _log(self, msg):
        self._log_box.config(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.config(state="disabled")
        self.update_idletasks()

    def _generate_and_serve(self):
        self._generate()
        if self.on_server_start:
            self.on_server_start()

    def _preview(self):
        videos  = self.get_videos()
        devices = self.get_devices()
        if not videos or not devices:
            messagebox.showinfo("Preview", "Najprv pridaj videá a zariadenia."); return
        try:
            start = datetime.date.fromisoformat(self._start_var.get())
        except ValueError:
            messagebox.showerror("Chyba", "Neplatný dátum (YYYY-MM-DD)."); return
        schedule = make_schedule(len(videos), len(devices),
                                 self._vmin.get(), self._vmax.get(), start)
        lines = [f"{'Dátum':<13} " + "  ".join(f"{d['name'][:12]:<12}" for d in devices)]
        lines.append("-" * (13 + 14 * len(devices)))
        for date, assignments in schedule[:20]:
            row = f"{date.isoformat():<13} "
            for di, dev in enumerate(devices):
                vids = assignments.get(di, [])
                row += f"{','.join(str(v+1) for v in vids):<14}"
            lines.append(row)
        if len(schedule) > 20:
            lines.append(f"... (+{len(schedule)-20} dní)")
        lines.append(f"\nSpolu: {len(schedule)} dní  ·  "
                     f"{len(videos)*len(devices)} kópií celkovo")
        win = tk.Toplevel(self)
        win.title("Preview rozvrhu")
        win.configure(bg=BG)
        txt = scrolledtext.ScrolledText(win, width=80, height=30,
                                         bg="#0a0a14", fg="#0f0",
                                         font=("Courier", 9))
        txt.pack(padx=10, pady=10)
        txt.insert("1.0", "\n".join(lines))
        txt.config(state="disabled")

    def _generate(self):
        videos  = self.get_videos()
        devices = self.get_devices()
        if not videos:
            messagebox.showwarning("Chýbajú videá", "Pridaj videá v záložke Videá."); return
        if not devices:
            messagebox.showwarning("Chýbajú zariadenia", "Pridaj zariadenia."); return
        try:
            start = datetime.date.fromisoformat(self._start_var.get())
        except ValueError:
            messagebox.showerror("Chyba", "Neplatný dátum (YYYY-MM-DD)."); return

        if len(devices) > len(videos):
            self._log(f"⚠  {len(devices)} zariadení, ale len {len(videos)} videí – "
                      f"rozvrh pokryje prvých {min(len(devices), len(videos))} zariadení.")

        if self.orig_var.get() and not check_tool("exiftool"):
            messagebox.showerror("Chýba exiftool",
                                 "Pre úpravu originálov (GPS + metadáta) je potrebný exiftool v PATH.")
            return

        out_dir = self._output_dir.get().strip()
        os.makedirs(out_dir, exist_ok=True)

        schedule = make_schedule(len(videos), len(devices),
                                 self._vmin.get(), self._vmax.get(), start)
        self._schedule = schedule

        # Update server state
        _srv["schedule"]   = schedule
        _srv["devices"]    = devices
        _srv["videos"]     = videos
        _srv["output_dir"] = out_dir

        # Save schedule.json
        with open(os.path.join(out_dir, "schedule.json"), "w") as f:
            json.dump(schedule_to_json(schedule, devices, videos), f, indent=2, ensure_ascii=False)

        total = sum(len(vids) for _, day in schedule for vids in day.values())
        if self.orig_var.get():
            total += len(videos)
        self._info_var.set(f"{len(schedule)} dní · {total} súborov · spracúvam...")
        self._gen_btn.config(state="disabled")
        self._gen_btn2.config(state="disabled")
        self._cancelled = False

        def worker():
            done = 0
            try:
                for date, assignments in schedule:
                    for di, vid_idxs in assignments.items():
                        dev = devices[di]
                        for vi in vid_idxs:
                            if self._cancelled: return
                            src = videos[vi]
                            stem, ext = os.path.splitext(os.path.basename(src))
                            fname = f"{stem}_x_{di+1}{ext}"
                            day_dir = os.path.join(out_dir, dev["name"], date.isoformat())
                            out_path = os.path.join(day_dir, fname)
                            self._log(f"[{done+1}/{total}] {dev['name']} / {date.isoformat()} / {fname}")
                            spoof_video(src, out_path,
                                        dev["lat"], dev["lon"], dev["jitter"],
                                        dev["make"], dev["model"],
                                        self._log)
                            done += 1
                            self._prog_var.set(done / total * 100)

                # Originály: len GPS + metadáta, bez zmeny kvality
                if self.orig_var.get() and videos:
                    dev0 = devices[0]
                    self._log("\nUpravujem originály (GPS + metadáta, kvalita sa nemení)...")
                    for vi, src in enumerate(videos, 1):
                        if self._cancelled: return
                        self._log(f"[{done+1}/{total}] originál {os.path.basename(src)}")
                        update_original_meta(src, dev0["lat"], dev0["lon"], dev0["jitter"],
                                             dev0["make"], dev0["model"], self._log)
                        done += 1
                        self._prog_var.set(done / total * 100)

                self._log(f"\n✓ Hotovo! {done} súborov (kópie + originály) v {out_dir}")
                self._info_var.set(f"✓ {done} súborov vygenerovaných/upravených.")
                messagebox.showinfo("Hotovo", f"Spracovaných {done} súborov.\n{out_dir}")
            except Exception as e:
                self._log(f"✗ Chyba: {e}")
                messagebox.showerror("Chyba", str(e))
            finally:
                self._gen_btn.config(state="normal")
                self._gen_btn2.config(state="normal")

        threading.Thread(target=worker, daemon=True).start()
# ─── Planner: Server / QR Tab ─────────────────────────────────────────────────

class ServerTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self._running = False
        self._thread  = None

        self.step_bar = StepBar(self, 3)
        self.step_bar.pack(fill="x", padx=16, pady=(12, 2))

        tk.Label(self, text="Spusti lokálny server → otvor QR kód na mobile → stiahni videá.",
                 bg=BG, fg="#666", font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(12, 8))

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", padx=16, pady=(0, 10))
        self._toggle_btn = btn(row, text="▶ Spustiť server", command=self._toggle,
                               bg=GREEN, fg="white", font=("Segoe UI", 11, "bold"),
                               padx=20, pady=10)
        self._toggle_btn.pack(side="left")
        self._status_var = tk.StringVar(value="Server nie je spustený.")
        tk.Label(row, textvariable=self._status_var, bg=BG, fg="#555",
                 font=("Segoe UI", 9)).pack(side="left", padx=16)

        self._url_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._url_var, bg=BG, fg="#4da3ff",
                 font=("Segoe UI", 11, "bold")).pack(pady=(0, 12))

        # QR frame (scrollable)
        self._qr_canvas = tk.Canvas(self, bg=BG, highlightthickness=0)
        qr_sb = ttk.Scrollbar(self, orient="vertical", command=self._qr_canvas.yview)
        self._qr_inner = tk.Frame(self._qr_canvas, bg=BG)
        self._qr_inner.bind("<Configure>",
            lambda e: self._qr_canvas.configure(scrollregion=self._qr_canvas.bbox("all")))
        self._qr_canvas.create_window((0, 0), window=self._qr_inner, anchor="nw")
        self._qr_canvas.configure(yscrollcommand=qr_sb.set)
        self._qr_canvas.pack(side="left", fill="both", expand=True, padx=16)
        qr_sb.pack(side="right", fill="y")
        self._qr_images = []  # keep refs

    def start_now(self):
        if not self._running:
            self._start()

    def _toggle(self):
        if not self._running:
            self._start()
        else:
            self._stop()

    def _start(self):
        self._thread = threading.Thread(target=start_server, daemon=True)
        self._thread.start()
        self._running = True
        ip = get_local_ip()
        url = f"http://{ip}:{SERVER_PORT}"
        self._url_var.set(url)
        self._status_var.set(f"Server beží na {url}")
        self._toggle_btn.config(text="■ Zastaviť server", bg=RED)
        self._show_qr_codes(url)

    def _stop(self):
        threading.Thread(target=stop_server, daemon=True).start()
        self._running = False
        self._status_var.set("Server zastavený.")
        self._url_var.set("")
        self._toggle_btn.config(text="▶ Spustiť server", bg=GREEN)
        for w in self._qr_inner.winfo_children(): w.destroy()
        self._qr_images.clear()

    def _show_qr_codes(self, base_url):
        for w in self._qr_inner.winfo_children(): w.destroy()
        self._qr_images.clear()
        devices = _srv["devices"]
        if not devices:
            tk.Label(self._qr_inner,
                     text="Žiadne zariadenia. Generuj rozvrh v záložke Rozvrh.",
                     bg=BG, fg="#444").pack(pady=20)
            return
        for i, dev in enumerate(devices):
            url = f"{base_url}/device/{i}"
            card = tk.Frame(self._qr_inner, bg=CARD_BG, padx=12, pady=10,
                            highlightbackground="#222240", highlightthickness=1)
            card.pack(fill="x", pady=6)
            tk.Label(card, text=f"📱  {dev['name']}", bg=CARD_BG, fg="white",
                     font=("Segoe UI", 11, "bold")).pack(anchor="w")
            tk.Label(card, text=url, bg=CARD_BG, fg="#4da3ff",
                     font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 6))
            if QR_AVAILABLE:
                qr = qrcode.make(url)
                qr = qr.resize((180, 180))
                img = ImageTk.PhotoImage(qr)
                self._qr_images.append(img)
                tk.Label(card, image=img, bg=CARD_BG).pack(anchor="w")
            else:
                tk.Label(card, text="(nainštaluj qrcode[pil] pre QR kódy)",
                         bg=CARD_BG, fg="#555", font=("Segoe UI", 8)).pack(anchor="w")


# ─── Google Drive Tab (rclone) ────────────────────────────────────────────────

class DriveTab(tk.Frame):
    def __init__(self, parent, get_output_dir):
        super().__init__(parent, bg=BG)
        self.get_output_dir = get_output_dir
        self._busy = False

        self.step_bar = StepBar(self, 4)
        self.step_bar.pack(fill="x", padx=16, pady=(12, 2))

        tk.Label(self,
                 text="Nahraj vygenerovaný rozvrh na Google Drive (rclone).\n"
                      "Štruktúra v Drive: CaPPy/<názov>/<zariadenie>/<dátum>/<video>.mp4",
                 bg=BG, fg="#888", font=("Segoe UI", 9), justify="left"
                 ).pack(anchor="w", padx=16, pady=(12, 6))

        self._status_var = tk.StringVar(value="Kontrolujem rclone...")
        tk.Label(self, textvariable=self._status_var, bg=BG, fg="#4da3ff",
                 font=("Segoe UI", 9)).pack(anchor="w", padx=16)

        cfg = tk.Frame(self, bg=BG)
        cfg.pack(fill="x", padx=16, pady=(10, 6))
        row1 = tk.Frame(cfg, bg=BG)
        row1.pack(fill="x", pady=4)
        tk.Label(row1, text="Remote (rclone):", bg=BG, fg="#888").pack(side="left")
        self.remote_var = tk.StringVar(value="gdrive")
        tk.Entry(row1, textvariable=self.remote_var, width=20,
                 bg=ENTRY_BG, fg="white", insertbackground="white", relief="flat").pack(side="left", padx=8)
        tk.Label(row1, text="Cieľ v Drive:", bg=BG, fg="#888").pack(side="left", padx=(16, 0))
        self.target_var = tk.StringVar(value="CaPPy")
        tk.Entry(row1, textvariable=self.target_var, width=24,
                 bg=ENTRY_BG, fg="white", insertbackground="white", relief="flat").pack(side="left", padx=8)

        btn_row = tk.Frame(self, bg=BG)
        btn_row.pack(fill="x", padx=16, pady=(4, 8))
        self._up_btn = btn(btn_row, text="⬆  Nahrať na Google Drive",
                           command=self._upload, bg=ACCENT, fg="white",
                           font=("Segoe UI", 11, "bold"), padx=16, pady=10)
        self._up_btn.pack(side="left")
        btn(btn_row, text="Nastaviť rclone config...", command=self._open_config,
            bg=ENTRY_BG, fg="white", padx=10, pady=6).pack(side="left", padx=6)
        btn(btn_row, text="Stiahnuť rclone", command=lambda: webbrowser.open("https://rclone.org/downloads/"),
            bg=ENTRY_BG, fg="white", padx=10, pady=6).pack(side="left", padx=6)

        tk.Label(self, text="Log:", bg=BG, fg="#555").pack(anchor="w", padx=16)
        self._log_box = scrolledtext.ScrolledText(self, height=14, state="disabled",
                                                   bg="#060610", fg="#00ff88",
                                                   font=("Courier", 8))
        self._log_box.pack(fill="both", expand=True, padx=16, pady=(2, 12))

        self._check()

    def _check(self):
        if not check_tool("rclone"):
            self._status_var.set(
                "⚠  rclone nenájdený – klikni „Stiahnuť rclone“ alebo spusti:  winget install Rclone.Rclone")
            self._up_btn.config(state="disabled")
            return
        r = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True)
        remotes = [x.strip() for x in r.stdout.splitlines() if x.strip()]
        self._status_var.set(
            f"✓ rclone OK  ·  remotes: {', '.join(remotes) or 'žiadne (spusti rclone config)'}")
        self._up_btn.config(state="normal")

    def _log(self, msg):
        self._log_box.config(state="normal")
        self._log_box.insert("end", msg + "\n")
        self._log_box.see("end")
        self._log_box.config(state="disabled")
        self.update_idletasks()

    def _open_config(self):
        try:
            subprocess.Popen(["cmd", "/K", "rclone", "config"],
                             creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        except Exception as e:
            messagebox.showerror("Chyba", str(e))
            return
        messagebox.showinfo("rclone config",
                            "V novom okne vyber: n → rclone config → 1) New remote → n → "
                            "name: gdrive → Storage: 18) Google Drive → client_id/secret nechaj prázdne → "
                            "scope: 1 → service_account: n →  Open browser... → prihlás sa do Google → "
                            "✓. Potom okno zatvor.")
        threading.Thread(target=self._check, daemon=True).start()

    def _upload(self):
        if self._busy:
            return
        remote = self.remote_var.get().strip().rstrip(":")
        target = self.target_var.get().strip().strip("/")
        src = self.get_output_dir()
        if not src or not os.path.isdir(src):
            messagebox.showwarning("Prázdne", "Najprv vygeneruj rozvrh (záložka Rozvrh).")
            return
        if not remote:
            messagebox.showwarning("Chýba remote", "Zadaj názov rclone remote.")
            return
        if not check_tool("rclone"):
            messagebox.showerror("Chýba rclone", "Nainštaluj rclone a nastav config.")
            return
        r = subprocess.run(["rclone", "listremotes"], capture_output=True, text=True)
        remotes = [x.strip() for x in r.stdout.splitlines() if x.strip()]
        if not any(x.rstrip(":") == remote for x in remotes):
            messagebox.showwarning(
                "Remote nenájdený",
                f"rclone nemá remote '{remote}'. Nájdené: {', '.join(remotes) or 'žiadne'}.\n"
                f"Klikni „Nastaviť rclone config...“ a pridaj Google Drive remote.")
            return
        dest = f"{remote}:{target}/{os.path.basename(os.path.normpath(src))}"
        self._busy = True
        self._up_btn.config(state="disabled")
        threading.Thread(target=self._worker, args=(src, dest), daemon=True).start()

    def _worker(self, src, dest):
        self._log(f"rclone copy {src}  →  {dest}")
        cmd = ["rclone", "copy", src, dest, "-v", "--transfers", "4",
               "--stats", "5s", "--stats-one-line"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace")
        for line in p.stdout:
            line = line.rstrip()
            if line:
                self._log(line)
        p.wait()
        if p.returncode == 0:
            self._log(f"\n✓ Hotovo – nahraté do {dest}")
            messagebox.showinfo("Hotovo", f"Rozvrh nahratý do Google Drive:\n{dest}")
        else:
            self._log(f"\n✗ rclone zlyhal (exit {p.returncode})")
            messagebox.showerror("Chyba", "rclone zlyhal.\nDetaily v logu.")
        self._up_btn.config(state="normal")
        self._busy = False


# ─── Startup: kontrola a auto-inštalácia závislostí ───────────────────────────

PIP_PACKAGES = [
    ("yt_dlp",        "yt-dlp",       "sťahovanie reelov"),
    ("tkinterdnd2",   "tkinterdnd2",  "drag & drop"),
    ("tkintermapview","tkintermapview","interaktívna mapa"),
    ("qrcode",        "qrcode[pil]",  "QR kódy"),
]

WINGET_TOOLS = [
    ("ffmpeg",    "Gyan.FFmpeg",        "spracovanie videí"),
    ("exiftool",  "OliverBetz.Exiftool","metadáta / fingerprint"),
    ("rclone",    "Rclone.Rclone",      "Google Drive upload"),
]

TOOL_PAGES = {
    "ffmpeg":   "https://www.gyan.dev/ffmpeg/builds/",
    "exiftool": "https://exiftool.org/",
    "rclone":   "https://rclone.org/downloads/",
}


def import_ok(modname):
    try:
        importlib.import_module(modname)
        return True
    except ImportError:
        return False


def _progress_window(root, title, text):
    win = tk.Toplevel(root)
    win.title(title)
    win.configure(bg=BG)
    win.resizable(False, False)
    win.grab_set()
    tk.Label(win, text=text, bg=BG, fg="white", font=("Segoe UI", 10),
             padx=20, pady=14, wraplength=440, justify="left").pack()
    tk.Label(win, text="Prebieha... môže to chvíľu trvať",
             bg=BG, fg="#888", font=("Segoe UI", 8)).pack(pady=(0, 14))
    return win


def install_pip(root, names):
    win = _progress_window(root, "Inštalácia knižníc", "Inštalujem: " + ", ".join(names))
    holder = {"ok": False, "err": ""}

    def worker():
        try:
            # pip nemusí byť v Pythone prítomný (napr. MSYS2) – najprv ho doinštalujeme
            if not import_ok("pip"):
                subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                               capture_output=True, text=True)
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-U",
                                "--disable-pip-version-check", "--no-input", *names],
                               capture_output=True, text=True)
            holder["ok"] = r.returncode == 0
            holder["err"] = ((r.stdout or "") + "\n" + (r.stderr or ""))[-1200:]
        except Exception as e:
            holder["ok"] = False
            holder["err"] = str(e)
        # Pozor: nikdy sa tu nedotýkame tkinter – to rieši len poll() v hlavnom vlákne

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def poll():
        if t.is_alive():
            win.after(100, poll)
        else:
            win.destroy()

    win.after(100, poll)
    root.wait_window(win)
    return holder["ok"], holder["err"]


def install_winget(root, exe, pkgid):
    win = _progress_window(root, f"Inštalácia {exe}", f"Inštalujem '{exe}' cez winget...")
    holder = {"ok": False, "err": ""}

    def worker():
        try:
            cmd = ["winget", "install", "--id", pkgid,
                   "--accept-source-agreements", "--accept-package-agreements"]
            r = subprocess.run(cmd, capture_output=True, text=True)
            holder["ok"] = r.returncode == 0
            holder["err"] = ((r.stdout or "") + "\n" + (r.stderr or ""))[-1200:]
        except Exception as e:
            holder["ok"] = False
            holder["err"] = str(e)
        # Pozor: nikdy sa tu nedotýkame tkinter – to rieši len poll() v hlavnom vlákne

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def poll():
        if t.is_alive():
            win.after(100, poll)
        else:
            win.destroy()

    win.after(100, poll)
    root.wait_window(win)
    return holder["ok"], holder["err"]


def ensure_tool_on_path(exe):
    """Ak sa nástroj po winget inštalácii nenašiel v PATH, nájde .exe a pridá do user PATH."""
    la = os.environ.get("LOCALAPPDATA", "")
    bases = [os.path.join(la, "Microsoft", "WinGet"),
             os.path.join(la, "Programs")]
    found = []
    for base in bases:
        if not os.path.isdir(base):
            continue
        for root, _, files in os.walk(base):
            for f in files:
                if f.lower() == exe + ".exe":
                    found.append(root)
                    break
    if not found:
        return False
    d = found[0]
    env = dict(os.environ, _CAPPY_PATH_D=d)
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    "$d=$env:_CAPPY_PATH_D; "
                    "$p=[Environment]::GetEnvironmentVariable('Path','User'); "
                    "if($p -notlike '*'+$d+'*'){ "
                    "[Environment]::SetEnvironmentVariable('Path', ($p.TrimEnd(';')+';'+$d), 'User') }"],
                   capture_output=True, env=env)
    os.environ["Path"] = os.environ.get("Path", "") + ";" + d
    return True


def restart_app():
    subprocess.Popen([sys.executable, os.path.abspath(__file__)])
    os._exit(0)


def run_dep_check(root):
    """Kontrola závislostí pred štartom – vráti True, ak treba reštartovať appku."""
    restart = False

    missing = [p for p in PIP_PACKAGES if not import_ok(p[0])]
    if missing:
        text = "\n".join(f"• {p[1]}  ({p[2]})" for p in missing)
        if messagebox.askyesno(
                "Chýbajú knižnice",
                f"Pre plnú funkčnosť chýbajú tieto Python knižnice:\n\n{text}\n\n"
                "Nainštalovať ich teraz cez pip?\n\n"
                "(Ak zvolíš Nie, niektoré funkcie nebudú dostupné.)"):
            ok, err = install_pip(root, [p[1] for p in missing])
            if ok:
                restart = True
                messagebox.showinfo("Hotovo",
                                    "Knižnice sú nainštalované. Appka sa reštartuje.")
            else:
                messagebox.showerror("Inštalácia zlyhala",
                                     "pip install zlyhal.\nSkús ručne:\n"
                                     f"python -m pip install -U {' '.join(p[1] for p in missing)}"
                                     f"\n\n{err}")

    for exe, pkgid, desc in WINGET_TOOLS:
        if check_tool(exe):
            continue
        if messagebox.askyesno(
                "Chýba nástroj",
                f"Chýba '{exe}' ({desc}).\n"
                f"Chceš ho nainštalovať cez winget (id: {pkgid})?\n\n"
                "(Ak nemáš winget, otvorí sa stránka na ručné stiahnutie.)"):
            ok, err = install_winget(root, exe, pkgid)
            if not ok:
                messagebox.showerror("Inštalácia zlyhala",
                                     f"winget install zlyhal:\n{err}\n\n"
                                     "Otvorí sa stránka na ručné stiahnutie.")
                webbrowser.open(TOOL_PAGES[exe])
                continue
            if not check_tool(exe):
                ensure_tool_on_path(exe)
            if check_tool(exe):
                messagebox.showinfo("OK", f"✓ '{exe}' je dostupný.")
            else:
                messagebox.showwarning(
                    "Pozor",
                    f"'{exe}' sa nenašiel v PATH. Reštartuj appku, PATH sa doplní.")
                restart = True

    return restart


# ── Main App ──────────────────────────────────────────────────────────────────

class PlannerApp:
    def __init__(self, root):
        self.root = root
        root.title("CaPPy Tools")
        root.geometry("780x860")
        root.configure(bg=BG)

        # ── Hlavička ──
        hdr = tk.Frame(root, bg=BG)
        hdr.pack(fill="x", padx=18, pady=(14, 2))
        tk.Label(hdr, text="📦  CaPPy Tools", font=("Segoe UI", 19, "bold"),
                 bg=BG, fg="white").pack(anchor="w")
        tk.Label(hdr, text="Metadata Cleaner · Reels Downloader · Planner pre viac zariadení",
                 bg=BG, fg="#4da3ff", font=("Segoe UI", 9)).pack(anchor="w", pady=(2, 0))

        # ── Stav nástrojov ──
        tools = tk.Frame(root, bg="#0b0b16")
        tools.pack(fill="x", padx=18, pady=(10, 4))
        tk.Label(tools, text="Nástroje:", bg="#0b0b16", fg="#556",
                 font=("Segoe UI", 8)).pack(side="left", padx=(10, 8))
        for name in ("ffmpeg", "exiftool", "yt-dlp", "rclone"):
            tool_badge(tools, name, check_tool(name)).pack(side="left", padx=(0, 6))

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background="#1a1a2e", foreground="#888",
                        padding=(14, 5), font=("Segoe UI", 10))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)],
                  foreground=[("selected", "white")])
        style.configure("TScrollbar", background=ENTRY_BG, troughcolor=BG, borderwidth=0)

        self.nb = ttk.Notebook(root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=4)

        self.vid_tab = VideoTab(self.nb, on_change=self._on_change)
        self.dev_tab = DevicesTab(self.nb, on_change=self._on_change)
        self.sch_tab = ScheduleTab(self.nb,
                                    get_videos=lambda: self.vid_tab.videos,
                                    get_devices=lambda: self.dev_tab.devices)
        self.srv_tab = ServerTab(self.nb)
        self.drive_tab = DriveTab(self.nb,
                                   get_output_dir=lambda: _srv["output_dir"])

        self.nb.add(MetadataTab(self.nb), text="  Metadata Cleaner  ")
        self.nb.add(DownloaderTab(self.nb), text="  Reels Downloader  ")
        self.nb.add(self.vid_tab, text="  Videá  ")
        self.nb.add(self.dev_tab, text="  Zariadenia  ")
        self.nb.add(self.sch_tab, text="  Rozvrh  ")
        self.nb.add(self.srv_tab, text="  Server / QR  ")
        self.nb.add(self.drive_tab, text="  Drive  ")

        self.sch_tab.on_server_start = self._generate_and_serve
        for tab in (self.vid_tab, self.dev_tab, self.sch_tab, self.srv_tab, self.drive_tab):
            tab.step_bar.set_nav(self._goto_planner)

    def _generate_and_serve(self):
        self.srv_tab.start_now()
        self.nb.select(self.srv_tab)

    def _goto_planner(self, idx):
        planner_tabs = [self.vid_tab, self.dev_tab, self.sch_tab, self.srv_tab, self.drive_tab]
        if 0 <= idx < len(planner_tabs):
            self.nb.select(planner_tabs[idx])

    def _on_change(self):
        v = len(self.vid_tab.videos)
        d = len(self.dev_tab.devices)
        if v and d:
            msg = f"{v} videí  ×  {d} zariadení  =  {v*d} kópií celkovo"
        else:
            msg = f"{v} videí  ·  {d} zariadení"
        self.vid_tab.summary_var.set(msg)
        self.dev_tab.summary_var.set(msg)
        self.sch_tab._info_var.set(msg)


def main():
    root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
    try:
        if run_dep_check(root):
            restart_app()
    except Exception:
        pass
    PlannerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
