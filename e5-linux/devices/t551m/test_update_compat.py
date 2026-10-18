"""Check update compatibility in temporary roots; never install on the host."""
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

BASE = Path(__file__).parent / 'infoscreen/base'


class UpdateCompatibility(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = dict(os.environ, FIXTURE_ROOT=str(self.root))
        self.marker = self.root / 'usr/share/e5-infoscreen/ADAPTATION'
        self.marker.parent.mkdir(parents=True)
        self.marker.write_text('e5-device-ui-v1\n')

    def archive(self, name, files):
        path = self.root / (name + '.tar.gz')
        with tarfile.open(path, 'w:gz') as tar:
            for name, data in files.items():
                data = data.encode()
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return path

    def check_archive(self, files):
        source = (BASE / 'update').read_text()
        fn = source[source.index('compatible_archive() {'):source.index('# true when')]
        fn = fn.replace('"/$marker"', '"$FIXTURE_ROOT/$marker"')
        script = self.root / 'check'
        script.write_text('die() { echo "$*" >&2; exit 1; }\n' + fn + '\ncompatible_archive "$1"\n')
        return subprocess.run(['sh', str(script), str(self.archive('update', files))],
                              env=self.env, capture_output=True, text=True, timeout=10)

    def test_generic_or_wrong_update_is_rejected(self):
        for files in ({'usr/share/e5-infoscreen/VERSION': '999'},
                      {'usr/share/e5-infoscreen/ADAPTATION': 'other-v1'}):
            result = self.check_archive(files)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('device UI integration', result.stderr)

    def test_matching_update_and_dot_paths_are_accepted(self):
        for prefix in ('', './'):
            result = self.check_archive({prefix + 'usr/share/e5-infoscreen/ADAPTATION': 'e5-device-ui-v1\n'})
            self.assertEqual(result.returncode, 0, result.stderr)

    def install_plugin(self, name, marker=None):
        source = (BASE / 'plugin').read_text()
        for key, value in [('WWW', self.root / 'www'), ('USER_DIR', self.root / 'apps')]:
            source = '\n'.join(f'{key}={value}' if line.startswith(key + '=') else line
                               for line in source.splitlines())
        script = self.root / 'plugin'
        script.write_text(source + '\n')
        # Only manifest JSON is needed; the production parser remains untouched.
        parser = self.root / 'jsonfilter'
        parser.write_text('#!/usr/bin/env python3\nimport json,sys\ntry:\n'
                          ' d=json.load(open(sys.argv[sys.argv.index("-i")+1]))\n'
                          ' for key in sys.argv[sys.argv.index("-e")+1][2:].split("."): d=d[key]\n'
                          ' print(d if isinstance(d,str) else json.dumps(d))\n'
                          'except (OSError,KeyError,TypeError): sys.exit(1)\n')
        parser.chmod(0o755)
        manifest = dict(id=name, api_version=2, name='Test', version='2')
        if marker is not None:
            manifest['device_integration'] = marker
        package = self.archive('plugin-package', {'manifest.json': json.dumps(manifest), 'app.js': 'new'})
        return subprocess.run(['sh', str(script), 'install', str(package)],
                              env=dict(self.env, PATH=str(self.root) + ':' + os.environ['PATH']),
                              capture_output=True, text=True, timeout=10)

    def old_phone(self, builtin=False):
        path = self.root / ('www' if builtin else 'apps') / 'phone'
        path.mkdir(parents=True)
        (path / 'manifest.json').write_text(json.dumps(dict(id='phone', device_integration='e5-phone-audio-v1')))
        (path / 'app.js').write_text('old')
        return path

    def test_generic_phone_cannot_replace_user_or_builtin_integration(self):
        for builtin in (False, True):
            path = self.old_phone(builtin)
            result = self.install_plugin('phone')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('device-integrated', result.stderr)
            self.assertEqual((path / 'app.js').read_text(), 'old')
            for p in path.iterdir():
                p.unlink()
            path.rmdir()

    def test_adapted_phone_update_and_other_apps_remain_available(self):
        self.old_phone()
        for name, marker in [('phone', 'e5-phone-audio-v1'), ('notes', None)]:
            result = self.install_plugin(name, marker)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((self.root / 'apps' / name / 'app.js').read_text(), 'new')


if __name__ == '__main__':
    unittest.main()
