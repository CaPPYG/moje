#!/usr/bin/env python3
"""
PasteBin – Background cleaner pre expirované záznamy a súbory.
"""
import time
import threading
import db


def _run_loop(interval=60):
    while True:
        try:
            db.cleanup_expired()
        except Exception as e:
            print(f"Chyba pri čistení expirovaných pastes: {e}")
        time.sleep(interval)


def start_cleaner(interval=60):
    t = threading.Thread(target=_run_loop, args=(interval,), daemon=True)
    t.start()
    return t
