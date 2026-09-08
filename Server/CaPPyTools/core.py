#!/usr/bin/env python3
"""
CaPPy Tools – core (čistý Python bez tkinteru).
Spoločné jadro pre desktop (cappy_tools.py) aj web appku (server.py).
"""
import os, re, random, shutil, subprocess, datetime, uuid

# ─── Konštanty ────────────────────────────────────────────────────────────────

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".tiff", ".bmp"}

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

# ─── Nástroje ─────────────────────────────────────────────────────────────────

def check_tool(name):
    return shutil.which(name) is not None

def dms_ref(v, pos, neg):
    return pos if v >= 0 else neg

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


# ─── Exiftool ─────────────────────────────────────────────────────────────────

def apply_fingerprint(out_path, fp, log):
    """Write device fingerprint metadata via exiftool."""
    if not fp.get("enabled"):
        return
    if not check_tool("exiftool"):
        raise RuntimeError("exiftool nie je nájdený v PATH.")
    log("Zapisujem device fingerprint (exiftool)...")

    cmd = ["exiftool", "-overwrite_original"]

    make, model = fp.get("make"), fp.get("model")
    if fp.get("mode") == "random":
        _, make, model = random.choice(DEVICES[1:])
    if make and model:
        cmd += [f"-Make={make}", f"-Model={model}",
                f"-DeviceMake={make}", f"-DeviceModel={model}"]

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

    if fp.get("random_uid"):
        uid = uuid.uuid4().hex.upper()
        cmd += [f"-ImageUniqueID={uid}", f"-MediaDataOffset=0"]

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


# ─── Planner: spoof one video per device ──────────────────────────────────────

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
    """Zmení LEN GPS a metadáta originálu – video stream sa nedotýka."""
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

# ─── Schedule algorithm ────────────────────────────────────────────────────────

def make_schedule(n_videos, n_devices, vmin, vmax, start_date):
    """
    Rozvrh s garanciou: v ten istý deň žiadne dve zariadenia nepostujú rovnaké
    originálne video. Každé zariadenie dostane VŠETKY videá presne raz.
    Vracia list (date, {dev_idx: [video_indices]}).
    """
    if n_videos < 1 or n_devices < 1:
        return []
    n_devices = min(n_devices, n_videos)
    offset = max(1, n_videos // n_devices)
    vmax_eff = min(vmax, offset)
    vmin_eff = min(vmin, vmax_eff)

    base = list(range(n_videos))
    random.shuffle(base)
    queues = []
    for i in range(n_devices):
        s = (i * offset) % n_videos
        queues.append(base[s:] + base[:s])

    schedule, positions, day_n = [], [0] * n_devices, 0
    while positions[0] < n_videos:
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


# ─── Frame / Audio Extractors + Cloaker ───────────────────────────────────────

def probe_duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                            path], capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except Exception:
        pass
    return None

def unique_path(path):
    stem, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(path):
        path = f"{stem}_{n}{ext}"
        n += 1
    return path

def extract_frames(src, out_dir, mode, value, fmt="jpg", quality=2, log=None):
    if not check_tool("ffmpeg"):
        raise RuntimeError("ffmpeg nie je nájdený v PATH.")
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    folder = unique_path(os.path.join(out_dir, f"frames_{stem}"))
    os.makedirs(folder, exist_ok=True)
    ext = ".png" if fmt == "png" else ".jpg"
    pat = os.path.join(folder, "frame_%04d" + ext)
    args = ["-q:v", str(quality)]
    if fmt == "png":
        args += ["-compression_level", "6"]

    if mode == "time":
        t = float(value)
        out = os.path.join(folder, f"frame_{t:.2f}s" + ext)
        cmd = ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", src,
               "-frames:v", "1"] + args + [out]
        if log: log("  " + " ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"ffmpeg zlyhal:\n{r.stderr[-1000:]}")
        return 1, folder

    if mode == "interval":
        interval = float(value)
        if interval <= 0:
            raise ValueError("Interval musí byť > 0.")
        vf = f"fps=1/{interval:.4f}"
    else:
        n = int(value)
        if n <= 0:
            raise ValueError("Počet frameov musí byť > 0.")
        dur = probe_duration(src)
        if not dur or dur <= 0:
            raise RuntimeError("Nepodarilo sa zistiť dĺžku videa (ffprobe).")
        vf = f"fps={n / dur:.6f}"

    cmd = ["ffmpeg", "-y", "-i", src, "-vf", vf] + args + [pat]
    if log: log("  " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg zlyhal:\n{r.stderr[-1000:]}")
    count = len([f for f in os.listdir(folder) if f.endswith(ext)])
    return count, folder

AUDIO_CODECS = {
    "mp3":  [".mp3", ["-c:a", "libmp3lame", "-b:a"]],
    "wav":  [".wav", ["-c:a", "pcm_s16le"]],
    "m4a":  [".m4a", ["-c:a", "aac", "-b:a"]],
    "ogg":  [".ogg", ["-c:a", "libvorbis", "-b:a"]],
    "flac": [".flac", ["-c:a", "flac"]],
}

def extract_audio(src, out_dir, fmt="mp3", bitrate="192k", log=None):
    if not check_tool("ffmpeg"):
        raise RuntimeError("ffmpeg nie je nájdený v PATH.")
    if fmt not in AUDIO_CODECS:
        raise ValueError(f"Neznámy formát: {fmt}")
    ext, codec = AUDIO_CODECS[fmt]
    os.makedirs(out_dir, exist_ok=True)
    stem = os.path.splitext(os.path.basename(src))[0]
    out = unique_path(os.path.join(out_dir, stem + ext))
    cmd = ["ffmpeg", "-y", "-i", src, "-map", "0:a:0", "-vn"]
    cmd += codec
    if len(codec) == 3:
        cmd.append(bitrate)
    cmd.append(out)
    if log: log("  " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg zlyhal:\n{r.stderr[-1000:]}")
    return out

def cloak_links(base_url, links):
    base = (base_url or "").strip().rstrip("/")
    out = []
    for ln in links:
        slug = str(ln.get("slug", "")).strip()
        if not slug:
            continue
        out.append({"slug": slug,
                    "cloak": f"{base}/c/{slug}",
                    "url": str(ln.get("url", "")).strip(),
                    "title": str(ln.get("title", "")).strip()})
    return out

def extract_links(raw):
    seen, result = set(), []
    for line in raw.splitlines():
        l = line.strip()
        if l and re.match(r"^https?://", l) and l not in seen:
            seen.add(l); result.append(l)
    return result



