#include <stdio.h>
#include <stdlib.h>
#include <pthread.h>
#include <unistd.h>
#include <stdbool.h>
#include <sys/socket.h>
#include <arpa/inet.h>
#include "snake.h"

HAD *zdielany_had;
bool hra_bezi = true;
pthread_mutex_t mutex_had;

// 1. VLÁKNO: Prijíma príkazy od klienta
void* spracuj_vstupy(void* data) {
    int socket = *((int*)data);
    char prikaz;
    while (hra_bezi && recv(socket, &prikaz, 1, 0) > 0) {
        pthread_mutex_lock(&mutex_had);
        if (prikaz == 'w') zdielany_had->aktualny_smer = HORE;
        else if (prikaz == 's') zdielany_had->aktualny_smer = DOLE;
        else if (prikaz == 'a') zdielany_had->aktualny_smer = VLAVO;
        else if (prikaz == 'd') zdielany_had->aktualny_smer = VPRAVO;
        else if (prikaz == 'q') hra_bezi = false;
        pthread_mutex_unlock(&mutex_had);
    }
    return NULL;
}

// 2. VLÁKNO: Herná slučka (Pohyb a odosielanie)
void* herna_slucka(void* data) {
    int socket = *((int*)data);
    BOD export_hry[100];

    while (hra_bezi) {
        pthread_mutex_lock(&mutex_had);
        
        pohni_hada(zdielany_had, 0); // Tu sa had reálne pohne
        int pocet = serializuj_hada(zdielany_had, export_hry);
        
        pthread_mutex_unlock(&mutex_had);

        // Odoslanie klientovi
        if (send(socket, &pocet, sizeof(int), 0) <= 0) break;
        if (send(socket, export_hry, sizeof(BOD) * pocet, 0) <= 0) break;
        
        usleep(150000); // Rýchlosť hada (150ms)
    }
    hra_bezi = false;
    return NULL;
}

int main() {
    zdielany_had = vytvor_hada(10, 10);
    pthread_mutex_init(&mutex_had, NULL);

    int server_fd, new_socket;
    struct sockaddr_in address;
    int opt = 1;
    int addrlen = sizeof(address);

    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(12345);

    bind(server_fd, (struct sockaddr *)&address, sizeof(address));
    listen(server_fd, 3);

    printf("Server čaká na pripojenie...\n");
    new_socket = accept(server_fd, (struct sockaddr *)&address, (socklen_t*)&addrlen);
    
    // Spustíme OBE vlákna pre jedného klienta
    pthread_t vlakno_logiky, vlakno_vstupov;
    
    // Alokujeme socket do pamäte, aby ho obe vlákna mali bezpečne
    int *s_ptr = malloc(sizeof(int));
    *s_ptr = new_socket;

    pthread_create(&vlakno_logiky, NULL, herna_slucka, s_ptr);
    pthread_create(&vlakno_vstupov, NULL, spracuj_vstupy, s_ptr);

    // Čakáme, kým hra skončí (napr. stlačením 'q')
    pthread_join(vlakno_logiky, NULL);
    // Vlakno vstupov môžeme ukončiť násilne alebo nechať dobehnúť
    
    printf("Ukončujem hru...\n");
    pthread_mutex_destroy(&mutex_had);
    zmaz_hada(zdielany_had);
    close(new_socket);
    close(server_fd);
    free(s_ptr);

    return 0;
}