// SPDX-License-Identifier: GPL-2.0-only
/* Adapt the legacy UMS9620 audio-access binding in RAM, never on flash.
 * The newer audio drivers use runtime-PM/genpd instead of agdsp_access().
 * Register accesses without those consumer links can raise a fatal SError.
 */
#include <linux/init.h>
#include <linux/of.h>
#include <linux/printk.h>

static struct of_changeset audio_changes;

static const char * const consumers[] = {
	"unisoc,qogirn6pro-vbc", "unisoc,pdm-ums9620", "unisoc,tdm",
	"unisoc,audio-codec-dig-agcp", "sprd,voice_trigger_irq",
	"unisoc,ump9620-audio-codec", "unisoc,qogirn6pro-pcm-platform",
	"unisoc,qogirn6pro-compress-platform", "unisoc,fe-dai",
};

static int __init sprd_legacy_audio_dt(void)
{
	struct device_node *provider, *np;
	u32 phandle = 0;
	int ret, i, count = 0;

	if (!of_machine_is_compatible("sprd,ums9620"))
		return 0;
	provider = of_find_compatible_node(NULL, NULL, "unisoc,agdsp-access");
	if (!provider)
		return 0;
	if (of_property_present(provider, "#power-domain-cells")) {
		of_node_put(provider);
		return 0;
	}
	for_each_of_allnodes(np)
		phandle = max(phandle, np->phandle);
	if (phandle >= 0xfffffffe) {
		ret = -EINVAL;
		goto out;
	}
	phandle = provider->phandle ?: phandle + 1;
	of_changeset_init(&audio_changes);
	ret = of_changeset_update_prop_string(&audio_changes, provider,
					    "compatible", "sprd,agdsp-pd");
	if (ret)
		goto fail;
	ret = of_changeset_add_prop_u32(&audio_changes, provider,
				       "#power-domain-cells", 0);
	if (ret)
		goto fail;
	if (!provider->phandle) {
		ret = of_changeset_add_prop_u32(&audio_changes, provider,
					       "phandle", phandle);
		if (ret)
			goto fail;
	}
	for (i = 0; i < ARRAY_SIZE(consumers); i++) {
		for_each_compatible_node(np, NULL, consumers[i]) {
			if (of_property_present(np, "power-domains"))
				continue;
			ret = of_changeset_add_prop_u32(&audio_changes, np,
						       "power-domains", phandle);
			if (ret) {
				of_node_put(np);
				goto fail;
			}
			count++;
		}
	}
	ret = of_changeset_apply(&audio_changes);
	if (ret)
		goto fail;
	/* Existing unflattened nodes cache their phandle in this field. */
	provider->phandle = phandle;
	pr_info("sprd-audio: adapted legacy power domain and %d consumers\n", count);
	goto out;
fail:
	of_changeset_destroy(&audio_changes);
	pr_err("sprd-audio: legacy power-domain binding failed: %d\n", ret);
out:
	of_node_put(provider);
	return ret;
}
/* Before platform population, providers and audio modules can be probed. */
postcore_initcall(sprd_legacy_audio_dt);
