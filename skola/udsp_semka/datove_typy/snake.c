#include <stdlib.h>
#include <stdbool.h>
#include "snake.h"

LL* vytvor_uzol(void *data) { 
    LL *novy_uzol = malloc(sizeof(LL));
    if (!novy_uzol) return NULL;
    novy_uzol->data = data; 
    novy_uzol->next = NULL;
    
    return novy_uzol;
}

/**
 * Inicializácia nového hada
 * Vytvára hada s hlavou a jedným článkom tela.
 */
HAD* vytvor_hada(int x, int y) {
    HAD *had = malloc(sizeof(HAD));
    if (!had) return NULL;

    // Najprv musíme vytvoriť dáta (OBJEKT)
    OBJEKT *obj = malloc(sizeof(OBJEKT));
    obj->pozicia = (BOD){x, y};
    obj->znak = '@';

    // Potom ich pošleme do uzla
    had->hlava = vytvor_uzol(obj);
    
    had->chvost = had->hlava;
    had->velkost = 1;
    had->aktualny_smer = 4; // VPRAVO
    had->turbo_counter = 0;

    return had;
}

/**
 * Logika pohybu hada
 * @param rastie - ak je 1, chvost sa neodstráni a had sa predĺži
 */
void pohni_hada(HAD *had, int rastie) {
    if (!had || !had->hlava) return;
    
    // 1. Vypočítaj novú pozíciu hlavy
    OBJEKT *stara_hlava_obj = (OBJEKT*)had->hlava->data;
    BOD nova_poz = stara_hlava_obj->pozicia;

    switch (had->aktualny_smer) {
        case HORE:  nova_poz.y--; break;
        case DOLE:  nova_poz.y++; break;
        case VLAVO: nova_poz.x--; break;
        case VPRAVO: nova_poz.x++; break;
    }

    // 2. Starú hlavu zmeníme na znak tela '*'
    stara_hlava_obj->znak = '*';

    // 3. Vytvoríme novú hlavu '@' a pripojíme ju na začiatok
    OBJEKT *novy_obj = malloc(sizeof(OBJEKT));
    novy_obj->pozicia = nova_poz;
    novy_obj->znak = '@';

    LL *nova_hlava = vytvor_uzol(novy_obj);
    nova_hlava->next = had->hlava;
    had->hlava = nova_hlava;

    // 4. Ak had nerastie, musíme odstrániť chvost
    if (!rastie) {
        LL *aktualny = had->hlava;
        // Nájdeme predposledný uzol
        while (aktualny->next != had->chvost) {
            aktualny = aktualny->next;
        }
        // Uvoľníme dáta chvosta a chvost samotný
        free(had->chvost->data);
        free(had->chvost);
        
        // Predposledný sa stáva chvostom
        had->chvost = aktualny;
        had->chvost->next = NULL;
    } else {
        had->velkost++;
    }
}

/**
 * Uvoľnenie pamäte (Deštruktor)
 */
void zmaz_hada(HAD *had) {
    if (!had) return;
    LL *aktualny = had->hlava;
    while (aktualny != NULL) {
        LL *dalsi = aktualny->next;
        free(aktualny->data); // Najprv uvoľníme OBJEKT
        free(aktualny);       // Potom uzol
        aktualny = dalsi;
    }
    free(had);
}

/**
 * Serializácia (Aritmetika ukazovateľov)
 * Prevedie spájaný zoznam na pole súradníc pre sieťový prenos.
 */
int serializuj_hada(HAD *had, BOD *buffer) {
    int pocet = 0;
    LL *curr = had->hlava;
    
    // Použijeme smerník na zápis do poľa pomocou aritmetiky
    BOD *zapis = buffer; 

    while (curr != NULL && pocet < 100) {
        OBJEKT *obj = (OBJEKT*)curr->data;
        
        *zapis = obj->pozicia; // Zapíšeme na aktuálnu adresu
        zapis++;               // ARITMETIKA UKAZOVATEĽOV: posun na ďalší BOD v poli
        
        curr = curr->next;
        pocet++;
    }
    return pocet;
}

/**
 * Zapuzdrená kontrola kolízií
 * @param preskoc_hlavu - true ak kontrolujeme náraz do seba (hlava vs telo)
 */
bool skontroluj_koliziu_s_telom(HAD* had, BOD bod, bool preskoc_hlavu) {
    if (!had || !had->hlava) return false;

    LL *curr = had->hlava;
    if (preskoc_hlavu) curr = curr->next;

    while (curr != NULL) {
        OBJEKT *obj = (OBJEKT*)curr->data;
        if (obj->pozicia.x == bod.x && obj->pozicia.y == bod.y) {
            return true;
        }
        curr = curr->next;
    }
    return false;
}

BOD get_pozicia_hlavy(HAD *had) {
    if (!had || !had->hlava) return (BOD){0, 0};
    // Pretypovanie: (OBJEKT*)had->hlava->data
    return ((OBJEKT*)had->hlava->data)->pozicia;
}

void nastav_poziciu_hlavy(HAD* had, int x, int y) {
    ((OBJEKT*)had->hlava->data)->pozicia.x = x;
    ((OBJEKT*)had->hlava->data)->pozicia.y = y;
}

int get_dlzka_hada(HAD* had) {
    if (!had) return 0;
    return had->velkost;
}
void zmen_smer_hada(HAD* had, char klaves) {
    if (!had) return;
    int stary = had->aktualny_smer;
    if (klaves == 'w' && stary != DOLE)   had->aktualny_smer = HORE;
    else if (klaves == 's' && stary != HORE)   had->aktualny_smer = DOLE;
    else if (klaves == 'a' && stary != VPRAVO) had->aktualny_smer = VLAVO;
    else if (klaves == 'd' && stary != VLAVO)  had->aktualny_smer = VPRAVO;
}


void resetuj_poziciu_hada(HAD *had, int x, int y) {
    if (!had || !had->hlava) return;

    // 1. Zmažeme VŠETKO za hlavou
    LL *aktualny = had->hlava->next;
    while (aktualny != NULL) {
        LL *na_zmazanie = aktualny;
        aktualny = aktualny->next;
        
        if (na_zmazanie->data) free(na_zmazanie->data); // Uvoľníme OBJEKT
        free(na_zmazanie);                             // Uvoľníme uzol
    }

    // 2. Dôležité: Ukončíme zoznam hneď za hlavou
    had->hlava->next = NULL;
    had->chvost = had->hlava; // Hlava je teraz zároveň aj chvostom
    had->velkost = 1;         // Dĺžka je späť na 1

    // 3. Resetujeme dáta v hlave
    OBJEKT *obj_hlavy = (OBJEKT*)had->hlava->data;
    if (obj_hlavy) {
        obj_hlavy->pozicia.x = x;
        obj_hlavy->pozicia.y = y;
        obj_hlavy->znak = '@';
    }
}

bool skontroluj_koliziu_v_zozname(LL *zoznam, BOD bod) {
    LL *curr = zoznam;
    while (curr != NULL) {
        OBJEKT *obj = (OBJEKT*)curr->data;
        if (obj->pozicia.x == bod.x && obj->pozicia.y == bod.y) {
            return true;
        }
        curr = curr->next;
    }
    return false;
}