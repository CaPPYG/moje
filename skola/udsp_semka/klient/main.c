#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <arpa/inet.h>

int main() {
    int sock = 0;
    struct sockaddr_in serv_addr;
    char buffer[1024] = {0};

    // 1. Vytvorenie socketu
    sock = socket(AF_INET, SOCK_STREAM, 0);

    serv_addr.sin_family = AF_INET;
    serv_addr.sin_port = htons(12345);

    // Prevod IP adresy (127.0.0.1 je tvoj vlastný PC)
    inet_pton(AF_INET, "127.0.0.1", &serv_addr.sin_addr);

    // 2. Pripojenie k serveru
    if (connect(sock, (struct sockaddr *)&serv_addr, sizeof(serv_addr)) < 0) {
        printf("Pripojenie zlyhalo!\n");
        return -1;
    }

    // 3. Prijatie správy
    read(sock, buffer, 1024);
    printf("Správa od servera: %s\n", buffer);

    close(sock);
    return 0;
}