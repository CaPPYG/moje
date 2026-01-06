# =============================================================================
# MAKEFILE - Zostavení semestrálnej práce
# =============================================================================
#
# SEMESTRÁLKA - SPLNENÉ POŽIADAVKY:
# [x] MAKEFILE (1 bod): Kompilovateľné cez 'make all'
# [x] ROZČLENENIE MODULOV: datove_typy/, server/, klient/
#
# POUŽITIE:
#   make          - Skompiluje server_app aj klient_app
#   make clean    - Zmaže binárky
#
# OVERENIE ÚNIKOV PAMÄTE (Valgrind):
#   valgrind --leak-check=full ./server_app
#   valgrind --leak-check=full ./klient_app
#
# =============================================================================

# Kompilátor a vlajky
CC = gcc
CFLAGS = -Wall -Wextra -I./datove_typy -I./server -I./klient
LDFLAGS = -pthread
LDLIBS = -lncurses

# Zdrojové súbory (Rozdelené podľa modulov)
COMMON_SRC = datove_typy/snake.c
SERVER_SRC = server/main.c server/logika.c
CLIENT_SRC = klient/main.c klient/gui.c

# Binárky
SERVER_BIN = server_app
CLIENT_BIN = klient_app

all: $(SERVER_BIN) $(CLIENT_BIN)

# Kompilácia servera (spája main.c + logika.c + snake.c)
$(SERVER_BIN): $(SERVER_SRC) $(COMMON_SRC)
	$(CC) $(CFLAGS) $^ -o $@ $(LDFLAGS)
	@echo "[OK] Server skompilovany."

# Kompilácia klienta (spája main.c + gui.c + snake.c)
$(CLIENT_BIN): $(CLIENT_SRC) $(COMMON_SRC)
	$(CC) $(CFLAGS) $^ -o $@ $(LDFLAGS) $(LDLIBS)
	@echo "[OK] Klient skompilovany."

clean:
	rm -f $(SERVER_BIN) $(CLIENT_BIN)
	@echo "[CLEAN] Hotovo."