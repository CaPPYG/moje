# 🧠 BrainDump Android — Native Wrapper & 4x2 AppWidget

Natívna Android aplikácia (Kotlin / Android Studio) pre **Voice BrainDump**, ktorá obaľuje webovú aplikáciu do plnohodnotného WebView s podporou mikrofónu pre Web Speech API a pridáva **natívny 4x2 minimalistický widget** na domovskú obrazovku.

---

## 📱 Funkcie aplikácie & Widgetu

### 1. WebView Wrapper (`MainActivity.kt`)
- **Web Speech API & Mikrofón:** Plná podpora pre nahrávanie hlasu cez `WebChromeClient.onPermissionRequest` a dynamické vyžiadanie runtime povolenia `RECORD_AUDIO`.
- **Deep Links & Skratky:**
  - `?action=record` (alebo `braindump://record`): Okamžite po otvorení spustí nahrávanie hlasu.
  - `?action=add` (alebo `braindump://add`): Okamžite po otvorení otvorí modál pre manuálne písanie úlohy (TickTick štýl).
- **Pull-to-refresh:** Možnosť potiahnuť nadol na obnovenie aplikácie (`SwipeRefreshLayout`).
- **Plynulá navigácia:** Hardvérové tlačidlo späť vracia históriu vo WebView.

### 2. Natívny 4x2 AppWidget (`BrainDumpWidgetProvider.kt`)
- **Minimalistický Dark Glassmorphism:** Tmavé polopriehľadné zaoblené pozadie (`#E6151B26`), ktoré dokonale ladí s Android Material You / Dark Mode.
- **Hlavička widgetu:**
  - 🧠 Logo a názov aplikácie
  - 🔢 **Odznak s počtom úloh:** Zobrazuje celkový počet otvorených úloh (napr. `4`)
  - **Tlačidlo `+` (TickTick štýl):** Jedným ťuknutím otvorí aplikáciu s otvoreným oknom na manuálne napísanie úlohy
  - **Tlačidlo `🎤` (Mikrofón):** Jedným ťuknutím otvorí aplikáciu a spustí nahrávanie hlasu
  - **Tlačidlo `🔄` (Obnoviť):** Okamžitý manuálny refresh zoznamu úloh na pozadí
- **Zoznam úloh (`ListView` cez `TaskWidgetService`):**
  - Dynamický rolovateľný zoznam posledných otvorených úloh
  - Farebné bodky podľa kategórií:
    - 🖥️ **Work** (modrá)
    - 🛒 **Nákup** (zelená)
    - 👤 **Osobné** (fialová)
    - 📌 **Ostatné** (oranžová)
  - Kliknutie na úlohu otvorí aplikáciu

### 3. Background Sync (`WorkManager`)
- `WidgetUpdateWorker` každých 15–30 minút na pozadí kontaktuje:
  `GET https://garcarzp.online/braindump/api/tasks/widget?password=patrik3924`
- Nevybíja batériu (využíva štandardný `PeriodicWorkRequestBuilder` a `Constraints.NetworkType.CONNECTED`).

---

## 🛠️ Návod na Build finálneho APK

### Možnosť A: Cez Android Studio (Najjednoduchšie)

1. **Otvorenie projektu:**
   - Spusti **Android Studio**.
   - Vyber **Open** a zvoľ priečinok:
     `c:\Users\patri\Desktop\moje\Server\BrainDump-Android`
2. **Synchronizácia Gradle:**
   - Počkaj na dokončenie Gradle Sync (stiahnu sa potrebné knižnice).
3. **Zostavenie Debug APK:**
   - V hornom menu klikni na: **Build** → **Build Bundle(s) / APK(s)** → **Build APK(s)**.
   - Po dokončení sa vpravo dole zobrazí hlásenie s odkazom `locate`.
   - Výsledný APK súbor nájdeš v:
     `app/build/outputs/apk/debug/app-debug.apk`
4. **Inštalácia do mobilu:**
   - Pripoj telefón cez USB kábel (alebo pošli súbor cez Drive / Telegram).
   - Nainštaluj súbor `app-debug.apk` na mobile.

---

### Možnosť B: Zostavenie cez príkazový riadok (Gradle CLI)

Otvori terminál v priečinku projektu:
```bash
cd c:\Users\patri\Desktop\moje\Server\BrainDump-Android
```

#### 1. Debug APK:
```bash
# Windows
.\gradlew.bat assembleDebug

# Linux / macOS
./gradlew assembleDebug
```
Výsledné APK:
`app/build/outputs/apk/debug/app-debug.apk`

#### 2. Podpísaný Release APK:
```bash
.\gradlew.bat assembleRelease
```
Výsledné APK:
`app/build/outputs/apk/release/app-release-unsigned.apk`

*(Na podpis vlastným kľúčom použi Android Studio: **Build** → **Generate Signed Bundle / APK**).*

---

## ⚙️ Konfigurácia servera a hesla

Predvolené hodnoty sú predkonfigurované v:
`app/src/main/java/online/garcarzp/braindump/widget/WidgetPreferences.kt`

- **Server URL:** `https://garcarzp.online/braindump/`
- **Widget API:** `https://garcarzp.online/braindump/api/tasks/widget`
- **Master Password:** `patrik3924`

---

## 🧩 Ako pridať widget na plochu mobilu

1. Po nainštalovaní aplikácie dlho podrž prst na voľnom mieste domovskej obrazovky.
2. Zvoľ **Widgety** (Nástroje).
3. Nájdi **BrainDump** a potiahni widget **BrainDump Úlohy (4x2)** na plochu.
4. Widget okamžite načíta tvoje úlohy zo servera!
