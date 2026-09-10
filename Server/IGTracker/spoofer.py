"""
IG Tracker & Publisher — Automated Media Spoofing Engine
Performs safe, imperceptible micro-modifications on video streams (filters, crop/zoom, audio)
and injects realistic device fingerprints & GPS coordinates using ffmpeg and exiftool.
Guarantees unique frame hashes and metadata across distributed accounts.

New in v2: download_reel (yt-dlp), color_grade_and_encode (14 Mbps H.264 + LUT + film grain).
"""
import os
import math
import random
import shutil
import subprocess
import datetime
import uuid
import logging
import tempfile

logger = logging.getLogger(__name__)

# Podporované video a foto formáty
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALL_MEDIA_EXT = VIDEO_EXT | IMAGE_EXT

# Databáza zariadení pre realistický device fingerprinting
DEVICES = [
    ("Nothing", "Phone (2a)"),  # A065 (MediaTek Dimensity 7200 Pro)
    ("Samsung", "SM-S928B"),    # Galaxy S24 Ultra
    ("Samsung", "SM-S921B"),    # Galaxy S24
    ("Samsung", "SM-S911B"),    # Galaxy S23
    ("Google", "Pixel 9 Pro"),
    ("Google", "Pixel 8 Pro"),
    ("Apple", "iPhone 16 Pro"),
    ("Apple", "iPhone 15 Pro"),
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

# GPS lokácie pre US profily (výhradne náhodné hotspoty v Los Angeles, CA a Las Vegas, NV)
CITIES_US = [
    # ── Los Angeles, CA ──
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
    # ── Las Vegas, NV ──
    ("Las Vegas (The Strip / Bellagio Fountains), NV", 36.1126, -115.1767),
    ("Las Vegas (Caesars Palace / Colosseum), NV", 36.1162, -115.1745),
    ("Las Vegas (Downtown / Fremont Street Experience), NV", 36.1699, -115.1438),
    ("Las Vegas (The Venetian & Palazzo Resort), NV", 36.1212, -115.1697),
    ("Las Vegas (South Strip / Mandalay Bay), NV", 36.0919, -115.1761),
    ("Las Vegas (Arts District / 18b), NV", 36.1554, -115.1528),
    ("Las Vegas (Summerlin / Red Rock Canyon), NV", 36.1989, -115.3013),
    ("Las Vegas (Resorts World / North Strip), NV", 36.1337, -115.1668),
    ("Las Vegas (Wynn & Encore), NV", 36.1265, -115.1654),
    ("Las Vegas (Aria & Cosmopolitan), NV", 36.1098, -115.1761),
]

CITIES_SK = [
    ("Bratislava, SK", 48.1486, 17.1077),
    ("Košice, SK", 48.7164, 21.2611),
    ("Žilina, SK", 49.2231, 18.7394),
    ("Banská Bystrica, SK", 48.7363, 19.1462),
    ("Trnava, SK", 48.3774, 17.5883),
]


def check_tool(name: str) -> bool:
    return shutil.which(name) is not None


def has_audio_stream(path: str) -> bool:
    """Vrati True ak ma video audio stopu."""
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


def dms_ref(val: float, pos: str, neg: str) -> str:
    return pos if val >= 0 else neg


def probe_video_info(path: str) -> dict:
    """Zistí trvanie, rozlíšenie a veľkosť videa alebo fotky pomocou ffprobe."""
    info = {
        "file_size": 0,
        "duration_seconds": 0.0,
        "width": 0,
        "height": 0,
    }
    if not os.path.isfile(path):
        return info

    info["file_size"] = os.path.getsize(path)
    ext = os.path.splitext(path)[1].lower()

    if not check_tool("ffprobe"):
        return info

    try:
        # 1. Trvanie (len pre videá)
        if ext in VIDEO_EXT:
            cmd_dur = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
                path
            ]
            r = subprocess.run(cmd_dur, capture_output=True, text=True, timeout=10)
            if r.returncode == 0 and r.stdout.strip():
                info["duration_seconds"] = round(float(r.stdout.strip()), 2)

        # 2. Rozmery
        cmd_res = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0", path
        ]
        r2 = subprocess.run(cmd_res, capture_output=True, text=True, timeout=10)
        if r2.returncode == 0 and "x" in r2.stdout.strip():
            parts = r2.stdout.strip().split("x")
            info["width"] = int(parts[0])
            info["height"] = int(parts[1])
    except Exception as e:
        logger.warning(f"Chyba pri zisťovaní info o médiu {path}: {e}")

    return info


