#ifndef SNAKE_H
#define SNAKE_H
#define MAPA_WIDTH 120
#define MAPA_HEIGHT 30
#define MAX_HRACOV 4
#define POCET_JEDLA 8 
#define SIFROVACI_KLUC 0xAB 

#include <stdbool.h> 
#include <stddef.h>

typedef enum {
    HORE, DOLE, VLAVO, VPRAVO
} SMER;

typedef struct {
    int x;
    int y;
} BOD;

typedef enum { JEDLO_KLASIK, JEDLO_TURBO, JEDLO_DOUBLE } TYP_BONUSU;

typedef struct {
    BOD poloha;
    TYP_BONUSU typ;
} POWER_UP;


//GENERICKY LINKED LIST
typedef struct LL{
    void *data;        
    struct LL *next;  
} LL;

typedef struct {
    BOD pozicia;
    char znak;
} OBJEKT;

typedef struct {
    LL *hlava;       
    LL *chvost;
    int velkost;  
    int aktualny_smer;
    int turbo_counter;
} HAD;


typedef struct {
    BOD polohy[MAX_HRACOV][100];  
    int dlzky[MAX_HRACOV];         
    bool aktivny[MAX_HRACOV];      
    POWER_UP jedla[POCET_JEDLA];   
    bool koniec_hry;               
    char sprava[128];             
} HRA_STAV;

LL* vytvor_uzol(void *data);

HAD* vytvor_hada(int start_x, int start_y);
void pohni_hada(HAD *had, int rastie);
void zmaz_hada(HAD *had);
int serializuj_hada(HAD *had, BOD *buffer);
bool skontroluj_koliziu_s_telom(HAD* had, BOD bod, bool preskoc_hlavu);

// CALLBACK PATTERN - testuje prvky v LL alebo poli
typedef bool (*TestCallback)(void* prvok, void* context);
void* ll_najdi_prvok(LL* zoznam, TestCallback test_func, void* context);
void* pole_najdi_prvok(void* pole, int pocet, size_t velkost_prvku, TestCallback test_func, void* context);

// KOLÍZNE CALLBACKY
bool test_telo_hada(void* prvok, void* context);
bool test_jedlo(void* prvok, void* context);        
bool test_hranica_mapy(void* prvok, void* context); 

BOD get_pozicia_hlavy(HAD* had);
void nastav_poziciu_hlavy(HAD* had, int x, int y);
void resetuj_poziciu_hada(HAD* had, int x, int y);
int get_dlzka_hada(HAD* had);
void zmen_smer_hada(HAD* had, char klaves);

void sifruj_data(void *data, size_t velkost);
void desifruj_data(void *data, size_t velkost);

#endif