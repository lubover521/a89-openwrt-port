#!/usr/bin/env python3
"""Apply the pinned T551M board adaptations to linux-lts-e5."""
import argparse
import hashlib
from pathlib import Path
import re
import runpy
import subprocess
import shutil
import urllib.request

VENDOR_COMMIT = '63b8011056a5060e274fc1dcc9051c94d9a7bab8'
CHARGER_SHA256 = 'e7a99ea539a66a5dfcf2b25f8a275c8eb0567a675ed029fdb0b087133822dd51'
KERNEL_COMMIT = '020b970e351e'


_helpers = runpy.run_path(str(Path(__file__).resolve().parents[1] / "linux_device_common/kernel/charger.py"))
replace_function = _helpers["replace_function"]
board_charger = _helpers["board_charger"]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('kernel', type=Path)
    args = ap.parse_args()
    k = args.kernel
    head = subprocess.check_output(['git', '-C', str(k), 'rev-parse', 'HEAD']).decode().strip()
    if not head.startswith(KERNEL_COMMIT):
        raise SystemExit('Expected linux-lts-e5 commit ' + KERNEL_COMMIT)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/display.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/power.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/charger-capabilities.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/emmc.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/sd-power.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/eic.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/thermal.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/sipa.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/fuel-gauge.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/wifi-sae.py'))['apply'](k)
    runpy.run_path(str(Path(__file__).resolve().parents[1] / 'linux_device_common/kernel/wifi-stations.py'))['apply'](k)
    url = ('https://raw.githubusercontent.com/Enceka/kernel_sprd_ums9158/'
           + VENDOR_COMMIT + '/drivers/power/supply/bq2560x-charger.c')
    source = urllib.request.urlopen(url, timeout=60).read()
    if hashlib.sha256(source).hexdigest() != CHARGER_SHA256:
        raise SystemExit('Charger source checksum mismatch')
    text = source.decode().replace('GPL-2.0:', 'GPL-2.0-only')
    text = text.replace('#include <linux/gpio/consumer.h>',
                        '#include <linux/gpio/consumer.h>\n#include <linux/gpio.h>\n#include <linux/extcon.h>')
    text = text.replace('static int bq2560x_charger_probe(struct i2c_client *client,\n\t\tconst struct i2c_device_id *id)',
                        'static int bq2560x_charger_probe(struct i2c_client *client)')
    text = text.replace('static int bq2560x_charger_remove(struct i2c_client *client)',
                        'static void bq2560x_charger_remove(struct i2c_client *client)')
    text = text.replace('\tmutex_destroy(&info->lock);\n\n\treturn 0;\n}',
                        '\tmutex_destroy(&info->lock);\n}')
    text = text.replace('charger_cfg.of_node = dev->of_node;',
                        'charger_cfg.fwnode = dev_fwnode(dev);')
    text = text.replace('GPIOF_DIR_IN', 'GPIOF_IN')
    text = board_charger(text)
    (k / 'drivers/power/supply/bq2560x-charger.c').write_text(text)
    additions = {
        'drivers/power/supply/Kconfig': '\nconfig CHARGER_BQ2560X_SPRD\n\ttristate "Unisoc BQ2560x charger (T551M)"\n\tdepends on I2C && CHARGER_MANAGER && GPIOLIB\n',
        'drivers/power/supply/Makefile': '\nobj-$(CONFIG_CHARGER_BQ2560X_SPRD) += bq2560x-charger.o\n',
    }
    for name, addition in additions.items():
        path = k / name
        text = path.read_text()
        if 'CHARGER_BQ2560X_SPRD' not in text:
            path.write_text(text + addition)
    # E5's compiled-in touch firmware is board-specific. Never burn it into a
    # T551M controller on probe; use the factory firmware already on the IC.
    path = k / 'drivers/input/touchscreen/tlsc6x/tlsc6x_main.c'
    text = path.read_text().replace('\ttlsc6x_do_update_ifneed();',
                                   '\t/* T551M: preserve factory touch firmware. */')
    path.write_text(text)
    path = k / 'sound/soc/sprd/unisoc/machine/sprd-asoc-card-utils-hook.c'
    text = path.read_text()
    text = re.sub(r'ret = (aw87xxx_set_profile\([^;]*);',
                  r'ret = IS_REACHABLE(CONFIG_SND_SOC_UNISOC_PA_AW87XXX) ? \1 : 0;', text)
    path.write_text(text)
    # Android DT requests the vendor PD extcon, which is not built in this port.
    # Fall back to the already-working USB PHY BC1.2 notifications.
    path = k / 'drivers/power/supply/sprd_vchg_detect.c'
    text = path.read_text()
    marker = '\tinfo->use_typec_extcon = device_property_read_bool(info->dev, "use-typec-extcon");'
    if 'T551M BC1.2 fallback' not in text:
        text = text.replace(marker, marker + '\n\t/* T551M BC1.2 fallback without the vendor PD stack. */\n\tif (!IS_ENABLED(CONFIG_SC27XX_PD))\n\t\tinfo->use_typec_extcon = false;')
    path.write_text(text)
    runpy.run_path(str((Path(__file__).resolve().parent / '../linux_device_common/kernel/usb_charger.py')))['apply'](k, replace_function, charge_profile=Path(__file__).with_name('charge-profile.h'))
    runpy.run_path(str((Path(__file__).resolve().parent / '../linux_device_common/kernel/otg.py')))['apply'](k)
    runpy.run_path(str((Path(__file__).resolve().parent / '../linux_device_common/kernel/cpufreq.py')))['apply'](k)
    runpy.run_path(str((Path(__file__).resolve().parent / '../linux_device_common/kernel/wifi.py')))['apply'](k)
    # mu300-linux f0323bf: keep firmware debug traffic off across WCN power
    # cycles. This board uses the integrated WCN stack, not MU300's PCIe path;
    # its resume does not force armlog on, so only the shared default applies.
    path = k / 'drivers/unisoc_platform/sprdwcn/platform/sysfs.c'
    text = path.read_text()
    if 'Default firmware debug log off' not in text:
        old = '\t\tsysfs_info.armlog_status = 1;\n#endif'
        if text.count(old) != 1:
            raise SystemExit('Unexpected WCN firmware log default')
        text = text.replace(old, old + '\n\t/* Default firmware debug log off; sysfs may enable it explicitly. */\n\tsysfs_info.armlog_status = 0;')
        path.write_text(text)
    # The factory DT uses "qogirn6l" and a GPIO pulse backlight, not PWM.
    disp = k / 'drivers/unisoc_platform/sprd_disp'
    shutil.copy2(Path(__file__).with_name('t551m-backlight.h'), disp / 't551m-backlight.h')
    path = disp / 'sprd_bl.h'
    text = path.read_text()
    if 'step_gpio' not in text:
        text = text.replace('struct sprd_backlight {', 'struct sprd_backlight {\n\tstruct gpio_desc *step_gpio;\n\tint step_level;')
    path.write_text(text)
    path = disp / 'sprd_bl.c'
    text = path.read_text()
    if '#include "t551m-backlight.h"' not in text:
        text = text.replace('int sprd_cabc_backlight_update', '#include "t551m-backlight.h"\n\nint sprd_cabc_backlight_update', 1)
        text = text.replace('\tmutex_lock(&bd->update_lock);', '\tif (bl->step_gpio)\n\t\treturn 0;\n\n\tmutex_lock(&bd->update_lock);', 1)
        text = text.replace('\tsprd_backlight_normalize_map(bd, &level);', '\tif (bl->step_gpio)\n\t\treturn t551m_backlight_update(bd);\n\n\tsprd_backlight_normalize_map(bd, &level);', 1)
        start = text.index('\tbl->pwm = devm_pwm_get')
        end = text.index('\tbd = devm_backlight_device_register', start)
        pwm = text[start:end]
        text = text[:start] + '''
\tif (of_device_is_compatible(pdev->dev.of_node, "sprd,qogirn6l-backlight")) {
\t\tbl->step_gpio = devm_gpiod_get(&pdev->dev, "lcm_backlight", GPIOD_OUT_LOW);
\t\tif (IS_ERR(bl->step_gpio)) return PTR_ERR(bl->step_gpio);
\t\tif (gpiod_cansleep(bl->step_gpio)) return -EINVAL;
\t\tbl->step_level = -1;
\t} else {
''' + pwm + '\t}\n' + text[end:]
        text = text.replace('\t{ .compatible = "sprd,sharkl3-backlight" },', '\t{ .compatible = "sprd,qogirn6l-backlight" },\n\t{ .compatible = "sprd,sharkl3-backlight" },', 1)
    path.write_text(text)


if __name__ == '__main__':
    main()
