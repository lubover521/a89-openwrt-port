"""Install the Unisoc firmware CPUFreq driver and boot voltage-offset ABI."""
from pathlib import Path


def apply(kernel):
    source = Path(__file__).with_name('cpufreq')
    for name, target in {
        'sprd-cpufreq-v2-driver.c': 'drivers/cpufreq/sprd-cpufreq-v2-driver.c',
        'sprd-cpufreq-v2.h': 'drivers/cpufreq/sprd-cpufreq-v2.h',
        'sprd_sip_svc.c': 'drivers/firmware/sprd_sip_svc.c',
        'sprd_sip_svc.h': 'include/linux/sprd_sip_svc.h',
    }.items():
        (kernel / target).write_bytes((source / name).read_bytes().replace(b'\r\n', b'\n'))
    additions = {
        'drivers/firmware/Makefile': 'obj-$(CONFIG_SPRD_SIP_SVC) += sprd_sip_svc.o\n',
        'drivers/firmware/Kconfig': 'config SPRD_SIP_SVC\n\tbool "Unisoc SIP firmware services"\n\tdepends on ARM64 && HAVE_ARM_SMCCC\n',
        'drivers/cpufreq/Makefile': 'obj-$(CONFIG_ARM_SPRD_CPUFREQ_V2) += sprd-cpufreq-v2-driver.o\n',
        'drivers/cpufreq/Kconfig.arm': 'config ARM_SPRD_CPUFREQ_V2\n\ttristate "Unisoc firmware CPUFreq v2"\n\tdepends on SPRD_SIP_SVC && NVMEM\n\tselect PM_OPP\n',
    }
    for target, addition in additions.items():
        path = kernel / target
        text = path.read_text()
        text = text.replace('config ARM_SPRD_CPUFREQ_V2\n\tbool ', 'config ARM_SPRD_CPUFREQ_V2\n\ttristate ')
        if addition.splitlines()[0] not in text:
            text += '\n' + addition
        path.write_text(text)


if __name__ == '__main__':
    import sys
    apply(Path(sys.argv[1]))
