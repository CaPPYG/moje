#ifndef SNAKE_H
#define SNAKE_H
#define MAPA_WIDTH 120
#define MAPA_HEIGHT 30
#define MAX_HRACOV 4

#include <stdbool.h> // Toto opraví chybu 'bool'
#include "data_types.h"

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
    BOD jedlo;
} HRA_STAV;

HAD* vytvor_hada(int start_x, int start_y);
void pohni_hada(HAD *had, int rastie);
void zmaz_hada(HAD *had);
int serializuj_hada(HAD *had, BOD *buffer);

#endif