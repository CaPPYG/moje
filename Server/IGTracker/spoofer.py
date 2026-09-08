"""
IG Tracker & Publisher — Automated Media Spoofing Engine
Performs safe, imperceptible micro-modifications on video streams (filters, crop/zoom, audio)
and injects realistic device fingerprints & GPS coordinates using ffmpeg and exiftool.
Guarantees unique frame hashes and metadata across distributed accounts.
"""
import os
import random
import shutil
import subprocess
import datetime
import uuid
import logging

logger = logging.getLogger(__name__)

# Podporované video a foto formáty
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
ALL_MEDIA_EXT = VIDEO_EXT | IMAGE_EXT

# Databáza zariadení pre realistický device fingerprinting
DEVICES = [
    ("Apple", "iPhone 16 Pro"),
    ("Apple", "iPhone 15 Pro"),
    ("Apple", "iPhone 15"),
    ("Apple", "iPhone 14 Pro"),
    ("Samsung", "SM-S928B"),  # Galaxy S24 Ultra
    ("Samsung", "SM-S921B"),  # Galaxy S24
    ("Samsung", "SM-S911B"),  # Galaxy S23
    ("Google", "Pixel 9 Pro"),
    ("Google", "Pixel 8 Pro"),
    ("OnePlus", "CPH2573"),
]

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


def build_spoof_filters() -> str:
    """
    Vygeneruje bezpečné náhodné filtre (jemný jitter), ktoré ľudské oko
    nevníma, ale pre algoritmus Instagramu menia každý jeden pixelový hash.
    """
    sat = random.uniform(0.985, 1.015)
    cont = random.uniform(0.985, 1.015)
    bright = random.uniform(-0.008, 0.008)
    gamma = random.uniform(0.985, 1.015)
    zoom = random.uniform(1.002, 1.008)
    hue = random.uniform(-1.0, 1.0)
    col_temp = random.uniform(-0.015, 0.015)

    filters = [
        f"eq=saturation={sat:.4f}:contrast={cont:.4f}:brightness={bright:.4f}:gamma={gamma:.4f}",
        f"colorbalance=rs={col_temp:.4f}:gs=0:bs={-col_temp:.4f}:rm={col_temp/2:.4f}:gm=0:bm={-col_temp/2:.4f}",
        f"hue=h={hue:.2f}",
        f"scale=iw*{zoom:.4f}:ih*{zoom:.4f},crop=iw/{zoom:.4f}:ih/{zoom:.4f}",
        "unsharp=lx=5:ly=5:la=0.45:cx=5:cy=5:ca=0",
        "hqdn3d=2.0:2.0:6.0:6.0",
        "deband",
    ]
    return ",".join(filters)


def apply_exif_metadata(file_path: str, region: str = "us"):
    """Zapíše čisté EXIF metadáta a device fingerprint pomocou exiftool."""
    if not check_tool("exiftool"):
        logger.warning("exiftool nie je dostupný, preskakujem zápis metadát.")
        return

    # 1. Výber náhodného smartfónu
    make, model = random.choice(DEVICES)

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
        "city": city_name,
        "lat": j_lat,
        "lon": j_lon,
        "created_at": dt_str,
        "unique_id": uid
    }
    logger.info(f"Aplikované EXIF metadáta pre {os.path.basename(file_path)}: {make} {model}, GPS: {city_name} ({j_lat}, {j_lon})")
    return meta


def spoof_video_for_account(src_video_path: str, out_spoofed_path: str, region: str = "us") -> dict:
    """
    Kompletný proces spoofovania pre jeden konkrétny profil:
    1. Aplikuje micro-jitter filtre cez ffmpeg
    2. Zbaví video pôvodných podpisov a metadát
    3. Zapíše čerstvý device fingerprint a GPS (pre US: náhodne Los Angeles alebo Las Vegas)
    """
    if not os.path.isfile(src_video_path):
        raise FileNotFoundError(f"Master video neexistuje: {src_video_path}")

    if not check_tool("ffmpeg"):
        raise RuntimeError("ffmpeg nie je nainštalovaný.")

    os.makedirs(os.path.dirname(out_spoofed_path), exist_ok=True)

    vf = build_spoof_filters()

    # ffmpeg príkaz: re-enkóduje video s bitexact nastaveniami a novým video streamom
    cmd = [
        "ffmpeg", "-y", "-i", src_video_path,
        "-map_metadata", "-1",
        "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
        "-vf", vf,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-crf", "18", "-preset", "fast",
        "-c:a", "aac", "-b:a", "192k",
        out_spoofed_path
    ]

    logger.info(f"Spoofujem video {os.path.basename(src_video_path)} -> {os.path.basename(out_spoofed_path)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if r.returncode != 0 or not os.path.exists(out_spoofed_path):
        raise RuntimeError(f"ffmpeg zlyhal pri spoofovaní: {r.stderr[-400:]}")

    # Aplikácia nového device fingerprintu a GPS metadát (LA / Las Vegas pre US)
    meta = apply_exif_metadata(out_spoofed_path, region=region)

    logger.info(f"Video úspešne spoofnuté ({os.path.getsize(out_spoofed_path)} bajtov, región={region.upper()}, GPS={meta.get('city') if meta else 'N/A'})")
    return meta or {}

