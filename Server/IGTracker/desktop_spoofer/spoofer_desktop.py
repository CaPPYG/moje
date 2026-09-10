#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  IG TRACKER & PUBLISHER — DESKTOP REELS STUDIO v2.0
================================================================================
  GUI nastroj pre stiahnutie, upscaling, color grading a batch spoofing Reels.
  Zalozka 1: Batch Spoofing — vyberes priecinok, spustis pipeline
  Zalozka 2: Stahovat Reels — zadas URL, stiahne + spoofuje
"""

import os
import re
import sys
import glob
import time
import uuid
import random
import shutil
import datetime
import math
import subprocess
import threading
import queue
import concurrent.futures
import tempfile
import json
import ssl
import urllib.request
import urllib.parse
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─── Colors ──────────────────────────────────────────────────────────────────
BG_DARK   = "#0f1117"
BG_CARD   = "#1a1d27"
BG_CARD2  = "#20243a"
ACCENT    = "#7c5cfc"
ACCENT2   = "#fc5c7d"
ACCENT3   = "#56ccf2"
GREEN     = "#2dce89"
TEXT      = "#e8eaf0"
MUTED     = "#7b7fa0"
BORDER    = "#2d3254"
BTN_HOVER = "#6a48e8"

# ─── Devices ──────────────────────────────────────────────────────────────────
DEVICES = [
    ("Nothing", "Phone (2a)"),  # A065 (MediaTek Dimensity 7200 Pro)
    ("Samsung", "SM-S928B"),    # Galaxy S24 Ultra
    ("Samsung", "SM-S921B"),    # Galaxy S24
    ("Samsung", "SM-S911B"),    # Galaxy S23
    ("Google", "Pixel 9 Pro"),
    ("Google", "Pixel 8 Pro"),
    ("Apple", "iPhone 16 Pro"),
    ("Apple", "iPhone 15 Pro Max"),
    ("Apple", "iPhone 15"),
    ("OnePlus", "CPH2573"),
]


def resolve_device(device_str=None):
    """Vráti (make, model, software) pre zadaný reťazec alebo náhodné zariadenie."""
    if not device_str:
        make, model = random.choice(DEVICES)
        if make == "Nothing":
            return "Nothing", "A065", "Nothing OS 2.6 (Android 14)"
        return make, model, "Android 14"

    d = device_str.lower()
    if "nothing" in d or "2a" in d:
        return "Nothing", "A065", "Nothing OS 2.6 (Android 14)"
    elif "ultra" in d or "s928" in d:
        return "Samsung", "SM-S928B", "One UI 6.1 (Android 14)"
    elif "s24" in d or "s921" in d:
        return "Samsung", "SM-S921B", "One UI 6.1 (Android 14)"
    elif "s23" in d or "s911" in d:
        return "Samsung", "SM-S911B", "One UI 6.1 (Android 14)"
    elif "pixel" in d or "google" in d:
        return "Google", "Pixel 9 Pro", "Android 15"
    elif "iphone" in d or "apple" in d:
        return "Apple", "iPhone 16 Pro", "iOS 18.2"
    elif "oneplus" in d:
        return "OnePlus", "CPH2573", "OxygenOS 14"
    else:
        parts = device_str.strip().split(" ", 1)
        if len(parts) == 2:
            return parts[0], parts[1], "Android 14"
        return "Android", device_str.strip(), "Android 14"

CITIES_US = [
    ("Los Angeles (Downtown / DTLA), CA", 34.0407, -118.2468),
    ("Los Angeles (Hollywood & Sunset Blvd), CA", 34.0928, -118.3287),
    ("Los Angeles (Beverly Hills / Rodeo Dr), CA", 34.0696, -118.4053),
    ("Los Angeles (Santa Monica Pier), CA", 34.0099, -118.4960),
    ("Los Angeles (Venice Beach Boardwalk), CA", 33.9850, -118.4695),
    ("Los Angeles (West Hollywood / Sunset Strip), CA", 34.0900, -118.3617),
    ("Los Angeles (Griffith Observatory / Los Feliz), CA", 34.1184, -118.3004),
    ("Los Angeles (Malibu Beach / PCH), CA", 34.0259, -118.7798),
    ("Los Angeles (Century City), CA", 34.0577, -118.4140),
    ("Los Angeles (Silver Lake / Echo Park), CA", 34.0869, -118.2702),
    ("Las Vegas (The Strip / Bellagio Fountains), NV", 36.1126, -115.1767),
    ("Las Vegas (Caesars Palace / Colosseum), NV", 36.1162, -115.1745),
    ("Las Vegas (Downtown / Fremont Street), NV", 36.1699, -115.1438),
    ("Las Vegas (The Venetian & Palazzo), NV", 36.1212, -115.1697),
    ("Las Vegas (South Strip / Mandalay Bay), NV", 36.0919, -115.1761),
    ("Las Vegas (Arts District / 18b), NV", 36.1554, -115.1528),
    ("Las Vegas (Summerlin / Red Rock), NV", 36.1989, -115.3013),
    ("Las Vegas (Resorts World / North Strip), NV", 36.1337, -115.1668),
    ("Las Vegas (Wynn & Encore), NV", 36.1265, -115.1654),
    ("Las Vegas (Aria & Cosmopolitan), NV", 36.1098, -115.1761),
]
CITIES_SK = [
    ("Bratislava, SK", 48.1486, 17.1077),
    ("Kosice, SK", 48.7164, 21.2611),
    ("Zilina, SK", 49.2231, 18.7394),
    ("Banska Bystrica, SK", 48.7363, 19.1462),
    ("Trnava, SK", 48.3774, 17.5883),
]

VIDEO_EXTENSIONS    = {".mp4", ".mov", ".m4v", ".webm", ".avi"}
DEFAULT_VAULT_ID    = "1NyPnFW4O8NYd_BEzMf5c43XWQlr8zsSJ"


# ─── System helpers ───────────────────────────────────────────────────────────

def _init_paths():
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "tools", "realesrgan"),
        os.path.join(base, "tools"),
        os.path.join(base, "bin"),
    ]
    for c in candidates:
        if os.path.isdir(c) and c not in os.environ.get("PATH", ""):
            os.environ["PATH"] = c + os.pathsep + os.environ["PATH"]

_init_paths()


def has_tool(name):
    return shutil.which(name) is not None


def _probe_encoder(enc: str) -> bool:
    """Otestuje ci dany hardverovy enkoder skutocne funguje na tejto grafickej karte."""
    try:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=s=720x1280:d=0.04:rate=30", "-c:v", enc, "-f", "null", "-"]
        r = subprocess.run(cmd, capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:
        return False


def detect_encoder():
    """Použije vysoko kvalitný procesorový enkóder libx264 s CRF 18 pre vizuálne bezstratový export bez artefaktov."""
    return "libx264 (CPU - CRF 18 Multicore)", [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p"
    ]


def get_sharpen_filter():
    """Vráti AMD FidelityFX CAS 0.3 (Contrast Adaptive Sharpening) alebo unsharp fallback."""
    try:
        r = subprocess.run(["ffmpeg", "-h", "filter=cas"], capture_output=True, timeout=2)
        if r.returncode == 0:
            return "cas=0.3"
    except Exception:
        pass
    return "unsharp=5:5:0.6:5:5:0.0"


# Overené TOP univerzálne hodnoty pre maximálnu prirodzenosť a ľudské oko
BASE_EQ_FILTER = "eq=contrast=1.055:brightness=-0.007:gamma=0.97:saturation=1.035"


def build_spoof_filters(is_copy=False):
    """Vráti vyladený Cinematic EQ filter (alebo náhodný jitter pre kópie)."""
    if not is_copy:
        return BASE_EQ_FILTER
    return build_copy_jitter_filter()


def build_copy_jitter_filter():
    """Jemný jitter okolo 1.0 pre kópie z hlavného videa, aby bol každý hash pre algo unikátny a hodnoty zostali v TOP rozsahu."""
    cont   = random.uniform(0.992, 1.008)
    bright = random.uniform(-0.002, 0.002)
    gamma  = random.uniform(0.992, 1.008)
    sat    = random.uniform(0.992, 1.008)
    ct     = random.uniform(-0.006, 0.006)
    hue    = random.uniform(-0.5, 0.5)
    return (
        f"eq=contrast={cont:.4f}:brightness={bright:.4f}:gamma={gamma:.4f}:saturation={sat:.4f},"
        f"colorbalance=rs={ct:.4f}:gs=0:bs={-ct:.4f}:rm={ct/2:.4f}:gm=0:bm={-ct/2:.4f},"
        f"hue=h={hue:.2f}"
    )


def get_video_fps(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=r_frame_rate",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10
        )
        frac = r.stdout.strip()
        if "/" in frac:
            n, d = frac.split("/")
            return round(float(n) / float(d), 3)
    except Exception:
        pass
    return 30.0


def has_audio_stream(path):
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_type",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=10
        )
        return "audio" in (r.stdout or "")
    except Exception:
        return False


def apply_exif(path, region="us", target_device=None):
    if not has_tool("exiftool"):
        return None
    make, model, software = resolve_device(target_device)
    dt = datetime.datetime.now() - datetime.timedelta(days=random.randint(1, 14))
    dt = dt.replace(hour=random.randint(9, 21), minute=random.randint(0, 59),
                    second=random.randint(0, 59))
    dt_str = dt.strftime("%Y:%m:%d %H:%M:%S")
    cities = CITIES_US if region.lower() == "us" else CITIES_SK
    city_name, lat, lon = random.choice(cities)
    jitter = random.uniform(-0.004, 0.004)
    j_lat, j_lon = round(lat + jitter, 6), round(lon + jitter, 6)
    uid = uuid.uuid4().hex.upper()
    cmd = [
        "exiftool", "-overwrite_original",
        f"-Make={make}", f"-Model={model}",
        f"-DeviceMake={make}", f"-DeviceModel={model}",
        f"-Software={software}",
        f"-CreateDate={dt_str}", f"-ModifyDate={dt_str}", f"-DateTimeOriginal={dt_str}",
        f"-MediaCreateDate={dt_str}", f"-TrackCreateDate={dt_str}",
        f"-ImageUniqueID={uid}",
        f"-GPSCoordinates={j_lat}, {j_lon}",
        f"-Keys:GPSCoordinates={j_lat}, {j_lon}",
        f"-QuickTime:GPSCoordinates={j_lat}, {j_lon}",
        path
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return {"device": f"{make} {model}", "software": software, "city": city_name}
    except Exception:
        return None


# ─── Pipeline functions ───────────────────────────────────────────────────────

def download_reel(url, out_dir, cookies_path=None, log=None):
    """Stahuje Reel pomocou yt-dlp v plnej kvalite bez úprav. Vracia cestu k súboru alebo None."""
    if not has_tool("yt-dlp"):
        if log: log("  ERROR: yt-dlp nie je nainštalovaný! (winget install yt-dlp.yt-dlp)")
        return None
    os.makedirs(out_dir, exist_ok=True)
    before = set(os.listdir(out_dir))
    cmd = [
        "yt-dlp",
        "-o", os.path.join(out_dir, "%(uploader)s_%(id)s.%(ext)s"),
        "--no-playlist", "--ignore-errors", "--newline",
        "--retries", "5", "--fragment-retries", "5", "--no-part",
        "--age-limit", "100",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
    ]
    if not cookies_path or not os.path.isfile(cookies_path):
        env_c = os.environ.get("CAPPY_REELS_COOKIES")
        if env_c and os.path.isfile(env_c):
            cookies_path = env_c
    if cookies_path and os.path.isfile(cookies_path):
        cmd += ["--cookies", cookies_path]
    if has_tool("deno"):
        cmd += ["--js-runtimes", "deno"]
    cmd.append(url)
    if log: log(f"  Stiahnutie: yt-dlp {url[:60]}...")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        if log: log("  CHYBA: Časový limit (10 min) prekročený.")
        return None
    except Exception as e:
        if log: log(f"  CHYBA: {e}")
        return None
    after = set(os.listdir(out_dir))
    new = sorted(after - before)
    media = [f for f in new if os.path.splitext(f)[1].lower() in {".mp4", ".mov", ".mkv", ".webm"}]
    pick = media or new
    if pick:
        path = os.path.join(out_dir, pick[0])
        if log: log(f"  OK: Stiahnutý súbor: {pick[0]}")
        return path

    # Fallback pre prípad, že video už v zložke bolo stiahnuté predtým
    if r.returncode == 0:
        combined = (r.stdout or "") + "\n" + (r.stderr or "")
        m = re.search(r"\[download\]\s+(.*?)\s+has already been downloaded", combined)
        if m:
            fp = m.group(1).strip().strip('"').strip("'")
            if os.path.isfile(fp):
                if log: log(f"  OK (už existuje): {os.path.basename(fp)}")
                return fp
        m2 = re.search(r"(?:Destination:|Merging formats into)\s*\"?([^\"\r\n]+)", combined)
        if m2:
            fp = m2.group(1).strip().strip('"').strip("'")
            if os.path.isfile(fp):
                if log: log(f"  OK: {os.path.basename(fp)}")
                return fp

    tail = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
    if log: log("  CHYBA: " + (tail[-1] if tail else "neznáma chyba"))
    return None


def generate_anti_ai_lut(out_path=None, size=33):
    """
    Procedurálny 3D LUT (33×33×33 point .cube súbor) Anti-AI Filmic:
    - Lifted Blacks: Jemné zdvihnutie čierneho bodu (+1.5 %) pre analógový filmový kontrast.
    - Soft Highlight Roll-off: Stiahnutie najvyšších svetiel o 4 % s jemným oteplením (eliminácia digitálnych prepalov).
    - Luma vs. Saturation: Desaturácia hlbokých tieňov (<10 % jasu) a extrémnych svetiel (>90 % jasu).
    - Split Toning: Neutrálne/chladné tiene, prirodzené teplé tóny v stredoch (ochrana farby pokožky), stiahnutie neónovej zelenej.
    """
    if out_path and os.path.isfile(out_path):
        return out_path
    if not out_path:
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
        os.makedirs(cache_dir, exist_ok=True)
        out_path = os.path.join(cache_dir, "anti_ai_filmic_33.cube")
        if os.path.isfile(out_path):
            return out_path

    lines = [
        '# Procedural Anti-AI Filmic 3D LUT (33x33x33)',
        'TITLE "Anti-AI Filmic"',
        f'LUT_3D_SIZE {size}',
        ''
    ]
    for b_idx in range(size):
        b = b_idx / (size - 1)
        for g_idx in range(size):
            g = g_idx / (size - 1)
            for r_idx in range(size):
                r = r_idx / (size - 1)

                # 1. Základný jas (Rec. 709)
                lum = 0.2126 * r + 0.7152 * g + 0.0722 * b

                # 2. Hlboká prirodzená čierna – bez umelého dvíhania (zachováva hlboký, bohatý kontrast originálu)
                r1, g1, b1 = r, g, b
                y1 = lum

                # 3. Soft Highlight Roll-off (jemné stiahnutie najvyšších prepalov s jemným oteplením)
                if y1 > 0.85:
                    hf = (y1 - 0.85) / 0.15
                    roll = (hf ** 2) * 0.025
                    r2 = r1 - roll * 0.70
                    g2 = g1 - roll * 1.00
                    b2 = b1 - roll * 1.20
                else:
                    r2, g2, b2 = r1, g1, b1

                # 4. Prirodzené pleťové tóny v stredoch + potlačenie presýtených chemických farieb
                r3, g3, b3 = r2, g2, b2
                if 0.35 <= y1 <= 0.70:
                    mw = math.sin((y1 - 0.35) / 0.35 * math.pi) * 0.012
                    r3 += mw * 1.1
                    g3 += mw * 0.2
                    b3 -= mw * 0.5

                # Stiahnutie neónovej zelenej
                if g > r and g > b:
                    excess_g = g - max(r, b)
                    g3 -= excess_g * 0.22

                # 5. Jemná desaturácia len extrémnych prepálených svetiel (>95 %)
                lum3 = 0.2126 * r3 + 0.7152 * g3 + 0.0722 * b3
                if y1 > 0.95:
                    sat_f = 1.0 - 0.20 * ((y1 - 0.95) / 0.05)
                    r4 = lum3 + sat_f * (r3 - lum3)
                    g4 = lum3 + sat_f * (g3 - lum3)
                    b4 = lum3 + sat_f * (b3 - lum3)
                else:
                    r4, g4, b4 = r3, g3, b3

                # 6. Clamp
                rf = max(0.0, min(1.0, r4))
                gf = max(0.0, min(1.0, g4))
                bf = max(0.0, min(1.0, b4))
                lines.append(f"{rf:.6f} {gf:.6f} {bf:.6f}")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


def upscale_with_realesrgan(src, out, model="realesrgan-x4plus", binary="realesrgan-ncnn-vulkan", log=None):
    """
    Real-ESRGAN upscaling engine:
    - Zachováva pôvodnú snímkovú frekvenciu (FPS) bez interpolácie.
    - Zväčšuje zdrojové video na 1080p cez zadaný model (default: realesrgan-x4plus / realesr-animevideov3).
    """
    bin_path = shutil.which(binary)
    if not bin_path:
        return False
    model_dir = os.path.join(os.path.dirname(bin_path), "models")
    fps = get_video_fps(src)
    tmp_frames = tempfile.mkdtemp(prefix="ig_frames_")
    tmp_up = tempfile.mkdtemp(prefix="ig_up_")
    try:
        if log: log(f"  Real-ESRGAN ({model}): Extrahujem snimky (FPS={fps} zachovane)...")
        r1 = subprocess.run(
            ["ffmpeg", "-y", "-i", src, os.path.join(tmp_frames, "frame_%06d.png")],
            capture_output=True, text=True, timeout=300
        )
        if r1.returncode != 0: return False
        cnt = len(glob.glob(os.path.join(tmp_frames, "*.png")))
        if log: log(f"  Real-ESRGAN: Upscalujem {cnt} snimkov na GPU (AMD Radeon) cez {model}...")
        cmd_up = [
            bin_path, "-i", tmp_frames, "-o", tmp_up,
            "-n", model,
            "-t", "192",
            "-j", "1:1:1",
            "-f", "png"
        ]
        if os.path.isdir(model_dir):
            cmd_up += ["-m", model_dir]
        r2 = subprocess.run(
            cmd_up,
            capture_output=True, text=True, timeout=3600
        )
        if r2.returncode != 0:
            if log: log(f"  Real-ESRGAN chyba: {r2.stderr[-200:] if r2.stderr else 'neznáma chyba'}")
            return False
        if log: log(f"  Real-ESRGAN: Skladam video (FPS={fps} bez zmeny)...")
        has_a = has_audio_stream(src)
        cmd = ["ffmpeg", "-y", "-framerate", str(fps),
               "-i", os.path.join(tmp_up, "frame_%06d.png")]
        if has_a:
            cmd += ["-i", src, "-map", "1:a"]
        cmd += ["-map", "0:v",
                "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out]
        r3 = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        return r3.returncode == 0 and os.path.exists(out)
    except Exception as e:
        if log: log(f"  Real-ESRGAN CHYBA: {e}")
        return False
    finally:
        shutil.rmtree(tmp_frames, ignore_errors=True)
        shutil.rmtree(tmp_up, ignore_errors=True)


def color_grade_and_encode(src, out, is_copy=False, enc_args=None, log=None, **kwargs):
    """
    Kompletný FFmpeg pipeline pre hlavné video:
    1. Pomer strán a vycentrovaný orez na presných 1080x1920:
       scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2
    2. Adaptívne doostrenie: AMD FidelityFX CAS 0.3 (alebo unsharp)
    3. Cinematic EQ: eq=contrast=1.055:brightness=-0.007:gamma=0.97:saturation=1.035
    4. Audio Guard: -c:a copy pre bezstratový prenos, anullsrc stereo ak audio chýba
    5. Instagram Enkódovanie: libx264 CPU s -crf 18 -preset fast pre vizuálne bezstratový export
    6. Vymazané metadáta: -map_metadata -1 (následne zapísané čisté GPS/EXIF)
    """
    if enc_args is None:
        _, enc_args = detect_encoder()
    has_a = has_audio_stream(src)

    sharp_filter = get_sharpen_filter()
    eq_filter = build_spoof_filters(is_copy=is_copy)

    vf_parts = [
        "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos",
        "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2",
        sharp_filter,
        eq_filter
    ]
    vf = ",".join(vf_parts)

    cmd = ["ffmpeg", "-y", "-threads", "0", "-i", src]
    if not has_a:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd += ["-map_metadata", "-1", "-vf", vf] + enc_args
    if "-pix_fmt" not in enc_args:
        cmd += ["-pix_fmt", "yuv420p"]
    if has_a:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-ac", "2", "-b:a", "320k"]
    cmd += [
        "-map", "0:v",
        "-map", ("0:a?" if has_a else "1:a"),
        "-movflags", "+faststart", "-shortest", out
    ]
    if log: log(f"  Enkódujem hlavné video: 1080x1920 Lanczos + {sharp_filter} + EQ (1.055/-0.007/0.97/1.035), CRF 18")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.exists(out):
        if log: log("  Enkódovanie s copy zlyhalo, prepínam na kompatibilný fallback s AAC re-encode...")
        cmd2 = ["ffmpeg", "-y", "-threads", "0", "-i", src]
        if not has_a:
            cmd2 += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd2 += [
            "-map_metadata", "-1",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2", "-b:a", "320k",
            "-map", "0:v", "-map", ("0:a?" if has_a else "1:a"),
            "-movflags", "+faststart", "-shortest", out
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=600)
        return r2.returncode == 0 and os.path.exists(out)
    return True


def create_copy_with_jitter(main_src, out_copy, region="us", target_device=None, enc_args=None, log=None):
    """
    Rýchle vytvorenie kópie z už spracovaného hlavného videa:
    - Aplikuje rýchly náhodný jitter hodnôt (kontrast, jas, gamma, saturácia, hue, colorbalance).
    - Zachováva 1080x1920 a CAS 0.4 ostrosť bez opätovného škálovania.
    - libx264 -crf 18 -preset fast + bezstratové audio copy (-c:a copy).
    - -map_metadata -1 a nové unikátne GPS/EXIF metadáta pre daný účet.
    """
    if enc_args is None:
        _, enc_args = detect_encoder()
    has_a = has_audio_stream(main_src)
    jitter_filter = build_copy_jitter_filter()

    cmd = ["ffmpeg", "-y", "-threads", "0", "-i", main_src]
    if not has_a:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd += ["-map_metadata", "-1", "-vf", jitter_filter] + enc_args
    if "-pix_fmt" not in enc_args:
        cmd += ["-pix_fmt", "yuv420p"]
    if has_a:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-ac", "2", "-b:a", "320k"]
    cmd += [
        "-map", "0:v",
        "-map", ("0:a?" if has_a else "1:a"),
        "-movflags", "+faststart", "-shortest", out_copy
    ]
    if log: log(f"  Vytváram kópiu s náhodným jitterom pre unikátny hash...")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    ok = r.returncode == 0 and os.path.exists(out_copy)
    if not ok:
        cmd2 = ["ffmpeg", "-y", "-threads", "0", "-i", main_src]
        if not has_a:
            cmd2 += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd2 += [
            "-map_metadata", "-1",
            "-vf", jitter_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2", "-b:a", "320k",
            "-map", "0:v", "-map", ("0:a?" if has_a else "1:a"),
            "-movflags", "+faststart", "-shortest", out_copy
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
        ok = r2.returncode == 0 and os.path.exists(out_copy)

    if ok:
        meta = apply_exif(out_copy, region=region, target_device=target_device)
        if meta and log:
            log(f"  EXIF: {meta['device']} | GPS: {meta['city']}")
    return ok


def full_pipeline(src, out, config, enc_args, log=None):
    """Kompletny pipeline pre hlavne video: [upscale] -> [color grade + encode] -> [EXIF]."""
    upscale_method = config.get("upscale_method", "none")
    do_grade = config.get("color_grade", True)
    region = config.get("region", "us")
    target_device = config.get("device")

    current = src
    temps = []
    try:
        # 1. AI Upscaling (iba ak je zvolený Real-ESRGAN)
        if upscale_method == "realesrgan":
            tmp_up = tempfile.mktemp(suffix="_upscaled.mp4")
            temps.append(tmp_up)
            ok = upscale_with_realesrgan(current, tmp_up, log=log)
            if ok:
                current = tmp_up
                if log: log("  Real-ESRGAN AI Upscaling OK.")
            else:
                if log: log("  Real-ESRGAN zlyhal, pokracujem s rychlym Lanczos 1080p...")

        # 2. Color grade + Lanczos 1080p + CAS 0.4 + encode
        if do_grade:
            ok = color_grade_and_encode(current, out, enc_args=enc_args, log=log)
        else:
            has_a = has_audio_stream(current)
            cmd = ["ffmpeg", "-y", "-i", current]
            if not has_a:
                cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
            cmd += ["-map_metadata", "-1",
                    "-vf", BASE_EQ_FILTER] + enc_args + [
                "-pix_fmt", "yuv420p",
                "-c:a", "copy" if has_a else "aac",
                "-map", "0:v", "-map", ("0:a?" if has_a else "1:a"),
                "-movflags", "+faststart", "-shortest", out
            ]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            ok = r.returncode == 0 and os.path.exists(out)

        if not ok:
            if log: log("  CHYBA: Encode pipeline zlyhala!")
            return False

        # 3. EXIF & GPS
        meta = apply_exif(out, region=region, target_device=target_device)
        if meta and log:
            log(f"  EXIF: {meta['device']} | GPS: {meta['city']}")
        return True
    finally:
        for t in temps:
            if t and os.path.isfile(t):
                try: os.remove(t)
                except: pass
        for t in temps:
            if t and os.path.isfile(t):
                try: os.remove(t)
                except: pass


# ─── Google Drive ─────────────────────────────────────────────────────────────

def init_gdrive():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        return None, "Chybaju kniznice google-api-python-client a google-auth (pip install -r requirements.txt)"
    base = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(base, "drive_token.json"),
        os.path.join(base, "..", "data", "drive_token.json"),
        os.path.join(base, "..", "..", "Drive", "data", "drive_token.json"),
    ]
    token = next((c for c in candidates if os.path.exists(c)), None)
    if not token:
        return None, "Subor drive_token.json nebol najdeny."
    try:
        # Nacitanie bez pevnych scopes zabrani chybe 'invalid_scope' pri refreshovani
        creds = Credentials.from_authorized_user_file(token)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        svc = build("drive", "v3", credentials=creds)
        return svc, None
    except Exception as e:
        return None, f"Chyba autentifikacie: {e}"


_DRIVE_FOLDER_CACHE = {}


def get_or_create_drive_folder(svc, folder_name, parent_id=DEFAULT_VAULT_ID):
    """Nájde existujúci alebo vytvorí nový priečinok na Google Drive v rodičovskom priečinku."""
    if not folder_name:
        return parent_id
    cache_key = f"{parent_id}:{folder_name}"
    if cache_key in _DRIVE_FOLDER_CACHE:
        return _DRIVE_FOLDER_CACHE[cache_key]
    try:
        q = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        res = svc.files().list(
            q=q,
            fields="files(id, name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        files = res.get("files", [])
        if files:
            f_id = files[0]["id"]
            _DRIVE_FOLDER_CACHE[cache_key] = f_id
            return f_id
        meta = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id]
        }
        f = svc.files().create(body=meta, fields="id, name", supportsAllDrives=True).execute()
        f_id = f["id"]
        _DRIVE_FOLDER_CACHE[cache_key] = f_id
        return f_id
    except Exception as e:
        print(f"Chyba pri vytvarani priecinka na Drive {folder_name}: {e}")
        return parent_id


def upload_to_drive(svc, path, name, folder_id=None):
    from googleapiclient.http import MediaFileUpload
    target_parent = folder_id or DEFAULT_VAULT_ID
    meta = {"name": name, "parents": [target_parent]}
    media = MediaFileUpload(path, mimetype="video/mp4", resumable=True)
    req = svc.files().create(body=meta, media_body=media, fields="id,name", supportsAllDrives=True)
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp


class DriveUploadManager:
    """Manažér pre asynchrónny upload videí na Google Drive na pozadí bez blokovania CPU."""
    def __init__(self, gdrive_svc, log_fn=None):
        self.gdrive_svc = gdrive_svc
        self.log = log_fn
        self.queue = queue.Queue()
        self.active_count = 0
        self.lock = threading.Lock()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker.start()

    def queue_upload(self, file_path: str, file_name: str, folder_name: str = None):
        with self.lock:
            self.active_count += 1
        self.queue.put((file_path, file_name, folder_name))
        target_info = f" ({folder_name}/{file_name})" if folder_name else f" ({file_name})"
        if self.log:
            self.log(f"  ☁ Zaradené do pozadia na Drive upload:{target_info}")

    def _worker_loop(self):
        while True:
            item = self.queue.get()
            if item is None:
                break
            path, name, folder_name = item
            try:
                target_folder_id = None
                if folder_name and self.gdrive_svc:
                    target_folder_id = get_or_create_drive_folder(self.gdrive_svc, folder_name, DEFAULT_VAULT_ID)
                upload_to_drive(self.gdrive_svc, path, name, target_folder_id)
                tag = f"{folder_name}/{name}" if folder_name else name
                if self.log:
                    self.log(f"  ☁ Drive upload OK: {tag}")
            except Exception as e:
                if self.log:
                    self.log(f"  ☁ Drive CHYBA pri {name}: {e}")
            finally:
                with self.lock:
                    self.active_count -= 1
                self.queue.task_done()

    def wait_all(self):
        self.queue.join()


# ─── Server API Client (Pure urllib) ──────────────────────────────────────────

def _urlopen_safe(req, timeout=30):
    """Bezpečné otvorenie URL s automatickým fallbackom pre Windows PC s chýbajúcim CA zväzkom."""
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except Exception as e:
        try:
            ctx = ssl._create_unverified_context()
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except Exception:
            raise e


def http_multipart_post(url, fields, files, headers=None, timeout=300):
    """
    Vykoná HTTP multipart/form-data POST bez nutnosti inštalácie 'requests' (čistý urllib).
    fields: dict {field_name: string_value}
    files: dict {field_name: (filename, bytes_data, content_type)}
    """
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()

    for k, v in fields.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"))
        body.extend(f"{v}\r\n".encode("utf-8"))

    for k, (fname, fbytes, ctype) in files.items():
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="{k}"; filename="{fname}"\r\n'.encode("utf-8"))
        body.extend(f'Content-Type: {ctype}\r\n\r\n'.encode("utf-8"))
        body.extend(fbytes)
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    req = urllib.request.Request(url, data=bytes(body), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.add_header("User-Agent", "IGDesktopSpoofer/2.0")
    if headers:
        for hk, hv in headers.items():
            req.add_header(hk, hv)

    with _urlopen_safe(req, timeout=timeout) as resp:
        res_data = resp.read().decode("utf-8")
        try:
            return json.loads(res_data)
        except Exception:
            return {"status": "ok", "raw": res_data}


# ─── GUI ──────────────────────────────────────────────────────────────────────

class ScrollableFrame(tk.Frame):
    def __init__(self, parent, bg=BG_DARK, *args, **kwargs):
        super().__init__(parent, bg=bg, *args, **kwargs)
        self.canvas = tk.Canvas(self, bg=bg, borderwidth=0, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = tk.Frame(self.canvas, bg=bg)

        self.content.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        self._win_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self._win_id, width=e.width)
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def on_mousewheel(self, event):
        sr = self.canvas.bbox("all")
        if sr and (sr[3] - sr[1]) > self.canvas.winfo_height():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120) * 2), "units")


class ReelsStudio(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("IG Reels Studio v2.0")
        self.geometry("980x780")
        self.minsize(860, 580)
        self.configure(bg=BG_DARK)

        self.enc_name, self.enc_args = detect_encoder()
        self.gdrive_svc = None
        self.is_running = False

        # Premenné
        self.v_input_dir  = tk.StringVar()
        self.v_output_dir = tk.StringVar()
        self.v_region     = tk.StringVar(value="us")
        self.v_variants   = tk.IntVar(value=1)
        self.v_upscale    = tk.StringVar(value="lanczos")
        self.v_grade      = tk.BooleanVar(value=True)
        self.v_grain      = tk.IntVar(value=3)
        self.v_lut        = tk.StringVar()
        self.v_drive      = tk.BooleanVar(value=False)
        self.v_url        = tk.StringVar()
        self.v_dl_dir     = tk.StringVar()
        self.v_dl_grade   = tk.BooleanVar(value=True)
        self.v_dl_drive   = tk.BooleanVar(value=False)

        # Premenné pre Farmu profilov (Sync)
        self.v_farm_url        = tk.StringVar(value="https://garcarzp.online/ig")
        self.v_farm_pwd        = tk.StringVar(value="patrik3924")
        self.v_farm_dir        = tk.StringVar()
        self.v_farm_region     = tk.StringVar(value="us")
        self.v_farm_grade      = tk.BooleanVar(value=True)
        self.v_farm_save_local = tk.BooleanVar(value=True)
        self.farm_accounts     = []
        self.farm_account_vars = {}
        self.farm_summary      = {}

        self._build_ui()
        self.after(300, self._check_tools)
        self.after(500, self._connect_drive)
        self.after(800, self._load_farm_profiles)

    def _card(self, parent, title=""):
        wrap = tk.Frame(parent, bg=BG_DARK, highlightbackground=BORDER, highlightthickness=1)
        wrap.pack(fill="x", padx=6, pady=4)
        if title:
            tk.Label(wrap, text=title, fg=MUTED, bg=BG_DARK,
                     font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=10, pady=(6, 0))
        inner = tk.Frame(wrap, bg=BG_CARD, padx=14, pady=10)
        inner.pack(fill="x", padx=6, pady=(0, 6))
        return inner

    def _entry(self, parent, var, width=None):
        kw = dict(textvariable=var, bg=BG_CARD2, fg=TEXT, relief="flat",
                  font=("Segoe UI", 10), insertbackground=ACCENT)
        if width: kw["width"] = width
        return tk.Entry(parent, **kw)

    def _btn(self, parent, text, cmd, color=None, fg="white"):
        c = color or BG_CARD2
        return tk.Button(parent, text=text, command=cmd,
                         bg=c, fg=fg if color else TEXT,
                         relief="flat", font=("Segoe UI", 9),
                         activebackground=ACCENT, activeforeground="white",
                         padx=10, pady=6, cursor="hand2")

    def _radio_row(self, parent, var, items):
        for val, lbl in items:
            tk.Radiobutton(parent, text=lbl, variable=var, value=val,
                           bg=BG_CARD, fg=TEXT, selectcolor=BG_CARD,
                           activebackground=BG_CARD, activeforeground=TEXT,
                           font=("Segoe UI", 10)).pack(anchor="w", pady=1)

    def log(self, msg):
        def _do():
            self._log.configure(state="normal")
            self._log.insert("end", msg + "\n")
            self._log.see("end")
            self._log.configure(state="disabled")
        self.after(0, _do)

    def _set_progress(self, cur, tot):
        pct = int(cur / tot * 100) if tot else 0
        self.after(0, lambda: [
            self._prog.configure(value=pct),
            self._prog_lbl.configure(text=f"{cur}/{tot} ({pct}%)")
        ])

    def _set_running(self, val):
        self.is_running = val
        s1 = "disabled" if val else "normal"
        s2 = "normal" if val else "disabled"
        def _update():
            if hasattr(self, "_start_btn"):
                self._start_btn.configure(state=s1)
            if hasattr(self, "_stop_btn"):
                self._stop_btn.configure(state=s2)
            if hasattr(self, "_dl_start_btn"):
                self._dl_start_btn.configure(state=s1)
            if hasattr(self, "_farm_start_btn"):
                self._farm_start_btn.configure(state=s1)
            if hasattr(self, "_farm_load_btn"):
                self._farm_load_btn.configure(state=s1)
        self.after(0, _update)

    def _build_ui(self):
        # 1. Header (Hore)
        hdr = tk.Frame(self, bg=BG_DARK)
        hdr.pack(side="top", fill="x", padx=18, pady=(12, 4))
        tk.Label(hdr, text="🎬  IG REELS STUDIO", font=("Segoe UI", 20, "bold"),
                 fg=ACCENT, bg=BG_DARK).pack(side="left")
        self._enc_lbl = tk.Label(hdr, text=f"⚡ {self.enc_name}", font=("Segoe UI", 10),
                                  fg=GREEN, bg=BG_DARK)
        self._enc_lbl.pack(side="right")

        # 2. Akčné tlačidlá (Ukotvené celkom dole, aby boli vždy na očiach)
        br = tk.Frame(self, bg=BG_DARK)
        br.pack(side="bottom", fill="x", padx=14, pady=(6, 12))
        self._start_btn = tk.Button(br, text="▶  SPUSTIT", font=("Segoe UI", 12, "bold"),
                                     bg=ACCENT, fg="white", activebackground=BTN_HOVER,
                                     activeforeground="white", relief="flat",
                                     padx=26, pady=9, cursor="hand2", command=self._on_start)
        self._start_btn.pack(side="left", padx=(0, 8))
        self._stop_btn = tk.Button(br, text="⬛  STOP", font=("Segoe UI", 12, "bold"),
                                    bg="#363a4f", fg=MUTED, activebackground="#4a4e6a",
                                    activeforeground=TEXT, relief="flat",
                                    padx=26, pady=9, cursor="hand2",
                                    command=self._on_stop, state="disabled")
        self._stop_btn.pack(side="left")
        self._drive_lbl = tk.Label(br, text="☁ Drive: –", fg=MUTED, bg=BG_DARK,
                                    font=("Segoe UI", 10))
        self._drive_lbl.pack(side="right")
        self._btn(br, "🔗 Pripojit Drive", self._connect_drive,
                  color="#1e2235", fg=ACCENT3).pack(side="right", padx=8)

        # 3. Progress bar (Hneď nad tlačidlami)
        bot = tk.Frame(self, bg=BG_DARK)
        bot.pack(side="bottom", fill="x", padx=14, pady=(0, 4))
        pr = tk.Frame(bot, bg=BG_DARK)
        pr.pack(fill="x")
        self._prog_lbl = tk.Label(pr, text="Pripraveny", fg=MUTED, bg=BG_DARK,
                                   font=("Segoe UI", 9))
        self._prog_lbl.pack(side="left")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Neon.Horizontal.TProgressbar",
                         troughcolor=BG_CARD, background=ACCENT)
        self._prog = ttk.Progressbar(bot, style="Neon.Horizontal.TProgressbar",
                                      mode="determinate", length=100)
        self._prog.pack(fill="x", pady=2)

        # 4. Log konzola (Kompaktná, hneď nad progress barom)
        self._log = scrolledtext.ScrolledText(
            self, height=5, bg="#0b0d14", fg="#a8b2d8",
            font=("Consolas", 9), relief="flat", borderwidth=0,
            insertbackground=ACCENT
        )
        self._log.pack(side="bottom", fill="x", padx=14, pady=(0, 6))
        self._log.configure(state="disabled")

        # 5. Notebook / Záložky (Vyplní celý stred okna a je scrolovateľný)
        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_CARD, foreground=MUTED,
                         font=("Segoe UI", 11, "bold"), padding=[18, 7])
        style.map("TNotebook.Tab",
                  background=[("selected", BG_CARD2)],
                  foreground=[("selected", TEXT)])

        self._nb = ttk.Notebook(self)
        self._nb.pack(side="top", fill="both", expand=True, padx=12, pady=(2, 6))

        t1 = tk.Frame(self._nb, bg=BG_DARK)
        t2 = tk.Frame(self._nb, bg=BG_DARK)
        t3 = tk.Frame(self._nb, bg=BG_DARK)
        self._nb.add(t1, text="📦  Batch Spoofing")
        self._nb.add(t2, text="⬇  Stiahnut Reels")
        self._nb.add(t3, text="📱  Farma profilov (Sync)")

        self._t1_scroll = ScrollableFrame(t1, bg=BG_DARK)
        self._t1_scroll.pack(fill="both", expand=True)
        self._build_batch(self._t1_scroll.content)

        self._t2_scroll = ScrollableFrame(t2, bg=BG_DARK)
        self._t2_scroll.pack(fill="both", expand=True)
        self._build_download(self._t2_scroll.content)

        self._t3_scroll = ScrollableFrame(t3, bg=BG_DARK)
        self._t3_scroll.pack(fill="both", expand=True)
        self._build_farm_sync(self._t3_scroll.content)

        # Globálny mousewheel listener – scroluje aktuálne otvorenú záložku
        self.bind_all("<MouseWheel>", self._on_global_mousewheel)

    def _on_global_mousewheel(self, event):
        if hasattr(self, "_log") and str(event.widget).startswith(str(self._log)):
            return
        try:
            active_tab = self._nb.index("current")
            if active_tab == 0 and hasattr(self, "_t1_scroll"):
                self._t1_scroll.on_mousewheel(event)
            elif active_tab == 1 and hasattr(self, "_t2_scroll"):
                self._t2_scroll.on_mousewheel(event)
            elif active_tab == 2 and hasattr(self, "_t3_scroll"):
                self._t3_scroll.on_mousewheel(event)
        except Exception:
            pass

    def _build_batch(self, parent):
        c1 = self._card(parent, "📂  Vstupne videa")
        r = tk.Frame(c1, bg=BG_CARD); r.pack(fill="x", pady=2)
        self._entry(r, self.v_input_dir).pack(side="left", fill="x", expand=True)
        self._btn(r, "Vybrat...", lambda: self._pick_dir(self.v_input_dir)).pack(side="left", padx=(6, 0))

        c2 = self._card(parent, "📁  Vystupna zlozka")
        r2 = tk.Frame(c2, bg=BG_CARD); r2.pack(fill="x", pady=2)
        self._entry(r2, self.v_output_dir).pack(side="left", fill="x", expand=True)
        self._btn(r2, "Vybrat...", lambda: self._pick_dir(self.v_output_dir)).pack(side="left", padx=(6, 0))

        row = tk.Frame(parent, bg=BG_DARK)
        row.pack(fill="x", pady=2)

        rc = self._card(row, "🌍  Region")
        rc.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self._radio_row(rc, self.v_region, [("us", "🇺🇸  USA (LA + Vegas)"), ("sk", "🇸🇰  Slovensko")])

        vc = self._card(row, "🔢  Varianty / video")
        vc.pack(side="left", fill="both", expand=True, padx=(0, 4))
        tk.Spinbox(vc, from_=1, to=20, textvariable=self.v_variants, width=4,
                   font=("Segoe UI", 14, "bold"), bg=BG_CARD2, fg=ACCENT,
                   relief="flat", buttonbackground=BG_CARD2).pack(pady=4)
        tk.Label(vc, text="každá kópia do zložky:\nkopie 1, kopie 2...",
                 fg=MUTED, bg=BG_CARD, font=("Segoe UI", 8), justify="center").pack(pady=(0, 2))

        uc = self._card(row, "📐  Upscaling")
        uc.pack(side="left", fill="both", expand=True)
        self._radio_row(uc, self.v_upscale, [
            ("lanczos", "Lanczos 1080p (Rýchle & bezpečné - ODPORÚČANÉ)"),
            ("none", "Žiadny (Pôvodné rozlíšenie)"),
            ("realesrgan", "Real-ESRGAN AI (Vysoká záťaž GPU/zdroja)"),
        ])

        gc = self._card(parent, "🎨  Vizuálny štýl (Cinematic EQ + CAS 0.3)")
        tk.Checkbutton(gc, text="Aplikovať Cinematic EQ + CAS 0.3 doostrenie (odporúčané)",
                       variable=self.v_grade, bg=BG_CARD, fg=TEXT,
                       selectcolor=ACCENT, activebackground=BG_CARD,
                       activeforeground=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(gc, text="• Hlavné video: contrast=1.055, brightness=-0.007, gamma=0.97, saturation=1.035\n• Adaptívne doostrenie: AMD FidelityFX CAS 0.3 (prirodzené hrany, oči a detaily)\n• Enkóder: CPU libx264 -crf 18 (vizuálne bezstratový export bez artefaktov)\n• Kópie: mikro-jitter hodnôt v TOP rozsahu pre unikátny hash + unikátne GPS",
                 fg=MUTED, bg=BG_CARD, font=("Segoe UI", 9), justify="left").pack(anchor="w", padx=4, pady=(4, 0))

        tk.Checkbutton(self._card(parent, "☁  Google Drive"),
                       text="Po dokonceni nahrat na Google Drive IG_VAULT",
                       variable=self.v_drive, bg=BG_CARD, fg=TEXT,
                       selectcolor=ACCENT, activebackground=BG_CARD,
                       activeforeground=TEXT, font=("Segoe UI", 10)).pack(anchor="w")

    def _build_download(self, parent):
        # 1. Zoznam Reels odkazov (viacriadkový vstup)
        uc = self._card(parent, "🔗  Zoznam Reels na stiahnutie (vlož odkazy pod seba)")

        info_lbl = tk.Label(
            uc,
            text="Vlož odkazy na Reels (každý odkaz na nový riadok).\n"
                 "Videá sa stiahnu postupne v plnej kvalite bez dodatočných úprav (bez spoofingu).\n"
                 "Každý úspešne stiahnutý odkaz sa automaticky vymaže zo zoznamu; zlyhané odkazy zostanú.",
            fg=MUTED, bg=BG_CARD, font=("Segoe UI", 9), justify="left"
        )
        info_lbl.pack(anchor="w", pady=(0, 6))

        txt_frame = tk.Frame(uc, bg=BORDER, padx=1, pady=1)
        txt_frame.pack(fill="x", pady=2)

        self._dl_urls_txt = scrolledtext.ScrolledText(
            txt_frame, height=8, bg=BG_CARD2, fg=TEXT,
            font=("Consolas", 10), relief="flat", borderwidth=0,
            insertbackground=ACCENT, wrap="none"
        )
        self._dl_urls_txt.pack(fill="both", expand=True)
        self._dl_urls_txt.bind("<KeyRelease>", self._update_url_count)
        self._dl_urls_txt.bind("<FocusIn>", self._update_url_count)

        ctrl_bar = tk.Frame(uc, bg=BG_CARD)
        ctrl_bar.pack(fill="x", pady=(6, 0))

        self._dl_count_lbl = tk.Label(
            ctrl_bar, text="Počet odkazov: 0", fg=ACCENT3, bg=BG_CARD,
            font=("Segoe UI", 9, "bold")
        )
        self._dl_count_lbl.pack(side="left")

        self._btn(ctrl_bar, "🗑️ Vyčistiť zoznam", self._clear_urls,
                  color="#26293d", fg=MUTED).pack(side="right", padx=(4, 0))
        self._btn(ctrl_bar, "📋 Vložiť zo schránky", self._paste_urls_from_clipboard,
                  color="#26293d", fg=TEXT).pack(side="right")

        # 2. Výstupná zložka
        dc = self._card(parent, "📁  Výstupná zložka pre stiahnuté videá")
        dr = tk.Frame(dc, bg=BG_CARD)
        dr.pack(fill="x", pady=2)
        if not self.v_dl_dir.get():
            self.v_dl_dir.set(os.path.join(os.path.expanduser("~"), "Desktop", "ig_downloads"))
        self._entry(dr, self.v_dl_dir).pack(side="left", fill="x", expand=True)
        self._btn(dr, "Vybrať...", lambda: self._pick_dir(self.v_dl_dir)).pack(side="left", padx=(6, 0))
        self._btn(dr, "📂 Otvoriť", lambda: self._open_dir(self.v_dl_dir),
                  color="#26293d", fg=TEXT).pack(side="left", padx=(4, 0))

        # 3. Možnosti
        oc = self._card(parent, "⚙  Nastavenia sťahovania")
        tk.Checkbutton(
            oc, text="Po úspešnom stiahnutí nahrať na Google Drive (IG_VAULT)",
            variable=self.v_dl_drive, bg=BG_CARD, fg=TEXT,
            selectcolor=ACCENT, activebackground=BG_CARD,
            activeforeground=TEXT, font=("Segoe UI", 10)
        ).pack(anchor="w", pady=2)
        tk.Label(
            oc,
            text="Podporované: Instagram Reels, TikTok, YouTube Shorts, Facebook Reels a 1000+ ďalších.\n"
                 "Všetky videá sa sťahujú v originálnej kvalite (.mp4) bez spoofovania a bez kódovania.",
            fg=MUTED, bg=BG_CARD, font=("Segoe UI", 8), justify="left"
        ).pack(anchor="w", pady=(4, 0))

        # 4. Spúšťacie tlačidlo v záložke
        btn_wrap = tk.Frame(parent, bg=BG_DARK)
        btn_wrap.pack(fill="x", pady=16)

        self._dl_start_btn = tk.Button(
            btn_wrap, text="⬇  STIAHNUŤ VŠETKY REELS",
            font=("Segoe UI", 12, "bold"),
            bg=GREEN, fg="white", activebackground="#25b374",
            activeforeground="white", relief="flat",
            padx=28, pady=10, cursor="hand2", command=self._on_download
        )
        self._dl_start_btn.pack(anchor="center")

    # ── Actions ───────────────────────────────────────────────────────────────

    def _pick_dir(self, var):
        d = filedialog.askdirectory()
        if d: var.set(d)

    def _pick_lut(self):
        f = filedialog.askopenfilename(filetypes=[("LUT", "*.cube"), ("All", "*.*")])
        if f: self.v_lut.set(f)

    def _check_tools(self):
        msgs = []
        if not has_tool("ffmpeg"):
            msgs.append("ERROR: ffmpeg chyba! (winget install Gyan.FFmpeg)")
        if not has_tool("exiftool"):
            msgs.append("WARN: exiftool chyba, EXIF/GPS nebude zapisany. (winget install PhilHarvey.ExifTool)")
        if not has_tool("yt-dlp"):
            msgs.append("INFO: yt-dlp chyba (potrebne pre zalobku Stahovat). (winget install yt-dlp.yt-dlp)")
        if not has_tool("realesrgan-ncnn-vulkan"):
            msgs.append("INFO: realesrgan-ncnn-vulkan nie je - Lanczos bude pouzity ako fallback.")
        if msgs:
            for m in msgs: self.log(m)
        else:
            self.log(f"OK  Vsetky nastroje dostupne | Enkoder: {self.enc_name}")

    def _connect_drive(self):
        self.log("Pripajam Google Drive...")
        svc, err = init_gdrive()
        if svc:
            self.gdrive_svc = svc
            self._drive_lbl.configure(text="☁ Drive: Pripojeny", fg=GREEN)
            self.log("OK  Google Drive pripojeny!")
        else:
            self._drive_lbl.configure(text="☁ Drive: Chyba", fg=ACCENT2)
            self.log(f"CHYBA  Drive: {err or 'Neznama chyba'}")

    def _on_start(self):
        try:
            active_tab = self._nb.index("current")
        except Exception:
            active_tab = 0

        if active_tab == 1:
            self._on_download()
            return

        in_dir = self.v_input_dir.get().strip()
        if not in_dir or not os.path.isdir(in_dir):
            messagebox.showerror("Chyba", "Vyberte platny vstupny priecinok.")
            return
        out_dir = self.v_output_dir.get().strip()
        if not out_dir:
            out_dir = os.path.join(in_dir, "hotove_spoofnute")
        os.makedirs(out_dir, exist_ok=True)
        self.v_output_dir.set(out_dir)

        files = [os.path.join(in_dir, f) for f in os.listdir(in_dir)
                 if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS]
        if not files:
            messagebox.showerror("Chyba", f"V priecinkoch sa nenasli ziadne videa (MP4/MOV/M4V).")
            return

        cfg = {
            "region": self.v_region.get(),
            "variants": self.v_variants.get(),
            "upscale_method": self.v_upscale.get(),
            "color_grade": self.v_grade.get(),
            "grain": self.v_grain.get(),
            "lut_path": self.v_lut.get().strip() or None,
        }
        do_drive = self.v_drive.get() and self.gdrive_svc is not None
        self._set_running(True)
        self.log(f"\n{'='*58}")
        self.log(f"BATCH SPOOFING: {len(files)} videi x {cfg['variants']} variantov")
        if cfg['variants'] > 1:
            self.log(f"Vystup: Rozdelenie do {cfg['variants']} zložiek: kopie 1 až kopie {cfg['variants']}")
        self.log(f"Region: {cfg['region'].upper()} | Grain: {cfg['grain']} | Upscale: {cfg['upscale_method']}")
        self.log(f"{'='*58}")
        threading.Thread(target=self._batch_worker,
                         args=(files, out_dir, cfg, do_drive), daemon=True).start()

    def _batch_worker(self, files, out_dir, cfg, do_drive):
        variants = cfg.get("variants", 1)
        total = len(files) * variants
        done = 0
        t0 = time.time()

        uploader = DriveUploadManager(self.gdrive_svc, self.log) if (do_drive and self.gdrive_svc) else None

        for src in files:
            if not self.is_running:
                self.log("STOP — prerušene pouzivatelom.")
                self._set_running(False)
                return

            base = os.path.splitext(os.path.basename(src))[0]

            # 1. Hlavné video (kópia 1)
            done += 1
            if variants > 1:
                target_dir_1 = os.path.join(out_dir, "kopie 1")
                os.makedirs(target_dir_1, exist_ok=True)
            else:
                target_dir_1 = out_dir

            tok1 = uuid.uuid4().hex[:6]
            suf1 = "_v1" if variants > 1 else ""
            name1 = f"spoofed_{base}{suf1}_{tok1}.mp4"
            out1 = os.path.join(target_dir_1, name1)

            folder_tag1 = "kopie 1/" if variants > 1 else ""
            self.log(f"\n[{done}/{total}] (Hlavné video 1/{variants}) {os.path.basename(src)} -> {folder_tag1}{name1}")
            self._set_progress(done - 1, total)

            vt = time.time()
            ok1 = full_pipeline(src, out1, cfg, self.enc_args, log=self.log)
            dur1 = round(time.time() - vt, 1)

            if not ok1:
                self.log(f"  CHYBA hlavného videa po {dur1}s")
                continue

            mb1 = round(os.path.getsize(out1) / 1048576, 1) if os.path.exists(out1) else 0
            self.log(f"  OK hlavné video: {dur1}s | {mb1} MB")
            self._set_progress(done, total)

            if uploader:
                folder_name1 = "kopie 1" if variants > 1 else None
                uploader.queue_upload(out1, name1, folder_name=folder_name1)

            # 2. Ďalšie kópie z hlavného videa s náhodným jitterom (Paralelne na viacerých jadrách CPU)
            if variants > 1 and self.is_running:
                cpu_cores = os.cpu_count() or 4
                worker_count = min(3, max(1, cpu_cores // 3))
                self.log(f"  ⚡ Spúšťam paralelné spracovanie {variants - 1} kópií ({worker_count} jadrá naraz)...")

                def _process_copy(v_idx):
                    if not self.is_running:
                        return False
                    folder_name_v = f"kopie {v_idx + 1}"
                    target_dir_v = os.path.join(out_dir, folder_name_v)
                    os.makedirs(target_dir_v, exist_ok=True)

                    tok_v = uuid.uuid4().hex[:6]
                    name_v = f"spoofed_{base}_v{v_idx + 1}_{tok_v}.mp4"
                    out_v = os.path.join(target_dir_v, name_v)

                    vt2 = time.time()
                    ok_v = create_copy_with_jitter(out1, out_v, region=cfg.get("region", "us"),
                                                   enc_args=self.enc_args, log=None)
                    dur_v = round(time.time() - vt2, 1)

                    if ok_v:
                        mb_v = round(os.path.getsize(out_v) / 1048576, 1) if os.path.exists(out_v) else 0
                        self.log(f"  ✓ OK kópia {v_idx+1}/{variants} s jitterom: {dur_v}s | {mb_v} MB ({folder_name_v}/{name_v})")
                        if uploader:
                            uploader.queue_upload(out_v, name_v, folder_name=folder_name_v)
                        return True
                    else:
                        self.log(f"  ✗ CHYBA kópie {v_idx+1} po {dur_v}s")
                        return False

                with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                    futures = [executor.submit(_process_copy, v) for v in range(1, variants)]
                    for fut in concurrent.futures.as_completed(futures):
                        done += 1
                        self._set_progress(done, total)

        if uploader and uploader.active_count > 0:
            self.log(f"\nČakám na dokončenie uploadu na Drive ({uploader.active_count} videí vo fronte)...")
            uploader.wait_all()
            self.log("Všetky videá boli úspešne nahrané na Drive!")

        elapsed = round(time.time() - t0, 1)
        self.log(f"\n{'='*58}")
        self.log(f"HOTOVO za {elapsed}s | {done}/{total} videi")
        if variants > 1:
            self.log(f"Vystup: {out_dir} (roztriedene do {variants} zložiek: kopie 1 až kopie {variants})")
        else:
            self.log(f"Vystup: {out_dir}")
        if do_drive:
            self.log("Otvorit: https://garcarzp.online/ig/publisher -> Media Vault -> Synchronizovat")
        self.log(f"{'='*58}")
        self._set_progress(total, total)
        self._set_running(False)

    def _on_stop(self):
        self.is_running = False
        self.log("Zastavujem po aktualnom video...")

    def _get_urls_list(self):
        """Vráti zoznam platných URL adries zo vstupného textového poľa."""
        if not hasattr(self, "_dl_urls_txt"):
            return []
        raw = self._dl_urls_txt.get("1.0", "end-1c")
        urls = []
        for line in raw.splitlines():
            line = line.strip()
            if line.startswith("http://") or line.startswith("https://"):
                urls.append(line)
        return urls

    def _update_url_count(self, event=None):
        """Aktualizuje počítadlo zadaných URL adries."""
        try:
            urls = self._get_urls_list()
            count = len(urls)
            if hasattr(self, "_dl_count_lbl"):
                self._dl_count_lbl.configure(text=f"Počet odkazov: {count}")
        except Exception:
            pass

    def _paste_urls_from_clipboard(self):
        """Vloží odkazy zo schránky do textového poľa."""
        try:
            clip = self.clipboard_get()
            if clip:
                current = self._dl_urls_txt.get("1.0", "end-1c").strip()
                if current:
                    self._dl_urls_txt.insert("end", "\n" + clip.strip() + "\n")
                else:
                    self._dl_urls_txt.insert("1.0", clip.strip() + "\n")
                self._update_url_count()
        except Exception:
            messagebox.showwarning("Schránka", "Nepodarilo sa načítať text zo schránky.")

    def _clear_urls(self):
        """Vymaže textové pole so zoznamom odkazov."""
        if hasattr(self, "_dl_urls_txt"):
            self._dl_urls_txt.delete("1.0", "end")
            self._update_url_count()

    def _open_dir(self, var):
        """Otvorí zvolenú zložku v prieskumníkovi súborov (Windows Explorer)."""
        d = var.get().strip() if hasattr(var, "get") else str(var)
        if not d:
            d = os.path.join(os.path.expanduser("~"), "Desktop", "ig_downloads")
        os.makedirs(d, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(d)
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            self.log(f"CHYBA pri otváraní zložky: {e}")

    def _remove_url_from_text(self, target_url):
        """Odstráni stiahnutý odkaz z textového poľa priamo za behu."""
        def _do():
            try:
                raw = self._dl_urls_txt.get("1.0", "end-1c")
                lines = raw.splitlines()
                target_clean = target_url.strip()
                new_lines = []
                removed = False
                for line in lines:
                    if not removed and line.strip() == target_clean:
                        removed = True
                        continue
                    new_lines.append(line)
                self._dl_urls_txt.delete("1.0", "end")
                if new_lines:
                    self._dl_urls_txt.insert("1.0", "\n".join(new_lines) + "\n")
                self._update_url_count()
            except Exception:
                pass
        self.after(0, _do)

    def _on_download(self):
        if self.is_running:
            return
        urls = self._get_urls_list()
        if not urls:
            messagebox.showerror("Chyba", "Vložte aspoň jeden platný URL odkaz (napr. https://www.instagram.com/reel/...).")
            return
        out_dir = self.v_dl_dir.get().strip()
        if not out_dir:
            out_dir = os.path.join(os.path.expanduser("~"), "Desktop", "ig_downloads")
        os.makedirs(out_dir, exist_ok=True)
        self.v_dl_dir.set(out_dir)

        base = os.path.dirname(os.path.abspath(__file__))
        cookies = next((c for c in [
            os.environ.get("CAPPY_REELS_COOKIES"),
            os.path.join(base, "cookies.txt"),
            os.path.join(base, "..", "data", "cookies.txt"),
            os.path.join(base, "..", "cookies.txt"),
        ] if c and os.path.isfile(c)), None)

        do_drive = self.v_dl_drive.get() and self.gdrive_svc is not None
        self._set_running(True)
        self.log(f"\n{'='*58}")
        self.log(f"SŤAHOVANIE REELS: {len(urls)} videí postupne do {out_dir}")
        self.log(f"Režim: Čisté sťahovanie (bez spoofingu a kódovania)")
        self.log(f"{'='*58}")

        threading.Thread(
            target=self._download_worker,
            args=(urls, out_dir, cookies, do_drive),
            daemon=True
        ).start()

    def _download_worker(self, urls, out_dir, cookies, do_drive):
        total = len(urls)
        success_count = 0
        failed_count = 0
        t0 = time.time()

        for idx, url in enumerate(urls):
            if not self.is_running:
                self.log("\nSTOP — sťahovanie prerušené používateľom.")
                break

            self.log(f"\n[{idx + 1}/{total}] Sťahujem: {url}")
            self._set_progress(idx, total)

            dl = download_reel(url, out_dir, cookies_path=cookies, log=self.log)

            if dl and os.path.exists(dl):
                success_count += 1
                fname = os.path.basename(dl)
                fsize = round(os.path.getsize(dl) / 1048576, 1)
                self.log(f"  ✓ OK: {fname} ({fsize} MB)")

                # Vymazať úspešný odkaz zo zoznamu v GUI
                self._remove_url_from_text(url)

                if do_drive and self.gdrive_svc:
                    self.log(f"  ☁ Uploadujem na Drive: {fname}...")
                    try:
                        upload_to_drive(self.gdrive_svc, dl, fname)
                        self.log("  ☁ Drive upload OK!")
                    except Exception as e:
                        self.log(f"  ☁ Drive CHYBA: {e}")
            else:
                failed_count += 1
                self.log(f"  ✗ CHYBA pri sťahovaní: {url} (ponechané v zozname)")

            self._set_progress(idx + 1, total)

        elapsed = round(time.time() - t0, 1)
        self.log(f"\n{'='*58}")
        self.log(f"SŤAHOVANIE DOKONČENÉ za {elapsed}s | Úspešné: {success_count}/{total} | Zlyhalo: {failed_count}")
        if failed_count > 0:
            self.log(f"⚠ V zozname zostalo {failed_count} odkazov, ktoré zlyhali a môžeš ich skúsiť znova.")
        self.log(f"Výstupná zložka: {out_dir}")
        self.log(f"{'='*58}")

        self._set_progress(total, total)
        self._set_running(False)

    # ─── Farm Sync (Tab 3) ───────────────────────────────────────────────────

    def _build_farm_sync(self, parent):
        # Card 1: Server & Autentifikácia
        c1 = self._card(parent, "🌐  Server & Autentifikácia (Farma)")
        r1 = tk.Frame(c1, bg=BG_CARD); r1.pack(fill="x", pady=2)
        tk.Label(r1, text="Server URL:", fg=MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(side="left")
        self._entry(r1, self.v_farm_url, width=30).pack(side="left", padx=(6, 12))
        tk.Label(r1, text="Master heslo:", fg=MUTED, bg=BG_CARD, font=("Segoe UI", 9)).pack(side="left")
        e_pwd = tk.Entry(r1, textvariable=self.v_farm_pwd, bg=BG_CARD2, fg=TEXT, relief="flat",
                         font=("Segoe UI", 10), insertbackground=ACCENT, show="*", width=14)
        e_pwd.pack(side="left", padx=(6, 12))
        self._farm_load_btn = self._btn(r1, "📥 Načítať profily zo Servera", self._load_farm_profiles, color=ACCENT)
        self._farm_load_btn.pack(side="left")
        self._btn(r1, "🌐 Otvoriť Web Plánovač", self._open_web_planner, color=BG_CARD2, fg=ACCENT3).pack(side="left", padx=(8, 0))

        self._farm_status_lbl = tk.Label(c1, text="Pripájanie k serveru...", fg=MUTED, bg=BG_CARD, font=("Segoe UI", 9))
        self._farm_status_lbl.pack(anchor="w", pady=(6, 0))

        # Card 2: Vstupné fresh videá
        c2 = self._card(parent, "📁  Vstupné fresh Reels (Zložka na PC)")
        r2 = tk.Frame(c2, bg=BG_CARD); r2.pack(fill="x", pady=2)
        self._entry(r2, self.v_farm_dir).pack(side="left", fill="x", expand=True)
        self._btn(r2, "Vybrať zložku...", self._pick_farm_dir).pack(side="left", padx=(6, 0))
        self._btn(r2, "Otvoriť", lambda: self._open_dir(self.v_farm_dir)).pack(side="left", padx=(6, 0))

        self._farm_stats_lbl = tk.Label(c2, text="Zvoľte zložku s fresh videami na PC, ktoré chcete rozdeliť do farmy.",
                                        fg=MUTED, bg=BG_CARD, font=("Segoe UI", 9))
        self._farm_stats_lbl.pack(anchor="w", pady=(6, 0))

        # Card 3: Profily farmy a Odtlačky zariadení
        c3 = self._card(parent, "📱  Profily farmy a Odtlačky zariadení (Server Sync)")
        info_sub = tk.Label(c3, text="Každý profil má unikátny model mobilu (Nothing Phone 2a pre main, Samsung S24 / Pixel pre ostatné). Videá sa rozdelia rovnomerne.",
                            fg=MUTED, bg=BG_CARD, font=("Segoe UI", 8))
        info_sub.pack(anchor="w", pady=(0, 6))

        sel_bar = tk.Frame(c3, bg=BG_CARD); sel_bar.pack(fill="x", pady=(0, 4))
        self._btn(sel_bar, "✓ Označiť všetky", lambda: self._farm_select_all(True), color=BG_CARD2).pack(side="left", padx=(0, 6))
        self._btn(sel_bar, "✗ Odznačiť všetky", lambda: self._farm_select_all(False), color=BG_CARD2).pack(side="left")

        self._farm_accounts_frame = tk.Frame(c3, bg=BG_CARD)
        self._farm_accounts_frame.pack(fill="x", pady=4)
        tk.Label(self._farm_accounts_frame, text="Zatiaľ žiadne profily. Kliknite hore na 'Načítať profily zo Servera'.",
                 fg=MUTED, bg=BG_CARD).pack(anchor="w", pady=4)

        # Card 4: Možnosti & Štart
        c4 = self._card(parent, "⚙  Nastavenia spoofingu a distribúcie")
        r_opt = tk.Frame(c4, bg=BG_CARD); r_opt.pack(fill="x", pady=2)

        rc = tk.Frame(r_opt, bg=BG_CARD); rc.pack(side="left", fill="both", expand=True)
        tk.Label(rc, text="Región GPS súradníc:", fg=MUTED, bg=BG_CARD, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self._radio_row(rc, self.v_farm_region, [("us", "🇺🇸  USA (LA + Vegas mestá)"), ("sk", "🇸🇰  Slovensko")])

        rc2 = tk.Frame(r_opt, bg=BG_CARD); rc2.pack(side="left", fill="both", expand=True, padx=(20, 0))
        tk.Label(rc2, text="Kvalita a Anti-AI Ochrana:", fg=MUTED, bg=BG_CARD, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Checkbutton(rc2, text="Anti-AI Filmic Color Grading + Noise", variable=self.v_farm_grade,
                       bg=BG_CARD, fg=TEXT, selectcolor=BG_CARD, activebackground=BG_CARD,
                       font=("Segoe UI", 9)).pack(anchor="w", pady=1)
        tk.Checkbutton(rc2, text="Uložiť zálohu na disk (spoofed_farm_export/@user/)", variable=self.v_farm_save_local,
                       bg=BG_CARD, fg=TEXT, selectcolor=BG_CARD, activebackground=BG_CARD,
                       font=("Segoe UI", 9)).pack(anchor="w", pady=1)

        # Veľké akčné tlačidlo
        act_row = tk.Frame(parent, bg=BG_DARK); act_row.pack(fill="x", padx=6, pady=(10, 16))
        self._farm_start_btn = tk.Button(
            act_row,
            text="🚀  SPOOFNÚŤ A ROZDELIŤ NA PROFILY (UPLOAD NA GOOGLE DRIVE)",
            font=("Segoe UI", 12, "bold"),
            bg="#059669", fg="white", activebackground="#10b981", activeforeground="white",
            relief="flat", padx=24, pady=12, cursor="hand2", command=self._on_start_farm_sync
        )
        self._farm_start_btn.pack(fill="x")

    def _pick_farm_dir(self):
        d = filedialog.askdirectory(title="Vybrať priečinok s fresh Reels")
        if d:
            self.v_farm_dir.set(d)
            self._update_farm_calc()

    def _farm_select_all(self, state=True):
        for var in self.farm_account_vars.values():
            var.set(state)
        self._update_farm_calc()

    def _load_farm_profiles(self):
        url = self.v_farm_url.get().strip().rstrip("/")
        pwd = self.v_farm_pwd.get().strip()
        if not url:
            if hasattr(self, "_farm_status_lbl"):
                self._farm_status_lbl.configure(text="Zadajte URL servera.", fg=ACCENT2)
            return
        api_url = f"{url}/api/planner/desktop-jobs"
        if hasattr(self, "_farm_status_lbl"):
            self._farm_status_lbl.configure(text=f"Načítavam profily zo servera: {api_url} ...", fg=MUTED)

        def _fetch():
            try:
                req = urllib.request.Request(api_url, headers={"X-Master-Password": pwd, "User-Agent": "IGDesktopSpoofer/2.0"})
                with _urlopen_safe(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if data.get("status") == "ok":
                    accounts = data.get("accounts", [])
                    summary = data.get("summary", {})
                    self.after(0, lambda: self._on_farm_profiles_loaded(accounts, summary))
                else:
                    msg = data.get("message", "Neznáma chyba servera")
                    self.after(0, lambda: self._farm_status_lbl.configure(text=f"CHYBA: {msg}", fg=ACCENT2))
            except Exception as e:
                self.after(0, lambda: self._farm_status_lbl.configure(text=f"CHYBA spojenia: {e}", fg=ACCENT2))

        threading.Thread(target=_fetch, daemon=True).start()

    def _open_web_planner(self):
        import webbrowser
        url = self.v_farm_url.get().strip().rstrip("/") + "/publisher?tab=planner"
        webbrowser.open(url)

    def _on_farm_profiles_loaded(self, accounts, summary):
        self.farm_accounts = accounts
        self.farm_summary = summary or {}
        count = len(accounts)
        self.log(f"  ✓ Načítaných {count} profilov zo servera:")
        for acc in accounts:
            u = acc.get("username")
            dev = acc.get("device_model") or ("Nothing Phone (2a)" if u.lower() == "clarigarzi" else "Samsung Galaxy S24")
            self.log(f"    • @{u} -> {dev}")
        if hasattr(self, "_farm_status_lbl"):
            self._farm_status_lbl.configure(
                text=f"✅ Načítaných {count} profilov farmy zo servera. (Pripravené na synchronizáciu)",
                fg=GREEN
            )
        self._render_farm_accounts_ui()

    def _render_farm_accounts_ui(self):
        if not hasattr(self, "_farm_accounts_frame"):
            return
        for w in self._farm_accounts_frame.winfo_children():
            w.destroy()

        self.farm_account_vars = {}
        if not self.farm_accounts:
            tk.Label(self._farm_accounts_frame, text="Zatiaľ žiadne profily. Kliknite hore na 'Načítať profily zo Servera'.",
                     fg=MUTED, bg=BG_CARD).pack(anchor="w", pady=4)
            return

        sum_accounts = self.farm_summary.get("accounts", []) if hasattr(self, "farm_summary") and isinstance(self.farm_summary, dict) else []
        sum_map = {s.get("username"): s for s in sum_accounts if isinstance(s, dict)}

        for acc in self.farm_accounts:
            u = acc.get("username")
            dev = acc.get("device_model") or ("Nothing Phone (2a)" if u.lower() == "clarigarzi" else "Samsung Galaxy S24")
            var = tk.BooleanVar(value=True)
            self.farm_account_vars[u] = var

            row = tk.Frame(self._farm_accounts_frame, bg=BG_CARD2, padx=10, pady=6)
            row.pack(fill="x", pady=2)

            cb = tk.Checkbutton(row, variable=var, bg=BG_CARD2, selectcolor=BG_CARD,
                                activebackground=BG_CARD2, command=self._update_farm_calc)
            cb.pack(side="left")

            is_main = (u.lower() == "clarigarzi")
            badge_text = "★ MAIN" if is_main else "FARM"
            badge_color = ACCENT if is_main else "#2563eb"
            tk.Label(row, text=badge_text, fg="white", bg=badge_color,
                     font=("Segoe UI", 8, "bold"), padx=6, pady=2).pack(side="left", padx=(4, 10))

            tk.Label(row, text=f"@{u}", fg=TEXT, bg=BG_CARD2,
                     font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 10))

            tk.Label(row, text=f"📱 {dev}", fg=ACCENT3, bg=BG_CARD2,
                     font=("Segoe UI", 9)).pack(side="left", padx=6)

            timing = acc.get("post_times") or "18:00 - 21:00 US"
            tk.Label(row, text=f"⏰ {timing}", fg=MUTED, bg=BG_CARD2,
                     font=("Segoe UI", 8)).pack(side="right")

            acc_s = sum_map.get(u)
            if acc_s:
                unp = acc_s.get("unposted_count", 0)
                dl = acc_s.get("days_left", 0)
                badge_fg = GREEN if dl >= 7 else "#fbbf24"
                tk.Label(row, text=f"📦 {unp} klipov ({dl}d zásoba)", fg=badge_fg, bg=BG_CARD2,
                         font=("Segoe UI", 8, "bold")).pack(side="right", padx=(0, 12))

        self._update_farm_calc()

    def _update_farm_calc(self):
        d = self.v_farm_dir.get().strip()
        selected_accounts = [acc for acc in self.farm_accounts if self.farm_account_vars.get(acc["username"], tk.BooleanVar(value=True)).get()]
        acc_count = len(selected_accounts)

        if not d or not os.path.isdir(d):
            if hasattr(self, "_farm_stats_lbl"):
                self._farm_stats_lbl.configure(text=f"Vybraných {acc_count} profilov. Zvoľte zložku s fresh videami.", fg=MUTED)
            return

        videos = [f for f in os.listdir(d) if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS]
        vid_count = len(videos)
        if acc_count == 0:
            msg = f"Nájdených {vid_count} videí. (Upozornenie: Žiadny profil nie je vybraný!)"
            color = ACCENT2
        else:
            per_profile = vid_count // acc_count
            remainder = vid_count % acc_count
            rem_str = f" (+{remainder} profilov dostane o 1 navyše)" if remainder else ""
            msg = f"Nájdených {vid_count} fresh videí pre {acc_count} profilov -> cca {per_profile} videí na profil{rem_str}."
            color = GREEN

        if hasattr(self, "_farm_stats_lbl"):
            self._farm_stats_lbl.configure(text=msg, fg=color)

    def _on_start_farm_sync(self):
        if self.is_running:
            return
        input_dir = self.v_farm_dir.get().strip()
        if not input_dir or not os.path.isdir(input_dir):
            messagebox.showerror("Chyba", "Vyberte platný priečinok s fresh videami.")
            return

        active_accounts = [acc for acc in self.farm_accounts if self.farm_account_vars.get(acc["username"], tk.BooleanVar(value=False)).get()]
        if not active_accounts:
            messagebox.showerror("Chyba", "Vyberte aspoň jeden profil zo zoznamu.")
            return

        server_url = self.v_farm_url.get().strip().rstrip("/")
        pwd = self.v_farm_pwd.get().strip()
        if not server_url:
            messagebox.showerror("Chyba", "Zadajte URL servera.")
            return

        region = self.v_farm_region.get().strip()
        do_grade = self.v_farm_grade.get()
        save_local = self.v_farm_save_local.get()

        self._set_running(True)
        threading.Thread(
            target=self._farm_sync_worker,
            args=(input_dir, active_accounts, region, do_grade, save_local, server_url, pwd),
            daemon=True
        ).start()

    def _farm_sync_worker(self, input_dir, accounts, region, do_grade, save_local, server_url, pwd):
        files = [os.path.join(input_dir, f) for f in os.listdir(input_dir)
                 if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS]
        files.sort()
        tot = len(files)
        if tot == 0:
            self.log("CHYBA: V zvolenom priečinku sa nenašli žiadne video súbory.")
            self._set_running(False)
            return

        acc_count = len(accounts)
        self.log(f"\n{'='*62}")
        self.log(f"🚀 ŠTART FARMA SPOOFING & DRIVE SYNC")
        self.log(f"Videí: {tot} | Aktívnych profilov: {acc_count} | Región: {region.upper()}")
        self.log(f"Server: {server_url} (Priečinky Google Drive: @username)")
        self.log(f"{'='*62}")

        export_base = os.path.join(input_dir, "spoofed_farm_export") if save_local else None
        if export_base:
            os.makedirs(export_base, exist_ok=True)

        success_count = 0
        failed_count = 0
        t0 = time.time()

        for idx, src_path in enumerate(files):
            if not self.is_running:
                self.log("\nSTOP — spracovanie farmy prerušené používateľom.")
                break

            target_acc = accounts[idx % acc_count]
            username = target_acc["username"]
            device_model = target_acc.get("device_model") or ("Nothing Phone (2a)" if username.lower() == "clarigarzi" else "Samsung Galaxy S24")

            base_name = os.path.splitext(os.path.basename(src_path))[0]
            tok = uuid.uuid4().hex[:6]
            safe_name = f"spoofed_{username}_{base_name}_{tok}.mp4"

            temp_dir = tempfile.mkdtemp(prefix="farm_spoof_")
            temp_out = os.path.join(temp_dir, safe_name)

            self.log(f"\n[{idx + 1}/{tot}] Video: {os.path.basename(src_path)}")
            self.log(f"  👤 Priradené profilu: @{username}")
            self.log(f"  📱 Odtlačok: {device_model} | 📍 GPS: {region.upper()} mestá")
            self._set_progress(idx, tot)

            cfg = {
                "upscale_method": "none",
                "color_grade": do_grade,
                "region": region,
                "device": device_model
            }

            t_spoof = time.time()
            ok = full_pipeline(src_path, temp_out, cfg, self.enc_args, log=self.log)
            dur_spoof = round(time.time() - t_spoof, 1)

            if not ok or not os.path.isfile(temp_out):
                failed_count += 1
                self.log(f"  ✗ CHYBA pri lokálnom spoofovaní po {dur_spoof}s")
                shutil.rmtree(temp_dir, ignore_errors=True)
                continue

            fsize_mb = round(os.path.getsize(temp_out) / 1048576, 1)
            self.log(f"  ✓ Spoofing hotový za {dur_spoof}s ({fsize_mb} MB)")

            # Lokálna kópia ak je povolená
            if export_base:
                prof_dir = os.path.join(export_base, f"@{username}")
                os.makedirs(prof_dir, exist_ok=True)
                local_saved = os.path.join(prof_dir, safe_name)
                try:
                    shutil.copy2(temp_out, local_saved)
                    self.log(f"  💾 Lokálna záloha: @{username}/{safe_name}")
                except Exception as ex:
                    self.log(f"  ⚠ Záloha na disk zlyhala: {ex}")

            # Upload na server API -> Google Drive @username
            self.log(f"  ☁ Odosielam na Server API -> Google Drive (@{username})...")
            try:
                with open(temp_out, "rb") as vf:
                    video_bytes = vf.read()

                fields = {
                    "username": username,
                    "device_model": device_model,
                    "caption": f"Reel vibes ✨ @{username}"
                }
                files_payload = {
                    "video": (safe_name, video_bytes, "video/mp4")
                }
                headers = {
                    "X-Master-Password": pwd
                }
                api_endpoint = f"{server_url}/api/vault/upload-profile-clip"
                res = http_multipart_post(api_endpoint, fields, files_payload, headers=headers, timeout=600)

                if res.get("status") == "ok":
                    success_count += 1
                    self.log(f"  🎉 DRIVE OK: {res.get('message')}")
                else:
                    failed_count += 1
                    self.log(f"  ✗ SERVER CHYBA: {res.get('message', 'Neznáma chyba')}")
            except Exception as e:
                failed_count += 1
                self.log(f"  ✗ CHYBA UPLOADU na server: {e}")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

            self._set_progress(idx + 1, tot)

        elapsed = round(time.time() - t0, 1)
        self.log(f"\n{'='*62}")
        self.log(f"🏁 FARMA SYNC DOKONČENÝ za {elapsed}s")
        self.log(f"Úspešne: {success_count}/{tot} | Zlyhalo: {failed_count}")
        if export_base:
            self.log(f"Lokálne zálohy: {export_base}")
        self.log(f"Plánovač: {server_url}/publisher?tab=planner")
        self.log(f"{'='*62}")

        self._set_progress(tot, tot)
        self._set_running(False)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    if not has_tool("ffmpeg"):
        root = tk.Tk(); root.withdraw()
        messagebox.showerror(
            "Chyba FFmpeg",
            "FFmpeg nebol najdeny!\n\nNainstalovajte:\nwinget install Gyan.FFmpeg\n\nPotom restartujte."
        )
        return
    app = ReelsStudio()
    app.mainloop()


if __name__ == "__main__":
    main()
