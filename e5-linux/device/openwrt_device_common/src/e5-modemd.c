/*
 * e5-modemd: the CP log daemon's part in a CP reset, for plain Linux.
 *
 * modem_control (the vendor chroot) serves its clients on the abstract unix
 * socket "modemd": it sends them the modem's state as text ("Modem Assert:
 * ...", "Modem Reset", "Modem Alive"), and after an assert it waits for
 * "SLOGMODEM DUMP COMPLETE" from the CP log daemon before it resets the CP.
 * Android's log daemon sends that once it has saved the dump; nothing does on
 * Linux, so every assert cost modem_control's full 300 s timeout
 * (docs/FINDINGS.md 30).  This client answers every assert at once -- no dump
 * is kept -- and logs the state messages to stdout.
 *
 * The vendor RIL also tells modem_control when the CP's AT server stops
 * answering, with "Modem Blocked"; modem_control passes that on to its
 * clients and, like after an assert, resets the CP once the dump is done.  An AT
 * server that hangs without an assert is otherwise there until a reboot.
 *
 *   e5-modemd            connect (retrying), then serve until the socket closes
 *   e5-modemd blocked    tell modem_control the AT server is blocked, and exit
 */
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <unistd.h>

#ifndef SOCKET_NAME
#define SOCKET_NAME "modemd"
#endif
#define DUMP_COMPLETE "SLOGMODEM DUMP COMPLETE"

/* Notifications are stream data: read boundaries are not message boundaries.
 * Match state tokens incrementally, accepting vendor messages with or without
 * a trailing NUL. Keep only a bounded suffix, never an entire CP dump/reason.
 */
struct state_reader {
	char tail[64];
	size_t used;
};

static int send_all(int fd, const char *message, size_t size)
{
	while (size) {
		ssize_t n = send(fd, message, size, MSG_NOSIGNAL);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			return -1;
		message += n;
		size -= n;
	}
	return 0;
}

static int read_states(struct state_reader *reader, int fd,
		       const char *data, size_t size)
{
	static const struct { const char *name; int dump; } events[] = {
		{"Modem Assert", 1}, {"Modem State: Assert", 1},
		{"Modem Blocked", 1}, {"Modem State: Blocked", 1},
		{"Modem Reset", 0}, {"Modem Alive", 0},
		{"Modem State: Reset", 0}, {"Modem State: Alive", 0}
	};
	for (size_t i = 0; i < size; i++) {
		if (!data[i]) {
			reader->used = 0;
			continue;
		}
		if (reader->used == sizeof(reader->tail)) {
			memmove(reader->tail, reader->tail + 1, --reader->used);
		}
		reader->tail[reader->used++] = data[i];
		for (size_t e = 0; e < sizeof(events) / sizeof(events[0]); e++) {
			size_t len = strlen(events[e].name);
			if (reader->used < len ||
			    memcmp(reader->tail + reader->used - len, events[e].name, len))
				continue;
			printf("e5-modemd: %s\n", events[e].name);
			if (events[e].dump) {
				if (send_all(fd, DUMP_COMPLETE, sizeof(DUMP_COMPLETE)) < 0) {
					fprintf(stderr, "e5-modemd: dump acknowledgement: %s\n", strerror(errno));
					return -1;
				}
				printf("e5-modemd: sent \"%s\" (CP dump skipped)\n", DUMP_COMPLETE);
			}
		}
	}
	return 0;
}

static int connect_modemd(void)
{
	struct sockaddr_un addr;
	socklen_t len;
	int fd;

	fd = socket(AF_UNIX, SOCK_STREAM, 0);
	if (fd < 0)
		return -1;
	memset(&addr, 0, sizeof(addr));
	addr.sun_family = AF_UNIX;
	/* abstract namespace: a leading NUL, no terminator (bionic's socket_local_client) */
	memcpy(addr.sun_path + 1, SOCKET_NAME, strlen(SOCKET_NAME));
	len = offsetof(struct sockaddr_un, sun_path) + 1 + strlen(SOCKET_NAME);
	if (connect(fd, (struct sockaddr *)&addr, len) < 0) {
		close(fd);
		return -1;
	}
	return fd;
}

#define MODEM_BLOCKED "Modem Blocked"

int main(int argc, char **argv)
{
	char buf[1024];
	int fd, n, waited = 0;
	struct state_reader reader = {0};

	setvbuf(stdout, NULL, _IOLBF, 0);
	if (argc > 1) {
		if (argc != 2 || strcmp(argv[1], "blocked")) {
			fprintf(stderr, "usage: e5-modemd [blocked]\n");
			return 2;
		}
		fd = connect_modemd();
		if (fd < 0 || send_all(fd, MODEM_BLOCKED, sizeof(MODEM_BLOCKED)) < 0) {
			fprintf(stderr, "e5-modemd: modemd: %s\n", strerror(errno));
			if (fd >= 0)
				close(fd);
			return 1;
		}
		printf("e5-modemd: sent \"%s\"\n", MODEM_BLOCKED);
		close(fd);
		return 0;
	}
	while ((fd = connect_modemd()) < 0) {
		if (!waited++)
			printf("e5-modemd: waiting for modem_control's socket\n");
		sleep(1);
	}
	printf("e5-modemd: connected to modemd\n");

	for (;;) {
		n = read(fd, buf, sizeof(buf));
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			break;
		if (read_states(&reader, fd, buf, (size_t)n) < 0)
			break;
	}
	printf("e5-modemd: modemd closed the socket\n");
	close(fd);
	/* procd restarts it: modem_control may have been restarted */
	return 1;
}
