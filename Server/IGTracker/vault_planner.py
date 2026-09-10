"""
IG Tracker & Publisher — Smart Scheduler & Content Vault Planner
Features:
- US Peak Time Targeting (EST/PST peak hours mapped to CET with random jitter)
- Slovak Peak Time Targeting (CET lunch & prime-time)
- Anti-robotics jitter: ± 7 to 23 minutes offset
- Content Matrix: Distributes master videos so no two accounts post identical master in the same window
- Safety Guard: Automatically skips accounts in 🟡 (Action Required) or 🔴 (Error/Banned) state
- Automated Spoofing & Thumbnail Generation for every slot
"""
import os
import random
import logging
from datetime import datetime, date, time as dtime, timedelta, timezone
import db
import spoofer
import ig_api
import fb_api
import gdrive_vault

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_DIR = os.path.join(BASE_DIR, "data", "vault")
SPOOFED_DIR = os.path.join(VAULT_DIR, "spoofed")
THUMBS_DIR = os.path.join(VAULT_DIR, "thumbs")

os.makedirs(VAULT_DIR, exist_ok=True)
os.makedirs(SPOOFED_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)


def calculate_slot_time(target_date: date, slot_index: int = 0, region: str = "us", slot_type: str = None,
                        time_str: str = None, jitter_minutes: int = 10) -> tuple[datetime, str]:
    """
    Vypočíta čas pre post s voliteľným vlastným časom (HH:MM), anti-bot jitterom (± X minút)
    alebo US peak time targetingom.
    Vracia: (datetime_v_cet, peak_window_label)
    """
    j_mins_limit = max(1, int(jitter_minutes or 10))
    jitter_sign = random.choice([-1, 1])
    jitter_mins = jitter_sign * random.randint(1, j_mins_limit)
    jitter_secs = random.randint(0, 59)

    if time_str and ":" in str(time_str):
        try:
            parts = str(time_str).strip().split(":")
            th = int(parts[0]) % 24
            tm = int(parts[1]) % 60
            base_dt = datetime.combine(target_date, dtime(th, tm, 0))
            slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
            est_hour = (slot_dt.hour - 6) % 24
            window_label = f"🇺🇸 US Peak ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET ±{j_mins_limit}m)"
            return slot_dt, window_label
        except Exception:
            pass

    reg = (region or "us").lower()
    if reg == "us":
        if slot_type == "lunch" or slot_index == 1:
            base_dt = datetime.combine(target_date, dtime(19, 15, 0))
            slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
            est_hour = (slot_dt.hour - 6) % 24
            window_label = f"🇺🇸 US Lunch/Popoludnie ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET ±{j_mins_limit}m)"
        elif slot_type == "morning" or slot_index >= 2:
            base_dt = datetime.combine(target_date, dtime(15, 15, 0))
            slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
            est_hour = (slot_dt.hour - 6) % 24
            window_label = f"🇺🇸 US Ráno ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET ±{j_mins_limit}m)"
        else:
            base_dt = datetime.combine(target_date, dtime(1, 30, 0)) + timedelta(days=1)
            slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
            est_hour = (slot_dt.hour - 6) % 24
            window_label = f"🇺🇸 US Prime Evening ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET ±{j_mins_limit}m)"
    else:
        base_dt = datetime.combine(target_date, dtime(19, 45, 0))
        slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
        window_label = f"🇸🇰 SK Prime Večer ({slot_dt.hour:02d}:{slot_dt.minute:02d} CET ±{j_mins_limit}m)"

    return slot_dt, window_label


def create_spoofed_copy_for_slot(master_video: dict, username: str, target_date: date, slot_idx: int) -> tuple[str, str]:
    """Vygeneruje unikátne spoofnuté video a thumbnail pre konkrétny slot a účet."""
    storage_type = master_video.get("storage_type", "local")
    gdrive_id = master_video.get("gdrive_file_id")
    rand_token = random.randint(1000, 9999)
    spoofed_filename = f"spoof_{username}_{target_date.strftime('%Y%m%d')}_s{slot_idx+1}_{rand_token}.mp4"
    spoofed_out_path = os.path.join(SPOOFED_DIR, spoofed_filename)
    thumb_filename = f"thumb_{os.path.splitext(spoofed_filename)[0]}.jpg"
    thumb_out_path = os.path.join(THUMBS_DIR, thumb_filename)

    try:
        if storage_type == "gdrive" and gdrive_id:
            with gdrive_vault.temporary_master(gdrive_id) as temp_master_path:
                spoofer.spoof_video_for_account(temp_master_path, spoofed_out_path, region="us")
                spoofer.generate_thumbnail(spoofed_out_path, thumb_out_path)
        else:
            master_path = os.path.join(VAULT_DIR, master_video["filename"])
            if os.path.isfile(master_path):
                spoofer.spoof_video_for_account(master_path, spoofed_out_path, region="us")
                spoofer.generate_thumbnail(spoofed_out_path, thumb_out_path)
            else:
                return master_video["filename"], master_video.get("thumbnail_path") or ""
        return spoofed_filename, thumb_filename
    except Exception as e:
        logger.error(f"Chyba pri vytváraní spoof kópie pre @{username}: {e}")
        return master_video["filename"], master_video.get("thumbnail_path") or ""


