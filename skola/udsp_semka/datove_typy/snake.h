#ifndef SNAKE_H
#define SNAKE_H
#define MAPA_WIDTH 120
#define MAPA_HEIGHT 30
#define MAX_HRACOV 4
#define POCET_JEDLA 5 // Koľko vecí bude naraz na mape

#include <stdbool.h> // Toto opraví chybu 'bool'

typedef enum {
    HORE, DOLE, VLAVO, VPRAVO
} SMER;

typedef struct {
    int x;
    int y;
} BOD;

typedef enum { JEDLO_KLASIK, JEDLO_TURBO, JEDLO_DOUBLE } TYP_BONUSU;

typedef struct {
    BOD poloha;
    TYP_BONUSU typ;
} POWER_UP;

typedef struct SnakeNode {
    BOD pozicia;
    struct SnakeNode *next; 
    struct SnakeNode *prev;
} SnakeNode;

typedef struct {
    SnakeNode *hlava;
    SnakeNode *chvost;
    int dlzka;
    SMER aktualny_smer;
} HAD;

typedef struct {
    BOD polohy[MAX_HRACOV][100]; // Polohy pre každého hada
    int dlzky[MAX_HRACOV];       // Aktuálna dĺžka každého hada
    bool aktivny[MAX_HRACOV];    // Či je hráč v hre
    POWER_UP jedla[POCET_JEDLA];

    // NOVÉ POLIA PRE KONIEC HRY
    bool koniec_hry;
    char sprava[128];
} HRA_STAV;

HAD* vytvor_hada(int start_x, int start_y);
void pohni_hada(HAD *had, int rastie);
void zmaz_hada(HAD *had);
int serializuj_hada(HAD *had, BOD *buffer);
bool skontroluj_koliziu_s_telom(HAD* had, BOD bod, bool preskoc_hlavu);
void resetuj_poziciu_hada(HAD* had, int x, int y);
BOD get_pozicia_hlavy(HAD* had);
void nastav_poziciu_hlavy(HAD* had, int x, int y);
int get_dlzka_hada(HAD* had);
void zmen_smer_hada(HAD* had, char klaves);

#endif