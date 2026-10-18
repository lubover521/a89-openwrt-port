/* Run a four-instruction AArch64 guest and verify its MMIO exit.
 * No disk, network, firmware or host device is passed to the guest.
 * Build: aarch64-linux-gnu-gcc -O2 -static -Wall -Wextra -o kvm-smoke kvm-smoke.c
 */
#include <asm/kvm.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/kvm.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

static void fail(const char *operation)
{
    perror(operation);
    exit(1);
}

static void set_reg(int vcpu, uint64_t id, uint64_t value)
{
    struct kvm_one_reg reg = { .id = id, .addr = (uintptr_t)&value };
    if (ioctl(vcpu, KVM_SET_ONE_REG, &reg) < 0)
        fail("KVM_SET_ONE_REG");
}

#define CORE_REG(field) (KVM_REG_ARM64 | KVM_REG_SIZE_U64 | KVM_REG_ARM_CORE | KVM_REG_ARM_CORE_REG(field))

int main(void)
{
    alarm(5);
    int kvm = open("/dev/kvm", O_RDWR | O_CLOEXEC);
    if (kvm < 0) fail("open /dev/kvm");
    int api = ioctl(kvm, KVM_GET_API_VERSION, 0);
    if (api != 12) { fprintf(stderr, "Unsupported KVM API: %d\n", api); return 1; }
    int vm = ioctl(kvm, KVM_CREATE_VM, 0);
    if (vm < 0) fail("KVM_CREATE_VM");
    const size_t size = (size_t)sysconf(_SC_PAGESIZE);
    uint32_t *ram = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (ram == MAP_FAILED) fail("mmap guest RAM");
    /* mov x0,#0x1000; mov w1,#0x4b56; str w1,[x0]; wfi */
    const uint32_t guest[] = { 0xd2820000, 0x52896ac1, 0xb9000001, 0xd503207f };
    memcpy(ram, guest, sizeof(guest));
    struct kvm_userspace_memory_region region = {
        .slot = 0, .guest_phys_addr = 0x40000000, .memory_size = size, .userspace_addr = (uintptr_t)ram
    };
    if (ioctl(vm, KVM_SET_USER_MEMORY_REGION, &region) < 0) fail("KVM_SET_USER_MEMORY_REGION");
    struct kvm_vcpu_init init = {0};
    if (ioctl(vm, KVM_ARM_PREFERRED_TARGET, &init) < 0) fail("KVM_ARM_PREFERRED_TARGET");
    int vcpu = ioctl(vm, KVM_CREATE_VCPU, 0);
    if (vcpu < 0) fail("KVM_CREATE_VCPU");
    if (ioctl(vcpu, KVM_ARM_VCPU_INIT, &init) < 0) fail("KVM_ARM_VCPU_INIT");
    set_reg(vcpu, CORE_REG(regs.pc), 0x40000000);
    set_reg(vcpu, CORE_REG(regs.pstate), 0x3c5); /* EL1h, interrupts masked */
    int run_size = ioctl(kvm, KVM_GET_VCPU_MMAP_SIZE, 0);
    if (run_size <= 0) fail("KVM_GET_VCPU_MMAP_SIZE");
    struct kvm_run *run = mmap(NULL, run_size, PROT_READ | PROT_WRITE, MAP_SHARED, vcpu, 0);
    if (run == MAP_FAILED) fail("mmap kvm_run");
    if (ioctl(vcpu, KVM_RUN, 0) < 0) fail("KVM_RUN");
    uint32_t value = 0;
    memcpy(&value, run->mmio.data, sizeof(value));
    if (run->exit_reason != KVM_EXIT_MMIO || !run->mmio.is_write || run->mmio.len != 4 ||
        run->mmio.phys_addr != 0x1000 || value != 0x4b56) {
        fprintf(stderr, "Unexpected guest exit: reason=%u address=%llx value=%x\n",
                run->exit_reason, (unsigned long long)run->mmio.phys_addr, value);
        return 1;
    }
    puts("PASS: KVM API 12, ARM64 VM/vCPU creation, guest execution and verified MMIO exit");
    munmap(run, run_size); munmap(ram, size);
    close(vcpu); close(vm); close(kvm);
    return 0;
}
