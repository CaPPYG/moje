#include <stdlib.h>
#include <stdbool.h>
#include "snake.h"

/**
 * Inicializácia nového hada (Objektový prístup)
 * Vytvára hada s hlavou a jedným článkom tela.
 */
HAD* vytvor_hada(int start_x, int start_y) {
    HAD *had = malloc(sizeof(HAD));
    if (!had) return NULL;

    had->dlzka = 2; 
    had->aktualny_smer = VPRAVO;

    // 1. Vytvorenie hlavy
    SnakeNode *hlava = malloc(sizeof(SnakeNode));
    hlava->pozicia.x = start_x;
    hlava->pozicia.y = start_y;
    hlava->prev = NULL;

    // 2. Vytvorenie druhého článku (telo)
    SnakeNode *telo = malloc(sizeof(SnakeNode));
    telo->pozicia.x = start_x - 1; // Telo za hlavou
    telo->pozicia.y = start_y;
    
    // 3. Obojsmerné prepojenie
    hlava->next = telo;
    telo->prev = hlava;
    telo->next = NULL;

    had->hlava = hlava;
    had->chvost = telo;
    
    return had;
}

/**
 * Logika pohybu hada
 * @param rastie - ak je 1, chvost sa neodstráni a had sa predĺži
 */
void pohni_hada(HAD *had, int rastie) {
    if (!had || !had->hlava) return;

    // Vytvorenie novej hlavy na základe aktuálneho smeru
    SnakeNode *nova_hlava = malloc(sizeof(SnakeNode));
    nova_hlava->pozicia = had->hlava->pozicia;

    if (had->aktualny_smer == HORE) nova_hlava->pozicia.y--;
    else if (had->aktualny_smer == DOLE) nova_hlava->pozicia.y++;
    else if (had->aktualny_smer == VLAVO) nova_hlava->pozicia.x--;
    else if (had->aktualny_smer == VPRAVO) nova_hlava->pozicia.x++;

    // Prepojenie novej hlavy so zvyškom zoznamu
    nova_hlava->next = had->hlava;
    nova_hlava->prev = NULL;
    had->hlava->prev = nova_hlava;
    had->hlava = nova_hlava;

    if (!rastie) {
        // Logika posunu: odstránime posledný článok (chvost)
        SnakeNode *stary_chvost = had->chvost;
        if (stary_chvost->prev) {
            had->chvost = stary_chvost->prev;
            had->chvost->next = NULL;
            free(stary_chvost);
        }
    } else {
        had->dlzka++;
    }
}

/**
 * Uvoľnenie pamäte (Deštruktor)
 */
void zmaz_hada(HAD *had) {
    if (!had) return;
    SnakeNode *aktualny = had->hlava;
    while (aktualny != NULL) {
        SnakeNode *dalsi = aktualny->next;
        free(aktualny);
        aktualny = dalsi;
    }
    free(had);
}

/**
 * Serializácia (Aritmetika ukazovateľov)
 * Prevedie spájaný zoznam na pole súradníc pre sieťový prenos.
 */
int serializuj_hada(HAD *had, BOD *buffer) {
    if (!had || !buffer) return 0;
    int i = 0;
    SnakeNode *aktualny = had->hlava;
    while (aktualny != NULL) {
        // Demonštrácia aritmetiky ukazovateľov podľa zadania
        *(buffer + i) = aktualny->pozicia; 
        aktualny = aktualny->next;
        i++;
    }
    return i; // Vráti aktuálnu dĺžku
}

/**
 * Zapuzdrená kontrola kolízií
 * @param preskoc_hlavu - true ak kontrolujeme náraz do seba (hlava vs telo)
 */
bool skontroluj_koliziu_s_telom(HAD* had, BOD bod, bool preskoc_hlavu) {
    if (!had || !had->hlava) return false;
    
    SnakeNode *curr = had->hlava;
    if (preskoc_hlavu && curr) {
        curr = curr->next; // Preskočíme hlavu pri kontrole seba-nárazu
    }

    while (curr) {
        if (curr->pozicia.x == bod.x && curr->pozicia.y == bod.y) {
            return true;
        }
        curr = curr->next;
    }
    return false;
}
void resetuj_poziciu_hada(HAD* had, int x, int y) {
    if (had && had->hlava) {
        had->hlava->pozicia.x = x;
        had->hlava->pozicia.y = y;
    }
}

BOD get_pozicia_hlavy(HAD* had) {
    return had->hlava->pozicia;
}

void nastav_poziciu_hlavy(HAD* had, int x, int y) {
    had->hlava->pozicia.x = x;
    had->hlava->pozicia.y = y;
}

int get_dlzka_hada(HAD* had) {
    if (!had) return 0;
    return had->dlzka;
}
void zmen_smer_hada(HAD* had, char klaves) {
    if (!had) return;
    int stary = had->aktualny_smer;
    if (klaves == 'w' && stary != DOLE)   had->aktualny_smer = HORE;
    else if (klaves == 's' && stary != HORE)   had->aktualny_smer = DOLE;
    else if (klaves == 'a' && stary != VPRAVO) had->aktualny_smer = VLAVO;
    else if (klaves == 'd' && stary != VLAVO)  had->aktualny_smer = VPRAVO;
}