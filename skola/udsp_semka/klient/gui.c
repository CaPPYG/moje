#include "gui.h"
#include <ncurses.h>

void inicializuj_ncurses() {
    // --- GUI INICIALIZÁCIA ---
    initscr();
    start_color();
    use_default_colors();
    curs_set(0);           
    noecho();             
    cbreak();             
    nodelay(stdscr, TRUE); 

    // OPRAVA FAREBNÝCH PÁROV (Nesmú sa ID duplikovať)
    init_pair(1, COLOR_GREEN, -1);   // Hráč 1
    init_pair(2, COLOR_RED, -1);     // Jedlo / Hráč 2 (v tvojom kóde bol konflikt)
    init_pair(3, COLOR_BLUE, -1);    // Steny
    init_pair(4, COLOR_YELLOW, -1);  // Text
    init_pair(5, COLOR_MAGENTA, -1); // Hráč 3
    init_pair(6, COLOR_CYAN, -1);    // Špeciálne jedlo
}

void vykresli_stav(HRA_STAV *stav) {
    erase();
    // 1. VYKRESLENIE MAPY
        attron(COLOR_PAIR(3)); 
        for (int x = 0; x < MAPA_WIDTH; x++) {
            mvaddch(0, x, '-');               
            mvaddch(MAPA_HEIGHT - 1, x, '-');  
        }
        for (int y = 0; y < MAPA_HEIGHT; y++) {
            mvaddch(y, 0, '|');               
            mvaddch(y, MAPA_WIDTH - 1, '|');   
        }
        attroff(COLOR_PAIR(3));

        // 2. VYKRESLENIE JEDLA (Zosúladené so serverom)
        for (int j = 0; j < POCET_JEDLA; j++) {
            attron(COLOR_PAIR(2)); 
            char znak = '*'; 
            if (stav.jedla[j].typ == JEDLO_TURBO) znak = 'T';
            if (stav.jedla[j].typ == JEDLO_DOUBLE) znak = '2';
            mvaddch(stav.jedla[j].poloha.y, stav.jedla[j].poloha.x, znak);
            attroff(COLOR_PAIR(2));
        }

        // 3. VYKRESLENIE HADOU
        for (int h = 0; h < MAX_HRACOV; h++) {
            if (stav.aktivny[h]) {
                // Farba 1 pre vás, farba 5 pre ostatných
                int color = (h == 0) ? 1 : 5; 
                attron(COLOR_PAIR(color));
                
                for (int i = 0; i < stav.dlzky[h]; i++) {
                    int x = stav.polohy[h][i].x;
                    int y = stav.polohy[h][i].y;

                    // Kontrola či súradnice nie sú náhodné (mimo mapy)
                    if (x >= 0 && x < MAPA_WIDTH && y >= 0 && y < MAPA_HEIGHT) {
                        mvaddch(y, x, (i == 0) ? '@' : 'o');
                    }
                }
                attroff(COLOR_PAIR(color));
            }
        }

        // 4. ŠTATISTIKY (Aritmetika ukazovateľov - SPLNENIE ZADANIA)
        attron(COLOR_PAIR(4));
        int y_offset = MAPA_HEIGHT + 1;
        mvprintw(y_offset++, 2, "--- AKTUALNI HRACI ---");
        
        int *ptr_dlzky = stav.dlzky; // Smerník na pole dĺžok
        for (int h = 0; h < MAX_HRACOV; h++) {
            if (stav.aktivny[h]) {
                // Použitie aritmetiky: *(ptr + h) namiesto [h]
                mvprintw(y_offset++, 2, "Hrac %d | Dlzk: %d", h + 1, *(ptr_dlzky + h));
            }
        }
        mvprintw(y_offset + 1, 2, "Ovladanie: WASD | Koniec: Q");
        attroff(COLOR_PAIR(4));
        refresh();
}


void vykresli_koniec(const char* sprava) {
    int stred_y = MAPA_HEIGHT / 2;
    int stred_x = MAPA_WIDTH / 2;

    attron(COLOR_PAIR(4) | A_BOLD); // Žltá tučná farba
    
    // Vykreslenie rámika pre správu
    mvprintw(stred_y - 2, stred_x - 15, "******************************");
    mvprintw(stred_y - 1, stred_x - 15, "* *");
    mvprintw(stred_y,     stred_x - 15, "* %-26s *", stav.sprava);
    mvprintw(stred_y + 1, stred_x - 15, "* *");
    mvprintw(stred_y + 2, stred_x - 15, "******************************");
    
    attroff(COLOR_PAIR(4) | A_BOLD);
    refresh();
}