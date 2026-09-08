# CaPPy Tools WEB – návod

## Spustenie
- `start_web.bat` alebo `python server.py` (Python 3.14)
- Otvor **http://127.0.0.1:5000**
- V LAN (mobil): `http://192.168.1.47:5000` (zisti si IP cez `ipconfig`)

## Admin účet
- Email: `patrikgarcarz@gmail.com` / heslo: `cappy3924`
- Prihlasovacie meno: `admin` / heslo: `admin3924`
- Admin vidí tab **👑 Admin** – zoznam užívateľov, veľkosť dát, mazanie účtov,
  povyšovanie na admina, prehľad rozvrhov a cloaker linkov všetkých užívateľov.
- Bežný užívateľ Admin tab nevidí a admin API je preňho uzavreté (403).

## Google Drive – prepojenie (raz)

Cieľ: po prihlásení každého užívateľa sa na **tvojom** Google Drive vytvorí
`CaPPy/<email>/` so subpriečinkami `Vault`, `Output`, `Planner`.

### 1. Vytvor Google Cloud projekt
1. Choď na https://console.cloud.google.com → prihlás sa s `patrikgarcarz@gmail.com`
2. Vytvor projekt (napr. `cappy-tools`)
3. **APIs & Services → Library** → vyhľadaj **Google Drive API** → **Enable**

### 2. OAuth consent screen
1. **APIs & Services → OAuth consent screen**
2. User type: **External** → Create
3. Vyplň app name (napr. `CaPPy Tools`), email → Save
4. **Audience** → pridaj do **Test users** svoj gmail `patrikgarcarz@gmail.com`
   (a prípadne ďalších, ktorí sa majú vedieť prihlásiť cez Google)
5. Publish app (ak chceš, aby fungovalo pre všetkých bez test userov)

### 3. Vytvor OAuth Client ID
1. **APIs & Services → Credentials → + Create credentials → OAuth client ID**
2. Application type: **Desktop app** → Create
3. Klikni na vytvorený klient → **Download JSON**

### 4. Nahraj do appky
- Stiahnutý súbor premenuj na **`credentials.json`**
- Ulož ho do priečinka `CaPPyTools/data/`
  → `C:\Users\patri\Desktop\moje\CaPPyTools\data\credentials.json`

### 5. Pripoj v appke
1. Prihlás sa ako admin → tab **👑 Admin → Google Drive**
2. Klikni **🔗 Pripojiť Google Drive** → otvorí sa Google prihlásenie
3. Povolíš prístup → vráti ťa to do appky a token sa uloží
   do `data/drive_token.json` (tam sa ukladajú len prístupové práva, nie heslo)
4. Klikni **🔄 Vytvoriť priečinky pre všetkých** (alebo sa vytvoria
   automaticky pri každej novej registrácii)

## Poznámky
- `data/` je v `.gitignore` – token, credentials ani dáta užívateľov
  sa nedostanú na git
- Free Google Drive má 15 GB – všetci užívatelia zdieľajú túto kvótu
- Ak `credentials.json` chýba, užívatelia sa bežne zaregistrujú, len Drive
  priečinky sa nevytvoria (až kým nepripojíš Drive a neklikneš sync)

## Dáta v priečinkoch
```
data/<email>/uploads/          ← originálne uploady
data/<email>/output/           ← spracované (spoofed, frames, audio)
data/<email>/output/planner/   ← vygenerované rozvrhy (per zariadenie/dátum)
data/<email>/schedule.json     ← rozvrh
data/<email>/settings.json     ← nastavenia, cloaker linky
```