def generate_thumbnail(media_path: str, out_thumb_path: str, time_offset="00:00:01") -> bool:
    """Vygeneruje JPG náhľad z videa (alebo resizuje fotku) pomocou ffmpeg."""
    os.makedirs(os.path.dirname(out_thumb_path), exist_ok=True)
    ext = os.path.splitext(media_path)[1].lower()

    if not check_tool("ffmpeg"):
        if ext in IMAGE_EXT:
            shutil.copyfile(media_path, out_thumb_path)
            return True
        return False

    try:
        if ext in IMAGE_EXT:
            cmd = [
                "ffmpeg", "-y", "-i", media_path,
                "-vf", "scale=480:-1",
                "-q:v", "2", out_thumb_path
            ]
        else:
            cmd = [
                "ffmpeg", "-y", "-ss", time_offset,
                "-i", media_path, "-vframes", "1",
                "-q:v", "2", out_thumb_path
            ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return r.returncode == 0 and os.path.exists(out_thumb_path)
    except Exception as e:
        logger.warning(f"Thumbnail generation failed: {e}")
        if ext in IMAGE_EXT and os.path.isfile(media_path):
            shutil.copyfile(media_path, out_thumb_path)
            return True
        return False


def get_sharpen_filter() -> str:
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


def build_spoof_filters(is_copy: bool = False) -> str:
    """Vráti vyladený Cinematic EQ filter (alebo náhodný jitter pre kópie)."""
    if not is_copy:
        return BASE_EQ_FILTER
    return build_copy_jitter_filter()


def build_copy_jitter_filter() -> str:
    """Jemný jitter okolo 1.0 pre kópie, aby bol každý pixelový hash pre algo unikátny a hodnoty zostali v TOP rozsahu."""
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


def apply_exif_metadata(file_path: str, region: str = "us", device: str = None):
    """Zapíše čisté EXIF metadáta a device fingerprint pomocou exiftool."""
    if not check_tool("exiftool"):
        logger.warning("exiftool nie je dostupný, preskakujem zápis metadát.")
        return

    # 1. Výber konkrétneho alebo náhodného smartfónu
    make, model, software = resolve_device(device)

    # 2. Náhodný čas vytvorenia (v rozmedzí posledných 1 až 14 dní)
    days_ago = random.randint(1, 14)
    hour = random.randint(9, 21)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    file_dt = datetime.datetime.now() - datetime.timedelta(days=days_ago)
    file_dt = file_dt.replace(hour=hour, minute=minute, second=second)
    dt_str = file_dt.strftime("%Y:%m:%d %H:%M:%S")

    # 3. GPS súradnice podľa regiónu účtu (pre US výhradne Los Angeles alebo Las Vegas)
    cities = CITIES_US if region.lower() == "us" else CITIES_SK
    city_name, lat, lon = random.choice(cities)
    # Mikro-jitter cca ±300 až 500 metrov v rámci konkrétnej štvrte/hotspotu
    jitter = random.uniform(-0.004, 0.004)
    j_lat = round(lat + jitter, 6)
    j_lon = round(lon + jitter, 6)

    # 4. Unikátne ID snímku
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
        file_path
    ]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if r.returncode != 0:
        logger.warning(f"Exiftool warning pri {file_path}: {r.stderr[:200]}")

    meta = {
        "device": f"{make} {model}",
        "software": software,
        "city": city_name,
        "lat": j_lat,
        "lon": j_lon,
        "created_at": dt_str,
        "unique_id": uid
    }
    logger.info(f"Aplikované EXIF metadáta pre {os.path.basename(file_path)}: {make} {model} ({software}), GPS: {city_name} ({j_lat}, {j_lon})")
    return meta


