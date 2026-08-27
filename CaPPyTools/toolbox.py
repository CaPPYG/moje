#!/usr/bin/env python3
"""
Toolbox: Metadata Cleaner + Reels Downloader
----------------------------------------------
Jedna lokalna appka, dve zalozky.

Zalozka 1 - Metadata Cleaner:
  • Drag & drop alebo vyber suboru
  • Nastav GPS polohu (map, adresa, zoznam miest)
  • Randomizacne filtre (saturacia, kontrast, jas, hue, zoom, denoise...)
  • Vymaze metadata, zapise GPS, aplikuje filtre, ulozi kopiu

Zalozka 2 - Reels Downloader:
  • Zoznam linkov -> stiahne vsetky cez yt-dlp

Potrebne nastroje:
  pip install -U yt-dlp tkinterdnd2 tkintermapview
  + ffmpeg a exiftool v PATH
"""

import os, re, random, shutil, subprocess, threading, uuid, datetime
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

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

# ─── Constants ────────────────────────────────────────────────────────────────

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff", ".bmp"}

BG       = "#0e0e1a"
CARD_BG  = "#13131f"
ACCENT   = "#2563eb"
ENTRY_BG = "#1a1a2e"

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
            e.bind("<FocusIn>",  lambda ev, v=var, ew=e: (ew.config(fg="white"),))
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
        # hide device combo when "random" (device is picked randomly anyway)
        # but keep it visible for "same" and "per_copy"
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
            "title":         self.title_var.get(),
            "artist":        self.artist_var.get(),
            "comment":       self.comment_var.get(),
            "random_date":   self.rand_date_var.get(),
            "random_uid":    self.rand_uid_var.get(),
            "no_ffmpeg_sig": self.no_sig_var.get(),
        }


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
        self.lat_var = tk.StringVar(value="48.591000")
        self.lon_var = tk.StringVar(value="19.126400")
        self.marker = None

        # ── Toggle ──
        tog_row = tk.Frame(self, bg=BG)
        tog_row.pack(fill="x", pady=(0, 8))
        self.enabled_var = tk.BooleanVar(value=True)
        tk.Checkbutton(tog_row, text="Zapisať GPS do výstupu", variable=self.enabled_var,
                       bg=BG, fg="white", selectcolor=ENTRY_BG,
                       activebackground=BG, font=("Segoe UI", 9)).pack(side="left")

        # ── City preset + Reset ──
        city_row = tk.Frame(self, bg=BG)
        city_row.pack(fill="x", pady=(0, 8))
        tk.Label(city_row, text="Mesto:", bg=BG, fg="#888",
                 font=("Segoe UI", 9)).pack(side="left")
        self.city_var = tk.StringVar(value=CITIES[0][0])
        city_names = [c[0] for c in CITIES]
        self.city_combo = ttk.Combobox(city_row, values=city_names,
                                        textvariable=self.city_var,
                                        width=28, state="readonly")
        self.city_combo.pack(side="left", padx=8)
        self.city_combo.bind("<<ComboboxSelected>>", self._on_city)
        tk.Button(city_row, text="Reset", command=self._on_reset,
                  bg=ENTRY_BG, fg="white", relief="flat", padx=8).pack(side="left")

        # ── Map widget (optional) ──
        if MAP_AVAILABLE:
            self.map_widget = tkintermapview.TkinterMapView(
                self, width=520, height=200, corner_radius=4)
            self.map_widget.pack(pady=(0, 8), fill="x")
            self.map_widget.set_position(48.591, 19.1264)
            self.map_widget.set_zoom(5)
            self.marker = self.map_widget.set_marker(48.591, 19.1264)
            self.map_widget.add_left_click_map_command(self._on_map_click)
        else:
            tk.Label(self, text="(Nainštaluj tkintermapview pre interaktívnu mapu)",
                     bg=BG, fg="#444", font=("Segoe UI", 8)).pack(pady=(0, 6))

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
        tk.Button(bar, text="All On", command=self._all_on,
                  bg=ENTRY_BG, fg="white", relief="flat", padx=8).pack(side="right", padx=2)
        tk.Button(bar, text="Reset", command=self._reset_all,
                  bg=ENTRY_BG, fg="white", relief="flat", padx=8).pack(side="right", padx=2)

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
        for fid, _, _, _, _, dmin, dmax, *_ in FILTER_DEFS:
            if fid in self.cards:
                self.cards[fid].set_enabled(_ := True)
                self.cards[fid].reset()
        # fix: reset uses default enabled state
        for fid, *_, on_def in [(f[0], *f[1:]) for f in FILTER_DEFS]:
            if fid in self.cards:
                self.cards[fid].set_enabled(FILTER_DEFS[[f[0] for f in FILTER_DEFS].index(fid)][-1])

    def get_states(self):
        return {fid: card.get_state() for fid, card in self.cards.items()}


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

        # ── Source Media ──
        src = tk.LabelFrame(p, text="  ⬆  Source Media", bg=BG, fg="white",
                            font=("Segoe UI", 10, "bold"), padx=10, pady=8,
                            relief="flat", highlightbackground="#222240", highlightthickness=1)
        src.pack(fill="x", padx=12, pady=(10, 6))

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
        tk.Button(btn_row, text="Vybrať súbor...", command=self.browse_file,
                  bg=ENTRY_BG, fg="white", relief="flat", padx=10, pady=4).pack(side="left")
        tk.Button(btn_row, text="Vybrať priečinok...", command=self.browse_folder,
              bg=ENTRY_BG, fg="white", relief="flat", padx=10, pady=4).pack(side="left", padx=(6, 0))
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

        self.proc_btn = tk.Button(
            bottom, text="⚡  Vyčistiť a spracovať",
            command=self.run_process, state="disabled",
            bg=ACCENT, fg="white",
            font=("Segoe UI", 11, "bold"), relief="flat", padx=20, pady=10)
        self.proc_btn.pack(fill="x")

        self.status_var = tk.StringVar(value="")
        tk.Label(bottom, textvariable=self.status_var, bg=BG, fg="#888",
                 wraplength=560, justify="left", font=("Segoe UI", 8)).pack(pady=(6, 0))

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
        states      = self.filters.get_states()
        fp_settings = self.fingerprint.get_settings()
        n_copies    = max(1, self.copies_var.get())
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
                        self._log(f"  ✓ {os.path.basename(out)}")

                summary = "\n".join(os.path.basename(p) for p in done)
                self._log(f"✓ Všetko hotovo ({len(done)} kópií).")
                messagebox.showinfo("Hotovo",
                    f"Vytvorených {len(done)} kópií:\n{summary}")
            except Exception as e:
                self._log(f"✗ Chyba: {e}")
                messagebox.showerror("Chyba", str(e))
            finally:
                self.proc_btn.config(state="normal")

        threading.Thread(target=worker, daemon=True).start()