def generate_auto_plan(target_date_str: str = None, posts_per_account: int = 1,
                       account_ids: list = None, default_caption: str = "", default_hashtags: str = "",
                       reuse_videos: bool = True) -> dict:
    """
    Hlavný engine Auto-Plannera:
    1. Filtruje len zdravé účty (🟢)
    2. Overí dostupnosť videí vo Vaulte
    3. Rozdelí master videá bez duplicity v rovnakom slote
    4. Automaticky vygeneruje spoofnuté kópie a náhľady
    5. Uloží naplánované sloty do databázy
    """
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            target_date = datetime.now().date()
    else:
        target_date = datetime.now().date()

    posts_per_account = max(1, min(2, int(posts_per_account)))

    # 1. Získanie a filtrovanie účtov
    all_accounts = db.get_accounts_with_metrics()
    healthy_accounts = []
    skipped_accounts = []

    for acc in all_accounts:
        if account_ids and acc["id"] not in account_ids:
            continue

        # Bezpečnostná kontrola: Preskočíme účty, ktoré vyžadujú akciu (🟡) alebo majú chybu (🔴)
        status = acc.get("health_status", "healthy")
        has_token = acc.get("has_token", False)

        if not has_token or status != "healthy":
            skipped_accounts.append({
                "username": acc["username"],
                "reason": f"Stav: {status.upper()} (Chýba aktívny token alebo vyžaduje overenie)"
            })
            logger.warning(f"Auto-Planner preskakuje @{acc['username']} – nie je v stave Healthy ({status})")
        else:
            healthy_accounts.append(acc)

    if not healthy_accounts:
        return {
            "status": "error",
            "message": "Nebol nájdený žiadny zdravý účet (🟢) pripravený na plánovanie. Skontrolujte tokeny v Health Monitore.",
            "skipped_accounts": skipped_accounts,
            "created_count": 0
        }

    # 2. Získanie master videí z Vaultu
    vault_videos = db.get_all_vault_videos(status="available" if not reuse_videos else None)
    if not vault_videos:
        # Skúsime akékoľvek videá vo vaulte
        vault_videos = db.get_all_vault_videos()

    if not vault_videos:
        return {
            "status": "error",
            "message": "Media Vault je prázdny! Najprv nahrajte master Reels videá do Vaultu.",
            "skipped_accounts": skipped_accounts,
            "created_count": 0
        }

    n_accs = len(healthy_accounts)
    total_slots_needed = n_accs * posts_per_account
    warnings = []

    if len(vault_videos) < n_accs:
        warnings.append(f"Pozor: Vo Vaulte je len {len(vault_videos)} videí pre {n_accs} účtov. Niektoré master videá sa použijú viackrát (každé však bude mať unikátny spoof).")

    # 3. Distribučná matica – rozdelenie videí naprieč účtami a slotmi
    # Každé zariadenie dostane video s rotovaným posunom, aby v rovnakom čase nebol rovnaký master
    created_posts = []
    shuffled_vault = list(vault_videos)
    random.shuffle(shuffled_vault)

    for slot_idx in range(posts_per_account):
        # Pre každý slot posunieme offset v zozname videí
        offset = slot_idx * max(1, len(shuffled_vault) // max(1, posts_per_account))

        for acc_idx, acc in enumerate(healthy_accounts):
            vid_idx = (acc_idx + offset) % len(shuffled_vault)
            master_video = shuffled_vault[vid_idx]
            storage_type = master_video.get("storage_type", "local")
            gdrive_id = master_video.get("gdrive_file_id")

            region = "us"
            slot_time, window_label = calculate_slot_time(target_date, slot_idx, region="us")

            # Vygenerovanie unikátneho spoofnutého videa pre tento konkrétny slot a účet
            rand_token = random.randint(1000, 9999)
            spoofed_filename = f"spoof_{acc['username']}_{target_date.strftime('%Y%m%d')}_s{slot_idx+1}_{rand_token}.mp4"
            spoofed_out_path = os.path.join(SPOOFED_DIR, spoofed_filename)
            thumb_filename = f"thumb_{os.path.splitext(spoofed_filename)[0]}.jpg"
            thumb_out_path = os.path.join(THUMBS_DIR, thumb_filename)

            try:
                if storage_type == "gdrive" and gdrive_id:
                    logger.info(f"Sťahujem dočasný master z Google Drive (ID: {gdrive_id}) pre @{acc['username']}...")
                    with gdrive_vault.temporary_master(gdrive_id) as temp_master_path:
                        spoofer.spoof_video_for_account(temp_master_path, spoofed_out_path, region="us")
                        spoofer.generate_thumbnail(spoofed_out_path, thumb_out_path)
                else:
                    master_path = os.path.join(VAULT_DIR, master_video["filename"])
                    if not os.path.isfile(master_path):
                        logger.warning(f"Súbor {master_path} neexistuje na disku, preskakujem.")
                        continue
                    spoofer.spoof_video_for_account(master_path, spoofed_out_path, region=region)
                    spoofer.generate_thumbnail(spoofed_out_path, thumb_out_path)
            except Exception as e:
                logger.error(f"Zlyhanie pri generovaní spoof videa pre @{acc['username']}: {e}")
                warnings.append(f"Zlyhal spoofing pre @{acc['username']}: {str(e)[:100]}")
                continue

            # Uloženie plánovaného postu do DB
            caption = default_caption or f"Reel vibes ✨ @{acc['username']}"
            hashtags = default_hashtags or "#reels #trending #viral #fyp"

            post_id = db.add_planned_post(
                account_id=acc["id"],
                vault_video_id=master_video["id"],
                spoofed_video_path=spoofed_filename,
                thumbnail_path=thumb_filename,
                scheduled_time=slot_time.strftime("%Y-%m-%d %H:%M:%S"),
                peak_window=window_label,
                caption=caption,
                hashtags=hashtags,
                first_comment=""
            )

            # Označenie master videa v databáze ako naplánované
            if not reuse_videos:
                db.update_vault_video_status(master_video["id"], "scheduled")

            created_posts.append({
                "post_id": post_id,
                "account": acc["username"],
                "region": region.upper(),
                "scheduled_time": slot_time.strftime("%Y-%m-%d %H:%M:%S"),
                "peak_window": window_label,
                "master_video": master_video["original_name"],
                "spoofed_filename": spoofed_filename
            })

    return {
        "status": "ok",
        "message": f"Úspešne naplánovaných {len(created_posts)} príspevkov pre {len(healthy_accounts)} účtov na {target_date.isoformat()}.",
        "target_date": target_date.isoformat(),
        "created_count": len(created_posts),
        "created_posts": created_posts,
        "skipped_accounts": skipped_accounts,
        "warnings": warnings
    }


def schedule_account_reel_set(account_id: int, saved_video_files: list,
                              start_date_str: str = None, frequency: str = "1_evening",
                              default_caption: str = "", default_hashtags: str = "") -> dict:
    """
    Naplánuje sadu vopred pripravených / spoofnutých Reels pre jeden konkrétny účet.
    Všetky profily cielia na US čas (New York EDT / LA PDT) s anti-bot časovým rozptylom.
    """
    account = db.get_account_by_id(account_id)
    if not account:
        return {"status": "error", "message": "Účet nebol nájdený."}

    username = account.get("username", "")
    region = "us"

    freq_str = str(frequency or "1_evening").lower()
    if freq_str in ("1_lunch", "lunch"):
        slot_types_sequence = ["lunch"]
    elif freq_str in ("2", "2_daily", "2_day"):
        slot_types_sequence = ["lunch", "evening"]
    elif freq_str in ("3", "3_daily", "3_day"):
        slot_types_sequence = ["morning", "lunch", "evening"]
    else:
        # Predvolené: 1 Reel denne na US Prime Evening (~19:30 EST)
        slot_types_sequence = ["evening"]

    if start_date_str:
        try:
            curr_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            curr_date = datetime.now().date()
    else:
        curr_date = datetime.now().date()

    created_posts = []
    current_seq_idx = 0

    for idx, vid_filename in enumerate(saved_video_files):
        video_full_path = os.path.join(SPOOFED_DIR, vid_filename)
        if not os.path.isfile(video_full_path):
            logger.warning(f"Súbor {video_full_path} neexistuje, preskakujem.")
            continue

        # Generovanie náhľadu (thumbnail) cez FFmpeg
        thumb_filename = f"thumb_{os.path.splitext(vid_filename)[0]}.jpg"
        thumb_out_path = os.path.join(THUMBS_DIR, thumb_filename)
        if not os.path.isfile(thumb_out_path):
            try:
                spoofer.generate_thumbnail(video_full_path, thumb_out_path)
            except Exception as e:
                logger.warning(f"Chyba pri generovaní náhľadu pre {vid_filename}: {e}")

        # Výpočet času pre slot s US peak targetingom a anti-bot rozptylom
        chosen_type = slot_types_sequence[current_seq_idx]
        slot_time, window_label = calculate_slot_time(curr_date, current_seq_idx, region="us", slot_type=chosen_type)

        caption = default_caption or f"Reel vibes ✨ @{username}"
        hashtags = default_hashtags or "#reels #trending #viral #fyp"

        post_id = db.add_planned_post(
            account_id=account_id,
            vault_video_id=None,
            spoofed_video_path=vid_filename,
            thumbnail_path=thumb_filename,
            scheduled_time=slot_time.strftime("%Y-%m-%d %H:%M:%S"),
            peak_window=window_label,
            caption=caption,
            hashtags=hashtags,
            first_comment=""
        )

        created_posts.append({
            "post_id": post_id,
            "account": username,
            "region": "US",
            "scheduled_time": slot_time.strftime("%Y-%m-%d %H:%M:%S"),
            "peak_window": window_label,
            "spoofed_filename": vid_filename
        })

        # Posun v rozvrhu na ďalší slot alebo ďalší deň
        current_seq_idx += 1
        if current_seq_idx >= len(slot_types_sequence):
            current_seq_idx = 0
            curr_date += timedelta(days=1)

    return {
        "status": "ok",
        "message": f"Úspešne naplánovaných {len(created_posts)} Reels pre @{username} (cielené na US čas).",
        "created_count": len(created_posts),
        "posts": created_posts
    }


def schedule_gdrive_reel_set(account_id: int, count: int = 7, start_date_str: str = None,
                             frequency: str = "1_evening",
                             randomize: bool = True, only_unused: bool = True,
                             default_caption: str = "", default_hashtags: str = "",
                             selected_video_ids: list = None,
                             folder_name: str = None) -> dict:
    """
    Naplánuje sadu Reels priamo z Google Drive priečinka IG_VAULT pre konkrétny účet.
    1. Zosynchronizuje zoznam videí z Google Drive bez zaťaženia VPS disku.
    2. Vyfiltruje videá z určenej zložky (kopie 1, kopie 2...), aby nedochádzalo k duplicitám na jednom účte.
    3. Nájde dostupné videá, náhodne ich premieša (randomize).
    4. Rozvrhne ich do US časových špičiek (s anti-bot jitterom ±7 až 23 min).
    5. Pri publikovaní ich server streamuje priamo z Google Drive.
    """
    account = db.get_account_by_id(account_id)
    if not account:
        return {"status": "error", "message": "Účet nebol nájdený."}

    username = account.get("username", "")

    # 1. Rýchla synchronizácia Google Drive, aby sme mali všetky nové videá v DB
    try:
        gdrive_vault.sync_drive_vault_to_db(quick=True)
    except Exception as e:
        logger.warning(f"Quick drive sync varovanie: {e}")

    # 2. Výber kandidátskych videí z Google Drive
    all_vault = db.get_all_vault_videos()
    gdrive_videos = [v for v in all_vault if v.get("storage_type") == "gdrive"]

    if not gdrive_videos:
        return {
            "status": "error",
            "message": "Na vašom Google Drive v priečinku IG_VAULT sa nenašli žiadne video súbory."
        }

    # Filter podľa zložky / variantu kópie (napr. kopie 1 pre účet 1, kopie 2 pre účet 2...)
    if folder_name and folder_name not in ("all", "vsetky", ""):
        if folder_name == "auto":
            all_accs = db.get_all_accounts()
            acc_index = 0
            for idx, a in enumerate(all_accs):
                if a["id"] == account_id:
                    acc_index = idx
                    break
            suggested_folder = f"kopie {acc_index + 1}"
            filtered_by_folder = [v for v in gdrive_videos if (v.get("folder_name") or "") == suggested_folder]
            if filtered_by_folder:
                gdrive_videos = filtered_by_folder
        else:
            filtered_by_folder = [v for v in gdrive_videos if (v.get("folder_name") or "") == folder_name]
            if filtered_by_folder:
                gdrive_videos = filtered_by_folder

    chosen_pool = []
    if selected_video_ids:
        selected_set = set(int(x) for x in selected_video_ids if str(x).isdigit())
        chosen_pool = [v for v in gdrive_videos if v["id"] in selected_set]
    else:
        # Filter: voľné nepoužité týmto účtom
        if only_unused:
            clean_u = f"@{username.lstrip('@')}"
            for v in gdrive_videos:
                used_by = v.get("used_by_accounts") or ""
                if clean_u not in used_by:
                    chosen_pool.append(v)
            if not chosen_pool:
                # Ak sú všetky použité, vezmeme všetky
                chosen_pool = list(gdrive_videos)
        else:
            chosen_pool = list(gdrive_videos)

    if not chosen_pool:
        return {"status": "error", "message": "Žiadne vhodné videá na Google Drive neboli nájdené."}

    # 3. Randomizácia (premiešanie poradia)
    if randomize:
        random.shuffle(chosen_pool)

    # Obmedzenie na požadovaný počet
    if count and count > 0:
        chosen_pool = chosen_pool[:count]

    # 4. Frekvencia a US časové sloty
    freq_str = str(frequency or "1_evening").lower()
    if freq_str in ("1_lunch", "lunch"):
        slot_types_sequence = ["lunch"]
    elif freq_str in ("2", "2_daily", "2_day"):
        slot_types_sequence = ["lunch", "evening"]
    elif freq_str in ("3", "3_daily", "3_day"):
        slot_types_sequence = ["morning", "lunch", "evening"]
    else:
        slot_types_sequence = ["evening"]

    if start_date_str:
        try:
            curr_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except ValueError:
            curr_date = datetime.now().date()
    else:
        curr_date = datetime.now().date()

    created_posts = []
    current_seq_idx = 0

    for vid in chosen_pool:
        # Výpočet času pre slot s US peak targetingom a anti-bot rozptylom
        chosen_type = slot_types_sequence[current_seq_idx]
        slot_time, window_label = calculate_slot_time(curr_date, current_seq_idx, region="us", slot_type=chosen_type)

        caption = default_caption or f"Reel vibes ✨ @{username}"
        hashtags = default_hashtags or "#reels #trending #viral #fyp"

        thumb_filename = vid.get("thumbnail_path") or ""

        post_id = db.add_planned_post(
            account_id=account_id,
            vault_video_id=vid["id"],
            spoofed_video_path=vid["filename"],
            thumbnail_path=thumb_filename,
            scheduled_time=slot_time.strftime("%Y-%m-%d %H:%M:%S"),
            peak_window=window_label,
            caption=caption,
            hashtags=hashtags,
            first_comment=""
        )

        try:
            db.mark_vault_video_used(vid["id"], username)
        except Exception as e:
            logger.warning(f"Chyba pri označovaní média ako použité: {e}")

        created_posts.append({
            "post_id": post_id,
            "account": username,
            "region": "US",
            "scheduled_time": slot_time.strftime("%Y-%m-%d %H:%M:%S"),
            "peak_window": window_label,
            "original_name": vid.get("original_name"),
            "gdrive_file_id": vid.get("gdrive_file_id")
        })

        # Posun v rozvrhu
        current_seq_idx += 1
        if current_seq_idx >= len(slot_types_sequence):
            current_seq_idx = 0
            curr_date += timedelta(days=1)

    return {
        "status": "ok",
        "message": f"Úspešne naplánovaných {len(created_posts)} Reels z Google Drive pre @{username} (cielené na US čas).",
        "created_count": len(created_posts),
        "posts": created_posts
    }


def publish_planned_post(post_id: int, base_public_url: str = "https://garcarzp.online/ig") -> dict:
    """
    Okamžite vypublikuje naplánovaný post cez Instagram Graph API a Facebook Graph API (Reels).
    1. Skontroluje zdravie a tokeny účtu
    2. Pripraví verejnú URL pre video
    3. Publikuje na povolené platformy (Instagram, Facebook)
    4. Aktualizuje stav v databáze (published / failed)
    """
    post = db.get_planned_post_by_id(post_id)
    if not post:
        return {"status": "error", "message": "Plánovaný príspevok nebol nájdený"}

    account_id = post["account_id"]
    token = post.get("ig_access_token")
    ig_user_id = post.get("ig_user_id")
    username = post.get("username", "")

    vault_vid = db.get_vault_video_by_id(post["vault_video_id"]) if post.get("vault_video_id") else None

    if vault_vid and vault_vid.get("storage_type") == "gdrive":
        public_video_url = f"{base_public_url.rstrip('/')}/api/vault/stream/{vault_vid['id']}/reel.mp4"
    else:
        spoofed_file = post.get("spoofed_video_path", "")
        full_local_path = os.path.join(SPOOFED_DIR, spoofed_file)
        if not os.path.isfile(full_local_path):
            alt_path = os.path.join(VAULT_DIR, spoofed_file)
            if os.path.isfile(alt_path):
                public_video_url = f"{base_public_url.rstrip('/')}/media/vault/{spoofed_file}"
            else:
                err_msg = f"Súbor spoofnutého videa nebol nájdený na serveri: {spoofed_file}"
                db.update_planned_post(post_id, status="failed", error_message=err_msg)
                return {"status": "error", "message": err_msg}
        else:
            public_video_url = f"{base_public_url.rstrip('/')}/media/vault/spoofed/{spoofed_file}"

    caption_text = (post.get("caption") or "").strip()
    hashtags = (post.get("hashtags") or "").strip()
    full_caption = caption_text
    if hashtags:
        full_caption = f"{caption_text}\n\n{hashtags}" if caption_text else hashtags

    post_to_ig = bool(post.get("post_to_ig", 1))
    post_to_fb = bool(post.get("post_to_fb", 1))

    ig_success = False
    fb_success = False
    errors = []
    ig_media_id = None
    fb_media_id = None

    # 1. Publikovanie na Instagram
    if post_to_ig:
        if not token or not ig_user_id:
            errors.append("IG: Účet nemá pripojený aktívny Meta Access Token")
        else:
            logger.info(f"Odosielam IG Reel pre @{username} (UID: {ig_user_id}): {public_video_url}")
            try:
                res = ig_api.publish_reel(
                    token=token,
                    ig_user_id=ig_user_id,
                    video_url=public_video_url,
                    caption=full_caption,
                    share_to_feed=True
                )
                if "error" in res:
                    err_str = res["error"]
                    logger.error(f"Zlyhanie publikovania IG Reelu pre @{username}: {err_str}")
                    errors.append(f"IG: {err_str}")
                else:
                    ig_success = True
                    ig_media_id = res.get("id") or res.get("container_id")
                    logger.info(f"IG Reel úspešne publikovaný pre @{username}! ID: {ig_media_id}")
            except Exception as e:
                logger.exception(f"Výnimka pri IG publikovaní: {e}")
                errors.append(f"IG Exception: {str(e)}")

    # 2. Publikovanie na Facebook (Pages / Reels)
    if post_to_fb:
        fb_page_id = post.get("fb_page_id")
        fb_token = post.get("fb_access_token") or token
        fb_enabled = bool(post.get("fb_enabled", 1))

        if fb_page_id and fb_token and fb_enabled:
            logger.info(f"Odosielam FB Reel pre @{username} na Page {fb_page_id}...")
            try:
                fb_res = fb_api.publish_facebook_reel(
                    page_access_token=fb_token,
                    page_id=fb_page_id,
                    video_url=public_video_url,
                    description=full_caption
                )
                if fb_res.get("success"):
                    fb_success = True
                    fb_media_id = fb_res.get("id")
                    db.update_planned_post(post_id, fb_status="published", fb_media_id=str(fb_media_id))
                    logger.info(f"FB Reel úspešne publikovaný pre @{username}! ID: {fb_media_id}")
                else:
                    fb_err = fb_res.get("error", "Chyba FB publikovania")
                    errors.append(f"FB: {fb_err}")
                    db.update_planned_post(post_id, fb_status="failed", fb_error=str(fb_err))
            except Exception as e:
                logger.exception(f"Výnimka pri FB publikovaní: {e}")
                errors.append(f"FB Exception: {str(e)}")
                db.update_planned_post(post_id, fb_status="failed", fb_error=str(e))
        else:
            db.update_planned_post(post_id, fb_status="skipped", fb_error="Chýba priradená FB Stránka alebo token")

    now_iso = datetime.now(timezone.utc).isoformat()
    # Vyhodnotenie celkového stavu
    if (post_to_ig and ig_success) or (post_to_fb and fb_success) or (not post_to_ig and not post_to_fb):
        db.update_planned_post(
            post_id,
            status="published",
            published_at=now_iso,
            ig_media_id=str(ig_media_id) if ig_media_id else None,
            fb_media_id=str(fb_media_id) if fb_media_id else None,
            error_message=" | ".join(errors) if errors else None
        )
        if post.get("vault_video_id"):
            try:
                db.mark_vault_video_used(post["vault_video_id"], username)
            except Exception:
                pass
        return {
            "status": "ok",
            "message": f"Publikovanie dokončené! (IG: {'OK' if ig_success else 'N/A'}, FB: {'OK' if fb_success else 'N/A'})",
            "ig_media_id": ig_media_id,
            "fb_media_id": fb_media_id,
            "published_at": now_iso
        }
    else:
        err_msg = " | ".join(errors) if errors else "Žiadna vybraná platforma nebola publikovaná."
        db.update_planned_post(post_id, status="failed", error_message=err_msg)
        return {"status": "error", "message": err_msg}


def re_spread_vault_pool(days: int = 7, posts_per_day: int = 1, default_caption: str = "", default_hashtags: str = "") -> dict:
    """
    Smart Pool Distribution inšpirovaná GoroTools:
    - Striktný anti-duplikátový režim pre bežné profily (žiadne dva účty nedostanú rovnaký master klip v rovnaký deň).
    - Ak klipy vo Vaulte dôjdu, naplánujú sa len dni s dostupnými klipmi a vráti sa kapacitné varovanie.
    - Podpora Burner profilov: točia 1-2 vybrané videá z Vaultu s denným unikátnym re-spoofom.
    - Účty bez tokenu sa zaradia tiež s príznakom is_manual_post=1 pre okamžité stiahnutie klipu (.mp4).
    """
    all_accounts = db.get_accounts_with_metrics()
    if not all_accounts:
        return {"status": "error", "message": "Žiadne účty nie sú k dispozícii v systéme."}

    vault_videos = db.get_all_vault_videos()
    if not vault_videos:
        return {"status": "error", "message": "Zásobník videí (Vault) je prázdny! Najprv nahrajte klipy."}

    vault_by_id = {v["id"]: v for v in vault_videos}
    shuffled_vault = list(vault_videos)
    random.shuffle(shuffled_vault)

    burner_accounts = [a for a in all_accounts if a.get("is_burner") == 1]
    regular_accounts = [a for a in all_accounts if a.get("is_burner") != 1]

    n_reg = len(regular_accounts)
    posts_per_day = max(1, min(3, int(posts_per_day or 1)))
    days = max(1, min(30, int(days or 7)))

    total_reg_slots_needed = n_reg * days * posts_per_day
    available_videos = len(vault_videos)
    missing_clips = max(0, total_reg_slots_needed - available_videos)

    today = datetime.now().date()
    created_posts = []

    # Vymažeme staré nepublikované ready/scheduled posty od dneška
    with db.get_db() as conn:
        conn.execute("DELETE FROM planned_posts WHERE status IN ('ready', 'scheduled') AND DATE(scheduled_time) >= DATE('now')")

    # 1. Naplánovanie pre bežné účty (striktná alokácia bez duplikátov v rovnaký deň)
    vid_cursor = 0
    for day_idx in range(days):
        target_date = today + timedelta(days=day_idx)

        for slot_idx in range(posts_per_day):
            # Skontrolujeme, či máme dosť unikátnych klipov pre všetkých regular_accounts v tomto slote
            if vid_cursor >= len(shuffled_vault):
                # Klipy sa minuli! Striktný režim: neopakujeme duplikáty
                break

            for acc_idx, acc in enumerate(regular_accounts):
                if vid_cursor >= len(shuffled_vault):
                    break

                master_video = shuffled_vault[vid_cursor]
                vid_cursor += 1

                # Vypočítame čas podľa nastavení účtu
                acc_time = acc.get("default_time") or "19:15"
                acc_jitter = acc.get("default_jitter") or 10
                slot_time, window_label = calculate_slot_time(
                    target_date, slot_idx, region="us",
                    time_str=acc_time, jitter_minutes=acc_jitter
                )

                # Generovanie unikátneho spoof súboru a náhľadu
                spoofed_name, thumb_name = create_spoofed_copy_for_slot(
                    master_video, acc["username"], target_date, slot_idx
                )

                caption = acc.get("default_caption") or default_caption or f"Reel vibes ✨ @{acc['username']}"
                hashtags = default_hashtags or "#reels #trending #viral #fyp"
                is_manual = 0 if acc.get("has_token") else 1

                post_id = db.add_planned_post(
                    account_id=acc["id"],
                    vault_video_id=master_video["id"],
                    spoofed_video_path=spoofed_name,
                    thumbnail_path=thumb_name,
                    scheduled_time=slot_time.strftime("%Y-%m-%d %H:%M:%S"),
                    peak_window=window_label,
                    caption=caption,
                    hashtags=hashtags,
                    first_comment=""
                )

                if is_manual:
                    with db.get_db() as conn:
                        conn.execute("UPDATE planned_posts SET is_manual_post = 1 WHERE id = ?", (post_id,))

                created_posts.append({
                    "post_id": post_id,
                    "account": acc["username"],
                    "scheduled_time": slot_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "video_name": master_video.get("original_name"),
                    "is_burner": False,
                    "is_manual": is_manual
                })

    # 2. Naplánovanie pre Burner účty (točia svoje zvolené video s denným unikátnym re-spoofom)
    for b_acc in burner_accounts:
        burner_vids_str = str(b_acc.get("burner_vault_ids") or "").strip()
        burner_vid_ids = [int(x.strip()) for x in burner_vids_str.split(",") if x.strip().isdigit()]
        
        # Ak nemá vybrané video, použijeme prvé z Vaultu
        assigned_vids = [vault_by_id[vid] for vid in burner_vid_ids if vid in vault_by_id]
        if not assigned_vids:
            assigned_vids = [vault_videos[0]]

        acc_time = b_acc.get("default_time") or "19:15"
        acc_jitter = b_acc.get("default_jitter") or 10

        for day_idx in range(days):
            target_date = today + timedelta(days=day_idx)
            for slot_idx in range(posts_per_day):
                master_video = assigned_vids[(day_idx * posts_per_day + slot_idx) % len(assigned_vids)]

                slot_time, window_label = calculate_slot_time(
                    target_date, slot_idx, region="us",
                    time_str=acc_time, jitter_minutes=acc_jitter
                )

                spoofed_name, thumb_name = create_spoofed_copy_for_slot(
                    master_video, b_acc["username"], target_date, slot_idx
                )

                caption = b_acc.get("default_caption") or default_caption or f"Viral vibes ✨ @{b_acc['username']}"
                hashtags = default_hashtags or "#reels #trending #viral #fyp"
                is_manual = 0 if b_acc.get("has_token") else 1

                post_id = db.add_planned_post(
                    account_id=b_acc["id"],
                    vault_video_id=master_video["id"],
                    spoofed_video_path=spoofed_name,
                    thumbnail_path=thumb_name,
                    scheduled_time=slot_time.strftime("%Y-%m-%d %H:%M:%S"),
                    peak_window=window_label,
                    caption=caption,
                    hashtags=hashtags,
                    first_comment=""
                )

                if is_manual:
                    with db.get_db() as conn:
                        conn.execute("UPDATE planned_posts SET is_manual_post = 1 WHERE id = ?", (post_id,))

                created_posts.append({
                    "post_id": post_id,
                    "account": b_acc["username"],
                    "scheduled_time": slot_time.strftime("%Y-%m-%d %H:%M:%S"),
                    "video_name": master_video.get("original_name"),
                    "is_burner": True,
                    "is_manual": is_manual
                })

    warning_msg = ""
    if missing_clips > 0 and n_reg > 0:
        warning_msg = f"Nahrajte ešte {missing_clips} klipov. {n_reg} bežných profilov x {posts_per_day}/deň potrebuje aspoň {total_reg_slots_needed} klipov na {days} dní (k dispozícii je {available_videos})."

    return {
        "status": "ok",
        "message": f"Zásobník bol úspešne prerozdelený ({len(created_posts)} slotov naplánovaných pre {len(all_accounts)} profilov na {days} dní).",
        "warning": warning_msg,
        "created_count": len(created_posts),
        "accounts_count": len(all_accounts),
        "regular_count": n_reg,
        "burner_count": len(burner_accounts),
        "days": days,
        "missing_clips": missing_clips,
        "total_needed": total_reg_slots_needed,
        "available_videos": available_videos
    }


def shuffle_account_unposted(account_id: int) -> dict:
    """Premieša nepostnuté videá pre daný účet."""
    posts = db.get_unposted_posts_by_account(account_id)
    if len(posts) <= 1:
        return {"status": "ok", "message": "Nie je dosť nepostnutých príspevkov na premiešanie."}

    v_ids = [p["vault_video_id"] for p in posts]
    random.shuffle(v_ids)

    with db.get_db() as conn:
        for p, vid in zip(posts, v_ids):
            conn.execute("UPDATE planned_posts SET vault_video_id = ? WHERE id = ?", (vid, p["id"]))

    return {"status": "ok", "message": f"Úspešne premiešaných {len(posts)} nepostnutých príspevkov pre účet."}


def get_planner_summary() -> dict:
    """Vráti GoroTools-inšpirovaný súhrn pre Plánovač (pozornosť, chýbajúce klipy, účty)."""
    accounts = db.get_accounts_with_metrics()
    vault_videos = db.get_all_vault_videos()
    available_videos = len(vault_videos)

    attention_accounts = []
    accounts_summary = []
    total_unposted = 0

    for acc in accounts:
        aid = acc["id"]
        unposted = db.get_unposted_posts_by_account(aid)
        total_unposted += len(unposted)

        has_token = bool(acc.get("has_token"))
        fb_enabled = bool(acc.get("fb_enabled", 1) and acc.get("fb_page_id"))
        is_burner = bool(acc.get("is_burner", 0))

        # Kontrola chýbajúcich popiskov
        missing_caption_count = sum(1 for p in unposted if not p.get("caption") or not p["caption"].strip())

        # Kontrola počtu dní obsahu
        unique_days = set()
        for p in unposted:
            st = p.get("scheduled_time")
            if st:
                unique_days.add(st[:10])
        days_left = len(unique_days)

        issues = []
        if not has_token:
            issues.append("Chýba pripojenie k sieti (manuálne postovanie)")
        if days_left == 0:
            issues.append("Žiadne naplánované príspevky")
        elif days_left <= 1:
            issues.append(f"Zostáva obsah len na {days_left} deň")
        if missing_caption_count > 0:
            issues.append(f"{missing_caption_count} bez popisku")

        if issues:
            attention_accounts.append({
                "account_id": aid,
                "username": acc["username"],
                "issues": issues
            })

        accounts_summary.append({
            "id": aid,
            "username": acc["username"],
            "has_token": has_token,
            "fb_page_id": acc.get("fb_page_id"),
            "fb_enabled": fb_enabled,
            "x_handle": acc.get("x_handle"),
            "is_burner": is_burner,
            "burner_vault_ids": acc.get("burner_vault_ids", ""),
            "device_model": acc.get("device_model", "Samsung Galaxy S24"),
            "default_time": acc.get("default_time", "19:15"),
            "default_jitter": acc.get("default_jitter", 10),
            "default_caption": acc.get("default_caption", ""),
            "days_left": days_left,
            "unposted_count": len(unposted),
            "missing_caption_count": missing_caption_count,
            "copies_ready": len(unposted)
        })

    regular_count = sum(1 for a in accounts if not a.get("is_burner"))
    needed_for_7_days = regular_count * 7
    missing_clips = max(0, needed_for_7_days - available_videos)

    return {
        "status": "ok",
        "total_accounts": len(accounts),
        "available_videos": available_videos,
        "missing_clips": missing_clips,
        "needed_for_7_days": needed_for_7_days,
        "attention_count": len(attention_accounts),
        "attention_accounts": attention_accounts,
        "accounts": accounts_summary
    }



def check_and_publish_scheduled_posts(base_public_url: str = "https://garcarzp.online/ig"):
    """
    Periodická kontrola naplánovaných postov.
    Ak nastal čas scheduled_time a status je 'ready' alebo 'scheduled',
    automaticky odošle Reel na Meta Graph API.
    """
    now_dt = datetime.now()
    with db.get_db() as conn:
        rows = conn.execute("""
            SELECT id, scheduled_time, status 
            FROM planned_posts 
            WHERE status IN ('ready', 'scheduled')
        """).fetchall()

    for r in rows:
        try:
            sched_str = r["scheduled_time"]
            if not sched_str:
                continue
            if "T" in sched_str:
                sched_dt = datetime.fromisoformat(sched_str.replace("Z", "+00:00")).replace(tzinfo=None)
            else:
                sched_dt = datetime.strptime(sched_str[:19], "%Y-%m-%d %H:%M:%S")

            if sched_dt <= now_dt:
                logger.info(f"Auto-Planner: Nastal naplánovaný čas pre post #{r['id']} ({sched_str}). Publikujem...")
                publish_planned_post(r["id"], base_public_url=base_public_url)
        except Exception as e:
            logger.error(f"Auto-Planner scheduler chyba pri poste #{r['id']}: {e}")


def start_background_planner_worker(interval_seconds: int = 60, base_public_url: str = "https://garcarzp.online/ig"):
    """Spustí background vlákno, ktoré každú minútu kontroluje a automaticky postuje naplánované posty."""
    import threading
    import time

    def _worker():
        logger.info(f"Auto-Planner background scheduler spustený (interval {interval_seconds}s).")
        while True:
            try:
                check_and_publish_scheduled_posts(base_public_url=base_public_url)
            except Exception as e:
                logger.error(f"Chyba vo workerovi Auto-Planneru: {e}")
            time.sleep(interval_seconds)

    t = threading.Thread(target=_worker, daemon=True, name="AutoPlannerScheduler")
    t.start()
    return t
