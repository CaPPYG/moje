# Drive Drop

Samostatná služba pre jednoduchý file upload a download na Google Drive (priečinok `UPLOADED`).

- **Port**: `5050`
- **URL**: `https://garcarzp.online/drive`
- **Predvolené heslo**: `patrik3924`
- **Priečinok**: `UPLOADED` (v koreni Google Drive)

## Funkcie
- Drag & Drop uploader + podpora Ctrl+V pre prilepenie súborov / screenshotov zo schránky
- Reálny priebeh uploadu s percentami
- Priame sťahovanie z Google Drive (vysoká rýchlosť, 0 MB egress)
- Serverové proxy sťahovanie cez `/download/<id>?proxy=1` (pre školské siete blokujúce Google Drive)
- Zmazanie súborov priamo cez web
- Lokálny fallback v `data/UPLOADED/` ak nie je Google Drive pripojený

## Spustenie lokálne (Windows)
```bat
start.bat
```

## Spustenie na serveri (Linux VM)
```bash
sudo cp drive.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now drive.service
```
