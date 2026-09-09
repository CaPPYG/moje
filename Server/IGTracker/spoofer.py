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
    """Vráti AMD FidelityFX CAS (Contrast Adaptive Sharpening) alebo unsharp fallback."""
    try:
        r = subprocess.run(["ffmpeg", "-h", "filter=cas"], capture_output=True, timeout=2)
        if r.returncode == 0:
            return "cas=0.35"
    except Exception:
        pass
    return "unsharp=5:5:0.6:5:5:0.0"


def build_spoof_filters() -> str:
    """
    Vygeneruje bezpečné náhodné filtre (jemný jitter), ktoré ľudské oko
    nevníma, ale pre algoritmus Instagramu menia každý jeden pixelový hash.
    """
    sat = random.uniform(0.985, 1.015)
    cont = random.uniform(0.985, 1.015)
    bright = random.uniform(-0.008, 0.008)
    gamma = random.uniform(0.985, 1.015)
    hue = random.uniform(-1.0, 1.0)
    col_temp = random.uniform(-0.015, 0.015)

    filters = [
        f"eq=saturation={sat:.4f}:contrast={cont:.4f}:brightness={bright:.4f}:gamma={gamma:.4f}",
        f"colorbalance=rs={col_temp:.4f}:gs=0:bs={-col_temp:.4f}:rm={col_temp/2:.4f}:gm=0:bm={-col_temp/2:.4f}",
        f"hue=h={hue:.2f}",
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


def spoof_video_for_account(
    src_video_path: str,
    out_spoofed_path: str,
    region: str = "us",
    color_grade: bool = True,
    grain: int = 9,
    lut_path: str = None,
) -> dict:
    """
    Kompletny proces spoofovania pre jeden konkretny profil.
    Ak color_grade=True: pouzije Instagram-ready pipeline (14 Mbps H.264 High 4.2,
    scale+crop 1080x1920, LUT, film grain, spoof jitter, AAC 320k stereo).
    Inak: jednoduchy jitter encode (legacy).
    """
    if not os.path.isfile(src_video_path):
        raise FileNotFoundError(f"Master video neexistuje: {src_video_path}")
    if not check_tool("ffmpeg"):
        raise RuntimeError("ffmpeg nie je nainstalovany.")
    os.makedirs(os.path.dirname(out_spoofed_path), exist_ok=True)

    if color_grade:
        ok = color_grade_and_encode(
            src_video_path, out_spoofed_path,
            lut_path=lut_path, grain=grain, spoof=True
        )
        if not ok:
            logger.warning("color_grade_and_encode zlyhalo, pouzivam legacy spoof.")
            color_grade = False

    if not color_grade:
        vf = build_spoof_filters()
        has_a = has_audio_stream(src_video_path)
        cmd = ["ffmpeg", "-y", "-i", src_video_path]
        if not has_a:
            cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd += [
            "-map_metadata", "-1",
            "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
            "-vf", vf,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-crf", "18", "-preset", "fast",
            "-c:a", "aac", "-ac", "2", "-b:a", "192k",
            "-map", "0:v", "-map", ("0:a?" if has_a else "1:a"),
            "-shortest",
            out_spoofed_path
        ]
        logger.info(f"Legacy spoof: {os.path.basename(src_video_path)} -> {os.path.basename(out_spoofed_path)}")
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0 or not os.path.exists(out_spoofed_path):
            raise RuntimeError(f"ffmpeg zlyhal: {r.stderr[-400:]}")

    meta = apply_exif_metadata(out_spoofed_path, region=region)
    logger.info(
        f"Video spoofnute ({os.path.getsize(out_spoofed_path)} B, "
        f"region={region.upper()}, GPS={meta.get('city') if meta else 'N/A'})"
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
    - Lifted Blacks: Jemné zdvihnutie čierneho bodu (+1.5 %) pre analógový filmový kontrast.
    - Soft Highlight Roll-off: Stiahnutie najvyšších svetiel o 4 % s jemným oteplením (eliminácia digitálnych prepalov).
    - Luma vs. Saturation: Desaturácia hlbokých tieňov (<10 % jasu) a extrémnych svetiel (>90 % jasu).
    - Split Toning: Neutrálne/chladné tiene, prirodzené teplé tóny v stredoch, stiahnutie neónovej zelenej.
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
                lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
                r1 = 0.015 + 0.985 * r
                g1 = 0.015 + 0.985 * g
                b1 = 0.015 + 0.985 * b
                y1 = 0.2126 * r1 + 0.7152 * g1 + 0.0722 * b1

                if y1 > 0.75:
                    hf = (y1 - 0.75) / 0.25
                    roll = (hf ** 2) * 0.04
                    r2 = r1 - roll * 0.80
                    g2 = g1 - roll * 1.00
                    b2 = b1 - roll * 1.30
                else:
                    r2, g2, b2 = r1, g1, b1

                r3, g3, b3 = r2, g2, b2
                if y1 < 0.35:
                    sw = (1.0 - y1 / 0.35) * 0.02
                    r3 -= sw * 0.5
                    b3 += sw
                elif 0.30 <= y1 <= 0.75:
                    mw = math.sin((y1 - 0.30) / 0.45 * math.pi) * 0.022
                    r3 += mw * 1.2
                    g3 += mw * 0.3
                    b3 -= mw * 0.6

                if g > r and g > b:
                    excess_g = g - max(r, b)
                    g3 -= excess_g * 0.22

                lum3 = 0.2126 * r3 + 0.7152 * g3 + 0.0722 * b3
                if y1 < 0.10:
                    sat_f = y1 / 0.10
                    r4 = lum3 + sat_f * (r3 - lum3)
                    g4 = lum3 + sat_f * (g3 - lum3)
                    b4 = lum3 + sat_f * (b3 - lum3)
                elif y1 > 0.90:
                    sat_f = 1.0 - 0.35 * ((y1 - 0.90) / 0.10)
                    r4 = lum3 + sat_f * (r3 - lum3)
                    g4 = lum3 + sat_f * (g3 - lum3)
                    b4 = lum3 + sat_f * (b3 - lum3)
                else:
                    r4, g4, b4 = r3, g3, b3

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
    lut_path: str = None,
    grain: int = 8,
    spoof: bool = True,
) -> bool:
    """
    Kompletný FFmpeg pipeline pre Instagram Reels (One-pass filter):
    1. Pomer strán a vycentrovaný orez na presných 1080x1920:
       scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2
    2. Color Grading: Procedurálny 33x33x33 Anti-AI Filmic alebo externý .cube cez lut3d
    3. Filmové zrno: noise=alls={grain}:allf=t+u (predvolená hodnota: 8)
    4. Audio Guard: anullsrc ak chýba audio stopa
    5. Instagram Enkódovanie: H.264 High 4.2 / ultrafast, 14M / 16M / 20M, faststart, AAC 320k
    """
    has_a = has_audio_stream(src_path)

    vf_parts = []
    if spoof:
        vf_parts.extend(build_spoof_filters().split(","))

    # Procedurálny Anti-AI Filmic LUT (ak používateľ nezadá vlastný .cube)
    if not lut_path or not os.path.isfile(lut_path):
        lut_path = generate_anti_ai_lut()
        logger.info("Aplikujem procedurálny Anti-AI Filmic LUT (33×33×33)")
    else:
        logger.info(f"Aplikujem externý LUT: {os.path.basename(lut_path)}")

    lut_norm = os.path.abspath(lut_path).replace("\\", "/")
    if len(lut_norm) >= 2 and lut_norm[1] == ":":
        lut_esc = lut_norm[0] + "\\\\:" + lut_norm[2:]
    else:
        lut_esc = lut_norm
    vf_parts.append(f"lut3d={lut_esc}")

    if grain and grain > 0:
        vf_parts.append(f"noise=alls={grain}:allf=t+u")

    sharp_filter = get_sharpen_filter()

    # Kompletný reťazec v správnom poradí:
    # 1. Scale & vycentrovaný Crop na 1080x1920 (Lanczos)
    # 2. Doostrenie (AMD CAS 0.35 alebo unsharp)
    # 3. Spoof farebné odchýlky
    # 4. Color Grading (.cube LUT)
    # 5. Filmové zrno (až po doostrení, aby zrno nebolo preostrené)
    vf_parts = [
        "scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos",
        "crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2",
        sharp_filter,
    ]
    if spoof:
        vf_parts.extend(build_spoof_filters().split(","))

    vf_parts.append(f"lut3d={lut_esc}")

    if grain and grain > 0:
        vf_parts.append(f"noise=alls={grain}:allf=t+u")

    vf = ",".join(vf_parts)

    cmd = ["ffmpeg", "-y", "-i", src_path]
    if not has_a:
        cmd += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
    cmd += [
        "-map_metadata", "-1",
        "-vf", vf,
        "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.2",
        "-preset", "veryfast",
        "-b:v", "14M", "-maxrate", "16M", "-bufsize", "20M",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ac", "2", "-b:a", "320k",
        "-map", "0:v",
        "-map", ("0:a?" if has_a else "1:a"),
        "-movflags", "+faststart",
        "-shortest",
        out_path
    ]

    logger.info(f"color_grade_and_encode: 1080x1920 Lanczos + {sharp_filter} + LUT + Grain {grain}, 14 Mbps H.264")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if r.returncode != 0 or not os.path.exists(out_path):
        logger.warning(f"Hlavny encode zlyhal, skusam fallback: {r.stderr[-300:]}")
        cmd2 = ["ffmpeg", "-y", "-i", src_path]
        if not has_a:
            cmd2 += ["-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100"]
        cmd2 += [
            "-map_metadata", "-1",
            "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920:(in_w-1080)/2:(in_h-1920)/2,{sharp_filter},lut3d={lut_esc},noise=alls={grain}:allf=t+u",
            "-c:v", "libx264", "-profile:v", "high", "-level:v", "4.2",
            "-preset", "slow",
            "-b:v", "14M", "-maxrate", "16M", "-bufsize", "20M",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ac", "2", "-b:a", "320k",
            "-map", "0:v", "-map", ("0:a?" if has_a else "1:a"),
            "-movflags", "+faststart", "-shortest",
            out_path
        ]
        r2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=300)
        return r2.returncode == 0 and os.path.exists(out_path)
    return True
