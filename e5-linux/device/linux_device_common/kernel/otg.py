"""Connect the reviewed OTG supply and implement bounded sink preference."""
from pathlib import Path
import runpy


def apply(kernel):
    path = kernel / 'drivers/usb/typec/sc27xx_typec.c'
    text = path.read_text()
    # MUSB intentionally ignores the vendor's hyphenated dr-mode property.
    start = text.index('static int sc27xx_typec_controller_mode(')
    end = text.index('static int sc27xx_typec_probe(', start)
    text = text[:start] + text[start:end].replace('"dr-mode"', '"dr_mode"') + text[end:]
    if '#include "board-usb-role.h"' not in text:
        text = text.replace('static irqreturn_t sc27xx_typec_interrupt(',
            '#include "board-usb-role.h"\n\nstatic irqreturn_t sc27xx_typec_interrupt(', 1)
    if 'struct mutex role_lock;' not in text:
        text = text.replace('struct sc27xx_typec {',
            'struct sc27xx_typec {\n\tstruct mutex role_lock;\n'
            '\tstruct delayed_work role_work;\n\tint role_phase;', 1)
        text = text.replace('#include <linux/module.h>',
                            '#include <linux/module.h>\n#include <linux/mutex.h>', 1)
    if text.startswith('#include <linux/mutex.h>\n'):
        text = text.removeprefix('#include <linux/mutex.h>\n')
        text = text.replace('#include <linux/module.h>',
                            '#include <linux/module.h>\n#include <linux/mutex.h>', 1)
    # usb_charger.py regenerates the IRQ body on each preparation.
    start = text.index('static irqreturn_t sc27xx_typec_interrupt(')
    end = text.index('\nstatic int sc27xx_vbus_ok_bypass', start)
    body = text[start:end]
    if 'sc27xx_typec_prefer_sink(sc)' not in body:
        body = body.replace('\tsc->state = status & sc->var_data->state_mask;\n', '', 1)
        body = body.replace('\tif (event & SC27XX_ERR_IN_INT)',
            '\tmutex_lock(&sc->role_lock);\n'
            '\tsc->state = status & sc->var_data->state_mask;\n\n'
            '\tif (event & SC27XX_ERR_IN_INT)', 1)
        body = body.replace('if (event & (SC27XX_DETACH_INT | SC27XX_ERR_IN_INT)) {',
            'if (event & (SC27XX_DETACH_INT | SC27XX_ERR_IN_INT)) {\n'
            '\t\tbool had_partner = sc->partner_connected;', 1)
        body = body.replace('\t\tsc27xx_typec_connect_state = 0;',
            '\t\tsc27xx_typec_connect_state = 0;\n'
            '\t\tif (had_partner)\n\t\t\tsc27xx_typec_role_detach(sc);', 1)
        body = body.replace('\t\tret = sc27xx_typec_connect(sc, sc->state);',
            '\t\tif (sc27xx_typec_prefer_sink(sc))\n\t\t\tgoto unlock;\n'
            '\t\tsc27xx_typec_role_finish(sc);\n'
            '\t\tret = sc27xx_typec_connect(sc, sc->state);', 1)
        body = body.replace('\tdev_info(sc->dev, "typec state',
            'unlock:\n\tmutex_unlock(&sc->role_lock);\n'
            '\tdev_info(sc->dev, "typec state', 1)
        text = text[:start] + body + text[end:]
    if 'INIT_DELAYED_WORK(&sc->role_work' not in text:
        marker = '\tsc->edev = devm_extcon_dev_allocate('
        init = ('\tmutex_init(&sc->role_lock);\n'
                '\tINIT_DELAYED_WORK(&sc->role_work, sc27xx_typec_role_work);\n'
                '\tret = devm_add_action_or_reset(dev, sc27xx_typec_role_cleanup, sc);\n'
                '\tif (ret)\n\t\treturn ret;\n\n')
        assert text.count(marker) == 1
        text = text.replace(marker, init + marker, 1)
        start = text.index('static void sc27xx_typec_remove(')
        tail = text[start:].replace('\n\tsysfs_remove_groups(',
            '\n\tdisable_irq(sc->irq);\n\tsc27xx_typec_role_cleanup(sc);\n\n'
            '\tsysfs_remove_groups(', 1)
        text = text[:start] + tail
    path.write_text(text)
    (path.parent / 'board-usb-role.h').write_bytes(Path(__file__).with_name('usb-role.h').read_bytes())

    # Sysfs controls the CC policy, not a synthetic ID/VBUS event. The
    # controller must still detect a real accessory before enabling boost.
    if '#include "board-usb-policy.h"' not in text:
        text = text.replace('static struct attribute *sc27xx_typec_attrs[] = {',
            '#include "board-usb-policy.h"\n\nstatic struct attribute *sc27xx_typec_attrs[] = {\n'
            '\t&dev_attr_usb_role_policy.attr,\n\t&dev_attr_usb_role.attr,', 1)
        assert '#include "board-usb-policy.h"' in text
    if 'bool role_irq_requested;' not in text:
        text = text.replace('struct mutex role_lock;',
                            'struct mutex role_lock;\n\tbool role_irq_requested;', 1)
        text = text.replace('\n\t/* typec get vbus extcon notify */',
                            '\n\tsc->role_irq_requested = true;\n\n\t/* typec get vbus extcon notify */', 1)
        text = text.replace('error:\n\t/* a deferred probe',
                            'error:\n\tsc27xx_typec_role_cleanup(sc);\n\t/* a deferred probe', 1)
        text = text.replace('\tdisable_irq(sc->irq);\n\tsc27xx_typec_role_cleanup(sc);',
                            '\tsc27xx_typec_role_cleanup(sc);', 1)
    path.write_text(text)
    (path.parent / 'board-usb-policy.h').write_bytes(Path(__file__).with_name('usb-policy.h').read_bytes())

    path = kernel / 'drivers/usb/musb/musb_sprd.c'
    text = path.read_text()
    start = text.index('static int musb_sprd_otg_start_host(')
    end = text.index('\nstatic ', start + 10)
    body = text[start:end]
    # Without TCPM there is no PD driver to switch the boost regulator.
    body = body.replace('if (!glue->use_pdhub_c2c) {',
        'if (!glue->use_pdhub_c2c || !IS_ENABLED(CONFIG_SPRD_TYPEC_TCPM)) {')
    # A missing real supply must defer/fail, never use a dummy "enabled" rail.
    body = body.replace('devm_regulator_get(glue->dev, "vddvbus")',
                        'devm_regulator_get_optional(glue->dev, "vddvbus")')
    text = text[:start] + body + text[end:]
    path.write_text(text)

    runpy.run_path(str(Path(__file__).with_name('usb_host.py')))['apply'](kernel)
