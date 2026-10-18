/* Native client for the persistent T551M AT owners. Never opens a modem port.
 * Request: JSON + newline; response: transport status ('0\n' or '1\n') + UTF-8,
 * framed by EOF. The daemon buffers through the final AT result before reply.
 */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/un.h>
#include <time.h>
#include <unistd.h>

#ifndef AT_SOCKET_PREFIX
#define AT_SOCKET_PREFIX "/run/t551m-at"
#endif
#define RESPONSE_MAX 262144

static int fail(const char *message)
{
    fprintf(stderr, "t551m-at: %s\n", message);
    return 1;
}

static int number(const char *text)
{
    char *end;
    long n;
    if (!text || !*text) return -1;
    errno = 0;
    n = strtol(text, &end, 10);
    return errno || *end || n < 0 || n > 1000 ? -1 : (int)n;
}

static int final_response(char *body)
{
    size_t length = strlen(body);
    char *last;
    while (length && (body[length - 1] == '\r' || body[length - 1] == '\n')) length--;
    if (!length) return 0;
    /* Temporarily terminate the last nonempty line; restore output verbatim. */
    char saved = body[length];
    body[length] = 0;
    last = strrchr(body, '\n');
    last = last ? last + 1 : body;
    int valid = !strcmp(last, "OK") || !strcmp(last, "ERROR") ||
        !strcmp(last, "NO CARRIER") || !strcmp(last, "BUSY") || !strcmp(last, "NO ANSWER") ||
        !strcmp(last, "CONNECT") || !strncmp(last, "CONNECT ", 8) ||
        !strcmp(last, "+CME ERROR") || !strcmp(last, "+CMS ERROR") ||
        !strncmp(last, "+CME ERROR:", 11) || !strncmp(last, "+CMS ERROR:", 11);
    body[length] = saved;
    return valid;
}

int main(int argc, char **argv)
{
    int timeout = 8, channel = 2, fd;
    const char *command = NULL, *env = getenv("T551M_AT_CHANNEL");
    char escaped[2049], request[2304];
    struct sockaddr_un address = { .sun_family = AF_UNIX };
    struct timespec now;
    size_t used = 0;
    if (env) channel = number(env);
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--help")) {
            puts("usage: t551m-at [--channel 2|6|7] [-t 1..60] AT+COMMAND");
            return 0;
        }
        if (!strcmp(argv[i], "-t") && i + 1 < argc) timeout = number(argv[++i]);
        else if (!strcmp(argv[i], "--channel") && i + 1 < argc) channel = number(argv[++i]);
        else if (!command) command = argv[i];
        else return fail("Unexpected argument");
    }
    if (channel != 2 && channel != 6 && channel != 7) return fail("Only channels 2, 6 and 7 are allowed");
    if (timeout < 1 || timeout > 60) return fail("Timeout must be 1..60 seconds");
    if (!command || strlen(command) < 2 || strlen(command) > 1024 ||
        (command[0] != 'A' && command[0] != 'a') || (command[1] != 'T' && command[1] != 't'))
        return fail("Expected one AT command");
    for (const unsigned char *p = (const unsigned char *)command; *p; p++) {
        if (*p < 32 || *p > 126) return fail("Control/non-ASCII characters are not allowed");
        if (*p == '"' || *p == '\\') escaped[used++] = '\\';
        escaped[used++] = (char)*p;
    }
    escaped[used] = 0;
    int count = snprintf(address.sun_path, sizeof(address.sun_path), AT_SOCKET_PREFIX "%d/cmd.sock", channel);
    if (count < 0 || (size_t)count >= sizeof(address.sun_path)) return fail("Socket path too long");
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return fail(strerror(errno));
    count = snprintf(request, sizeof(request),
        "{\"command\":\"%s\",\"timeout\":%d,\"deadline\":%.6f,\"plain\":true}\n",
        escaped, timeout, now.tv_sec + now.tv_nsec / 1e9 + 12);
    if (count < 0 || (size_t)count >= sizeof(request)) return fail("Request too large");
    fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (fd < 0) return fail(strerror(errno));
    struct timeval bound = { .tv_sec = timeout + 13, .tv_usec = 0 };
    if (setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &bound, sizeof(bound)) ||
        setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &bound, sizeof(bound))) {
        close(fd); return fail(strerror(errno));
    }
    alarm((unsigned)timeout + 15); /* includes connect/queue/send/read, even on a broken peer */
    if (connect(fd, (struct sockaddr *)&address, sizeof(address))) {
        close(fd); return fail(strerror(errno));
    }
    for (size_t sent = 0; sent < (size_t)count;) {
        ssize_t n = send(fd, request + sent, (size_t)count - sent, MSG_NOSIGNAL);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { close(fd); return fail("Failed to submit request; not retried"); }
        sent += (size_t)n;
    }
    char *response = malloc(RESPONSE_MAX + 1);
    if (!response) { close(fd); return fail("Out of memory"); }
    used = 0;
    for (;;) {
        ssize_t n = recv(fd, response + used, RESPONSE_MAX - used, 0);
        if (n < 0 && errno == EINTR) continue;
        if (n < 0) { close(fd); free(response); return fail("No complete response from daemon"); }
        if (!n) break;
        used += (size_t)n;
        if (used == RESPONSE_MAX) { close(fd); free(response); return fail("Response too large"); }
    }
    close(fd);
    alarm(0);
    response[used] = 0;
    int result;
    if (used < 2 || response[1] != '\n' || memchr(response, 0, used))
        result = fail("Invalid daemon response");
    else if (response[0] == '1') result = fail(response + 2);
    else if (response[0] != '0' || !final_response(response + 2))
        result = fail("No final AT response; not retried");
    else result = fwrite(response + 2, 1, used - 2, stdout) == used - 2 ? 0 : 1;
    free(response);
    return result;
}
