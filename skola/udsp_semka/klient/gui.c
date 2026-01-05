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

    // DEFINÍCIA FAREBNÝCH PÁROV (Bez tohto farby nefungujú)
    init_pair(1, COLOR_RED, -1);   // Pár 1: Hráč 1 (Červená)
    init_pair(2, COLOR_GREEN, -1);     // Pár 2: Jedlo (Zelená)
    init_pair(3, COLOR_BLUE, -1);    // Pár 3: Steny (Modrá)
    init_pair(4, COLOR_YELLOW, -1);  // Pár 4: Text/Nadpisy (Žltá)
    init_pair(5, COLOR_MAGENTA, -1); // Pár 5: Hráč 2 (Fialová)
    init_pair(6, COLOR_CYAN, -1);    // Pár 6: Hráč 3 (Azúrová)
    init_pair(7, COLOR_WHITE, -1);   // Pár 7: Hráč 4 (Biela)
}

void vykresli_stav(HRA_STAV *stav) {
    erase();

    // Mapovanie indexu hráča na ID farebného páru
    // Hráč 0 -> 1 (Zelená), Hráč 1 -> 5 (Fialová), atď.
    int farby[] = {1, 5, 6, 7};

    // 1. VYKRESLENIE MAPY (Blue)
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

    // 2. VYKRESLENIE JEDLA (Red)
    for (int j = 0; j < POCET_JEDLA; j++) {
        attron(COLOR_PAIR(2)); 
        char znak = '*'; 
        if (stav->jedla[j].typ == JEDLO_TURBO) znak = 'T';
        if (stav->jedla[j].typ == JEDLO_DOUBLE) znak = '2';
        mvaddch(stav->jedla[j].poloha.y, stav->jedla[j].poloha.x, znak);
        attroff(COLOR_PAIR(2));
    }

    // 3. VYKRESLENIE HADOV
    for (int h = 0; h < MAX_HRACOV; h++) {
        if (stav->aktivny[h]) {
            // Výber unikátnej farby pre hráča
            int hrac_color = farby[h % 4]; 
            attron(COLOR_PAIR(hrac_color));
            
            // Aritmetika ukazovateľov: prístup k poliam polôh
            BOD *p_bod = stav->polohy[h]; 

            for (int i = 0; i < stav->dlzky[h]; i++) {
                // Výpočet pozície článku pomocou aritmetiky smerníkov
                int curr_x = (p_bod + i)->x;
                int curr_y = (p_bod + i)->y;

                // Vykreslenie hlavy (@) alebo tela (o)
                if (curr_x > 0 && curr_x < MAPA_WIDTH - 1 && curr_y > 0 && curr_y < MAPA_HEIGHT - 1) {
                    mvaddch(curr_y, curr_x, (i == 0) ? '@' : 'o');
                }
            }
            attroff(COLOR_PAIR(hrac_color));
        }
    }
    
    // 4. ŠTATISTIKY
    int y_off = MAPA_HEIGHT + 1;
    attron(COLOR_PAIR(4));
    mvprintw(y_off++, 2, "--- AKTUALNI HRACI ---");
    attroff(COLOR_PAIR(4));

    for (int h = 0; h < MAX_HRACOV; h++) {
        if (stav->aktivny[h]) {
            // Text štatistík bude mať rovnakú farbu ako had na mape
            attron(COLOR_PAIR(farby[h % 4]));
            mvprintw(y_off++, 2, "Hrac %d | Body (dlzka): %d", h + 1, *(stav->dlzky + h));
            attroff(COLOR_PAIR(farby[h % 4]));
        }
    }

    attron(COLOR_PAIR(4));
    mvprintw(y_off + 1, 2, "Ovladanie: WASD | Koniec: Q");
    attroff(COLOR_PAIR(4));

    refresh();
}

void vykresli_koniec(const char* sprava) {
    int stred_y = MAPA_HEIGHT / 2;
    int stred_x = MAPA_WIDTH / 2;

    attron(COLOR_PAIR(4) | A_BOLD); 
    
    mvprintw(stred_y - 2, stred_x - 15, "******************************");
    mvprintw(stred_y - 1, stred_x - 15, "* *");
    mvprintw(stred_y,     stred_x - 15, "* %-26s *", sprava);
    mvprintw(stred_y + 1, stred_x - 15, "* *");
    mvprintw(stred_y + 2, stred_x - 15, "******************************");
    
    attroff(COLOR_PAIR(4) | A_BOLD);
    refresh();
}