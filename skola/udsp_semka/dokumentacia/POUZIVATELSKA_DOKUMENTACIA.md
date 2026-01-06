# SNAKE MULTIPLAYER - POUŽÍVATEĽSKÁ DOKUMENTÁCIA

**Predmet:** UDSP - Semestrálna práca  
**Autor:** [Tvoje meno]  
**Dátum:** Január 2026  

---

## 1. POPIS APLIKÁCIE

Snake Multiplayer je sieťová hra pre 1-4 hráčov, kde každý hráč ovláda svojho hada. Cieľom je zbierať jedlo, rásť a vyhýbať sa kolíziám so stenami, vlastným telom a inými hráčmi.

### 1.1 Vlastnosti hry

- **Multiplayer** - až 4 hráči súčasne
- **Sieťová hra** - server-klient architektúra
- **Power-upy** - rôzne typy jedla s efektmi
- **Farebné rozlíšenie** - každý hráč má inú farbu
- **Šifrovaná komunikácia** - bezpečný prenos dát

---

## 2. SYSTÉMOVÉ POŽIADAVKY

### 2.1 Operačný systém
- Linux (testované na Ubuntu/WSL)

### 2.2 Závislosti
- GCC kompilátor
- pthread knižnica
- ncurses knižnica

### 2.3 Inštalácia závislostí (Ubuntu/Debian)

```bash
sudo apt update
sudo apt install build-essential libncurses5-dev
```

---

## 3. INŠTALÁCIA A ZOSTAVENIE

### 3.1 Stiahnutie projektu

```bash
cd /cesta/k/projektu/udsp_semka
```

### 3.2 Kompilácia

```bash
make
```

Po úspešnej kompilácii sa vytvoria dva súbory:
- `server_app` - serverová aplikácia
- `klient_app` - klientská aplikácia

### 3.3 Vyčistenie projektu

```bash
make clean
```

---

## 4. SPUSTENIE HRY

### 4.1 Spustenie servera

Otvor terminál a spusti:

```bash
./server_app
```

Server sa spustí na porte **12345** a bude čakať na pripojenie hráčov.

**Výstup servera:**
```
==========================================
   SNAKE MULTIPLAYER SERVER STARTING...
   Port: 12345 | Max hracov: 4
==========================================
[GAME] Herny engine nastartovany.
```

### 4.2 Spustenie klienta

Otvor **nový terminál** a spusti:

```bash
./klient_app
```

Klient sa automaticky pripojí na server (localhost:12345).

### 4.3 Viacerí hráči

Pre každého ďalšieho hráča otvor nový terminál a spusti `./klient_app`.

**Tip:** Pre hru cez sieť zmeň IP adresu v `klient/main.c`:
```c
inet_pton(AF_INET, "192.168.1.100", &serv_addr.sin_addr);
```

---

## 5. OVLÁDANIE

### 5.1 Pohyb hada

| Kláves | Smer |
|--------|------|
| **W** | Hore ↑ |
| **A** | Vľavo ← |
| **S** | Dole ↓ |
| **D** | Vpravo → |

### 5.2 Ukončenie hry

| Kláves | Akcia |
|--------|-------|
| **Q** | Opustiť hru (klient) |
| **Ctrl+C** | Vypnúť server |

---

## 6. HERNÉ PRVKY

### 6.1 Had

```
Hlava: @
Telo:  o o o o
```

Každý hráč má inú farbu:
- **Hráč 1:** Červená
- **Hráč 2:** Fialová
- **Hráč 3:** Azúrová
- **Hráč 4:** Biela

### 6.2 Typy jedla

| Symbol | Názov | Efekt |
|--------|-------|-------|
| ***** | Klasické | Had rastie o 1 |
| **T** | Turbo | Zrýchlenie na 3 sekundy |
| **2** | Double | Had rastie o 2 |

### 6.3 Mapa

```
------------------------------------------------------------
|                                                          |
|   @ooo                    *                              |
|                                     T                    |
|                    2                                     |
|                                                          |
------------------------------------------------------------
```

- Modré čiary `|` a `-` sú steny
- Zelené symboly sú jedlo

---

## 7. PRAVIDLÁ HRY

### 7.1 Cieľ
Zbieraj jedlo a dosiahni čo najväčšiu dĺžku hada.

### 7.2 Respawn
Had sa "respawnuje" (objaví na novom mieste) ak:
- Narazí do steny
- Narazí do vlastného tela
- Narazí do iného hráča

### 7.3 Koniec hry
- Hráč môže kedykoľvek opustiť hru (kláves Q)
- Ak odídu všetci hráči, server sa vypne
- Ak sa vypne server (Ctrl+C), všetci hráči sú informovaní

### 7.4 Skóre
Skóre = dĺžka hada. Zobrazuje sa:
- Počas hry v spodnej časti obrazovky
- Na konci hry pred ukončením

---

## 8. OBRAZOVKY HRY

### 8.1 Počas hry

```
------------------------------------------------------------
|                                                          |
|   @ooooo                  *                              |
|                                     T                    |
|                          @oo                             |
|                    2                                     |
|                                                          |
------------------------------------------------------------

--- AKTUALNI HRACI ---
Hrac 1 | Body (dlzka): 6
Hrac 2 | Body (dlzka): 3

Ovladanie: WASD | Koniec: Q
```

### 8.2 Koniec hry

```
******************************
*                            *
* SERVER VYPNUTY! Body: 15   *
*                            *
******************************
```

---

## 9. RIEŠENIE PROBLÉMOV

### 9.1 "Pripojenie zlyhalo!"

**Príčina:** Server nebeží alebo beží na inej adrese.

**Riešenie:**
1. Skontroluj, či server beží (`./server_app`)
2. Skontroluj IP adresu v klientovi

### 9.2 "Bind zlyhal"

**Príčina:** Port 12345 je už obsadený.

**Riešenie:**
```bash
# Nájdi proces na porte
lsof -i :12345

# Ukonči ho
kill -9 <PID>
```

### 9.3 Blikajúca obrazovka

**Príčina:** Terminál nepodporuje ncurses správne.

**Riešenie:**
- Zväčši okno terminálu
- Použi iný terminál (napr. gnome-terminal, xterm)

### 9.4 Nesprávne zobrazenie znakov

**Riešenie:**
```bash
export LANG=en_US.UTF-8
./klient_app
```

---

## 10. TECHNICKÉ INFORMÁCIE

| Parameter | Hodnota |
|-----------|---------|
| Port | 12345 |
| Max hráčov | 4 |
| Rozmer mapy | 120 x 30 |
| FPS | 20 |
| Počet jedla | 5 |

---

## 11. KONTAKT A PODPORA

**Autor:** [Tvoje meno]  
**Email:** [Tvoj email]  
**Predmet:** UDSP - Semestrálna práca  

---

*Koniec používateľskej dokumentácie*
