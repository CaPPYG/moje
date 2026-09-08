# PasteBin

Zabezpečený pastebin pre dočasné zdieľanie textu, kódu a obrázkov.

- **Port**: `5060`
- **URL**: `https://garcarzp.online/paste`
- **Krátke linky**: `https://garcarzp.online/p/{id}`

## Funkcie
- Zdieľanie textu s automatickým syntax highlightingom
- Podpora pre obrázky (PNG, JPG, WEBP, GIF, max. 10 MB) s drag & drop a Ctrl+V
- Expirácia (TTL: 10m, 1h, 1d, 7d, nikdy) s automatickým čistením
- 🔥 Burn-after-reading: automatické a okamžité zmazanie po 1. prečítaní
- 🔒 Ochrana heslom (zahashované cez bcrypt / scrypt)
- REST API pre vytváranie aj čítanie vrátane surového formátu (`/raw`)

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
