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
import gdrive_vault

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VAULT_DIR = os.path.join(BASE_DIR, "data", "vault")
SPOOFED_DIR = os.path.join(VAULT_DIR, "spoofed")
THUMBS_DIR = os.path.join(VAULT_DIR, "thumbs")

os.makedirs(VAULT_DIR, exist_ok=True)
os.makedirs(SPOOFED_DIR, exist_ok=True)
os.makedirs(THUMBS_DIR, exist_ok=True)


def calculate_slot_time(target_date: date, slot_index: int, region: str = "us", slot_type: str = None) -> tuple[datetime, str]:
    """
    Vypočíta čas pre post s US peak time targetingom a náhodným časovým jitterom (± 7 až 23 minút).
    Všetky profily cielia na americké publikum (EST/PST).
    Vracia: (datetime_v_cet, peak_window_label)
    """
    # Náhodný časový jitter: ± 7 až 23 minút
    jitter_sign = random.choice([-1, 1])
    jitter_mins = jitter_sign * random.randint(7, 23)
    jitter_secs = random.randint(0, 59)

    reg = (region or "us").lower()

    if reg == "us":
        if slot_type == "lunch":
            # US Lunch / Popoludnie (13:15 EST = 19:15 CET)
            base_dt = datetime.combine(target_date, dtime(19, 15, 0))
            slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
            est_hour = (slot_dt.hour - 6) % 24
            window_label = f"🇺🇸 US Lunch/Popoludnie ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET)"
        elif slot_type == "morning":
            # US Ráno (09:15 EST = 15:15 CET)
            base_dt = datetime.combine(target_date, dtime(15, 15, 0))
            slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
            est_hour = (slot_dt.hour - 6) % 24
            window_label = f"🇺🇸 US Ráno ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET)"
        elif slot_type == "evening":
            # US Prime Evening (19:30 EST = 01:30 CET nasledujúci deň)
            base_dt = datetime.combine(target_date, dtime(1, 30, 0)) + timedelta(days=1)
            slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
            est_hour = (slot_dt.hour - 6) % 24
            window_label = f"🇺🇸 US Prime Evening ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET)"
        else:
            # Sekvencia podľa indexu:
            # Slot 0 = US Prime Evening (hlavná zlatá špička 19:30 EST = 01:30 CET)
            # Slot 1 = US Lunch / Popoludnie (13:15 EST = 19:15 CET)
            # Slot 2 = US Ráno (09:15 EST = 15:15 CET)
            if slot_index == 0:
                base_dt = datetime.combine(target_date, dtime(1, 30, 0)) + timedelta(days=1)
                slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
                est_hour = (slot_dt.hour - 6) % 24
                window_label = f"🇺🇸 US Prime Evening ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET)"
            elif slot_index == 1:
                base_dt = datetime.combine(target_date, dtime(19, 15, 0))
                slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
                est_hour = (slot_dt.hour - 6) % 24
                window_label = f"🇺🇸 US Lunch/Popoludnie ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET)"
            else:
                base_dt = datetime.combine(target_date, dtime(15, 15, 0))
                slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
                est_hour = (slot_dt.hour - 6) % 24
                window_label = f"🇺🇸 US Ráno ({est_hour:02d}:{slot_dt.minute:02d} EST / {slot_dt.hour:02d}:{slot_dt.minute:02d} CET)"
    else:
        # Fallback
        if slot_index == 0:
            base_dt = datetime.combine(target_date, dtime(19, 45, 0))
            slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
            window_label = f"🇸🇰 SK Prime Večer ({slot_dt.hour:02d}:{slot_dt.minute:02d} CET)"
        else:
            base_dt = datetime.combine(target_date, dtime(12, 45, 0))
            slot_dt = base_dt + timedelta(minutes=jitter_mins, seconds=jitter_secs)
            window_label = f"🇸🇰 SK Obed ({slot_dt.hour:02d}:{slot_dt.minute:02d} CET)"

    return slot_dt, window_label


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


def publish_planned_post(post_id: int, base_public_url: str = "https://garcarzp.online/ig") -> dict:
    """
    Okamžite vypublikuje naplánovaný post cez Instagram Graph API.
    1. Skontroluje zdravie a token účtu
    2. Pripraví verejnú URL pre spoofnuté MP4 video
    3. Zavolá oficiálny Reel publish container
    4. Aktualizuje stav v databáze (published / failed)
    """
    post = db.get_planned_post_by_id(post_id)
    if not post:
        return {"status": "error", "message": "Plánovaný príspevok nebol nájdený"}

    account_id = post["account_id"]
    token = post.get("ig_access_token")
    ig_user_id = post.get("ig_user_id")
    username = post.get("username", "")

    if not token or not ig_user_id:
        err_msg = "Účet nemá pripojený aktívny Meta Access Token alebo Instagram User ID."
        db.update_planned_post(post_id, status="failed", error_message=err_msg)
        return {"status": "error", "message": err_msg}

    spoofed_file = post.get("spoofed_video_path", "")
    full_local_path = os.path.join(SPOOFED_DIR, spoofed_file)

    if not os.path.isfile(full_local_path):
        err_msg = f"Súbor spoofnutého videa nebol nájdený na serveri: {spoofed_file}"
        db.update_planned_post(post_id, status="failed", error_message=err_msg)
        return {"status": "error", "message": err_msg}

    # Verejná URL adresa videa, ktorú stiahne Instagram Graph API
    public_video_url = f"{base_public_url.rstrip('/')}/media/vault/spoofed/{spoofed_file}"

    # Zostavenie caption
    caption_text = (post.get("caption") or "").strip()
    hashtags = (post.get("hashtags") or "").strip()
    full_caption = caption_text
    if hashtags:
        full_caption = f"{caption_text}\n\n{hashtags}" if caption_text else hashtags

    logger.info(f"Odosielam Reel pre @{username} (UID: {ig_user_id}): {public_video_url}")

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
            logger.error(f"Zlyhanie publikovania Reelu pre @{username}: {err_str}")
            db.update_planned_post(post_id, status="failed", error_message=str(err_str))

            # Trigger kontroly zdravia účtu pri zlyhaní
            import health_monitor
            health_monitor.check_account_health(account_id)

            return {"status": "error", "message": f"Chyba pri publikovaní: {err_str}"}

        # Úspešne publikované!
        media_id = res.get("id") or res.get("container_id")
        now_iso = datetime.now(timezone.utc).isoformat()
        db.update_planned_post(
            post_id,
            status="published",
            published_at=now_iso,
            ig_media_id=str(media_id),
            error_message=None
        )

        # Označenie master média vo Vaulte ako použité konkrétnym účtom
        if post.get("vault_video_id"):
            try:
                db.mark_vault_video_used(post["vault_video_id"], username)
            except Exception as e:
                logger.warning(f"Chyba pri označovaní vault média ako použité: {e}")

        logger.info(f"Reel úspešne publikovaný pre @{username}! Media ID: {media_id}")
        return {
            "status": "ok",
            "message": f"Reel bol úspešne publikovaný na @{username}!",
            "media_id": media_id,
            "published_at": now_iso
        }

    except Exception as e:
        logger.exception(f"Výnimka pri publikovaní Reelu: {e}")
        db.update_planned_post(post_id, status="failed", error_message=str(e))
        return {"status": "error", "message": f"Výnimka pri publikovaní: {str(e)}"}


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
