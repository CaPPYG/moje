#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
#include <stdbool.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include "snake.h"


HAD *hadi[MAX_HRACOV] = {NULL};
int klientske_sockety[MAX_HRACOV];
bool sloty_obsadene[MAX_HRACOV] = {false};
pthread_mutex_t mutex_hra = PTHREAD_MUTEX_INITIALIZER;
bool hra_bezi = true;

BOD aktualne_jedlo = {15, 5};
void generuj_nove_jedlo() {
    // Generujeme jedlo tak, aby nebolo na stene (1 až MAPA-2)
    aktualne_jedlo.x = (rand() % (MAPA_WIDTH - 2)) + 1;
    aktualne_jedlo.y = (rand() % (MAPA_HEIGHT - 2)) + 1;
}

// Vlákno pre obsluhu prichádzajúcich správ od konkrétneho hráča
void* spracuj_vstupy(void* data) {
    int index = *((int*)data);
    free(data);
    int sock = klientske_sockety[index];
    char prikaz;

    // Kým klient posiela dáta...
    while (recv(sock, &prikaz, 1, 0) > 0) {
        pthread_mutex_lock(&mutex_hra);
        if (hadi[index]) {
            if (prikaz == 'w') hadi[index]->aktualny_smer = HORE;
            else if (prikaz == 's') hadi[index]->aktualny_smer = DOLE;
            else if (prikaz == 'a') hadi[index]->aktualny_smer = VLAVO;
            else if (prikaz == 'd') hadi[index]->aktualny_smer = VPRAVO;
        }
        pthread_mutex_unlock(&mutex_hra);
        if (prikaz == 'q') break;
    }

    // Odpojenie hráča
    printf("[Server] Hráč %d sa odpojil.\n", index + 1);
    pthread_mutex_lock(&mutex_hra);
    close(sock);
    zmaz_hada(hadi[index]);
    hadi[index] = NULL;
    sloty_obsadene[index] = false;
    pthread_mutex_unlock(&mutex_hra);
    return NULL;
}

// Herná slučka (beží navždy v pozadí)
void* herna_slucka(void* data) {
    (void)data;
    HRA_STAV stav;
    srand(time(NULL));

    while (hra_bezi) {
        pthread_mutex_lock(&mutex_hra);
        stav.jedlo = aktualne_jedlo;

        for (int i = 0; i < MAX_HRACOV; i++) {
            if (sloty_obsadene[i] && hadi[i]) {
                BOD hlava = hadi[i]->hlava->pozicia;
                int rastie = 0;

                // 1. KONTROLA: Jedlo
                if (hlava.x == aktualne_jedlo.x && hlava.y == aktualne_jedlo.y) {
                    rastie = 1;
                    generuj_nove_jedlo();
                }

                pohni_hada(hadi[i], rastie);
                
                // Aktualizujeme polohu hlavy po pohybe pre ďalšie kontroly
                hlava = hadi[i]->hlava->pozicia;

                // 2. KONTROLA: Steny
                if (hlava.x <= 0 || hlava.x >= MAPA_WIDTH - 1 || 
                    hlava.y <= 0 || hlava.y >= MAPA_HEIGHT - 1) {
                    
                    // Reset hada pri náraze do steny
                    hadi[i]->hlava->pozicia.x = 10 + (i * 5);
                    hadi[i]->hlava->pozicia.y = 10;
                    // Voliteľne: skrátiť hada na pôvodnú dĺžku
                }

                // 3. KONTROLA: Náraz do iných hráčov (aj do seba)
                for (int j = 0; j < MAX_HRACOV; j++) {
                    if (sloty_obsadene[j] && hadi[j]) {
                        // Prechádzame všetky články hada 'j'
                        SnakeNode *curr = hadi[j]->hlava;
                        
                        // Ak kontrolujeme náraz do seba (i == j), preskočíme hlavu
                        if (i == j) curr = curr->next;

                        while (curr != NULL) {
                            if (hlava.x == curr->pozicia.x && hlava.y == curr->pozicia.y) {
                                // NÁRAZ! Resetujeme hada 'i'
                                hadi[i]->hlava->pozicia.x = 10 + (i * 5);
                                hadi[i]->hlava->pozicia.y = 10;
                                break;
                            }
                            curr = curr->next;
                        }
                    }
                }

                // Serializácia pre odoslanie
                stav.dlzky[i] = serializuj_hada(hadi[i], stav.polohy[i]);
                stav.aktivny[i] = true;
            } else {
                stav.aktivny[i] = false;
            }
        }
        pthread_mutex_unlock(&mutex_hra);
        
        // Broadcast (odoslanie všetkým)
        for (int i = 0; i < MAX_HRACOV; i++) {
            if (sloty_obsadene[i]) {
                send(klientske_sockety[i], &stav, sizeof(HRA_STAV), 0);
            }
        }

        usleep(150000);
    }
    return NULL;
}

int main() {
    int server_fd;
    struct sockaddr_in address;
    int addrlen = sizeof(address);

    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(12345);

    bind(server_fd, (struct sockaddr *)&address, sizeof(address));
    listen(server_fd, MAX_HRACOV);

    // Spustíme hernú slučku hneď na začiatku
    pthread_t t_logika;
    pthread_create(&t_logika, NULL, herna_slucka, NULL);

    printf("Server beží. Hráči sa môžu pripájať...\n");

    while (hra_bezi) {
        int new_sock = accept(server_fd, (struct sockaddr *)&address, (socklen_t*)&addrlen);
        
        pthread_mutex_lock(&mutex_hra);
        int volny_slot = -1;
        for (int i = 0; i < MAX_HRACOV; i++) {
            if (!sloty_obsadene[i]) {
                volny_slot = i;
                break;
            }
        }

        if (volny_slot != -1) {
            klientske_sockety[volny_slot] = new_sock;
            hadi[volny_slot] = vytvor_hada(10 + (volny_slot * 3), 10);
            sloty_obsadene[volny_slot] = true;
            
            int *arg = malloc(sizeof(int));
            *arg = volny_slot;
            pthread_t t_vstup;
            pthread_create(&t_vstup, NULL, spracuj_vstupy, arg);
            pthread_detach(t_vstup); // Vlákno sa samo uprace po skončení
            
            printf("Nový hráč pripojený na slot %d\n", volny_slot + 1);
        } else {
            printf("Server je plný, odpájam klienta.\n");
            close(new_sock);
        }
        pthread_mutex_unlock(&mutex_hra);
    }

    close(server_fd);
    return 0;
}