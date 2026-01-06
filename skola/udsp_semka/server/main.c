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

SERVER_DATA *global_sd_ptr = NULL;

void spracuj_signal(int sig) {
    if (global_sd_ptr) {
        printf("\n[SIGNAL] Prijaty SIGINT (%d). Server sa vypina...\n", sig);
        global_sd_ptr->server_sa_vypina = true;
    }
}

int main() {
    srand(time(NULL));

    SERVER_DATA sd;
    memset(&sd, 0, sizeof(SERVER_DATA));
    sd.hra_bezi = true;
    sd.server_sa_vypina = false;
    pthread_mutex_init(&sd.mutex_hra, NULL);

    // Priradenie do globálneho smerníka pre signál
    global_sd_ptr = &sd;
    signal(SIGINT, spracuj_signal);
    
    int server_fd = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    
    struct sockaddr_in address = {
        .sin_family = AF_INET, 
        .sin_addr.s_addr = INADDR_ANY, 
        .sin_port = htons(12345)
    };
    
    if (bind(server_fd, (struct sockaddr *)&address, sizeof(address)) < 0) {
        perror("[ERROR] Bind zlyhal");
        exit(EXIT_FAILURE);
    }
    
    listen(server_fd, MAX_HRACOV);
    printf("==========================================\n");
    printf("   SNAKE MULTIPLAYER SERVER STARTING...   \n");
    printf("   Port: 12345 | Max hracov: %d           \n", MAX_HRACOV);
    printf("==========================================\n");

    pthread_t t_vstupy[MAX_HRACOV];
    // herna slučka v samostatnom vlákne
    pthread_t t_logika;
    pthread_create(&t_logika, NULL, herna_slucka, &sd);

    while (sd.hra_bezi && !sd.server_sa_vypina) {
        struct timeval tv = { .tv_sec = 1, .tv_usec = 0 };
        setsockopt(server_fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

        int new_sock = accept(server_fd, NULL, NULL);
        if (new_sock < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) continue;
            break;
        }

        struct timeval no_tv = { .tv_sec = 0, .tv_usec = 0 };
        setsockopt(new_sock, SOL_SOCKET, SO_RCVTIMEO, &no_tv, sizeof(no_tv));
        
        int flag = 1;
        setsockopt(new_sock, IPPROTO_TCP, TCP_NODELAY, (char *) &flag, sizeof(int));

        pthread_mutex_lock(&sd.mutex_hra);
        int slot = -1;
        for (int i = 0; i < MAX_HRACOV; i++) {
            if (!sd.sloty_obsadene[i]) { 
                slot = i; 
                break; 
            }
        }

        if (slot != -1) {
            sd.klientske_sockety[slot] = new_sock;
            int r_x = (rand() % (MAPA_WIDTH - 4)) + 2;
            int r_y = (rand() % (MAPA_HEIGHT - 4)) + 2;
            sd.hadi[slot] = vytvor_hada(r_x, r_y);
            sd.sloty_obsadene[slot] = true;
            
            VSTUP_ARGS *arg = malloc(sizeof(VSTUP_ARGS));
            arg->sd = &sd;
            arg->hrac_index = slot;

            
            pthread_create(&t_vstupy[slot], NULL, spracuj_vstupy, arg);
            
            
            printf("[CONNECT] Novy hrac pripojeny do slotu %d.\n", slot + 1);
        } else {
            printf("[REJECT] Server je plny.\n");
            close(new_sock);
        }
        pthread_mutex_unlock(&sd.mutex_hra);
    }


    // Čakanie na ukončenie logiky
    pthread_join(t_logika, NULL);
    for (int i = 0; i < MAX_HRACOV; i++) {
        if (sd.sloty_obsadene[i]) {
            pthread_join(t_vstupy[i], NULL);
        }
    }

    // Uvoľnenie hadov - iba raz, s mutexom
    pthread_mutex_lock(&sd.mutex_hra);
    for (int i = 0; i < MAX_HRACOV; i++) {
        if (sd.hadi[i]) {
            zmaz_hada(sd.hadi[i]);
            sd.hadi[i] = NULL;
        }
    }
    pthread_mutex_unlock(&sd.mutex_hra);
    pthread_mutex_destroy(&sd.mutex_hra);
    sleep(2);
    
    close(server_fd);
    printf("==========================================\n");
    printf("   SERVER BOL USPESNE UKONCENY.           \n");
    printf("==========================================\n");
    return 0;
}