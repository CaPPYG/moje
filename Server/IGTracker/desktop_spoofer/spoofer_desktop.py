#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
  IG TRACKER & PUBLISHER — DESKTOP BATCH SPOOFER & CLOUD VAULT UPLOADER
================================================================================
  Tento nástroj využíva plný výkon vášho PC (GPU/CPU) na bleskový spoofing
  desiatok Reels videí naraz a ich priamy upload na 5 TB Google Drive.
"""

import os
import sys
import glob
import time
import uuid
import random
import shutil
import datetime
import subprocess

# Nastavenie kódovania konzoly pre diakritiku
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ── Databáza zariadení ────────────────────────────────────────────────────────
DEVICES = [
    ("Apple", "iPhone 16 Pro"),
    ("Apple", "iPhone 15 Pro Max"),
    ("Apple", "iPhone 15"),
    ("Apple", "iPhone 14 Pro"),
    ("Samsung", "SM-S928B"),  # Galaxy S24 Ultra
    ("Samsung", "SM-S921B"),  # Galaxy S24
    ("Samsung", "SM-S911B"),  # Galaxy S23
    ("Google", "Pixel 9 Pro"),
    ("Google", "Pixel 8 Pro"),
    ("OnePlus", "CPH2573"),
]

# ── GPS Lokácie (US: Los Angeles & Las Vegas) ─────────────────────────────────
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

VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm"}
DEFAULT_VAULT_FOLDER_ID = "1NyPnFW4O8NYd_BEzMf5c43XWQlr8zsSJ"


def has_tool(name):
    return shutil.which(name) is not None


def detect_best_ffmpeg_encoder():
    """Zistí, či je na PC dostupná hardvérová akcelerácia GPU (Nvidia NVENC, Intel QSV, AMD AMF)."""
    if not has_tool("ffmpeg"):
        return "libx264", ["-preset", "veryfast", "-crf", "18"]

    try:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
        out = r.stdout or ""
        if "h264_nvenc" in out:
            return "h264_nvenc (Nvidia GPU akcelerácia)", ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "19"]
        elif "h264_qsv" in out:
            return "h264_qsv (Intel QuickSync akcelerácia)", ["-c:v", "h264_qsv", "-preset", "faster", "-global_quality", "20"]
        elif "h264_amf" in out:
            return "h264_amf (AMD GPU akcelerácia)", ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cbr"]
    except Exception:
        pass

    return "libx264 (CPU)", ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]


def build_spoof_filters():
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


def apply_exif(file_path, region="us"):
    if not has_tool("exiftool"):
        return None

    make, model = random.choice(DEVICES)
    days_ago = random.randint(1, 14)
    hour = random.randint(9, 21)
    minute = random.randint(0, 59)
    second = random.randint(0, 59)
    file_dt = datetime.datetime.now() - datetime.timedelta(days=days_ago)
    file_dt = file_dt.replace(hour=hour, minute=minute, second=second)
    dt_str = file_dt.strftime("%Y:%m:%d %H:%M:%S")

    cities = CITIES_US if region.lower() == "us" else CITIES_SK
    city_name, lat, lon = random.choice(cities)
    jitter = random.uniform(-0.004, 0.004)
    j_lat = round(lat + jitter, 6)
    j_lon = round(lon + jitter, 6)
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
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return {"device": f"{make} {model}", "city": city_name, "lat": j_lat, "lon": j_lon}
    except Exception:
        return None


def init_gdrive():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        print("\n❌ Chýbajú knižnice pre Google Drive. Inštalujem potrebné balíčky...")
        subprocess.run([sys.executable, "-m", "pip", "install", "google-api-python-client", "google-auth-httplib2", "google-auth-oauthlib"])
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

    base_dir = os.path.dirname(os.path.abspath(__file__))
    token_candidates = [
        os.path.join(base_dir, "drive_token.json"),
        os.path.join(base_dir, "..", "data", "drive_token.json"),
        os.path.join(base_dir, "..", "Drive", "data", "drive_token.json"),
    ]
    token_file = None
    for tc in token_candidates:
        if os.path.exists(tc):
            token_file = tc
            break

    if not token_file:
        return None

    try:
        scopes = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_authorized_user_file(token_file, scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_file, "w", encoding="utf-8") as f:
                f.write(creds.to_json())
        return build("drive", "v3", credentials=creds)
    except Exception as e:
        print(f"⚠️ Chyba inicializácie Google Drive: {e}")
        return None


def upload_to_drive(svc, local_path, filename):
    from googleapiclient.http import MediaFileUpload
    file_metadata = {
        "name": filename,
        "parents": [DEFAULT_VAULT_FOLDER_ID]
    }
    media = MediaFileUpload(local_path, mimetype="video/mp4", resumable=True)
    request = svc.files().create(body=file_metadata, media_body=media, fields="id, name, webViewLink")
    response = None
    while response is None:
        status, response = request.next_chunk()
    return response


def main():
    print("=" * 76)
    print("  🚀 IG TRACKER & PUBLISHER — DESKTOP BATCH SPOOFER & DRIVE UPLOADER")
    print("=" * 76)

    # 1. Kontrola FFmpeg & ExifTool
    if not has_tool("ffmpeg"):
        print("\n❌ CHYBA: 'ffmpeg' nebol nájdený na tomto počítači!")
        print("Stiahnite ffmpeg z https://ffmpeg.org/download.html alebo cez 'winget install Gyan.FFmpeg'")
        input("\nStlačte ENTER pre ukončenie...")
        return

    has_exif = has_tool("exiftool")
    if not has_exif:
        print("⚠️ POZOR: 'exiftool' nebol nájdený. (Video filtre pobežia, ale EXIF/GPS bude preskočený).")
        print("Tip: Pre plný EXIF/GPS spoofing nainštalujte ExifTool: 'winget install PhilHarvey.ExifTool'\n")

    # 2. Detekcia HW akcelerácie
    enc_name, enc_args = detect_best_ffmpeg_encoder()
    print(f"⚡ Detegovaný enkóder: {enc_name}")

    # 3. Zložka so vstupnými videami
    default_input = os.path.join(os.path.dirname(os.path.abspath(__file__)), "videa_na_spoof")
    os.makedirs(default_input, exist_ok=True)

    print(f"\n📂 Zadajte cestu k priečinku s vašimi Reels videami:")
    print(f"   (Predvolená zložka: {default_input})")
    user_input = input("👉 Cesta [nechajte prázdne pre predvolenú]: ").strip().strip('"').strip("'")
    input_dir = user_input if user_input else default_input

    if not os.path.isdir(input_dir):
        print(f"❌ Priečinok '{input_dir}' neexistuje!")
        input("\nStlačte ENTER pre ukončenie...")
        return

    # Vyhľadanie video súborov
    all_files = [
        os.path.join(input_dir, f) for f in os.listdir(input_dir)
        if os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS
    ]

    if not all_files:
        print(f"\n⚠️ V priečinku '{input_dir}' sa nenašli žiadne videá (MP4/MOV)!")
        print(f"Vložte sem vaše videá a spustite skript znova.")
        input("\nStlačte ENTER pre ukončenie...")
        return

    print(f"\n✅ Nájdených {len(all_files)} videí na spracovanie.")

    # 4. Voľba regiónu
    print("\n🌍 Zvoľte cieľový región pre GPS a časové zóny:")
    print("   [1] 🇺🇸 USA — Los Angeles & Las Vegas (Hotspoty: Hollywood, Beverly Hills, Venice, Strip, Bellagio) [ODPORÚČANÉ]")
    print("   [2] 🇸🇰 Slovensko — Bratislava, Košice, Žilina, B. Bystrica, Trnava")
    reg_choice = input("👉 Výber [1/2, predvolené 1]: ").strip()
    region = "sk" if reg_choice == "2" else "us"

    # 5. Koľko unikátnych spoofnutých variantov vygenerovať na jedno video
    print("\n🔢 Koľko unikátnych spoofnutých kópií vygenerovať z KAŽDÉHO videa?")
    print("   (Napríklad ak máte 10 videí a 5 účtov, zadajte 5 — každé video dostane 5 rôznych spoofov)")
    var_input = input("👉 Počet variantov [predvolené 1]: ").strip()
    try:
        variants_per_video = max(1, int(var_input))
    except ValueError:
        variants_per_video = 1

    # 6. Priamy upload na Google Drive
    svc = init_gdrive()
    can_upload = svc is not None
    do_upload = False
    if can_upload:
        print("\n☁️ Google Drive účet s 5 TB úložiskom je PRIPOJENÝ!")
        up_choice = input("👉 Nahrať hotové videá priamo do priečinka IG_VAULT na Google Drive? [A/n, predvolené Áno]: ").strip().lower()
        do_upload = (up_choice != "n")
    else:
        print("\n⚠️ Google Drive token nebol nájdený v tomto priečinku. Videá budú uložené lokálne.")

    # Výstupný priečinok pre hotové videá
    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hotove_spoofnute_videa")
    os.makedirs(out_dir, exist_ok=True)

    total_tasks = len(all_files) * variants_per_video
    print("\n" + "=" * 76)
    print(f"  🎬 ZAČÍNA BATCH SPOOFING: {total_tasks} videí celkovo")
    print(f"  📁 Výstupná zložka: {out_dir}")
    if do_upload:
        print(f"  ☁️ Google Drive priečinok: IG_VAULT ({DEFAULT_VAULT_FOLDER_ID})")
    print("=" * 76 + "\n")

    start_time = time.time()
    processed = 0

    for idx, src_file in enumerate(all_files, start=1):
        base_name = os.path.splitext(os.path.basename(src_file))[0]

        for var_idx in range(variants_per_video):
            processed += 1
            rand_token = uuid.uuid4().hex[:6]
            var_suffix = f"_v{var_idx+1}" if variants_per_video > 1 else ""
            out_filename = f"spoofed_{base_name}{var_suffix}_{rand_token}.mp4"
            out_path = os.path.join(out_dir, out_filename)

            print(f"[{processed}/{total_tasks}] Spracovávam: {os.path.basename(src_file)} -> {out_filename}")

            # FFmpeg príkaz
            vf = build_spoof_filters()
            cmd = [
                "ffmpeg", "-y", "-i", src_file,
                "-map_metadata", "-1",
                "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
                "-vf", vf
            ] + enc_args + [
                "-c:a", "aac", "-b:a", "192k",
                out_path
            ]

            t0 = time.time()
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"   ❌ Chyba pri kódovaní: {res.stderr[-250:]}")
                continue

            dur = round(time.time() - t0, 1)
            file_mb = round(os.path.getsize(out_path) / (1024 * 1024), 2)

            # EXIF metadáta
            meta = apply_exif(out_path, region=region)
            gps_info = f"{meta['city']}" if meta else "Základné metadáta"
            dev_info = f"{meta['device']}" if meta else ""

            print(f"   ✅ Naspoofované za {dur}s ({file_mb} MB) | {dev_info} | GPS: {gps_info}")

            # Upload na Google Drive
            if do_upload and svc:
                print(f"   ☁️ Nahrávam do Google Drive IG_VAULT...", end="", flush=True)
                try:
                    drive_res = upload_to_drive(svc, out_path, out_filename)
                    print(f" HOTOVO! (ID: {drive_res.get('id')})")
                except Exception as e:
                    print(f" ❌ Zlyhal upload: {e}")

    total_time = round(time.time() - start_time, 1)
    print("\n" + "=" * 76)
    print(f"  🎉 BATCH SPOOFING DOKONČENÝ ZA {total_time} sekúnd!")
    print(f"  Úspešne spracovaných: {processed}/{total_tasks} videí.")
    if do_upload:
        print("  ☁️ Všetky videá sú na vašom 5 TB Google Drive v priečinku 'IG_VAULT'.")
        print("  👉 Teraz stačí otvoriť web https://garcarzp.online/ig/publisher")
        print("     a v záložke 'Media Vault' kliknúť na '🔄 Synchronizovať z Google Drive'!")
    else:
        print(f"  📁 Hotové videá nájdete v: {out_dir}")
    print("=" * 76 + "\n")

    input("Stlačte ENTER pre ukončenie...")


if __name__ == "__main__":
    main()
