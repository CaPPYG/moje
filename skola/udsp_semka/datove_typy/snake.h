#ifndef SNAKE_H
#define SNAKE_H
#define MAPA_SIRKA 60
#define MAPA_VYSKA 20

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

HAD* vytvor_hada(int start_x, int start_y);
void pohni_hada(HAD *had, int rastie);
void zmaz_hada(HAD *had);
int serializuj_hada(HAD *had, BOD *buffer);

#endif