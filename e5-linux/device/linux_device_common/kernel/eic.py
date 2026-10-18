#!/usr/bin/env python3
"""MU300 PR #184: expose all Unisoc EIC banks so TF detect can use its IRQ."""
import argparse
from pathlib import Path
import re


def apply(kernel):
    path = Path(kernel) / 'drivers/gpio/gpio-eic-sprd.c'
    text = path.read_text()
    match = re.search(r'(#define\s+SPRD_EIC_MAX_BANK\s+)(\d+)', text)
    if not match or int(match[2]) not in (3, 8):
        raise ValueError('Unexpected Unisoc EIC bank limit')
    if int(match[2]) == 3:
        path.write_text(text[:match.start(2)] + '8' + text[match.end(2):])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    apply(parser.parse_args().kernel)
