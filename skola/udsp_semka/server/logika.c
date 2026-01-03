#include "logika.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pthread.h>
#include <sys/socket.h>
#include <errno.h>

// Externé premenné z main.c
// Tieto premenné sa reálne nachádzajú v main.c
extern HAD *hadi[MAX_HRACOV];
extern int klientske_sockety[MAX_HRACOV];
extern bool sloty_obsadene[MAX_HRACOV];
extern pthread_mutex_t mutex_hra;
extern volatile bool hra_bezi;
extern volatile bool server_sa_vypina;

// Lokálne definované v tomto module
extern POWER_UP mapa_jedla[POCET_JEDLA];
typedef void (*PowerUpFunc)(int);
extern PowerUpFunc reakcie[];

void generuj_nove_jedlo(int index) {
    mapa_jedla[index].poloha.x = (rand() % (MAPA_WIDTH - 2)) + 1;
    mapa_jedla[index].poloha.y = (rand() % (MAPA_HEIGHT - 2)) + 1;
    mapa_jedla[index].typ = rand() % 3;
}
void* spracuj_vstupy(void* data) {
    int index = *((int*)data);
    free(data);
    int sock = klientske_sockety[index];
    char prikaz;

    printf("[INFO] Vlakno pre vstupy hraca %d spustene.\n", index + 1);

    while (hra_bezi && !server_sa_vypina) {
        int r = recv(sock, &prikaz, 1, 0);
        if (r > 0) {
            pthread_mutex_lock(&mutex_hra);
            if (hadi[index]) {
                zmen_smer_hada(hadi[index], prikaz);
            }
            pthread_mutex_unlock(&mutex_hra);
            if (prikaz == 'q') break;
        } else if (r == 0) {
            break; // Hrac sa odpojil
        } else {
            if (errno == EAGAIN || errno == EWOULDBLOCK) continue;
            break; // Ina chyba
        }
    }

    pthread_mutex_lock(&mutex_hra);
    int final_score = get_dlzka_hada(hadi[index]);
    printf("[DISCONNECT] Hrac %d odisiel. Konecne skore: %d\n", index + 1, final_score);
    close(sock);
    zmaz_hada(hadi[index]);
    hadi[index] = NULL;
    sloty_obsadene[index] = false;
    pthread_mutex_unlock(&mutex_hra);
    return NULL;
}
void* herna_slucka(void* data) {
    (void)data;
    HRA_STAV stav;
    srand(time(NULL));
    for (int i = 0; i < POCET_JEDLA; i++) generuj_nove_jedlo(i);

    printf("[GAME] Herny engine nastartovany.\n");

    while (hra_bezi) {
        memset(&stav, 0, sizeof(HRA_STAV));
        int pocet_aktivnych = 0;

        pthread_mutex_lock(&mutex_hra);
        for(int i=0; i<MAX_HRACOV; i++) if(sloty_obsadene[i]) pocet_aktivnych++;

        if (server_sa_vypina) {
            stav.koniec_hry = true;
            for (int i = 0; i < MAX_HRACOV; i++) {
                if (sloty_obsadene[i]) {
                    sprintf(stav.sprava, "SERVER VYPNUTY! Body: %d", get_dlzka_hada(hadi[i]));
                    send(klientske_sockety[i], &stav, sizeof(HRA_STAV), 0);
                }
            }
            pthread_mutex_unlock(&mutex_hra);
            sleep(5);
            hra_bezi = false;
            break;
        }

        if (pocet_aktivnych > 0) {
            for (int i = 0; i < POCET_JEDLA; i++) stav.jedla[i] = mapa_jedla[i];

            for (int i = 0; i < MAX_HRACOV; i++) {
                if (sloty_obsadene[i] && hadi[i]) {
                    BOD hlava = get_pozicia_hlavy(hadi[i]);
                    int rastie = 0;

                    for (int j = 0; j < POCET_JEDLA; j++) {
                        if (hlava.x == mapa_jedla[j].poloha.x && hlava.y == mapa_jedla[j].poloha.y) {
                            rastie = 1;
                            reakcie[mapa_jedla[j].typ](i);
                            generuj_nove_jedlo(j);
                        }
                    }

                    pohni_hada(hadi[i], rastie);
                    hlava = get_pozicia_hlavy(hadi[i]);

                    // Kontrola hranic
                    if (hlava.x <= 0 || hlava.x >= MAPA_WIDTH - 1 || hlava.y <= 0 || hlava.y >= MAPA_HEIGHT - 1) {
                        nastav_poziciu_hlavy(hadi[i], 10 + (i * 5), 10);
                    }

                    // Kolizie s telami
                    for (int j = 0; j < MAX_HRACOV; j++) {
                        if (sloty_obsadene[j] && hadi[j]) {
                            if (skontroluj_koliziu_s_telom(hadi[j], hlava, (i == j))) {
                                nastav_poziciu_hlavy(hadi[i], 10 + (i * 5), 10);
                            }
                        }
                    }
                    stav.dlzky[i] = serializuj_hada(hadi[i], stav.polohy[i]);
                    stav.aktivny[i] = true;
                }
            }
        }
        pthread_mutex_unlock(&mutex_hra);

        // Aritmetika ukazovatelov pre odoslanie
        HRA_STAV *p_stav = &stav;
        for (int i = 0; i < MAX_HRACOV; i++) {
            if (sloty_obsadene[i]) send(klientske_sockety[i], p_stav, sizeof(HRA_STAV), 0);
        }
        usleep(100000);
    }
    printf("[GAME] Herny engine zastaveny.\n");
    return NULL;
}