# SNAKE MULTIPLAYER - PROGRAMÁTORSKÁ DOKUMENTÁCIA

**Predmet:** UDSP - Semestrálna práca  
**Autor:** [Tvoje meno]  
**Dátum:** Január 2026  

---

## 1. ÚVOD

Táto dokumentácia popisuje architektúru, použité technológie a kľúčové časti implementácie distribuovanej viacvláknovej hry Snake pre viacerých hráčov.

### 1.1 Prehľad aplikácie

Aplikácia pozostáva z dvoch častí:
- **Server** - riadi hernú logiku, spravuje pripojených hráčov
- **Klient** - zobrazuje hru a odosiela vstupy od hráča

---

## 2. ARCHITEKTÚRA APLIKÁCIE

### 2.1 Komponentový diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         SERVER                               │
│  ┌──────────────┐    ┌──────────────┐                       │
│  │   main.c     │───▶│  logika.c    │                       │
│  │  (sockety,   │    │ (herná slučka│                       │
│  │   signály)   │    │   vlákna)    │                       │
│  └──────────────┘    └──────────────┘                       │
│         │                   │                                │
│         └───────────────────┼────────────────────────────────┤
│                             ▼                                │
│                    ┌──────────────┐                         │
│                    │   snake.c    │ ◀── SPOLOČNÝ MODUL      │
│                    │ (štruktúry,  │                         │
│                    │  správanie)  │                         │
│                    └──────────────┘                         │
│                             ▲                                │
│         ┌───────────────────┼────────────────────────────────┤
│         │                   │                                │
│  ┌──────────────┐    ┌──────────────┐                       │
│  │   main.c     │───▶│   gui.c      │                       │
│  │  (sockety,   │    │  (ncurses)   │                       │
│  │   vlákna)    │    │              │                       │
│  └──────────────┘    └──────────────┘                       │
│                         KLIENT                               │
└─────────────────────────────────────────────────────────────┘
                             │
                    ┌────────┴────────┐
                    │   TCP Socket    │
                    │   Port 12345    │
                    │  (šifrované)    │
                    └─────────────────┘
```

### 2.2 Štruktúra projektu

```
udsp_semka/
├── Makefile                    # Zostavenie projektu
├── server_app                  # Skompilovaný server
├── klient_app                  # Skompilovaný klient
│
├── datove_typy/
│   ├── snake.h                 # Deklarácie štruktúr a funkcií
│   └── snake.c                 # Implementácia (LL, HAD, šifrovanie)
│
├── server/
│   ├── main.c                  # Vstupný bod servera
│   ├── logika.h                # Deklarácie hernej logiky
│   └── logika.c                # Herná slučka, vlákna, kolízie
│
├── klient/
│   ├── main.c                  # Vstupný bod klienta
│   ├── gui.h                   # Deklarácie GUI
│   └── gui.c                   # ncurses vykresľovanie
│
└── dokumentacia/
    ├── README_UML.md           # UML diagramy (Mermaid)
    └── UML_diagramy.puml       # UML diagramy (PlantUML)
```

---

## 3. DÁTOVÉ ŠTRUKTÚRY

### 3.1 Generický Linked List (SEMESTRÁLKA: 1-3 body)

```c
typedef struct LL {
    void *data;         // Generický ukazovateľ na dáta
    struct LL *next;    // Ukazovateľ na ďalší uzol
} LL;
```

**Použitie:** Reprezentácia tela hada - každý uzol obsahuje OBJEKT s pozíciou.

**Generické funkcie:**
- `ll_najdi_prvok(LL*, TestCallback, void*)` - hľadá prvok podľa callbacku
- `pole_najdi_prvok(void*, int, size_t, TestCallback, void*)` - generická iterácia cez pole

### 3.2 Štruktúra HAD

```c
typedef struct {
    LL *hlava;           // Prvý uzol (hlava hada)
    LL *chvost;          // Posledný uzol
    int velkost;         // Počet článkov
    int aktualny_smer;   // HORE, DOLE, VLAVO, VPRAVO
    int turbo_counter;   // Počítadlo pre turbo efekt
} HAD;
```

### 3.3 Štruktúra pre sieťový prenos

```c
typedef struct {
    BOD polohy[MAX_HRACOV][100];  // Pozície všetkých hadov
    int dlzky[MAX_HRACOV];         // Dĺžky hadov
    bool aktivny[MAX_HRACOV];      // Ktorí hráči sú aktívni
    POWER_UP jedla[POCET_JEDLA];   // Pozície jedla
    bool koniec_hry;               // Flag pre ukončenie
    char sprava[128];              // Textová správa
} HRA_STAV;
```

---

## 4. ARITMETIKA UKAZOVATEĽOV (SEMESTRÁLKA: 1-2 body)

### 4.1 Príklady použitia

**Serializácia hada (snake.c):**
```c
BOD *zapis = buffer;
while (curr != NULL) {
    *zapis = obj->pozicia;
    zapis++;              // Posun ukazovateľa
    curr = curr->next;
}
```

**Kopírovanie jedla (logika.c):**
```c
POWER_UP *src = sd->mapa_jedla;
POWER_UP *dst = stav.jedla;
POWER_UP *koniec = src + POCET_JEDLA;