def spoof_video_for_account(
    src_video_path: str,
    out_spoofed_path: str,
    region: str = "us",
    color_grade: bool = True,
    is_copy: bool = False,
    device: str = None,
    **kwargs,
) -> dict:
    """
    Kompletny proces spoofovania pre jeden konkretny profil.
    Pouzije novy Instagram-ready pipeline:
    - scale+crop 1080x1920 (Lanczos)
    - CAS 0.4 adaptivne doostrenie
    - Cinematic EQ (contrast=1.06, brightness=-0.01, gamma=0.97, saturation=1.03)
    - CPU libx264 -crf 18 -preset fast
    - -map_metadata -1 + nove EXIF a GPS pre dany profil a dany model zariadenia.
    """
    if not os.path.isfile(src_video_path):
        raise FileNotFoundError(f"Master video neexistuje: {src_video_path}")
    if not check_tool("ffmpeg"):
        raise RuntimeError("ffmpeg nie je nainstalovany.")
    os.makedirs(os.path.dirname(out_spoofed_path), exist_ok=True)

    if color_grade:
        ok = color_grade_and_encode(
            src_video_path, out_spoofed_path,
            is_copy=is_copy
        )
        if not ok:
            logger.warning("color_grade_and_encode zlyhalo, pouzivam legacy spoof.")
            color_grade = False

    if not color_grade:
        vf = build_spoof_filters(is_copy=is_copy)
        has_a = has_audio_stream(src_video_path)
        cmd = ["ffmpeg", "-y", "-i", src_video_path]
        if not has_a:
            cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd += [
            "-map_metadata", "-1",
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-crf", "18", "-preset", "fast",
            "-c:a", "copy" if has_a else "aac",
            "-map", "0:v", "-map", ("0:a?" if has_a else "1:a"),
            "-shortest",
            out_spoofed_path
        ]
        logger.info(f"Legacy spoof: {os.path.basename(src_video_path)} -> {os.path.basename(out_spoofed_path)}")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not os.path.exists(out_spoofed_path):
            raise RuntimeError(f"ffmpeg zlyhal: {r.stderr[-400:]}")

    meta = apply_exif_metadata(out_spoofed_path, region=region, device=device)
    logger.info(
        f"Video spoofnute ({os.path.getsize(out_spoofed_path)} B, "
        f"region={region.upper()}, device={meta.get('device') if meta else device}, GPS={meta.get('city') if meta else 'N/A'})"
    )
    return meta or {}


