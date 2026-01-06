# UML DIAGRAMY - SNAKE MULTIPLAYER

## 1. KOMPONENTOVÝ DIAGRAM (Architektúra)

```mermaid
graph TB
    subgraph SERVER
        SM[main.c<br/>Sockety, Signály]
        SL[logika.c<br/>Herná slučka, Vlákna]
    end
    
    subgraph KLIENT
        KM[main.c<br/>Sockety, Vlákna]
        KG[gui.c<br/>ncurses GUI]
    end
    
    subgraph SPOLOCNE[SPOLOČNÉ]
        SC[snake.c<br/>Definície štruktúr a správanie hada]
    end
    
    SM --> SL
    SL --> SC
    SM --> SC
    
    KM --> KG
    KM --> SC
    
    SL -.->|XOR šifrovanie| KM
    KM -.->|klávesy WASD| SL
```

## 2. DIAGRAM TRIED (Štruktúry)

```mermaid
classDiagram
    class BOD {
        +int x
        +int y
    }
    
    class OBJEKT {
        +BOD pozicia
        +char znak
    }
    
    class LL {
        <<Generický Linked List>>
        +void* data
        +LL* next
    }
    
    class HAD {
        +LL* hlava
        +LL* chvost
        +int velkost
        +int aktualny_smer
        +int turbo_counter
    }
    
    class POWER_UP {
        +BOD poloha
        +TYP_BONUSU typ
    }
    
    class HRA_STAV {
        <<Sieťový prenos>>
        +BOD polohy[4][100]
        +int dlzky[4]
        +bool aktivny[4]
        +POWER_UP jedla[5]
        +bool koniec_hry
        +char sprava[128]
    }
    
    class SERVER_DATA {
        +HAD* hadi[4]
        +int klientske_sockety[4]
        +bool sloty_obsadene[4]
        +pthread_mutex_t mutex_hra
        +volatile bool hra_bezi
        +POWER_UP mapa_jedla[5]
    }
    
    HAD "1" *-- "*" LL : hlava/chvost
    LL "1" *-- "1" OBJEKT : data
    OBJEKT *-- BOD
    POWER_UP *-- BOD
    SERVER_DATA *-- HAD
    SERVER_DATA *-- POWER_UP
    HRA_STAV *-- BOD
    HRA_STAV *-- POWER_UP
```

## 3. SEKVENČNÝ DIAGRAM (Herný cyklus)

```mermaid
sequenceDiagram
    participant K1 as Klient 1
    participant K2 as Klient 2
    participant S as Server
    participant HL as Herná slučka
    
    rect rgb(200, 230, 200)
    Note over K1,S: PRIPOJENIE
    K1->>S: connect()
    S->>S: vytvor_hada()
    S-->>K1: slot pridelený
    K2->>S: connect()
    S-->>K2: slot pridelený
    end
    
    rect rgb(200, 200, 230)
    Note over K1,HL: HERNÝ CYKLUS (50ms)
    loop každý tik
        K1->>S: send('w')
        S->>HL: zmen_smer_hada()
        HL->>HL: pohni_hada()
        HL->>HL: kontrola kolízií
        HL->>HL: sifruj_data()
        HL-->>K1: send(HRA_STAV)
        HL-->>K2: send(HRA_STAV)
        K1->>K1: desifruj + vykresli
        K2->>K2: desifruj + vykresli
    end
    end
    
    rect rgb(230, 200, 200)
    Note over K1,S: UKONČENIE (Ctrl+C)
    S->>S: SIGINT handler
    S-->>K1: "SERVER VYPNUTY!"
    S-->>K2: "SERVER VYPNUTY!"
    end
```

## 4. DIAGRAM AKTIVÍT (Kontrola kolízií)

```mermaid
flowchart TD
    A[Získaj pozíciu hlavy] --> B{Kolízia s jedlom?}
    B -->|áno| C[rastie = 1]
    C --> D[reakcie typ - sd, i]
    D --> E[generuj_nove_jedlo]
    B -->|nie| F
    E --> F[pohni_hada]
    
    F --> G[Aktualizuj hlavu]
    G --> H{Kolízia s hranicami?}
    H -->|áno| I[respawn_hada]
    I --> END[Koniec tiku]
    
    H -->|nie| J{Kolízia s hadmi?}
    J -->|áno| K[respawn_hada]
    K --> END
    J -->|nie| L[Pokračuj v hre]
    L --> END
    
    style D fill:#ffcc00
    style B fill:#90EE90
    style H fill:#90EE90
    style J fill:#90EE90
```

## 5. UKAZOVATELE NA FUNKCIE (Power-up systém)

```mermaid
graph LR
    subgraph TYPEDEF
        PUF["PowerUpFunc<br/>void (*)(void*, int)"]
    end
    
    subgraph FUNKCIE
        EK[efekt_klasik<br/>Had +1]
        ET[efekt_turbo<br/>Turbo 3s]
        ED[efekt_double<br/>Had +2]
    end
    
    subgraph POLE
        R["reakcie[]<br/>Pole ukazovateľov"]
    end
    
    PUF --> EK
    PUF --> ET
    PUF --> ED
    
    R -->|"[0]"| EK
    R -->|"[1]"| ET
    R -->|"[2]"| ED
    
    style PUF fill:#ffcc00
    style R fill:#90EE90
```

## 6. ŠIFROVANIE (XOR)

```mermaid
sequenceDiagram
    participant S as Server
    participant N as Sieť
    participant K as Klient
    
    Note over S: HRA_STAV (nešifrované)
    S->>S: sifruj_data()<br/>XOR s 0xAB
    Note over S: Šifrované dáta
    
    S->>N: send()
    Note over N: Nečitateľné<br/>bez kľúča
    
    N->>K: recv()
    K->>K: desifruj_data()<br/>XOR s 0xAB
    Note over K: HRA_STAV (pôvodné)
    K->>K: vykresli_stav()
```

---

## Ako renderovať diagramy

### PlantUML (súbor `UML_diagramy.puml`)
1. Online: https://www.plantuml.com/plantuml/uml
2. VS Code: Rozšírenie "PlantUML" (Ctrl+Shift+P → PlantUML: Preview)

### Mermaid (tento súbor)
1. GitHub automaticky renderuje Mermaid v .md súboroch
2. VS Code: Rozšírenie "Markdown Preview Mermaid Support"
3. Online: https://mermaid.live