while (src < koniec) {
    *dst++ = *src++;      // Kopíruj a posuň oba pointre
}
```

**Šifrovanie (snake.c):**
```c
unsigned char *ptr = (unsigned char*)data;
unsigned char *koniec = ptr + velkost;

while (ptr < koniec) {
    *ptr ^= SIFROVACI_KLUC;
    ptr++;
}
```

---

## 5. UKAZOVATELE NA FUNKCIE (SEMESTRÁLKA: 1-2 body)

### 5.1 Power-up systém

```c
typedef void (*PowerUpFunc)(void*, int);

void efekt_klasik(void *data, int hrac);  // Obyčajné jedlo
void efekt_turbo(void *data, int hrac);   // Zrýchlenie
void efekt_double(void *data, int hrac);  // Dvojnásobné body

PowerUpFunc reakcie[] = {efekt_klasik, efekt_turbo, efekt_double};

// Volanie podľa typu jedla:
reakcie[zjedene->typ](sd, i);
```

### 5.2 Callback pattern pre kolízie

```c
typedef bool (*TestCallback)(void* prvok, void* context);

bool test_telo_hada(void* prvok, void* context);
bool test_jedlo(void* prvok, void* context);
bool test_hranica_mapy(void* prvok, void* context);

// Generické volanie:
if (ll_najdi_prvok(zoznam, test_telo_hada, &hlava)) {
    // Kolízia!
}
```

---

## 6. SOCKETY (SEMESTRÁLKA: 1-4 body)

### 6.1 Server

```c
int server_fd = socket(AF_INET, SOCK_STREAM, 0);
bind(server_fd, (struct sockaddr*)&address, sizeof(address));
listen(server_fd, MAX_HRACOV);

while (hra_bezi) {
    int new_sock = accept(server_fd, NULL, NULL);
    // Vytvor vlákno pre nového hráča
}
```

### 6.2 Klient

```c
int sock = socket(AF_INET, SOCK_STREAM, 0);
connect(sock, (struct sockaddr*)&serv_addr, sizeof(serv_addr));

while (1) {
    recv(sock, &stav, sizeof(HRA_STAV), 0);
    desifruj_data(&stav, sizeof(HRA_STAV));
    vykresli_stav(&stav);
}
```

---

## 7. VLÁKNA (SEMESTRÁLKA: 1-4 body)

### 7.1 Serverové vlákna

| Vlákno | Funkcia | Účel |
|--------|---------|------|
| Hlavné | main() | Accept loop - prijíma nových hráčov |
| Herná slučka | herna_slucka() | Aktualizuje stav hry 20x za sekundu |
| Vstup hráča N | spracuj_vstupy() | Prijíma klávesy od konkrétneho hráča |

### 7.2 Synchronizácia

```c
pthread_mutex_t mutex_hra;

pthread_mutex_lock(&sd->mutex_hra);
// Kritická sekcia - prístup k zdieľaným dátam
pthread_mutex_unlock(&sd->mutex_hra);
```

---

## 8. ŠIFROVANÁ KOMUNIKÁCIA (BONUS: 3 body)

### 8.1 XOR šifra

```c
#define SIFROVACI_KLUC 0xAB

void sifruj_data(void *data, size_t velkost) {
    unsigned char *ptr = (unsigned char*)data;
    unsigned char *koniec = ptr + velkost;
    
    while (ptr < koniec) {
        *ptr ^= SIFROVACI_KLUC;
        ptr++;
    }
}
```

**Princíp:** XOR je symetrická operácia - rovnaká funkcia šifruje aj dešifruje.

---

## 9. OBSLUHA SIGNÁLOV (BONUS: 2 body)

```c
void spracuj_signal(int sig) {
    printf("Prijaty SIGINT. Server sa vypina...\n");
    global_sd_ptr->server_sa_vypina = true;
}

