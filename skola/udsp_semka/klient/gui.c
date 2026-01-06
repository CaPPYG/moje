#include "gui.h"
#include <ncurses.h>
#include <pthread.h>
#include <time.h>

extern pthread_mutex_t curses_mtx;

void inicializuj_ncurses() {
    initscr();
    start_color();
    use_default_colors();
    curs_set(0);           
    noecho();             
    cbreak();             
    nodelay(stdscr, TRUE); 
    intrflush(stdscr, FALSE);
    keypad(stdscr, TRUE);

    init_pair(1, COLOR_RED, -1);   
    init_pair(2, COLOR_GREEN, -1);     
    init_pair(3, COLOR_BLUE, -1);  
    init_pair(4, COLOR_YELLOW, -1); 
    init_pair(5, COLOR_MAGENTA, -1);
    init_pair(6, COLOR_CYAN, -1);  
    init_pair(7, COLOR_WHITE, -1); 
} 

void vykresli_stav(HRA_STAV *stav) {
    static time_t posledny_clear = 0;
    time_t teraz = time(NULL);

    pthread_mutex_lock(&curses_mtx);

    // kazde 3s tvrdy clear
    if (teraz - posledny_clear >= 3) {
        clear(); 
        posledny_clear = teraz;
    } else {
        erase();
    }
    int farby[] = {1, 5, 6, 7};

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

    // 2. VYKRESLENIE JEDLA
    POWER_UP *jedlo = stav->jedla;                
    POWER_UP *jedlo_koniec = jedlo + POCET_JEDLA;
    
    while (jedlo < jedlo_koniec) {
        attron(COLOR_PAIR(2)); 
        char znak = '*'; 
        if (jedlo->typ == JEDLO_TURBO) znak = 'T';
        if (jedlo->typ == JEDLO_DOUBLE) znak = '2';
        mvaddch(jedlo->poloha.y, jedlo->poloha.x, znak);
        attroff(COLOR_PAIR(2));
        jedlo++; 
    }

    // 3. VYKRESLENIE HADOV
    for (int h = 0; h < MAX_HRACOV; h++) {
        if (stav->aktivny[h]) {
            int hrac_color = farby[h % 4]; 
            attron(COLOR_PAIR(hrac_color));
            
            // iterácia cez telo hada
            BOD *bod = stav->polohy[h];
            BOD *koniec = bod + stav->dlzky[h];         
            int index = 0;

            while (bod < koniec) {
                // Priamy prístup cez pointer
                if (bod->x > 0 && bod->x < MAPA_WIDTH - 1 && 
                    bod->y > 0 && bod->y < MAPA_HEIGHT - 1) {
                    mvaddch(bod->y, bod->x, (index == 0) ? '@' : 'o');
                }
                bod++;
                index++;
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
            attron(COLOR_PAIR(farby[h % 4]));
            mvprintw(y_off++, 2, "Hrac %d | Body (dlzka): %d", h + 1, *(stav->dlzky + h));
            attroff(COLOR_PAIR(farby[h % 4]));
        }
    }

    attron(COLOR_PAIR(4));
    mvprintw(y_off + 1, 2, "Ovladanie: WASD | Koniec: Q");
    attroff(COLOR_PAIR(4));

    refresh();
    pthread_mutex_unlock(&curses_mtx);
}

void vykresli_koniec(const char* sprava) {
    pthread_mutex_lock(&curses_mtx);
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

void ukonci_ncurses() {
    nocbreak();
    echo();
    nodelay(stdscr, FALSE);
    keypad(stdscr, FALSE);
    endwin();
}