# ─── Reels Downloader Tab ─────────────────────────────────────────────────────

def extract_links(raw):
    seen, result = set(), []
    for line in raw.splitlines():
        l = line.strip()
        if l and re.match(r"^https?://", l) and l not in seen:
            seen.add(l); result.append(l)
    return result


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
        tk.Button(folder_row, text="...", command=self._browse,
                  bg=ENTRY_BG, fg="white", relief="flat", padx=6).pack(side="left")

        ck_row = tk.Frame(self, bg=BG)
        ck_row.pack(fill="x", padx=16, pady=(0, 10))
        tk.Label(ck_row, text="Cookies from browser (voliteľné):",
                 bg=BG, fg="#888", font=("Segoe UI", 9)).pack(side="left")
        self.cookies_var = tk.StringVar()
        tk.Entry(ck_row, textvariable=self.cookies_var,
                 bg=ENTRY_BG, fg="white", insertbackground="white",
                 relief="flat", width=14).pack(side="left", padx=8)
        tk.Label(ck_row, text="napr. chrome / firefox",
                 bg=BG, fg="#444", font=("Segoe UI", 8)).pack(side="left")

        self.dl_btn = tk.Button(
            self, text="⬇  Stiahnuť všetko", command=self.start_download,
            bg=ACCENT, fg="white", font=("Segoe UI", 11, "bold"),
            relief="flat", padx=20, pady=10)
        self.dl_btn.pack(padx=16, pady=(0, 8), fill="x")

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

    def _run(self, links, out_folder):
        self._log(f"Spúšťam – {len(links)} linkov → {out_folder}\n")
        cookies = self.cookies_var.get().strip()
        ok = failed = 0
        for i, link in enumerate(links, 1):
            self._log(f"[{i}/{len(links)}]  {link}")
            cmd = ["yt-dlp",
                   "-o", os.path.join(out_folder, "%(uploader)s_%(id)s.%(ext)s"),
                   "--no-playlist"]
            if cookies:
                cmd += ["--cookies-from-browser", cookies]
            cmd.append(link)
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode == 0:
                ok += 1; self._log("  ✓ OK")
            else:
                failed += 1
                last = (r.stderr.strip().splitlines() or ["neznáma chyba"])[-1]
                self._log(f"  ✗ {last}")

        self._log(f"\nHotovo — ✓ {ok}  ✗ {failed}")
        self.dl_btn.config(state="normal")
        messagebox.showinfo("Hotovo",
                            f"Stiahnutých: {ok}\nZlyhalo: {failed}\nPriečinok: {out_folder}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
    root.title("Toolbox")
    root.geometry("780x860")
    root.configure(bg=BG)

    tk.Label(root, text="Toolbox",
             font=("Segoe UI", 14, "bold"), bg=BG, fg="white").pack(pady=(12, 0))
    tk.Label(root, text="beží lokálne  ·  ffmpeg  ·  exiftool  ·  yt-dlp",
             fg="#333355", bg=BG, font=("Segoe UI", 8)).pack(pady=(0, 6))

    style = ttk.Style()
    style.theme_use("default")
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background="#1a1a2e", foreground="#888",
                    padding=(14, 5), font=("Segoe UI", 10))
    style.map("TNotebook.Tab",
              background=[("selected", ACCENT)],
              foreground=[("selected", "white")])
    style.configure("TScrollbar", background=ENTRY_BG, troughcolor=BG, borderwidth=0)

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=8, pady=4)
    nb.add(MetadataTab(nb), text="   Metadata Cleaner   ")
    nb.add(DownloaderTab(nb), text="   Reels Downloader   ")

    root.mainloop()


if __name__ == "__main__":
    main()