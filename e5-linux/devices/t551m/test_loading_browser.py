"""Loading/error feedback with delayed responses; fixtures only, no device I/O."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--fixtures', type=Path, required=True)
    ap.add_argument('--webroot', type=Path, required=True)
    ap.add_argument('--screenshots', type=Path, default=Path('logs/t551m'))
    args = ap.parse_args()
    fixtures = json.loads(args.fixtures.read_text(encoding='utf-8'))
    fixtures['/api/status']['screen'].update(idle=0, lock_enabled=False)
    args.screenshots.mkdir(parents=True, exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            path = urlsplit(self.path).path
            if not path.startswith('/api/'): return super().do_GET()
            self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers()
            self.wfile.write(json.dumps(fixtures.get(path, {})).encode())
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', 0)))
            self.send_response(200); self.end_headers(); self.wfile.write(b'{"ok":true}')

    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(Handler, directory=str(args.webroot)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as p:
        chrome = Path('C:/Program Files/Google/Chrome/Application/chrome.exe')
        browser = p.chromium.launch(**({'executable_path': str(chrome)} if chrome.exists() else {}))
        page = browser.new_page(viewport={'width': 320, 'height': 480})
        errors = []
        page.on('pageerror', lambda e: errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}/')
        page.wait_for_function("typeof last !== 'undefined' && last !== null")
        page.wait_for_timeout(400)
        home_icon = page.locator('#mobile-back path').get_attribute('d')
        assert page.locator('#mobile-back').get_attribute('aria-label') == '主页'
        gaps = page.evaluate('''() => {
            const rect = id => document.getElementById(id).getBoundingClientRect();
            const signal = rect($('bar-dual').hidden ? 'bar-bars' : 'bar-dual');
            return [rect('bar-bat').left - signal.right,
                rect('bar-clock').left - rect('bar-batpct').right];
        }''')
        assert abs(gaps[0] - gaps[1]) < 0.1, gaps
        # Gate selected requests without slowing the status loop or invoking AT.
        page.evaluate('''() => {
            const realFetch = window.fetch;
            window.gates = {}; window.readCounts = {};
            window.fetch = (path, options) => {
                readCounts[path] = (readCounts[path] || 0) + 1;
                if (!gates[path]) return realFetch(path, options);
                return new Promise(resolve => gates[path].resolve = (body, code=200) =>
                    resolve(new Response(JSON.stringify(body), {status:code})));
            };
        }''')
        page.evaluate("gates['/api/sms']={};showPage(P.sms);loadSms();void loadSms()")
        page.wait_for_function("!!gates['/api/sms'].resolve")
        page.wait_for_timeout(200)
        loader = page.locator('#mobile-toolbar > .screen-loading')
        assert loader.is_visible()
        assert page.locator('#mobile-back path').get_attribute('d') != home_icon
        center = loader.bounding_box()
        toolbar = page.locator('#mobile-toolbar').bounding_box()
        assert abs(center['x'] + center['width']/2 - 160) < 0.1, center
        assert abs(center['y'] + center['height']/2 - toolbar['y'] - toolbar['height']/2) < 0.1
        assert page.locator('.page .screen-loading, .screen-inline-loading').count() == 0
        assert page.evaluate("readCounts['/api/sms']") == 1, 'Repeated opens must share the request'
        assert loader.locator('i').evaluate("e=>getComputedStyle(e).animationPlayState") == 'running'
        page.evaluate("gates['/api/sms'].resolve({messages:[{id:10,number:'TEST',text:'Keep this message'}]})")
        page.wait_for_function("smsList.length === 1")
        assert loader.is_hidden()
        page.wait_for_function("$('pages').getAnimations().every(a => a.playState !== 'running')")
        content_before = page.locator('#sms-list').bounding_box()
        page.evaluate("void loadSms()")
        page.wait_for_timeout(200)
        assert loader.is_visible()
        assert 'Keep this message' in page.locator('#sms-list').inner_text()
        content_after = page.locator('#sms-list').bounding_box()
        assert all(abs(content_before[k] - content_after[k]) < 0.1 for k in content_before), (content_before, content_after)
        page.screenshot(path=str(args.screenshots / 'title-loading-sms.png'))
        for state_class in ['blank', 'screen-locked', 'phone-overlay']:
            page.evaluate('(c)=>document.body.classList.add(c)', state_class)
            assert loader.locator('i').evaluate('e=>getComputedStyle(e).animationPlayState') == 'paused'
            page.evaluate('(c)=>document.body.classList.remove(c)', state_class)
        # An offscreen/blank spinner pauses, and a late reply stays on its page.
        page.evaluate('showPage(P.overview)')
        assert loader.is_hidden()
        assert loader.locator('i').evaluate('e=>getComputedStyle(e).animationPlayState') == 'paused'
        assert page.locator('#mobile-back path').get_attribute('d') == home_icon
        page.evaluate("gates['/api/sms'].resolve({},503)")
        page.wait_for_function("loadState(P.sms).error")
        assert 'Keep this message' in page.locator('#sms-list').inner_text()
        assert page.evaluate('page') == 0
        assert loader.is_hidden()
        page.evaluate('showPage(P.sms)')
        page.wait_for_timeout(200)
        assert loader.is_visible()
        page.evaluate("gates['/api/sms'].resolve({messages:[]})")
        page.wait_for_function('smsList.length === 0')
        assert loader.is_hidden()
        # Details continue spinning between HTTP replies while radio data is
        # pending, then stop on completion; a later refresh starts normally.
        page.evaluate("gates['/api/advanced']={};showPage(P.adv_info)")
        page.wait_for_function("!!gates['/api/advanced'].resolve")
        page.evaluate("gates['/api/advanced'].resolve({radio_pending:true,device:{}})")
        page.wait_for_function('loadState(P.adv_info).pending')
        assert loader.is_visible()
        assert page.locator('#ad-freshness').is_hidden()
        page.wait_for_timeout(900)
        page.evaluate("gates['/api/advanced'].resolve({radio_pending:false,device:{}})")
        page.wait_for_function('!loadState(P.adv_info).pending')
        assert loader.is_hidden()
        page.evaluate('void loadAdvanced()'); page.wait_for_timeout(200)
        assert loader.is_visible()
        page.evaluate("gates['/api/advanced'].resolve({},503)")
        page.wait_for_function('loadState(P.adv_info).error')
        assert loader.is_hidden()
        assert '加载失败' in page.locator('.page.is-current > .screen-load-error').inner_text()
        # Settings entry has the same progress feedback, with no duplicate
        # static loading label taking up a second row.
        page.evaluate("gates['/api/settings']={};stCats=null;showPage(P.settings)")
        page.wait_for_timeout(200)
        assert loader.is_visible()
        assert page.locator('#st-view').inner_text() == ''
        page.evaluate("gates['/api/settings'].resolve({categories:[]})")
        page.wait_for_function('loadState(P.settings).count === 0')
        # AT actions use the same header indicator, never a second content row.
        page.evaluate("gates['/api/at']={};st=[{view:'at',presets:[{cmd:'AT',label:'Test'}]}];void stClick('atp:0')")
        page.wait_for_timeout(200)
        assert loader.is_visible()
        assert '执行中' not in page.locator('#st-view').inner_text()
        page.evaluate("gates['/api/at'].resolve({ok:true,reply:'OK'})")
        page.wait_for_function("stTop().reply === 'OK'")
        assert loader.is_hidden()
        assert page.locator('.st-at-output').inner_text() == 'OK'
        # The home icon becomes Back as soon as an app opens, including while
        # its iframe is loading, and returns to Home after closing the app.
        page.evaluate("showPage(P.overview);openApp({id:'phone',name:{zh:'电话',en:'Phone'}})")
        assert page.locator('#mobile-back path').get_attribute('d') != home_icon
        page.locator('#mobile-back').click()
        assert page.evaluate('appOpen === null && page === P.overview')
        assert page.locator('#mobile-back path').get_attribute('d') == home_icon
        # Long titles and the largest font setting cannot overlap the spinner
        # or the two right-hand buttons in either language/theme.
        for language, theme in [('zh', 'dark'), ('en', 'light')]:
            fixtures['/api/status']['screen'].update(ui_size='extra', ui_theme=theme, lang=language)
            page.evaluate('''(language)=>{
                lang=language; document.documentElement.lang=language;
                last.screen.ui_size='extra';last.screen.ui_theme=language==='en'?'light':'dark';
                T551M.status(last);showPage(P.adv_info);
            }''', language)
            page.wait_for_timeout(300)
            title = page.locator('#mobile-title').bounding_box()
            spin = loader.bounding_box()
            lock = page.locator('#mobile-lock').bounding_box()
            assert spin and title['x'] + title['width'] + 6 <= spin['x'], (title, spin)
            assert spin['x'] + spin['width'] + 6 <= lock['x'], (spin, lock)
            assert title['height'] < toolbar['height'], title
            page.screenshot(path=str(args.screenshots / f'title-loading-{language}-{theme}-extra.png'))
        page.emulate_media(reduced_motion='reduce')
        assert loader.locator('i').evaluate('e=>getComputedStyle(e).animationName') == 'none'
        assert not errors, errors
        print('PASS: centered header loading without layout shifts, AT, retained SMS, errors/retry, deduplication, staged details, animation pause, home/back, status gaps and large titles')
        browser.close()
    server.shutdown()


if __name__ == '__main__': main()
