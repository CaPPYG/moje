#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
#include <stdbool.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include <signal.h>
#include <string.h>
#include <netinet/tcp.h> 
#include <errno.h>
#include "snake.h"

// Globálne premenné
HAD *hadi[MAX_HRACOV] = {NULL};
int klientske_sockety[MAX_HRACOV];
bool sloty_obsadene[MAX_HRACOV] = {false};
pthread_mutex_t mutex_hra = PTHREAD_MUTEX_INITIALIZER;

volatile bool hra_bezi = true;
volatile bool server_sa_vypina = false;

// --- UKAZOVATELE NA FUNKCIE ---
typedef void (*PowerUpFunc)(int);
void efekt_klasik(int hrac) { printf("[LOG] Hrac %d zjedol Jablko.\n", hrac + 1); }
void efekt_turbo(int hrac)  { printf("[LOG] Hrac %d aktivoval TURBO.\n", hrac + 1); }
void efekt_double(int hrac) { printf("[LOG] Hrac %d ziskal DOUBLE BODY.\n", hrac + 1); }

PowerUpFunc reakcie[] = {efekt_klasik, efekt_turbo, efekt_double};
POWER_UP mapa_jedla[POCET_JEDLA];

void generuj_nove_jedlo(int index) {
    mapa_jedla[index].poloha.x = (rand() % (MAPA_WIDTH - 2)) + 1;
    mapa_jedla[index].poloha.y = (rand() % (MAPA_HEIGHT - 2)) + 1;
    mapa_jedla[index].typ = rand() % 3;
}

void spracuj_signal(int sig) {
    printf("\n[SIGNAL] Prijaty SIGINT (%d). Server sa vypina...\n", sig);
    server_sa_vypina = true;
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

int main() {
    signal(SIGINT, spracuj_signal);
    
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    
    struct sockaddr_in address = { .sin_family = AF_INET, .sin_addr.s_addr = INADDR_ANY, .sin_port = htons(12345) };
    
    if (bind(server_fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
        perror("[ERROR] Bind zlyhal");
        exit(EXIT_FAILURE);
    }
    
    listen(server_fd, MAX_HRACOV);
    printf("==========================================\n");
    printf("   SNAKE MULTIPLAYER SERVER STARTING...   \n");
    printf("   Port: 12345 | Max hracov: %d           \n", MAX_HRACOV);
    printf("==========================================\n");

    pthread_t t_logika;
    pthread_create(&t_logika, NULL, herna_slucka, NULL);

    while (hra_bezi && !server_sa_vypina) {
        struct timeval tv = { .tv_sec = 1, .tv_usec = 0 };
        setsockopt(server_fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

        int new_sock = accept(server_fd, NULL, NULL);
        if (new_sock < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) continue;
            break;
        }

        // --- FIX: Reset timeoutu pre noveho hraca ---
        struct timeval no_tv = { .tv_sec = 0, .tv_usec = 0 };
        setsockopt(new_sock, SOL_SOCKET, SO_RCVTIMEO, &no_tv, sizeof(no_tv));
        
        int flag = 1;
        setsockopt(new_sock, IPPROTO_TCP, TCP_NODELAY, (char *) &flag, sizeof(int));

        pthread_mutex_lock(&mutex_hra);
        int slot = -1;
        for (int i = 0; i < MAX_HRACOV; i++) if (!sloty_obsadene[i]) { slot = i; break; }

        if (slot != -1) {
            klientske_sockety[slot] = new_sock;
            hadi[slot] = vytvor_hada(10 + (slot * 5), 10);
            sloty_obsadene[slot] = true;
            
            int *arg = malloc(sizeof(int));
            *arg = slot;
            pthread_t t_vstup;
            pthread_create(&t_vstup, NULL, spracuj_vstupy, arg);
            pthread_detach(t_vstup);
            
            printf("[CONNECT] Novy hrac pripojeny do slotu %d.\n", slot + 1);
        } else {
            printf("[REJECT] Server je plny.\n");
            close(new_sock);
        }
        pthread_mutex_unlock(&mutex_hra);
    }

    pthread_join(t_logika, NULL);
    close(server_fd);
    printf("==========================================\n");
    printf("   SERVER BOL USPESNE UKONCENY.           \n");
    printf("==========================================\n");
    return 0;
}