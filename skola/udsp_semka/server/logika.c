#include "logika.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/socket.h>
#include <errno.h>
#include <time.h>

// --- EFEKTY POWER-UPOV ---
// UKAZOVATELE NA FUNKCIE (ZADANIE: 1-2 body)
// Každý efekt je funkcia s podpisom: void (*)(void *data, int hrac)

void efekt_klasik(void *data, int hrac) {
    (void)data; // Potlačenie warningu
    printf("[LOG] Hrac %d zjedol Jablko.\n", hrac + 1);
}

void efekt_turbo(void *data, int hrac) {
    SERVER_DATA *sd = (SERVER_DATA*)data;
    if (sd->hadi[hrac]) {
        sd->hadi[hrac]->turbo_counter += 30;
        printf("[LOG] Hrac %d ma TURBO na 3 sekundy!\n", hrac + 1);
    }
}

void efekt_double(void *data, int hrac) {
    SERVER_DATA *sd = (SERVER_DATA*)data;
    if (sd->hadi[hrac]) {
        // Pridá 2 časti tela hada
        pohni_hada(sd->hadi[hrac], 2);
        printf("[LOG] Hrac %d ziskal DOUBLE BODY (+2 casti)!\n", hrac + 1);
    }
}

// Pole ukazovateľov na funkcie (používa tvoj LL prístup cez void*)
// UKAZOVATELE NA FUNKCIE - pole funkcií ktoré sa vyvolávajú podľa typu power-upu
typedef void (*PowerUpFunc)(void*, int);
PowerUpFunc reakcie[] = {efekt_klasik, efekt_turbo, efekt_double};

// --- POMOCNÉ FUNKCIE ---

void respawn_hada(HAD *had) {
    if (!had) return;
    int r_x = (rand() % (MAPA_WIDTH - 4)) + 2;
    int r_y = (rand() % (MAPA_HEIGHT - 4)) + 2;
    resetuj_poziciu_hada(had, r_x, r_y);
}

void generuj_nove_jedlo(SERVER_DATA *sd, int index) {
    sd->mapa_jedla[index].poloha.x = (rand() % (MAPA_WIDTH - 2)) + 1;
    sd->mapa_jedla[index].poloha.y = (rand() % (MAPA_HEIGHT - 2)) + 1;
    sd->mapa_jedla[index].typ = rand() % 3;
}

// --- VLÁKNO PRE VSTUPY ---

void* spracuj_vstupy(void* data) {
    VSTUP_ARGS *args = (VSTUP_ARGS*)data;
    SERVER_DATA *sd = args->sd;
    int index = args->hrac_index;
    int sock = sd->klientske_sockety[index];
    char prikaz;

    free(args);
    printf("[INFO] Vlakno pre vstupy hraca %d spustene.\n", index + 1);

    while (sd->hra_bezi && !sd->server_sa_vypina) {
        int r = recv(sock, &prikaz, 1, 0);
        if (r > 0) {
            if (prikaz == 'q') {
                printf("[QUIT] Hrac %d stlacil Q. Hrac sa odpaja...\n", index + 1);
                break;
            }
            pthread_mutex_lock(&sd->mutex_hra);
            if (sd->hadi[index]) {
                zmen_smer_hada(sd->hadi[index], prikaz);
            }
            pthread_mutex_unlock(&sd->mutex_hra);
        } else if (r <= 0) {
            // Disconnect - klient sa odpojil
            break; 
        }
    }

    pthread_mutex_lock(&sd->mutex_hra);
    printf("[DISCONNECT] Hrac %d odisiel.\n", index + 1);
    close(sock);
    zmaz_hada(sd->hadi[index]);
    sd->hadi[index] = NULL;
    sd->sloty_obsadene[index] = false;
    
    // Skontroluj ci su este nejaci hraci
    int pocet_hracov = 0;
    for (int i = 0; i < MAX_HRACOV; i++) {
        if (sd->sloty_obsadene[i]) {
            pocet_hracov++;
        }
    }
    
    // Ak neni ziadny hrac, vypni server
    if (pocet_hracov == 0) {
        printf("[INFO] Ziadni hraci na serveri. Server sa vypina...\n");
        sd->server_sa_vypina = true;
    }
    pthread_mutex_unlock(&sd->mutex_hra);
    
    return NULL;
}

// --- HLAVNÁ HERNÁ SLUČKA ---

