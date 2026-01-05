#ifndef LOGIKA_H
#define LOGIKA_H

#include "snake.h"
#include <pthread.h>
#include <stdbool.h>

typedef struct SERVER_DATA{
    HAD *hadi[MAX_HRACOV];
    
    int klientske_sockety[MAX_HRACOV];
    bool sloty_obsadene[MAX_HRACOV];
    pthread_mutex_t mutex_hra;
    volatile bool hra_bezi;
    volatile bool server_sa_vypina;
    POWER_UP mapa_jedla[POCET_JEDLA];
} SERVER_DATA;


typedef struct {
    SERVER_DATA *sd;
    int hrac_index;
} VSTUP_ARGS;

void* herna_slucka(void* data);
void* spracuj_vstupy(void* data);

void generuj_nove_jedlo(SERVER_DATA *sd, int index);

#endif