# Solar monitor app

Web server (Flask + Gunicorn + nginx) na VPS. **Prístupné pod `/solar`** – napr.
`http://35.209.172.238/solar/`. Zobrazuje solárne dáta z vendor platformy
a dáta z batérie z ESP.

## Endpointy (všetko pod `/solar`)

| Metóda | Cesta | Účel |
|---|---|---|
| GET  | `/solar/` | dashboard |
| POST | `/solar/api/esp/battery` | ESP posiela JSON z batérie (`X-API-Key`) |
| POST | `/solar/api/heartbeat` | prehliadač hlási prítomnosť |
| GET  | `/solar/api/status` | aktuálny stav (batéria + panely) |
| GET  | `/solar/api/history` | história pre grafy |
| GET  | `/solar/api/health` | health check |

## ESP – čo posielať a kam

**URL:** `POST http://35.209.172.238/solar/api/esp/battery`
**Hlavičky:** `Content-Type: application/json`, `X-API-Key: 3bad083106fa164908f918b768a58124`
**Telo (JSON):**
```json
{
  "voltage": 26.797,
  "current": -13.156,
  "power": -352.54,
  "soc": 63,
  "soh": 100,
  "remaining_capacity_ah": 200.371,
  "nominal_capacity_ah": 320,
  "cycle_count": 104,
  "temp_mos": 26.3,
  "temp_1": 24.5,
  "temp_2": 24.2,
  "balance_current": 1.974,
  "balancing_action": 1,
  "charge_mosfet": true,
  "discharge_mosfet": true,
  "errors_bitmask": 0,
  "cells": [3.355, 3.351, 3.355, 3.355, 3.334, 3.354, 3.354, 3.334]
}
```
**Odpoveď:** `{"status":"ok","interval":5}` (aktívny web) alebo `{"interval":60}` (idle).
ESP si môže interval čítať a podľa neho nastaviť vlastné odosielanie.

Povinné polia: `voltage`, `current`, `power`, `soc`.

## Idle / aktívny režim

- Kým je web otvorený, prehliadač posiela `/solar/api/heartbeat` + `/solar/api/status`.
- Ak > 20 s nikto nehlási → **idle**: ESP dostane interval 60 (sám spomalí),
  vendor zber sa zrazí na 300 s.
- Otvorenie webu → späť na 5 s. Prehliadač sám pozastaví heartbeat pri skrytej záložke.

## Vendor API (panely + sieť)

Overené proti reálnym requestom:
- Login: `POST /apis/login/account` – heslo je **MD5**, sign je
  `MD5(HmacSHA256(base64("IOT-Open-AppID=..&IOT-Open-Body-Hash=<sha256(body)>&IOT-Open-Nonce=.."), secret))`
  kde `secret` sa dešifruje AES‑CBC z `app_secret` (kľúč/IV z MD5(app_id)).
- Dáta: `POST /apis/ownerOverView/select/ownerStatistics` a
  `POST /apis/ownerOverView/station/stateAttributeSummary/category/daily?summaryCategoryKey=pvInverterPowerClass`
  s hlavičkou `IOT-Token`.

Konfigurácia v `config.yaml` (vendor: enabled, base_url, app_id, app_secret, email, password).
Heslo sa dá dať cez env `SOLAR_VENDOR_PASSWORD`.

## Nasadenie

```bash
bash /home/patrik/solarapp/deploy/deploy.sh
```

## 🔴 Firewall (GCP) – nevyhnutné pre verejný prístup

VM `vps-free` (zóna `us-central1-a`, sieť `default`, tagy `http-server`,`https-server`)
je zvonku zatvorená na 80/443. Pridaj pravidlo v **GCP Console → VPC network → Firewall**
(alebo zo stroja s oprávnením owner):

```bash
gcloud compute firewall-rules create allow-http-https \
  --network default \
  --direction INGRESS \
  --action allow \
  --rules tcp:80,tcp:443 \
  --source-ranges 0.0.0.0/0 \
  --target-tags http-server,https-server
```

Po vytvorení overiť: `curl http://35.209.172.238/solar/`