void* herna_slucka(void* data) {
    SERVER_DATA *sd = (SERVER_DATA*)data;
    HRA_STAV stav;
    int globalny_tik = 0;
    srand(time(NULL));

    for (int i = 0; i < POCET_JEDLA; i++) generuj_nove_jedlo(sd, i);

    printf("[GAME] Herny engine nastartovany.\n");
    int pocitadlo = 0;

    while (sd->hra_bezi) {
        memset(&stav, 0, sizeof(HRA_STAV));
        pthread_mutex_lock(&sd->mutex_hra);

        if (sd->server_sa_vypina) {
            stav.koniec_hry = true;
            for (int i = 0; i < MAX_HRACOV; i++) {
                if (sd->sloty_obsadene[i]) {
                    sprintf(stav.sprava, "SERVER VYPNUTY! Body: %d", get_dlzka_hada(sd->hadi[i]));
                    send(sd->klientske_sockety[i], &stav, sizeof(HRA_STAV), 0);
                }
            }
            pthread_mutex_unlock(&sd->mutex_hra);
            
            // Čakaj 3 sekundy aby klienti videli skóre
            sleep(3);
            
            // Teraz uzatvori sockety
            pthread_mutex_lock(&sd->mutex_hra);
            for (int i = 0; i < MAX_HRACOV; i++) {
                if (sd->sloty_obsadene[i]) {
                    close(sd->klientske_sockety[i]);
                    zmaz_hada(sd->hadi[i]);
                    sd->hadi[i] = NULL;
                    sd->sloty_obsadene[i] = false;
                }
            }
            pthread_mutex_unlock(&sd->mutex_hra);
            
            sd->hra_bezi = false;
            
            break;
        }

        for (int i = 0; i < MAX_HRACOV; i++) {
            if (sd->sloty_obsadene[i] && sd->hadi[i]) {
                
                // Určenie pohybu (Turbo logika)
                bool pohni_sa = false;
                if (sd->hadi[i]->turbo_counter > 0) {
                    pohni_sa = true; // Turbo had ide v každom tiku
                    sd->hadi[i]->turbo_counter--;
                } else if (globalny_tik % 2 == 0) {
                    pohni_sa = true; // Bežný had ide každý druhý tik
                }

                if (pohni_sa) {
                    BOD hlava = get_pozicia_hlavy(sd->hadi[i]);
                    int rastie = 0;

                    // 1. Kolízia s jedlom
                    for (int j = 0; j < POCET_JEDLA; j++) {
                        if (hlava.x == sd->mapa_jedla[j].poloha.x && hlava.y == sd->mapa_jedla[j].poloha.y) {
                            rastie = 1;
                            reakcie[sd->mapa_jedla[j].typ](sd, i);
                            generuj_nove_jedlo(sd, j);
                        }
                    }

                    // 2. Samotný pohyb (Linked List update)
                    pohni_hada(sd->hadi[i], rastie);
                    hlava = get_pozicia_hlavy(sd->hadi[i]);

                    // 3. Kolízia s hranicami
                    if (hlava.x <= 0 || hlava.x >= MAPA_WIDTH - 1 || hlava.y <= 0 || hlava.y >= MAPA_HEIGHT - 1) {
                        respawn_hada(sd->hadi[i]);
                    }

                    // 4. Kolízia s inými objektmi (Hadi a ich telá)
                    for (int j = 0; j < MAX_HRACOV; j++) {
                        if (sd->sloty_obsadene[j] && sd->hadi[j]) {
                            
                            // URČENIE ŠTARTOVACIEHO BODU PRE TEST
                            // Ak kontrolujem seba (i == j), musím začať od krku (hlava->next), 
                            // inak hlava koliduje s hlavou a had by bol v nekonečnom respawne.
                            LL *zaciatok_testu = (i == j) ? sd->hadi[j]->hlava->next : sd->hadi[j]->hlava;

                            // GENERICKÉ VOLANIE
                            // ll_najdi_prvok vráti void* na OBJEKT, ak dôjde ku kolízii, inak NULL
                            if (ll_najdi_prvok(zaciatok_testu, test_telo_hada, &hlava)) {
                                printf("[COLLISION] Hrac %d narazil do %s!\n", i + 1, (i == j) ? "seba" : "ineho hraca");
                                respawn_hada(sd->hadi[i]);
                                break; // Po respawne už netreba kontrolovať ďalšie kolízie v tomto tiku
                            }
                        }
                    }
                }

                // Serializácia do poľa pre sieťový prenos (v každom tiku pre plynulosť)
                stav.dlzky[i] = serializuj_hada(sd->hadi[i], stav.polohy[i]);
                stav.aktivny[i] = true;
            }
        }
        
        // Skopírujeme jedlo do stavu pre klienta
        for (int i = 0; i < POCET_JEDLA; i++) stav.jedla[i] = sd->mapa_jedla[i];

        pthread_mutex_unlock(&sd->mutex_hra);

        // Rozoslanie dát
        for (int i = 0; i < MAX_HRACOV; i++) {
            if (sd->sloty_obsadene[i]) {
                send(sd->klientske_sockety[i], &stav, sizeof(HRA_STAV), 0);
            }
        }

        if (pocitadlo++ % 1000 == 0) {
            printf("\r[LOG] Hra bezi, tik: %d", globalny_tik);
            fflush(stdout);
        }

        globalny_tik++;
        usleep(50000); // 50ms = 20 FPS základ
    }
    return NULL;
}