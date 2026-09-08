#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Reels Downloader (yt-dlp) – web integrovaná verzia pre CaPPy Tools.

Používa rovnakú logiku ako samostatný skript stahovanie/reels_downloader.py
(cookies, --age-limit, retries, deno), ale je volateľná priamo zo server.py:
stiahne jeden odkaz do daného priečinka a vráti cestu k novému súboru.

Voliteľné env premenné:
  CAPPY_REELS_COOKIES  -> cesta k cookies.txt (Netscape) pre obmedzený obsah
"""
import os
import re
import shutil
import subprocess

MEDIA_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".mp3",
             ".jpg", ".jpeg", ".png", ".webp"}


def tool(name):
    """Vráti True, ak je nástroj (yt-dlp/ffmpeg) dostupný v PATH."""
    return shutil.which(name) is not None


def check_tools():
    """Vráti zoznam chýbajúcich nástrojov."""
    return [n for n in ("yt-dlp", "ffmpeg") if not tool(n)]


def normalize_link(line):
    line = (line or "").lstrip("\ufeff").strip()
    if not line or not re.match(r"^https?://", line):
        return None
    return line


def build_cmd(link, out_dir):
    cmd = ["yt-dlp",
           "-o", os.path.join(out_dir, "%(uploader)s_%(id)s.%(ext)s"),
           "--no-playlist",
           "--ignore-errors",
           "--newline",
           "--retries", "5",
           "--fragment-retries", "5",
           "--no-part",
           "--age-limit", "100"]

    cookies = os.environ.get("CAPPY_REELS_COOKIES")
    if cookies and os.path.isfile(cookies):
        cmd += ["--cookies", cookies]

    # JS runtime (deno) zlepšuje extrakciu/deciphering na YouTube (age-gated).
    if shutil.which("deno"):
        cmd += ["--js-runtimes", "deno"]

    cmd.append(link)
    return cmd


def download(link, out_dir, log=None):
    """Stiahne jeden odkaz. Vráti cestu k novému mediálnemu súboru alebo None."""
    before = set(os.listdir(out_dir)) if os.path.isdir(out_dir) else set()
    cmd = build_cmd(link, out_dir)
    if log:
        log("  yt-dlp " + link)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        if log:
            log("  ✗ Časový limit (15 min) prekročený.")
        return None
    except Exception as e:
        if log:
            log("  ✗ Spustenie zlyhalo: " + str(e))
        return None

    if r.returncode == 0:
        after = set(os.listdir(out_dir))
        new = sorted(after - before)
        media = [f for f in new if os.path.splitext(f)[1].lower() in MEDIA_EXT]
        pick = media or new
        if pick:
            return os.path.join(out_dir, pick[0])
        if log:
            log("  ⚠ Stiahnuté, ale výstupný súbor sa nenašiel.")
        return None

    tail = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
    last = tail[-1] if tail else "neznáma chyba"
    if log:
        log("  ✗ " + last)
    return None
