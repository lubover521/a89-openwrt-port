#!/usr/bin/env python3
"""PR #190: valid hot sensors must survive another sensor's read failure."""
import argparse
from pathlib import Path


def adapt(text):
    marker = 'PR #190: retain valid thermal readings'
    if marker in text:
        return text
    # M8 installs its own replacement driver, which implements the same rule.
    if 'No valid sensor: do not fabricate a cold temperature.' in text:
        return text
    start = text.index('static int virtual_thm_get_temp(')
    end = text.index('\nstatic void virtual_thm_unregister', start)
    original = text[start:end]
    body = original
    replacements = {
        '\t\tif (!tz || IS_ERR(tz))\n\t\t\treturn -EINVAL;':
        '\t\tif (!tz || IS_ERR(tz))\n\t\t\tcontinue;',
        '\t\t\tdev_err(dev, "fail to get temp\\n");\n\t\t\treturn ret;':
        '\t\t\tdev_err_ratelimited(dev, "fail to get temp\\n");\n\t\t\tcontinue;',
        '\t*temp = max_temp;':
        '\t/* ' + marker + '. */\n\tif (max_temp == INT_MIN)\n\t\treturn -EIO;\n\t*temp = max_temp;',
        '\treturn ret;': '\treturn 0;',
    }
    for old, new in replacements.items():
        if old not in body:
            raise ValueError('Unexpected stock virtual thermal callback: ' + old)
        body = body.replace(old, new)
    return text[:start] + body + text[end:]


def apply(kernel):
    path = Path(kernel) / 'drivers/unisoc_platform/thermal/sprd_soc_thm.c'
    old = path.read_text()
    new = adapt(old)
    if new != old:
        path.write_text(new)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    apply(parser.parse_args().kernel)
