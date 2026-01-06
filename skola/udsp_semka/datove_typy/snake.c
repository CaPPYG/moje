/*
 * =============================================================================
 * SNAKE.C - Implementácia generických štruktúr a operácií s hadom
 * =============================================================================
 * 
 * SEMESTRÁLKA - SPLNENÉ POŽIADAVKY V TOMTO SÚBORE:
 * [x] GENERICKÉ ŠTRUKTÚRY (1-3 body): 
 *     - LL (linked list s void*) - riadky 8-14, 178-189
 *     - pole_najdi_prvok() - generická iterácia cez pole - riadky 200-211
 *     - ll_najdi_prvok() - generická iterácia cez LL - riadky 178-189
 * [x] ARITMETIKA UKAZOVATEĽOV (1-2 body):
 *     - serializuj_hada(): *zapis = ...; zapis++; - riadky 89-105
 *     - pole_najdi_prvok(): ptr + (i * velkost_prvku) - riadok 206
 * [x] UKAZOVATELE NA FUNKCIE (1-2 body):
 *     - TestCallback pattern v ll_najdi_prvok a pole_najdi_prvok
 *     - Callbacky: test_telo_hada, test_jedlo, test_hranica_mapy
 * 
 * =============================================================================
 */

#include <stdlib.h>
#include <stdbool.h>
#include "snake.h"

// Vytvorí nový uzol linked listu s ľubovoľným datovým typom
LL* vytvor_uzol(void *data) { 
    
    LL *novy_uzol = malloc(sizeof(LL));
    if (!novy_uzol) return NULL;
    novy_uzol->data = data; 
    novy_uzol->next = NULL;
    
    return novy_uzol;
}

// Inicializuje nového hada s hlavou na danej pozícii
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

// Posunie hada dopredu - pridá hlavu, odstráni chvost pokiaľ rastie==0
void pohni_hada(HAD *had, int rastie) {
    if (!had || !had->hlava) return;   
    
    OBJEKT *stara_hlava_obj = (OBJEKT*)had->hlava->data;
    BOD nova_poz = stara_hlava_obj->pozicia;

    switch (had->aktualny_smer) {
        case HORE:  nova_poz.y--; break;
        case DOLE:  nova_poz.y++; break;
        case VLAVO: nova_poz.x--; break;
        case VPRAVO: nova_poz.x++; break;
    }
    stara_hlava_obj->znak = '*';
    
    OBJEKT *novy_obj = malloc(sizeof(OBJEKT));
    novy_obj->pozicia = nova_poz;
    novy_obj->znak = '@';

    LL *nova_hlava = vytvor_uzol(novy_obj);
    nova_hlava->next = had->hlava;
    had->hlava = nova_hlava;

    //Ak had nerastie, musíme odstrániť chvost
    if (!rastie) {
        LL *aktualny = had->hlava;
        while (aktualny->next != had->chvost) {
            aktualny = aktualny->next;
        }
        free(had->chvost->data);
        free(had->chvost);
        
        had->chvost = aktualny;
        had->chvost->next = NULL;
    } else {
        had->velkost++;
    }
}

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

// Konvertuje LL hada na pole BOD pre sieťový prenos
int serializuj_hada(HAD *had, BOD *buffer) {
    int pocet = 0;
    LL *curr = had->hlava;
    
    // Smerník na zápis
    BOD *zapis = buffer; 

    while (curr != NULL && pocet < 100) {
        OBJEKT *obj = (OBJEKT*)curr->data;
        
        *zapis = obj->pozicia; 
        zapis++;               
        
        curr = curr->next;
        pocet++;
    }
    return pocet;
}


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

// Iteruje LL a vracia prvý prvok kde test_func vráti true
void* ll_najdi_prvok(LL* zoznam, TestCallback test_func, void* context) {
    if (!zoznam || !test_func) return NULL;
    
    LL *curr = zoznam;
    while (curr != NULL) {
        if (test_func(curr->data, context)) {
            return curr->data; 
        }
        curr = curr->next;
    }
    return NULL;
}

bool test_telo_hada(void* prvok, void* context) {
    OBJEKT *obj = (OBJEKT*)prvok;
    BOD *bod = (BOD*)context;
    
    return (obj->pozicia.x == bod->x && obj->pozicia.y == bod->y);
}

void* pole_najdi_prvok(void* pole, int pocet, size_t velkost_prvku, TestCallback test_func, void* context) {
    if (!pole || !test_func) return NULL;
    
    char *ptr = (char*)pole; 
    for (int i = 0; i < pocet; i++) {
        void *prvok = ptr + (i * velkost_prvku);
        if (test_func(prvok, context)) {
            return prvok;
        }
    }
    return NULL;
}


bool test_jedlo(void* prvok, void* context) {
    POWER_UP *jedlo = (POWER_UP*)prvok;
    BOD *bod = (BOD*)context;
    
    return (jedlo->poloha.x == bod->x && jedlo->poloha.y == bod->y);
}


bool test_hranica_mapy(void* prvok, void* context) {
    BOD *bod = (BOD*)prvok;
    int *hranice = (int*)context;
    
    return (bod->x <= 0 || bod->x >= hranice[0] - 1 || 
            bod->y <= 0 || bod->y >= hranice[1] - 1);
}

// sifrovanie xor 
void sifruj_data(void *data, size_t velkost) {
    unsigned char *ptr = (unsigned char*)data;     
    unsigned char *koniec = ptr + velkost;         
    while (ptr < koniec) {
        *ptr ^= SIFROVACI_KLUC;
        ptr++;                   
    }
}
void desifruj_data(void *data, size_t velkost) {
    sifruj_data(data, velkost);
}