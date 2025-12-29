#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <ncurses.h>
#include "snake.h"

void* odosielaj_vstupy(void* data) {
    int sock = *((int*)data);
    while (1) {
        int klaves = getch(); 
        if (klaves != ERR) {
            char c = (char)klaves;
            send(sock, &c, 1, 0);
            if (c == 'q') break;
        }
        usleep(10000); 
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

    // --- GUI INICIALIZÁCIA ---
    initscr();
    start_color();        // Zapnutie farieb
    use_default_colors();
    init_pair(1, COLOR_GREEN, -1); // -1 znamená priesvitné pozadie (použije farbu terminálu)
    init_pair(2, COLOR_RED, -1);
    init_pair(3, COLOR_BLUE, -1);
    init_pair(4, COLOR_YELLOW, -1);
    curs_set(0);          // Skrytie kurzora
    noecho();             // Nevypisovanie stlačených kláves
    cbreak();             // Čítanie znakov hneď (netreba Enter)
    nodelay(stdscr, TRUE); // getch nebude blokovať

    // Definícia farebných párov (ID, text, pozadie)
    init_pair(1, COLOR_GREEN, COLOR_BLACK);  // Had
    init_pair(2, COLOR_RED, COLOR_BLACK);    // Potrava
    init_pair(3, COLOR_BLUE, COLOR_BLACK);   // Steny/Box
    init_pair(4, COLOR_YELLOW, COLOR_BLACK); // Text/Skóre

    pthread_t vlakno_vstup;
    pthread_create(&vlakno_vstup, NULL, odosielaj_vstupy, &sock);

    while (1) {
        int pocet;
        if (recv(sock, &pocet, sizeof(int), 0) <= 0) break;

        BOD poloha_hada[100];
        recv(sock, poloha_hada, sizeof(BOD) * pocet, 0);

        // Použijeme erase() namiesto clear() pre plynulejší obraz
        erase(); 

        // 1. Vykreslenie modrého ohraničenia (GUI Box)
        attron(COLOR_PAIR(3));
        for (int i = 0; i < COLS; i++) {
            mvaddch(0, i, '#');          // Horná stena
            mvaddch(LINES - 1, i, '#');  // Dolná stena
        }
        for (int i = 0; i < LINES; i++) {
            mvaddch(i, 0, '#');          // Ľavá stena
            mvaddch(i, COLS - 1, '#');   // Pravá stena
        }
        attroff(COLOR_PAIR(3));

        // 2. Vykreslenie hada zelenou farbou
        attron(COLOR_PAIR(1));
        for (int i = 0; i < pocet; i++) {
            // Hlava @, telo o
            mvaddch(poloha_hada[i].y, poloha_hada[i].x, (i == 0) ? '@' : 'o');
        }
        attroff(COLOR_PAIR(1));

        // 3. Horný stavový riadok (Skóre)
        attron(COLOR_PAIR(4));
        mvprintw(0, 2, "[ HRAC: Patrik | DLZKA: %d ]", pocet);
        mvprintw(LINES - 1, 2, "[ Ovladanie: WASD | Koniec: Q ]");
        attroff(COLOR_PAIR(4));
        
        refresh(); 
    }

    endwin(); 
    close(sock);
    return 0;
}