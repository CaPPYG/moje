# PasteBin

Zabezpečený pastebin pre dočasné zdieľanie textu, kódu a obrázkov.

- **Port**: `5060`
- **URL**: `https://garcarzp.online/paste`
- **Krátke linky**: `https://garcarzp.online/p/{id}`

## Funkcie
- 📋 **Rýchly Cross-Device Clipboard**: Okamžité 1-click kopírovanie textu a kódov medzi počítačom a mobilom
- 🔗 **Prehľad všetkých liniek**: História aktívnych záznamov, počítadlo zobrazení a indikátory expirácie
- ⚡ **Živá synchronizácia (Live Sync)**: Automatická obnova schránky na pozadí a pri prepnutí záložky
- 📱 **QR Kódy**: Bleskové zobrazenie QR kódu pre naskenovanie odkazu mobilom
- 🔍 **Okamžité vyhľadávanie a filtre**: Rýchle filtrovanie textov a obrázkov
- Zdieľanie textu s automatickým syntax highlightingom
- Podpora pre obrázky (PNG, JPG, WEBP, GIF, max. 10 MB) s drag & drop a Ctrl+V
- Expirácia (TTL: 10m, 1h, 1d, 7d, nikdy) s automatickým čistením
- 🔥 Burn-after-reading: automatické a okamžité zmazanie po 1. prečítaní
- 🔒 Ochrana heslom (zahashované cez bcrypt / scrypt)
- REST API pre vytváranie, čítanie, výpis (`GET /api/pastes`), mazanie (`DELETE /api/paste/<id>`) a surový formát (`/raw`)

## Spustenie lokálne (Windows)
```bat
start.bat
```

## Spustenie na serveri (Linux VM)
```bash
sudo cp pastebin.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pastebin.service
```
