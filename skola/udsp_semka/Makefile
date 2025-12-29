CC = gcc
CFLAGS = -Wall -Wextra -pthread -I./datove_typy

all: server_app client_app

server_app: server/main.c datove_typy/snake.c
	$(CC) $(CFLAGS) server/main.c datove_typy/snake.c -o server_app

client_app: klient/main.c
	$(CC) $(CFLAGS) klient/main.c -o client_app -lncurses

clean:
	rm -f server_app client_app