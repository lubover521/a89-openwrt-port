'use strict';
'require view';
'require form';
'require rpc';
'require ui';
'require mu300.common as M';

var resetUsb = rpc.declare({ object: 'e5-infoscreen', method: 'usb_reset', expect: {} });
var checkNetwork = rpc.declare({ object: 'e5-infoscreen', method: 'network_check', expect: {} });

return view.extend({
	render: function() {
		var m = new form.Map('e5-infoscreen', '信息屏设置',
			'保存后重启信息屏服务使 enabled、息屏时间、触摸和语言设置生效。更新源和应用商店地址留空时使用默认地址。');
		var s = m.section(form.NamedSection, 'main', 'infoscreen');
		s.addremove = false;

		var o = s.option(form.Flag, 'enabled', '启用信息屏', '关闭后屏幕保持黑屏。');
		o.default = '1'; o.rmempty = false;
		o = s.option(form.Value, 'idle', '自动息屏时间（秒）', '0 表示不自动息屏。');
		o.datatype = 'range(0,86400)'; o.default = '60'; o.rmempty = false;
		o = s.option(form.Value, 'brightness', '亮度', '亮屏时的背光等级。');
		o.datatype = 'range(1,255)'; o.default = '120'; o.rmempty = false;
		o = s.option(form.Flag, 'touch', '启用触摸', '关闭后只响应实体按键。');
		o.default = '1'; o.rmempty = false;
		o = s.option(form.ListValue, 'lang', '语言');
		o.value('zh', '中文'); o.value('en', 'English'); o.default = 'zh'; o.rmempty = false;
		o = s.option(form.Value, 'update_url', M.translate('更新 JSON 地址'), M.translate('设备适配更新源需声明 adaptation=e5-device-ui-v1，更新包也须包含对应 ADAPTATION 标记；未适配的上游包不能覆盖当前界面。'));
		o.placeholder = 'https://enceka.github.io/infoscreen/latest.json'; o.rmempty = true;
		o = s.option(form.Value, 'store_url', '应用商店 JSON 地址', '留空使用官方应用商店。');
		o.placeholder = 'https://enceka.github.io/infoscreen-plugins/index.json'; o.rmempty = true;
		o = s.option(form.Button, '_usb_reset', 'USB 连接恢复',
			'重新识别 USB 设备，恢复 LAN/DHCP。电脑的 USB 网络会短暂断开，网络设置保留。');
		o.inputtitle = '重置 USB 连接'; o.inputstyle = 'apply';
		o.onclick = function() {
			return resetUsb().then(function(r) {
				ui.addNotification(null, E('p', r.ok ? 'USB 修复已启动，请等待重新识别。结果可在信息屏“高级 → USB”查看。' : r.message), r.ok ? 'info' : 'error');
			}).catch(function(err) { ui.addNotification(null, E('p', err.message), 'error'); });
		};
		o = s.option(form.Button, '_network_check', '连接诊断', '检查 USB、热点、LAN/DHCP，下载诊断报告，不修改网络设置。');
		o.inputtitle = '一键检查并下载报告';
		o.onclick = function() {
			return checkNetwork().then(function(r) {
				if (!r.ok) { ui.addNotification(null, E('p', r.message), 'error'); return; }
				var url = URL.createObjectURL(new Blob([JSON.stringify(r.report, null, 2)], { type: 'application/json' }));
				var link = document.createElement('a'); link.href = url; link.download = 'e5-network-diagnostics.json'; link.click();
				setTimeout(function() { URL.revokeObjectURL(url); }, 1000);
			}).catch(function(err) { ui.addNotification(null, E('p', err.message), 'error'); });
		};
		return m.render();
	}
});
