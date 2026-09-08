# GarcArzP HUB (centrálny portál)

Centrálna vstupná stránka (dashboard) pre projekty na doméne `garcarzp.online`.

## Čo HUB robí

| Cesta / služba | Kam smeruje | Beží na |
| --- | --- | --- |
| `garcarzp.online/` | HUB dashboard (statický `index.html`) | `/home/patrik/server` (Nginx) |
| `garcarzp.online/solar` | projekt **Solar** | Flask/Gunicorn `127.0.0.1:8000` |
| `garcarzp.online/cappytools` | projekt **Cappy Tools** | Flask `127.0.0.1:5000` |
| `garcarzp.online/drive` | projekt **Drive Drop** | Flask `127.0.0.1:5050` |
| `garcarzp.online/paste` | projekt **PasteBin** | Flask `127.0.0.1:5060` |
| `garcarzp.online/p/` | krátke linky pre **PasteBin** | Flask `127.0.0.1:5060` |

> Všetky Flask appky bežia s `ProxyFix` + `X-Forwarded-Prefix`, takže generujú správne prefixované URL.

## Štruktúra

```
Server/
├── CaPPyTools/          # Aplikácia Cappy Tools (Flask, port 5000)
├── Drive/               # Aplikácia Drive Drop (Flask, port 5050, uploader/downloader pre Google Drive)
├── Pastebin/            # Aplikácia PasteBin (Flask, port 5060, zabezpečený pastebin & image share)
├── Solar/               # Aplikácia Solar Monitor (Flask/Gunicorn, port 8000)
├── deploy/
│   ├── deploy.sh        # deployment skript pre Google Cloud VM
│   └── nginx-hub.conf   # zjednotená Nginx konfigurácia (/, /solar, /cappytools, /drive, /paste, /p proxy)
├── index.html           # HUB dashboard (čisté HTML + vnorený CSS, dark-mode, responzívne)
└── README.md
```

## Nasadenie na Google Cloud VM

Predpoklady: SSH na VM, užívateľ `patrik` so sudo, na VM je nainštalovaný Nginx
a beží služba Solar (`solar.service`).

1. Nahraj súbory na VM:
   ```bash
   scp -r ./Server patrik@35.209.172.238:/home/patrik/
   ```
   (alebo ručne vytvor `/home/patrik/server` a nahraj `index.html` + `deploy/`)

2. Spusti deployment:
   ```bash
   cd /home/patrik/server
   bash deploy/deploy.sh
   ```

Skript:
- vytvorí `/home/patrik/server` a nakopíruje `index.html`
- nainštaluje `nginx-hub.conf` do `/etc/nginx/sites-available/hub`
- prepne symlink v `sites-enabled` (odstráni staré `default` a `solar`, zapne `hub`)
- otestuje `nginx -t` a reloaduje Nginx

## Príkazy na Google Cloud VM

### Nginx (HUB + routovanie)

```bash
# Otestovať konfiguráciu
sudo nginx -t

# Načítať novú konfiguráciu (bez výpadku)
sudo systemctl reload nginx

# Plný reštart
sudo systemctl restart nginx

# Stav
sudo systemctl status nginx --no-pager -l
```

### Solar služba

```bash
sudo systemctl status solar.service --no-pager -l
sudo systemctl restart solar.service
```

### Cappy Tools

CappyTools beží na `http://127.0.0.1:5000` (systemd `cappy.service`) a je dostupný cez
`garcarzp.online/cappytools`. Vyžaduje, aby bežal na **rovnakom VM** ako Nginx
(inak zmeň `proxy_pass` v `nginx-hub.conf`).

```bash
sudo systemctl status cappy.service --no-pager -l
sudo systemctl restart cappy.service
```

### Drive Drop (File Uploader & Downloader)

Drive Drop beží na `http://127.0.0.1:5050` (systemd `drive.service`) a je dostupný cez
`garcarzp.online/drive`. Umožňuje nahrať akýkoľvek súbor (zo školy, mobilu, PC)
do Google Drive priečinka **`UPLOADED`**, zobraziť zoznam a stiahnuť priamo z Drive.

