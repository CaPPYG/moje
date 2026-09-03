#!/usr/bin/env python3
"""Klient na vendor IoT platformu (panely + siet).

Autentifikacia: open-API sign (AppID + Nonce + BodyHash) na login,
potom IOT-Token na dalsie volania.
"""
import base64
import hashlib
import hmac
import json
import logging
import time

import requests
from Crypto.Cipher import AES

log = logging.getLogger("collector")


def _md5hex(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


class VendorCollector:
    def __init__(self, cfg: dict):
        v = cfg.get("vendor", {})
        self.enabled = bool(v.get("enabled", False))
        self.base_url = (v.get("base_url") or "").rstrip("/")
        self.app_id = v.get("app_id", "")
        self.app_secret_enc = v.get("app_secret", "")
        self.email = v.get("email", "")
        self.password = v.get("password", "")
        self.timeout = int(v.get("timeout", 15))
        self._s = requests.Session()
        self._token = None
        self._token_time = 0.0
        self._secret = None

    def _decrypt_secret(self) -> str:
        if self._secret is not None:
            return self._secret
        h = _md5hex(self.app_id.encode())
        raw = AES.new(h[:16].encode(), AES.MODE_CBC, h[16:].encode()).decrypt(
            base64.b64decode(self.app_secret_enc)
        )
        self._secret = raw.replace(b"\x00", b"").decode("utf-8", "ignore").strip()
        return self._secret

    def _open_headers(self, body: str) -> dict:
        """Vypocita IOT-Open-Sign pre request s tielom body."""
        secret = self._decrypt_secret()
        nonce = _md5hex(str(time.time()).encode())
        body_hash = hashlib.sha256(body.encode()).hexdigest()
        params = {
            "IOT-Open-AppID": self.app_id,
            "IOT-Open-Body-Hash": body_hash,
            "IOT-Open-Nonce": nonce,
        }
        query = "&".join(f"{k}={params[k]}" for k in sorted(params))
        b64 = base64.b64encode(query.encode()).decode()
        sign = _md5hex(hmac.new(secret.encode(), b64.encode(), hashlib.sha256).digest())
        return {
            "Content-Type": "application/json; charset=utf-8",
            "IOT-Open-AppID": self.app_id,
            "IOT-Open-Nonce": nonce,
            "IOT-Open-Sign": sign,
            "IOT-Open-Body-Hash": body_hash,
            "IOT-Time-Zone": "Europe/Bratislava",
            "IOT-Token": "null",
            "Origin": self.base_url,
            "User-Agent": "Mozilla/5.0",
        }

    def _headers(self) -> dict:
        h = {
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json",
            "IOT-Time-Zone": "Europe/Bratislava",
            "User-Agent": "Mozilla/5.0",
        }
        if self._token:
            h["IOT-Token"] = self._token
        return h

    def login(self) -> bool:
        if not self.enabled or not self.password:
            return False
        body = json.dumps(
            {"account": self.email, "password": _md5hex(self.password.encode())},
            separators=(",", ":"),
            ensure_ascii=False,
        )
        try:
            url = f"{self.base_url}/login/account"
            r = self._s.post(url, data=body.encode(), headers=self._open_headers(body), timeout=self.timeout)
            r.raise_for_status()
            data = r.json()
            tok = (data.get("data") or {}).get("accessToken")
            if tok:
                self._token = tok
                self._token_time = time.time()
                log.info("Vendor login OK")
                return True
            log.warning("Vendor login: nenasiel accessToken: %s", str(data)[:200])
            return False
        except Exception as e:  # noqa: BLE001
            log.error("Vendor login zlyhal: %s", e)
            return False

    def _ensure_token(self) -> bool:
        if self._token and (time.time() - self._token_time) < 6000:
            return True
        return self.login()

    def _post(self, path: str, body: dict):
        if not self._ensure_token():
            return None
        try:
            r = self._s.post(
                f"{self.base_url}{path}",
                data=json.dumps(body),
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code == 401:
                self._token = None
                if self.login():
                    return self._post(path, body)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            log.error("Vendor volanie %s zlyhalo: %s", path, e)
            return None

    def _get(self, path: str):
        if not self._ensure_token():
            return None
        try:
            r = self._s.get(
                f"{self.base_url}{path}",
                headers=self._headers(),
                timeout=self.timeout,
            )
            if r.status_code == 401:
                self._token = None
                if self.login():
                    return self._get(path)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            log.error("Vendor GET %s zlyhalo: %s", path, e)
            return None

    def fetch(self) -> dict | None:
        if not self.enabled:
            return None

        out: dict = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S")}

        # 1) Primárny súhrn: správny TOTAL (totalProducedQuantity) a celkový výkon stanice.
        #    Ak {} nefunguje, skús so stationId.
        summary = self._post("/dashboard/summary/commons", {})
        if summary is None or summary.get("code") != 0:
            summary = self._post(
                "/dashboard/summary/commons",
                {"stationId": "436462865937825793"},
            )
        if summary and summary.get("code") == 0 and summary.get("data"):
            d = summary["data"]
            out["pv_power_kw"] = d.get("totalPower")
            out["pv_total_power"] = (d.get("totalPower") or 0) * 1000  # W
            out["daily_kwh"] = d.get("dailyProducedQuantity")
            out["total_kwh"] = d.get("totalProducedQuantity")  # správny celok (~2034 kWh)
            out["installed_kw"] = d.get("allInstalledCapacity")
            out["monthly_kwh"] = d.get("monthlyProducedQuantity")
            out["yearly_kwh"] = d.get("yearlyProducedQuantity")
            ss = d.get("stationStateSummary") or []
            if ss and isinstance(ss, list) and ss[0]:
                out["status"] = ss[0].get("stateDict")

        # 2) Detail invertora: živé hodnoty a timestamp.
        device = self._post(
            "/device/list",
            {
                "page": 1,
                "count": 10,
                "dtuId": "344063832024383524",
                "deviceSortKey": None,
            },
        )
        if device and device.get("code") == 0 and isinstance(device.get("data"), dict):
            lst = device["data"].get("list") or []
            if lst and isinstance(lst, list) and lst[0]:
                inv = lst[0]
                out["inverter_producing_power"] = inv.get("producingPower")
                out["inverter_non_nullable_producing_power"] = inv.get("nonNullableProducingPower")
                out["inverter_last_data_at"] = inv.get("lastDataAt")
                out["inverter_last_online_at"] = inv.get("lastOnlineAt")
                out["inverter_online"] = inv.get("isOnline")
                out["inverter_is_alarmed"] = inv.get("isAlarmed")
                out["inverter_state"] = inv.get("stateDict")
                out["inverter_name"] = inv.get("name")
                out["inverter_daily_kwh"] = inv.get("dailyProducedQuantity")
                out["inverter_total_kwh"] = inv.get("totalProducedQuantity")
                out["inverter_rated_kw"] = inv.get("ratedPower")

        # 3) Denná krivka PV pre graf.
        daily = self._post(
            "/ownerOverView/station/stateAttributeSummary/category/daily?summaryCategoryKey=pvInverterPowerClass",
            {"time": time.strftime("%Y-%m-%d")},
        )
        if daily and daily.get("code") == 0 and daily.get("data"):
            props = (daily["data"].get("properties") or [])
            for p in props:
                if p.get("property", {}).get("key") == "generationPower":
                    pts = p.get("timePoints") or []
                    out["daily_series"] = [
                        {"t": tp.get("time"), "value_kw": tp.get("value")} for tp in pts
                    ]
                    break

        # 4) Energetický tok stanice (panely / záťaž domu / batéria / sieť).
        flow = self._get(
            "/station/energy/flow?stationId=436462865937825793&isManualRefresh=false"
        )
        if flow and flow.get("code") == 0 and isinstance(flow.get("data"), dict):
            fd = flow["data"]
            out["flow_time_ms"] = fd.get("time")
            _pick = lambda fl: ((fd.get(fl) or {}).get("value") or {}).get("value")
            out["pv_active_kw"] = _pick("pvPanelFlow")
            out["grid_power_kw"] = _pick("gridFlow")
            out["battery_power_kw"] = _pick("batteryFlow")
            out["load_power_kw"] = _pick("loadFlow")
            for fl in ("pvPanelFlow", "gridFlow", "batteryFlow", "loadFlow"):
                for ev in ((fd.get(fl) or {}).get("extraValues") or []):
                    k = ev.get("key")
                    if k in ("pvVoltage", "gridPower", "gridVoltage", "batteryVoltage", "batteryCurrent", "loadVoltage"):
                        out[f"flow_{k}"] = ev.get("value")

        # Ak sme o ničom nedostali data, vratime None (neaktualizujeme stav).
        if not any(k in out for k in ("pv_total_power", "daily_kwh", "total_kwh")):
            return None
        return out
