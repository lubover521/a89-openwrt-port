#!/usr/bin/env python3
"""Keep SPRD framebuffer DMA addresses within the DPU's 32-bit registers."""
import argparse
from pathlib import Path


def apply(kernel):
    base = Path(kernel) / 'drivers/unisoc_platform/sprd_disp'
    edits = [
        (base / 'sprd_drm.c',
         'dma_set_mask_and_coherent(&pdev->dev, ~0)',
         'dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32))'),
        (base / 'sprd_gem.c',
         'DRM_INFO("args->pitch:%u args->size:%llu vaddr:0x%px\\n",\n'
         '              args->pitch, args->size, sprd_gem->vaddr);',
         'DRM_INFO("args->pitch:%u args->size:%llu vaddr:0x%px dma:%pad\\n",\n'
         '              args->pitch, args->size, sprd_gem->vaddr, &sprd_gem->dma_addr);'),
    ]
    staged = []
    # Validate both files before writing either; reject changed source layouts
    # rather than leaving a half-applied adaptation in a reused build tree.
    for path, old, new in edits:
        text = path.read_text()
        if text.count(new) == 1 and old not in text:
            continue
        if text.count(old) != 1 or new in text:
            raise ValueError('Unexpected display source: ' + path.name)
        staged.append((path, text.replace(old, new)))
    for path, text in staged:
        path.write_text(text)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kernel', type=Path)
    apply(parser.parse_args().kernel)