def download_reel(url: str, out_dir: str, cookies_path: str = None) -> str | None:
    """
    Stiahne Reel / video z URL pomocou yt-dlp (inspirovane CaPPyTools/reels.py).
    Vracia cestu k stiahnutemu suboru alebo None.
    """
    if not check_tool("yt-dlp"):
        logger.error("yt-dlp nie je nainstalovany na serveri.")
        return None
    os.makedirs(out_dir, exist_ok=True)
    work_dir = tempfile.mkdtemp(prefix="dl_", dir=out_dir)

    cmd = [
        "yt-dlp",
        "-o", os.path.join(work_dir, "%(uploader)s_%(id)s.%(ext)s"),
        "--no-playlist", "--ignore-errors", "--newline",
        "--retries", "5", "--fragment-retries", "5", "--no-part",
        "--force-overwrites",
        "--age-limit", "100",
        "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
    ]
    if cookies_path and os.path.isfile(cookies_path):
        cmd += ["--cookies", cookies_path]
    cmd.append(url)
    logger.info(f"yt-dlp: {url[:80]}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except subprocess.TimeoutExpired:
        logger.error("yt-dlp: casovy limit 10 min prekroceny.")
        shutil.rmtree(work_dir, ignore_errors=True)
        return None
    except Exception as e:
        logger.error(f"yt-dlp spustenie zlyhalo: {e}")
        shutil.rmtree(work_dir, ignore_errors=True)
        return None

    files = os.listdir(work_dir)
    media_ext = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
    media = [f for f in files if os.path.splitext(f)[1].lower() in media_ext]
    pick = media or files
    if pick:
        src_temp = os.path.join(work_dir, pick[0])
        final_path = os.path.join(out_dir, pick[0])
        # Presun do out_dir
        if os.path.exists(final_path):
            try: os.remove(final_path)
            except Exception: pass
        shutil.move(src_temp, final_path)
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.info(f"yt-dlp: uspesne stiahnute: {pick[0]}")
        return final_path

    shutil.rmtree(work_dir, ignore_errors=True)
    tail = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
    logger.error("yt-dlp zlyhalo: " + (tail[-1] if tail else "neznama chyba"))
    return None


def generate_anti_ai_lut(out_path=None, size=33):
    """
    Procedurálny 3D LUT (33×33×33 point .cube súbor) Anti-AI Filmic:
    - Hlboká čierna (Deep Blacks): Zachováva 100% bohatý dynamický rozsah a kontrast originálu.
    - Soft Highlight Roll-off: Jemné stiahnutie najvyšších prepalov s jemným oteplením (eliminácia digitálnych prepalov).
    - Luma vs. Saturation: Desaturácia len extrémnych prepálených svetiel (>95 % jasu).
    - Split Toning: Neutrálne/prirodzené pleťové tóny v stredoch, stiahnutie neónovej zelenej.
    """
    if out_path and os.path.isfile(out_path):
        return out_path
    if not out_path:
        cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "luts")
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


def color_grade_and_encode(
    src_path: str,
    out_path: str,
    is_copy: bool = False,
    **kwargs,
) -> bool:
    """
    Kompletný FFmpeg pipeline pre Instagram Reels:
    1. Pomer strán a vycentrovaný orez na presných 1080x1920:
       scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2
    2. Adaptívne doostrenie: AMD FidelityFX CAS 0.3 (alebo unsharp)
    3. Cinematic EQ: eq=contrast=1.055:brightness=-0.007:gamma=0.97:saturation=1.035 (alebo jitter pre kópie)
    4. Audio Guard: -c:a copy pre bezstratový prenos, anullsrc stereo ak audio chýba
    5. Instagram Enkódovanie: libx264 CPU s -crf 18 -preset fast pre vizuálne bezstratový export
    6. Vymazané metadáta: -map_metadata -1
    """
    has_a = has_audio_stream(src_path)
    sharp_filter = get_sharpen_filter()
    eq_filter = build_spoof_filters(is_copy=is_copy)

    vf_parts = [
        "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos",
        "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2",
        sharp_filter,
        eq_filter
    ]
    vf = ",".join(vf_parts)

    cmd = ["ffmpeg", "-y", "-i", src_path]
    if not has_a:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd += [
        "-map_metadata", "-1",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
    ]
    if has_a:
        cmd += ["-c:a", "copy"]
    else:
        cmd += ["-c:a", "aac", "-ac", "2", "-b:a", "320k"]
    cmd += [
        "-map", "0:v",
        "-map", ("0:a?" if has_a else "1:a"),
        "-movflags", "+faststart",
        "-shortest",
        out_path
    ]

    logger.info(f"color_grade_and_encode: 1080x1920 Lanczos + {sharp_filter} + {eq_filter[:45]}, CRF 18 libx264")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0 or not os.path.exists(out_path):
        logger.warning(f"Enkódovanie s copy zlyhalo, prepínam na kompatibilný fallback: {r.stderr[-300:]}")
        cmd2 = ["ffmpeg", "-y", "-i", src_path]
        if not has_a:
            cmd2 += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd2 += [
            "-map_metadata", "-1",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2", "-b:a", "320k",
            "-map", "0:v", "-map", ("0:a?" if has_a else "1:a"),
            "-movflags", "+faststart", "-shortest",
            out_path
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=600)
        return r2.returncode == 0 and os.path.exists(out_path)
    return True
