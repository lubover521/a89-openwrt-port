'use strict';
'require view';
'require form';

return view.extend({
    render: function() {
        var m = new form.Map('e5-infoscreen', '底部导航', '从左到右选择五个入口，保存后屏幕自动更新。顶部菜单仍可访问全部页面。');
        var s = m.section(form.NamedSection, 'main', 'infoscreen');
        s.addremove = false;
        var names = ['概览','信号','流量','短信','热点','设备','详细信息','设置','应用'];
        var defaults = ['0','1','2','3','7'];
        for (var i = 1; i <= 5; i++) {
            var o = s.option(form.ListValue, 'nav_slot' + i, '底部入口 ' + i);
            names.forEach(function(name, index) { o.value(String(index), name); });
            o.default = defaults[i-1];
            o.rmempty = false;
        }
        return m.render();
    }
});
