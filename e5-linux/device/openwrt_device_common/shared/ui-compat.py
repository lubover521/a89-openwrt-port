#!/usr/bin/env python3
"""Aurora 1.4.0 compatibility with the LuCI bundled in this root image."""
from pathlib import Path

path = Path('/usr/share/ucode/luci/template/themes/aurora/header.ut')
text = path.read_text()
old = '''		{% if (!blank_page): %}
		<script src="{{ dispatcher.build_url('admin/translations', dispatcher.lang) }}"></script>
		<script src="{{ resource }}/cbi.js?v=1.4.0"></script>
		{% endif %}'''
new = '''		{# T551M: LuCI initializes on login too, and needs cbi's String.format. #}
		<script src="{{ dispatcher.build_url('admin/translations', dispatcher.lang) }}"></script>
		<script src="{{ resource }}/cbi.js?v=1.4.0"></script>'''
if new in text:
    path.write_text(text.replace(new, old))
elif old not in text:
    raise SystemExit('Unexpected Aurora header: review LuCI compatibility before applying')

# This LuCI core always constructs LuCI and loads authenticated UCI/preload RPCs
# from its generic header, even on blank_page. Aurora's login is a plain HTML
# form and needs none of those. Use the theme shell directly for login only.
path = path.with_name('sysauth.ut')
text = path.read_text()
for name in ('header', 'footer'):
    old_include = "include('" + name + "', {"
    new_include = "include('themes/aurora/" + name + "', {"
    if old_include in text:
        text = text.replace(old_include, new_include)
    elif new_include not in text:
        raise SystemExit('Unexpected Aurora login template: ' + name)
path.write_text(text)
