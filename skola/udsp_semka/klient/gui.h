#ifndef GUI_H
#define GUI_H

#include "snake.h"

void inicializuj_ncurses();
void vykresli_stav(HRA_STAV *stav);
void vykresli_koniec(const char* sprava);
void ukonci_ncurses();

#endif