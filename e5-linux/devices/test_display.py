"""Regression coverage for framebuffer addressing and all display build entries."""
import argparse
import os
from pathlib import Path
import runpy
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

TOP = Path(__file__).resolve().parents[1]
ADAPTER = TOP / 'devices/common/display.py'
apply = runpy.run_path(str(ADAPTER))['apply']
KERNEL = None
DRM = 'drivers/unisoc_platform/sprd_disp/sprd_drm.c'
GEM = 'drivers/unisoc_platform/sprd_disp/sprd_gem.c'
OLD_MASK = 'dma_set_mask_and_coherent(&pdev->dev, ~0)'
NEW_MASK = 'dma_set_mask_and_coherent(&pdev->dev, DMA_BIT_MASK(32))'
OLD_LOG = ('DRM_INFO("args->pitch:%u args->size:%llu vaddr:0x%px\\n",\n'
           '              args->pitch, args->size, sprd_gem->vaddr);')
NEW_LOG = ('DRM_INFO("args->pitch:%u args->size:%llu vaddr:0x%px dma:%pad\\n",\n'
           '              args->pitch, args->size, sprd_gem->vaddr, &sprd_gem->dma_addr);')


class DisplayTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write(DRM, 'ret = '+OLD_MASK+';\n')
        self.write(GEM, OLD_LOG+'\n')
        self.write('arch/arm64/boot/dts/test.dts', 'memory and reserved memory stay unchanged\n')
        self.write('.config', 'CONFIG_CMDLINE="unchanged"\n')

    def write(self, name, text):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def contents(self):
        return {p.relative_to(self.root).as_posix():p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_only_display_changes_and_reapplying_does_not_rewrite_files(self):
        before = self.contents()
        apply(self.root)
        after = self.contents()
        self.assertEqual({p for p in after if after[p] != before[p]}, {DRM,GEM})
        self.assertIn(NEW_MASK, (self.root/DRM).read_text())
        self.assertIn(NEW_LOG, (self.root/GEM).read_text())
        for path in self.root.rglob('*'):
            if path.is_file(): os.utime(path, ns=(1000000000,1000000000))
        apply(self.root)
        self.assertEqual(self.contents(),after)
        self.assertTrue(all(p.stat().st_mtime_ns == 1000000000 for p in self.root.rglob('*') if p.is_file()))

    def test_cached_m8_or_partial_adaptation_converges(self):
        for mask, log in [(NEW_MASK,OLD_LOG),(OLD_MASK,NEW_LOG),(NEW_MASK,NEW_LOG)]:
            with self.subTest(mask=mask, log=log):
                self.write(DRM,'ret = '+mask+';\n');self.write(GEM,log+'\n')
                apply(self.root)
                self.assertIn(NEW_MASK,(self.root/DRM).read_text())
                self.assertIn(NEW_LOG,(self.root/GEM).read_text())

    def test_unknown_second_file_does_not_partially_modify_first(self):
        self.write(GEM,'unrecognized source\n')
        before = self.contents()
        with self.assertRaisesRegex(ValueError,'sprd_gem.c'): apply(self.root)
        self.assertEqual(self.contents(),before)

    def test_duplicate_old_or_fixed_mask_is_rejected_without_writes(self):
        for mask in [OLD_MASK+OLD_MASK, NEW_MASK+NEW_MASK, OLD_MASK+NEW_MASK]:
            with self.subTest(mask=mask):
                self.write(DRM,mask)
                before = self.contents()
                with self.assertRaisesRegex(ValueError,'sprd_drm.c'): apply(self.root)
                self.assertEqual(self.contents(),before)

    def test_each_device_entry_invokes_shared_adapter(self):
        class ReachedDisplay(Exception): pass
        for device in ['e5','t551m','m8']:
            with self.subTest(device=device):
                script = TOP/f'devices/{device}/prepare-kernel.py'
                module = runpy.run_path(str(script))
                def bridge(path):
                    self.assertEqual(Path(path).resolve(),ADAPTER.resolve())
                    def adapt(kernel):
                        apply(kernel)
                        raise ReachedDisplay()
                    return {'apply':adapt}
                def head(*args, **kwargs):
                    return '020b970e351e' if kwargs.get('text') else b'020b970e351e'
                with patch('runpy.run_path',side_effect=bridge), \
                     patch('subprocess.check_output',side_effect=head), \
                     patch.object(sys,'argv',[str(script),str(self.root)]):
                    with self.assertRaises(ReachedDisplay):
                        module['main']() if device == 't551m' else module['apply'](self.root)

    def test_legacy_m8_entry_uses_the_same_adapter(self):
        runpy.run_path(str(TOP/'devices/m8/display.py'))['apply'](self.root)
        self.assertIn(NEW_MASK,(self.root/DRM).read_text())

    def test_both_upstream_build_entries_patch_before_build(self):
        for name, command in [('build.sh','python3 /policy/display.py .'),
                              ('build-native.sh','python3 "$TOP/devices/common/display.py" .')]:
            with self.subTest(name=name):
                text = (TOP/'upstream'/name).read_text()
                self.assertEqual(text.count(command),1)
                self.assertLess(text.index(command),text.index('KV=$(make'))

    def test_prepared_kernel_sources(self):
        if KERNEL is None: self.skipTest('pass --kernel to verify prepared kernel sources')
        for name in [DRM,GEM]:
            target = self.root/name
            shutil.copyfile(KERNEL/name,target)
        apply(self.root)
        self.assertIn(NEW_MASK,(self.root/DRM).read_text())
        self.assertIn(NEW_LOG,(self.root/GEM).read_text())
        before = self.contents();apply(self.root)
        self.assertEqual(self.contents(),before)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel',type=Path)
    args, remaining = parser.parse_known_args()
    KERNEL = args.kernel
    unittest.main(argv=[sys.argv[0],*remaining])