- Prístupové heslo: `patrik3924`
- Pripojenie Google Drive: automaticky zdieľa token z CappyTools alebo cez vlastné pripojenie
- Lokálny fallback: ak Drive nie je pripojený, súbory sa ukladajú v `Drive/data/UPLOADED/`

```bash
# Inštalácia služby (raz na serveri)
sudo cp /home/patrik/server/Drive/drive.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now drive.service

# Stav a reštart
sudo systemctl status drive.service --no-pager -l
sudo systemctl restart drive.service
```

### PasteBin (Zabezpečený pastebin & image share)

PasteBin beží na `http://127.0.0.1:5060` (systemd `pastebin.service`) a je dostupný cez
`garcarzp.online/paste` a krátke odkazy `garcarzp.online/p/{id}`.

- Text/kód so syntax highlightingom + obrázky (PNG, JPG, WEBP, GIF do 10 MB)
- Expirácia (TTL) + automatické čistenie
- 🔥 Burn-after-reading (okamžité zmazanie z DB aj disku po 1. prečítaní)
- 🔒 Ochrana heslom (bcrypt hash)
- REST API pre vytváranie aj čítanie (`/raw`)

```bash
# Inštalácia služby (raz na serveri)
sudo cp /home/patrik/server/Pastebin/pastebin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pastebin.service

# Stav a reštart
sudo systemctl status pastebin.service --no-pager -l
sudo systemctl restart pastebin.service
```

### Reels Downloader (v CappyTools)

Nový tab **Reels** v CappyTools stiahne odkazy (Instagram Reels / YouTube Shorts) cez
`yt-dlp` a nahrá ich do Google Drive → priečinok **„AI RAK“** v koreni Drive.

- Vyžaduje na serveri `yt-dlp` a `ffmpeg`: `pip install -U yt-dlp`
- Google Drive musí byť pripojený (Admin → Google Drive v CappyTools)
- Voliteľne `CAPPY_REELS_COOKIES` (cesta k `cookies.txt`) pre vekovo/targetovane obmedzený obsah

## Testovanie

```bash
curl -I https://garcarzp.online/
curl -I https://garcarzp.online/solar/
curl -I http://127.0.0.1:8000/api/health
```

## Rozšírenie o ďalšie služby

1. Do `index.html` pridaj novú kartu do `.dashboard-grid`.
2. V `nginx-hub.conf` pridaj nový `location /nova-sluzba/ { proxy_pass http://127.0.0.1:PORT/; ... }`.
   (Ak služba nemá prefix podporu, pridaj jej `ProxyFix(x_prefix=1)` + `X-Forwarded-Prefix`,
   alebo ju nechaj na vlastnej doméne.)
3. `sudo nginx -t && sudo systemctl reload nginx`.

## Dôležité poznámky

- Konfigurácia Nginx je teraz **zjednotená** v `nginx-hub.conf`. Stará `Solar/solarapp/deploy/nginx-solar.conf`
  je nahradená (routovanie `/solar` je zachované bezo zmeny logiky).
- Ak spustíš starý `Solar/solarapp/deploy/deploy.sh`, jeho Nginx krok znovu zapne `solar` konfig
  a prepíše zjednotené nastavenie. Odporúča sa používať HUB `deploy.sh` ako jediný zdroj pravdy pre Nginx
  (Solar deploy skript potom spúšťaj len pre časť Python/systemd, nie Nginx).
- ESP endpoint `/solar/api/esp/battery` zostáva dostupný cez HTTP (ESP nevie TLS a nenasleduje redirect).
- CappyTools vyžaduje na serveri `yt-dlp` a `ffmpeg` pre Reels downloader
  (`pip install -U yt-dlp`). Stiahnuté reels sa nahrávajú do priečinka **„AI RAK“** v koreni Google Drive.
- Ak CappyTools beží na inom stroji ako Nginx, zmeň `proxy_pass http://127.0.0.1:5000/`
  v `nginx-hub.conf` na adresu toho stroja.
