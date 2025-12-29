#include <stdlib.h>
#include "snake.h"

HAD* vytvor_hada(int start_x, int start_y) {
    HAD *had = malloc(sizeof(HAD));
    had->dlzka = 2; // Nastavíme dĺžku na 2
    had->aktualny_smer = VPRAVO;

    // 1. Vytvorenie hlavy
    SnakeNode *hlava = malloc(sizeof(SnakeNode));
    hlava->pozicia.x = start_x;
    hlava->pozicia.y = start_y;
    hlava->prev = NULL;

    // 2. Vytvorenie druhého článku (telo)
    // Keďže had mieri doprava, telo bude na x - 1
    SnakeNode *telo = malloc(sizeof(SnakeNode));
    telo->pozicia.x = start_x - 1;
    telo->pozicia.y = start_y;
    
    // 3. Prepojenie (Obojsmerne viazaný zoznam)
    hlava->next = telo;
    telo->prev = hlava;
    telo->next = NULL;

    had->hlava = hlava;
    had->chvost = telo;
    
    return had;
}

void pohni_hada(HAD *had, int rastie) {
    // 1. Vytvoríme novú hlavu na základe smeru
    SnakeNode *nova_hlava = malloc(sizeof(SnakeNode));
    nova_hlava->pozicia = had->hlava->pozicia;

    if (had->aktualny_smer == HORE) nova_hlava->pozicia.y--;
    else if (had->aktualny_smer == DOLE) nova_hlava->pozicia.y++;
    else if (had->aktualny_smer == VLAVO) nova_hlava->pozicia.x--;
    else if (had->aktualny_smer == VPRAVO) nova_hlava->pozicia.x++;

    // Prepojenie novej hlavy so starou
    nova_hlava->next = had->hlava;
    nova_hlava->prev = NULL;
    had->hlava->prev = nova_hlava;
    had->hlava = nova_hlava;

    if (!rastie) {
        // Ak had nerastie, musíme odstrániť chvost (posun vpred)
        SnakeNode *stary_chvost = had->chvost;
        had->chvost = stary_chvost->prev;
        had->chvost->next = NULL;
        free(stary_chvost); // Dôležité pre Valgrind!
    } else {
        had->dlzka++;
    }
}

void zmaz_hada(HAD *had) {
    SnakeNode *aktualny = had->hlava;
    while (aktualny != NULL) {
        SnakeNode *dalsi = aktualny->next;
        free(aktualny);
        aktualny = dalsi;
    }
    free(had);
}
int serializuj_hada(HAD *had, BOD *buffer) {
    int i = 0;
    SnakeNode *aktualny = had->hlava;
    while (aktualny != NULL) {
        *(buffer + i) = aktualny->pozicia;
        aktualny = aktualny->next;
        i++;
    }
    return i;
}