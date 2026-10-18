#!/usr/bin/env python3
"""Reject an inconsistent GEM lookup and retain evidence during M8 bringup.

This contains the observed NULL dereference; it is not a root-cause fix.
The next full-image trial must determine whether the inconsistency recurs.
"""
from pathlib import Path


def apply(kernel):
    path = Path(kernel) / 'drivers/gpu/drm/panfrost/panfrost_drv.c'
    text = path.read_text()
    if 'inconsistent GEM lookup' in text:
        return
    old = '\t\tbo = to_panfrost_bo(job->bos[i]);\n\t\tmapping = panfrost_gem_mapping_get(bo, priv);'
    new = '''\t\tif (unlikely(!job->bos[i])) {
\t\t\tdev_err_ratelimited(dev->dev,
\t\t\t\t"inconsistent GEM lookup: object %u/%u is NULL\\n",
\t\t\t\ti, job->bo_count);
\t\t\tret = -EIO;
\t\t\tbreak;
\t\t}
''' + old
    if text.count(old) != 1:
        raise ValueError('Panfrost lookup anchor changed')
    path.write_text(text.replace(old, new))
