#!/usr/bin/env python3
"""Nacita konfiguracie z config.yaml + tajne hodnoty z prostredia."""
import os
import yaml

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "config.yaml")


def _load_yaml() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def load_config() -> dict:
    cfg = _load_yaml()
    # Tajne hodnoty cez prostredie prepisuju konfiguraciu
    cfg.setdefault("vendor", {})
    cfg.setdefault("esp", {})
    cfg.setdefault("web", {})

    env_password = os.environ.get("SOLAR_VENDOR_PASSWORD")
    if env_password:
        cfg["vendor"]["password"] = env_password

    env_key = os.environ.get("SOLAR_ESP_KEY")
    if env_key:
        cfg["esp"]["api_key"] = env_key

    cfg["_base"] = BASE
    return cfg
