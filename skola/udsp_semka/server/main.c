#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>

int main() {
    int server_fd, new_socket;
    struct sockaddr_in address;
    int opt = 1;
    int addrlen = sizeof(address);
    char *hello = "Ahoj, vitaj v hre Slither!";

    // 1. Vytvorenie socketu
    server_fd = socket(AF_INET, SOCK_STREAM, 0);
    
    // 2. Nastavenie socketu (opätovné použitie portu)
    setsockopt(server_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    address.sin_family = AF_INET;
    address.sin_addr.s_addr = INADDR_ANY;
    address.sin_port = htons(12345); // Port hry

    // 3. Bind - priradenie portu
    bind(server_fd, (struct sockaddr *)&address, sizeof(address));

    // 4. Listen - čakanie na pripojenie
    listen(server_fd, 3);
    printf("Server beží a čaká na hráčov...\n");

    // 5. Accept - prijatie pripojenia od klienta
    new_socket = accept(server_fd, (struct sockaddr *)&address, (socklist_t*)&addrlen);
    printf("Hráč sa pripojil!\n");

    // 6. Odoslanie správy
    send(new_socket, hello, strlen(hello), 0);
    
    close(new_socket);
    close(server_fd);
    return 0;
}