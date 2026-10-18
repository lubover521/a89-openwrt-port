/* Load and run a private socket filter through the kernel test interface.
 * No socket, interface or cgroup is modified; the program is freed on exit.
 * aarch64-linux-gnu-gcc -O2 -static -Wall -Wextra -o bpf-smoke bpf-smoke.c
 */
#include <linux/bpf.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(void)
{
    struct bpf_insn code[] = {
        { .code = BPF_ALU64 | BPF_MOV | BPF_K, .dst_reg = BPF_REG_0, .imm = 42 },
        { .code = BPF_JMP | BPF_EXIT },
    };
    char log[16384] = {0};
    union bpf_attr attr = {
        .prog_type = BPF_PROG_TYPE_SOCKET_FILTER,
        .insn_cnt = sizeof(code) / sizeof(code[0]), .insns = (uintptr_t)code,
        .license = (uintptr_t)"GPL", .log_buf = (uintptr_t)log,
        .log_size = sizeof(log), .log_level = 1,
    };
    alarm(10);
    int fd = syscall(__NR_bpf, BPF_PROG_LOAD, &attr, sizeof(attr));
    if (fd < 0) { perror("BPF_PROG_LOAD"); fputs(log, stderr); return 1; }
    struct bpf_prog_info info = {0};
    memset(&attr, 0, sizeof(attr));
    attr.info.bpf_fd = fd;
    attr.info.info_len = sizeof(info);
    attr.info.info = (uintptr_t)&info;
    if (syscall(__NR_bpf, BPF_OBJ_GET_INFO_BY_FD, &attr, sizeof(attr)) < 0) {
        perror("BPF_OBJ_GET_INFO_BY_FD"); close(fd); return 1;
    }
    unsigned char packet[64] = {0}, result[64] = {0};
    memset(&attr, 0, sizeof(attr));
    attr.test.prog_fd = fd;
    attr.test.data_in = (uintptr_t)packet;
    attr.test.data_size_in = sizeof(packet);
    attr.test.data_out = (uintptr_t)result;
    attr.test.data_size_out = sizeof(result);
    attr.test.repeat = 1;
    int rc = syscall(__NR_bpf, BPF_PROG_TEST_RUN, &attr, sizeof(attr));
    close(fd);
    if (rc < 0) { perror("BPF_PROG_TEST_RUN"); return 1; }
    if (!info.jited_prog_len || attr.test.retval != 42) {
        fprintf(stderr, "Unexpected JIT length %u or result %u\n", info.jited_prog_len, attr.test.retval);
        return 1;
    }
    printf("PASS: eBPF verified, JIT %u bytes, test returned 42; program released\n", info.jited_prog_len);
    return 0;
}
