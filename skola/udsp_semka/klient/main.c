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
    start_color();
    use_default_colors();
    // Použijeme rovnakú farbu pre text aj pozadie, aby vznikol plný blok
    // Definícia "blokov" (textová farba, pozadie)
    init_pair(1, COLOR_GREEN, COLOR_GREEN);   // Had: zelený blok
    init_pair(2, COLOR_RED, COLOR_RED);       // Potrava: červený blok
    init_pair(3, COLOR_BLUE, COLOR_BLUE);     // Steny: modrý blok
    init_pair(4, COLOR_YELLOW, -1);           // Text: žltý na priesvitnom
    curs_set(0);          // Skrytie kurzora
    noecho();             // Nevypisovanie stlačených kláves
    cbreak();             // Čítanie znakov hneď (netreba Enter)
    nodelay(stdscr, TRUE); // getch nebude blokovať

    // Definícia farebných párov (ID, text, pozadie)
    init_pair(1, COLOR_GREEN, -1);   // Hráč 1 - Zelený
    init_pair(2, COLOR_CYAN, -1);    // Hráč 2 - Tyrkysový
    init_pair(3, COLOR_BLUE, -1);    // Steny - Modré
    init_pair(4, COLOR_YELLOW, -1);  // Texty - Žlté
    init_pair(5, COLOR_MAGENTA, -1); // Hráč 3 - Fialový

    pthread_t vlakno_vstup;
    pthread_create(&vlakno_vstup, NULL, odosielaj_vstupy, &sock);

    while (1) {
        HRA_STAV stav;
        int bytes = recv(sock, &stav, sizeof(HRA_STAV), 0);
        if (bytes <= 0) break; // Server sa odpojil

        erase(); // Vymažeme obraz

        // 1. VYKRESLENIE PEVNEJ MAPY POMOCOU ZNAKOV
        attron(COLOR_PAIR(3)); // Modrá farba pre steny

        // Horný a dolný okraj
        for (int x = 0; x < MAPA_WIDTH; x++) {
            mvaddch(0, x, '-');               // Horná stena
            mvaddch(MAPA_HEIGHT - 1, x, '-');  // Dolná stena
        }

        // Bočné steny
        for (int y = 0; y < MAPA_HEIGHT; y++) {
            mvaddch(y, 0, '|');               // Ľavá stena
            mvaddch(y, MAPA_WIDTH - 1, '|');   // Pravá stena
        }

        // Rohy (aby to vyzeralo profesionálne)
        mvaddch(0, 0, '+');
        mvaddch(0, MAPA_WIDTH - 1, '+');
        mvaddch(MAPA_HEIGHT - 1, 0, '+');
        mvaddch(MAPA_HEIGHT - 1, MAPA_WIDTH - 1, '+');

        attroff(COLOR_PAIR(3));

        // VYKRESLENIE JEDLA
        attron(COLOR_PAIR(2)); // Červená farba (ID 2 sme si už definovali)
        mvaddch(stav.jedlo.y, stav.jedlo.x, '*'); 
        attroff(COLOR_PAIR(2));

        // 2. VYKRESLENIE HADA (Zelená farba, priesvitné pozadie)
        for (int h = 0; h < MAX_HRACOV; h++) {
            // Kreslíme hada len ak server oznámil, že je slot aktívny
            if (stav.aktivny[h]) {
                attron(COLOR_PAIR(h == 0 ? 1 : (h == 1 ? 2 : 5))); // Priradenie farby podľa indexu
                
                for (int i = 0; i < stav.dlzky[h]; i++) {
                    int x = stav.polohy[h][i].x;
                    int y = stav.polohy[h][i].y;

                    // Kontrola hraníc pred vykreslením
                    if (x > 0 && x < MAPA_WIDTH - 1 && y > 0 && y < MAPA_HEIGHT - 1) {
                        mvaddch(y, x, (i == 0) ? '@' : 'o');
                    }
                }
                attroff(COLOR_PAIR(h == 0 ? 1 : (h == 1 ? 2 : 5)));
            }
        }

       // Upravený "3. STATISTIKY POD MAPOU"
        attron(COLOR_PAIR(4));
        int y_offset = MAPA_HEIGHT + 1;
        mvprintw(y_offset++, 2, "--- AKTUALNI HRACI ---");
        for (int h = 0; h < MAX_HRACOV; h++) {
            if (stav.aktivny[h]) {
                mvprintw(y_offset++, 2, "Hrac %d | Dlzk: %d", h + 1, stav.dlzky[h]);
            }
        }
        mvprintw(y_offset + 1, 2, "Ovladanie: WASD | Koniec: Q");
        attroff(COLOR_PAIR(4));

        refresh();
        }

    endwin(); 
    close(sock);
    return 0;
}