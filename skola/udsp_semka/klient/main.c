#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <ncurses.h>
#include "snake.h"
#include "gui.h"

void* odosielaj_vstupy(void* data) {
    int sock = *((int*)data);
    while (1) {
        int klaves = getch(); 
        if (klaves != ERR) {
            char c = (char)klaves;
            send(sock, &c, 1, 0);
            if (c == 'q') break;
        }
        usleep(5000); 
    }
    return NULL;
}

int main() {
    int sock = 0;
    struct sockaddr_in serv_addr;

    sock = socket(AF_INET, SOCK_STREAM, 0);
    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(12345);
    inet_pton(AF_INET, "127.0.0.1", &serv_addr.sin_addr);

    if (connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {
        printf("Pripojenie zlyhalo!\n");
        return -1;
    }

    inicializuj_ncurses();

    pthread_t vlakno_vstup;
    int socket_copy = sock; // Bezpečnejšie poslať kópiu
    pthread_create(&vlakno_vstup, NULL, odosielaj_vstupy, &socket_copy);

    while (1) {
        HRA_STAV stav;
        int celkovo_prijate = 0;
        char *ptr = (char*)&stav;

        // Cyklus, ktorý číta, kým nemá celú štruktúru
        while (celkovo_prijate < (int)sizeof(HRA_STAV)) {
            int r = recv(sock, ptr + celkovo_prijate, sizeof(HRA_STAV) - celkovo_prijate, 0);
            if (r <= 0) {
                // Ak sa spojenie preruší
                endwin();
                printf("Server ukoncil spojenie.\n");
                return 0;
            }
            celkovo_prijate += r;
        }

        vykresli_stav(&stav);

        // KONIEC HRY (Ak sa server vypne)
        if (stav.koniec_hry) {
            vykresli_koniec(stav.sprava);
            pthread_join(vlakno_vstup, NULL);           
            // Klient zostane zobrazený, kým ho server neodpojí alebo neubehne čas
            continue; 
        }

        
    }

    endwin(); 
    close(sock);
    return 0;
}