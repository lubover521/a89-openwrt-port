#!/usr/bin/env python3
"""Keep the native phone card usable when DisplayPort support is absent."""
from pathlib import Path


def apply(kernel):
    plumbing = Path(kernel) / 'drivers/unisoc_platform/sprd_audio'
    (plumbing / 'audio-legacy-dt.c').write_bytes(
        (Path(__file__).resolve().parent / 'port/audio-legacy-dt.c').read_bytes())
    makefile = plumbing / 'Makefile'
    if 'audio-legacy-dt.o' not in makefile.read_text():
        makefile.write_text(makefile.read_text() + '\nobj-y += audio-legacy-dt.o\n')
    path = Path(kernel) / 'sound/soc/sprd/unisoc/machine/sprd-asoc-card-utils.c'
    text = path.read_text()
    if 'sprd_card_link_enabled' in text:
        return
    anchor = 'static int asoc_sprd_card_parse_of('
    start = text.index(anchor)
    text = text[:start] + '''/* The qogirn6pro vendor tree includes the optional DP audio pair.
 * Its AGCP IIS provider is not part of the phone audio build. Do not let
 * those links prevent the independent phone sound card from registering.
 */
static bool sprd_card_link_enabled(struct device_node *node)
{
\tconst char *name;

\tif (!of_device_is_available(node))
\t\treturn false;
\tif (IS_ENABLED(CONFIG_DRM_SPRD_DPU1) ||
\t    !of_machine_is_compatible("sprd,ums9620"))
\t\treturn true;
\tif (of_property_read_string(node, "link-name", &name))
\t\treturn true;
\treturn strcmp(name, "AGCP_IIS0_TX") &&
\t       strcmp(name, "DisplayPort MultiMedia");
}

''' + text[start:]
    old = '\t\tfor_each_child_of_node(node, np) {\n\t\t\tdev_dbg'
    new = '\t\tfor_each_child_of_node(node, np) {\n\t\t\tif (!sprd_card_link_enabled(np))\n\t\t\t\tcontinue;\n\t\t\tdev_dbg'
    if text.count(old) != 1:
        raise ValueError('Audio link iteration changed')
    text = text.replace(old, new)
    old = '''\tif (np && of_get_child_by_name(np, "sprd-audio-card,dai-link"))
\t\tnum_links = of_get_child_count(np);
\telse
\t\tnum_links = 1;'''
    new = '''\tif (np && of_get_child_by_name(np, "sprd-audio-card,dai-link")) {
\t\tstruct device_node *child;

\t\tnum_links = 0;
\t\tfor_each_child_of_node(np, child)
\t\t\tif (sprd_card_link_enabled(child))
\t\t\t\tnum_links++;
\t} else {
\t\tnum_links = 1;
\t}
\tif (!num_links)
\t\treturn -ENODEV;'''
    if text.count(old) != 1:
        raise ValueError('Audio link allocation changed')
    path.write_text(text.replace(old, new))
