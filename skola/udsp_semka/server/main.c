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
#include "logika.h"

// --- GLOBÁLNE PREMENNÉ (Fyzicky definované tu) ---
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

void spracuj_signal(int sig) {
    printf("\n[SIGNAL] Prijaty SIGINT (%d). Server sa vypina...\n", sig);
    server_sa_vypina = true;
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