// V main():
signal(SIGINT, spracuj_signal);
```

---

## 10. GRAFICKÝ REŽIM (BONUS: 5 bodov)

Použitá knižnica **ncurses** pre terminálové GUI:
- Farebné rozlíšenie hráčov
- Vykresľovanie mapy, hadov, jedla
- Štatistiky a skóre

---

## 11. KONTROLA KOLÍZIÍ

### 11.1 Typy kolízií

1. **Kolízia s jedlom** - `pole_najdi_prvok()` + `test_jedlo()`
2. **Kolízia s hranicami** - `test_hranica_mapy()`
3. **Kolízia s hadmi** - `ll_najdi_prvok()` + `test_telo_hada()`

### 11.2 Algoritmus

```
Pre každého hada:
  1. Skontroluj kolíziu s jedlom
  2. Pohni hada (pridaj hlavu, odstráň chvost)
  3. Skontroluj kolíziu s hranicami → respawn
  4. Skontroluj kolíziu s hadmi → respawn
```

---

## 12. ZOSTAVENIE A SPUSTENIE

```bash
# Kompilácia
make

# Spustenie servera
./server_app

# Spustenie klienta (v novom termináli)
./klient_app

# Vyčistenie
make clean
```

---

## 13. PREHĽAD SPLNENÝCH POŽIADAVIEK

| Požiadavka | Body | Stav | Súbor/Riadok |
|------------|------|------|--------------|
| Generické štruktúry | 1-3 | ✅ | snake.c: LL, ll_najdi_prvok |
| Aritmetika ukazovateľov | 1-2 | ✅ | snake.c, gui.c, logika.c |
| Ukazovatele na funkcie | 1-2 | ✅ | logika.c: PowerUpFunc |
| Sockety | 1-4 | ✅ | server/main.c, klient/main.c |
| Vlákna | 1-4 | ✅ | logika.c, server/main.c |
| Rozčlenenie .h/.c | 1-2 | ✅ | Celý projekt |
| Makefile | 1 | ✅ | Makefile |
| Grafický režim | +5 | ✅ | gui.c (ncurses) |
| Obsluha signálov | +2 | ✅ | server/main.c |
| Šifrovaná komunikácia | +3 | ✅ | snake.c |

---

## 14. PODROBNÝ POPIS ŠTRUKTÚR

### BOD
Základná štruktúra reprezentujúca pozíciu na 2D mape. Obsahuje súradnice X a Y, používa sa na uloženie pozície hada, jedla a pri kontrole kolízií.

### OBJEKT
Rozšírenie štruktúry BOD o vizuálnu reprezentáciu (znak). Každý článok tela hada je OBJEKT - hlava má znak '@', telo má znak 'o'.

### LL (Linked List)
Generický jednosmerný zreťazený zoznam s void* ukazovateľom na dáta. Umožňuje uložiť ľubovoľný dátový typ, v našom prípade OBJEKT. Každý uzol obsahuje dáta a ukazovateľ na nasledujúci uzol.

### HAD
Reprezentuje hada hráča ako linked list článkov. Obsahuje ukazovateľ na hlavu (prvý uzol) a chvost (posledný uzol), aktuálny smer pohybu a počítadlo pre turbo efekt. Veľkosť určuje počet článkov (skóre hráča).

### POWER_UP
Štruktúra pre jedlo/bonus na mape. Obsahuje pozíciu a typ bonusu (KLASIK, TURBO, DOUBLE). Typ určuje, aký efekt sa aplikuje po zjedení.

### HRA_STAV
Štruktúra pre sieťový prenos stavu hry od servera ku klientom. Obsahuje serializované pozície všetkých hadov, ich dĺžky, aktívnosť hráčov, pozície jedla a prípadnú správu (napr. pri ukončení hry).

### SERVER_DATA
Hlavná serverová štruktúra obsahujúca všetky herné dáta. Drží pole hadov, klientske sockety, mutex pre synchronizáciu vlákien a flagy pre riadenie hernej slučky. Zdieľaná medzi všetkými vláknami servera.

---

## 15. PODROBNÝ POPIS KOMPONENTOV (SÚBOROV)

### snake.h
Hlavičkový súbor obsahujúci definície všetkých dátových štruktúr a deklarácie funkcií. Definuje konštanty ako MAPA_WIDTH, MAX_HRACOV a POCET_JEDLA. Includovaný všetkými ostatnými modulmi.

### snake.c
Implementácia operácií s hadom a generických funkcií. Obsahuje vytváranie/mazanie hada, pohyb, serializáciu pre sieťový prenos, generické vyhľadávanie v linked liste a poli, kolízne callbacky a šifrovacie funkcie.

### server/main.c
Vstupný bod servera - inicializuje socket, nastavuje obsluhu signálu SIGINT. V hlavnej slučke prijíma nových klientov (accept), vytvára vlákna pre spracovanie vstupov a pri ukončení uvoľňuje všetky zdroje.

### server/logika.h
Hlavičkový súbor pre hernú logiku. Definuje štruktúru SERVER_DATA a VSTUP_ARGS pre predávanie parametrov vláknam. Deklaruje funkcie hernej slučky a spracovania vstupov.

### server/logika.c
Jadro hernej logiky servera. Obsahuje hernú slučku bežiacu v samostatnom vlákne (20 FPS), spracovanie vstupov od hráčov, kontrolu kolízií, power-up systém s ukazovateľmi na funkcie a šifrované odosielanie stavu klientom.

### klient/main.c
Vstupný bod klienta - pripája sa na server, vytvára vlákno pre odosielanie vstupov (WASD). Hlavné vlákno prijíma šifrovaný stav od servera, dešifruje ho a volá vykresľovacie funkcie.

### klient/gui.h
Hlavičkový súbor pre grafické rozhranie. Deklaruje funkcie pre inicializáciu ncurses, vykresľovanie herného stavu a koncovej obrazovky.

### klient/gui.c
Implementácia grafického rozhrania pomocou knižnice ncurses. Vykresluje mapu, hadov rôznymi farbami, jedlo s rôznymi symbolmi podľa typu a štatistiky hráčov. Používa aritmetiku ukazovateľov pri iterácii cez polia.

### Makefile
Súbor pre automatizované zostavenie projektu. Definuje pravidlá kompilácie pre server a klient, prepojenie s knižnicami pthread a ncurses. Príkaz `make` skompiluje obe aplikácie, `make clean` vymaže binárky.

---

## 16. PODROBNÝ POPIS KĽÚČOVÝCH FUNKCIÍ

### vytvor_hada(x, y)
Alokuje pamäť pre nového hada a vytvorí počiatočnú hlavu na zadanej pozícii. Vracia ukazovateľ na HAD štruktúru.

### pohni_hada(had, rastie)
Pridá novú hlavu v smere pohybu a ak had nerastie, odstráni chvost. Implementuje základný pohyb hada ako operácie na linked liste.

### serializuj_hada(had, buffer)
Konvertuje linked list hada na pole BOD pre sieťový prenos. Používa aritmetiku ukazovateľov na zápis do bufferu.

### ll_najdi_prvok(zoznam, callback, context)
Generická funkcia iterujúca cez linked list. Volá callback pre každý prvok a vracia prvý, kde callback vráti true. Použitie: detekcia kolízií s telom hada.

### pole_najdi_prvok(pole, pocet, velkost, callback, context)
Generická funkcia iterujúca cez pole ľubovoľného typu. Používa byte-level aritmetiku ukazovateľov pre prístup k prvkom. Použitie: detekcia kolízií s jedlom.

### sifruj_data(data, velkost) / desifruj_data(data, velkost)
XOR šifrovanie/dešifrovanie dát pomocou tajného kľúča. Symetrická operácia - rovnaká funkcia pre oba smery. Používa aritmetiku ukazovateľov na iteráciu cez byty.

### herna_slucka(data)
Hlavné vlákno hernej logiky bežiace 20x za sekundu. Spracováva pohyb hadov, kontroluje kolízie, generuje jedlo, šifruje a odosiela stav všetkým klientom.

### spracuj_vstupy(data)
Vlákno pre každého hráča - prijíma klávesy cez socket a mení smer hada. Pri stlačení Q alebo odpojení upratuje zdroje a aktualizuje stav servera.

### vykresli_stav(stav)
Vykreslí aktuálny stav hry pomocou ncurses. Používa farby pre rozlíšenie hráčov, iteruje cez jedlo a hadov pomocou aritmetiky ukazovateľov.

---

## 17. CALLBACKY PRE KOLÍZIE

### test_telo_hada(prvok, context)
Callback testujúci kolíziu bodu s článkom tela hada. Porovnáva pozíciu OBJEKT-u s testovaným BOD-om.

### test_jedlo(prvok, context)
Callback testujúci kolíziu bodu s jedlom. Porovnáva pozíciu POWER_UP s testovaným BOD-om.

### test_hranica_mapy(prvok, context)
Callback testujúci či bod je mimo hraníc mapy. Context obsahuje šírku a výšku mapy.

---

## 18. POWER-UP FUNKCIE

### efekt_klasik(data, hrac)
Obyčajné jedlo - had rastie o 1 článok. Základný efekt bez špeciálnych vlastností.

### efekt_turbo(data, hrac)
Turbo boost - nastaví turbo_counter na 30 tikov (3 sekundy). Počas turba sa had pohybuje 2x rýchlejšie.

### efekt_double(data, hrac)
Double body - had okamžite rastie o 2 články. Rýchlejší nárast skóre.

---

*Koniec programátorskej dokumentácie*
