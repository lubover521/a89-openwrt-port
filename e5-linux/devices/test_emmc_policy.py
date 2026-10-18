#!/usr/bin/env python3
"""Fresh pinned kernel, repeated application and migration from the V50 policy."""
from pathlib import Path
import runpy,subprocess,tempfile,sys,unittest
TOP=Path(__file__).resolve().parents[1]
apply=runpy.run_path(str(TOP/'devices/common/emmc.py'))['apply']
SOURCE=Path(sys.argv[1]);sys.argv=sys.argv[:1]
FILES=['drivers/mmc/host/sdhci-sprd.c','drivers/mmc/core/mmc.c','drivers/mmc/core/block.c','include/linux/mmc/host.h']

class Policy(unittest.TestCase):
    def fresh(self,root):
        for f in FILES:
            p=root/f;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_bytes(subprocess.check_output(['git','-C',str(SOURCE),'show','HEAD:'+f]))
    def test_fresh_idempotent_and_scope(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fresh(root);apply(root)
            before=[(root/f).read_bytes() for f in FILES];apply(root)
            self.assertEqual(before,[(root/f).read_bytes() for f in FILES])
            host=(root/FILES[0]).read_text();core=(root/FILES[1]).read_text()
            self.assertIn('!mmc_card_is_removable(host->mmc)',host)
            self.assertIn('MMC_CAP2_NO_MMC',host);self.assertIn('"sdio_wlan"',host);self.assertIn('"sdio_sd"',host)
            self.assertIn('if (clk > 400000) {',host)
            self.assertNotIn('runtime_keep_awake',host)
            self.assertNotIn('pm_runtime_forbid(&pdev->dev);',host)
            self.assertNotIn('pm_runtime_allow(&pdev->dev);',host)
            self.assertNotIn('~MMC_CAP_AGGRESSIVE_PM',host)
            self.assertIn('mmc_hsq_suspend(host->mmc);',host)
            self.assertIn('sdhci_runtime_resume_host(host, 1);',host)
            section=core[core.index('static int _mmc_suspend'):core.index('static void mmc_remove')]
            self.assertNotIn('Shared eMMC policy',section)
            self.assertIn('mmc_sleep(host)',section)
            system=core[core.index('static int mmc_suspend'):core.index('static int _mmc_resume')]
            self.assertIn('system-only power retention',system)
            self.assertIn('mmc_card_suspended(host->card) ? 0 : _mmc_flush_cache(host)',system)
            runtime=core[core.index('static int mmc_runtime_suspend'):core.index('static int mmc_runtime_resume')]
            self.assertIn('_mmc_suspend(host, MMC_POWEROFF_SUSPEND)',runtime)
            self.assertIn('_mmc_suspend(host, MMC_POWEROFF_SHUTDOWN)',core)
            self.assertIn('!(card->host->caps2 & MMC_CAP2_NO_REL_WR)',(root/FILES[2]).read_text())
    def test_v50_cached_migration(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fresh(root);p=root/FILES[0];s=p.read_text()
            anchor='\tsdhci_sprd_phy_param_parse(sprd_host, pdev->dev.of_node);'
            s=s.replace(anchor,'''\tif (!mmc_card_is_removable(host->mmc)) {
\t\tstruct device_node *aw = of_find_compatible_node(NULL, NULL, "awinic,aw9523b_led");
\t\tif (aw) { of_node_put(aw); }
\t}
'''+anchor,1);p.write_text(s)
            apply(root);self.assertNotIn('awinic,aw9523b_led',p.read_text());self.assertIn('Shared eMMC policy',p.read_text())
    def test_previous_shared_keep_awake_removed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fresh(root);p=root/FILES[0];s=p.read_text()
            s=s.replace('struct sdhci_sprd_host {','struct sdhci_sprd_host {\n\tbool runtime_keep_awake;',1)
            anchor='\tsdhci_sprd_phy_param_parse(sprd_host, pdev->dev.of_node);'
            s=s.replace(anchor,'''\t/* Shared eMMC policy: keep the non-removable memory controller awake.
\t * Exclude removable TF and non-memory SDIO hosts; no model-name gate. */
\tsprd_host->runtime_keep_awake = true;
\thost->mmc->caps &= ~MMC_CAP_AGGRESSIVE_PM;
'''+anchor,1)
            s=s.replace('\tpm_runtime_enable(&pdev->dev);','''\tpm_runtime_enable(&pdev->dev);
\tif (sprd_host->runtime_keep_awake) {
\t\tpm_runtime_forbid(&pdev->dev);
\t\tdev_notice(&pdev->dev, "eMMC: automatic sleep disabled\\n");
\t}''',1)
            for anchor in ['pm_runtime_disable:\n','\tsdhci_remove_host(host, 0);\n']:
                s=s.replace(anchor,anchor+'\tif (sprd_host->runtime_keep_awake)\n\t\tpm_runtime_allow(&pdev->dev);\n',1)
            s=s.replace('\t/* Enable CLK_AUTO when the clock is greater than 400K. */\n\tif (clk > 400000) {',
                        '\t/* Shared eMMC policy: no autonomous inner/outer clock gating. */\n\tif (clk > 400000 && !sprd_host->runtime_keep_awake) {',1)
            p.write_text(s);apply(root)
            self.assertNotIn('runtime_keep_awake',p.read_text());self.assertNotIn('pm_runtime_forbid',p.read_text())
            before=p.read_bytes();apply(root);self.assertEqual(before,p.read_bytes())

unittest.main()
