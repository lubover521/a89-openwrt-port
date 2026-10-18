const nav_choices = [
    {value:'0',label:L('概览','Home')}, {value:'1',label:L('信号','Signal')},
    {value:'2',label:L('流量','Usage')}, {value:'3',label:L('短信','Messages')},
    {value:'4',label:L('热点','Hotspot')}, {value:'5',label:L('设备','Device')},
    {value:'6',label:L('详细信息','Details')}, {value:'7',label:L('设置','Settings')},
    {value:'8',label:L('应用','Apps')}
];
const nav_defs = map([1,2,3,4,5], i => ({
    id:`nav_slot${i}`, type:'choice', uci:`e5-infoscreen.main.nav_slot${i}`,
    default:['0','1','2','3','7'][i-1], label:L(`底部入口 ${i}`,`Bottom item ${i}`), options:nav_choices
}));
const mobile_navigation = uci_category('navigation', L('底部导航', 'Bottom navigation'), nav_defs);
const mobile_ui = uci_category('ui', L('界面与锁屏', 'Interface & lock screen'), [
	{ id:'speed_unit', type:'choice', uci:'e5-infoscreen.main.speed_unit', default:'bits', label:L('网速单位','Speed unit'),
	  to_page:value => (value == 'mbs' || value == 'auto' || value == 'bytes') ? 'bytes' : 'bits',
	  note:L('自动进位：比特 bps / Kbps / Mbps / Gbps；字节 B/s / KB/s / MB/s / GB/s。锁屏与主页同步','Auto-scale bits: bps / Kbps / Mbps / Gbps; bytes: B/s / KB/s / MB/s / GB/s. Home and lock screen stay in sync'),
	  options:[{value:'bits',label:L('比特 · 自动','Bits · Auto')},{value:'bytes',label:L('字节 · 自动','Bytes · Auto')}] },
	{ id:'ui_theme', type:'choice', uci:'e5-infoscreen.main.ui_theme', default:'dark', label:L('外观模式','Appearance'),
	  options:[{value:'dark',label:L('暗色','Dark')},{value:'light',label:L('亮色','Light')}] },
	{ id:'ui_opacity', type:'number', uci:'e5-infoscreen.main.ui_opacity', default:'70', label:L('卡片不透明度','Card opacity'),
	  min:0, max:100, step:5, raw_min:0, raw_max:100, unit:'%',
	  note:L('壁纸下生效；0% 全透明，100% 实色。文字和图标不变','With wallpaper: 0% transparent, 100% solid. Text and icons stay opaque') },
	{ id:'ui_size', type:'choice', uci:'e5-infoscreen.main.ui_size', default:'standard', label:L('显示大小','Display size'),
	  note:L('同步调整文字、图标和控件；立即预览','Changes text, icons and controls immediately'),
	  options:[{value:'small',label:L('小 · 85%','Small · 85%')},{value:'standard',label:L('标准 · 100%','Standard · 100%')},{value:'large',label:L('大 · 120%','Large · 120%')},{value:'extra',label:L('特大 · 140%','Extra large · 140%')}] },
	{ id:'status_bar', type:'toggle', uci:'e5-infoscreen.main.status_bar', default:'1', label:L('顶部状态栏','Status bar') },
	{ id:'nav_bar', type:'toggle', uci:'e5-infoscreen.main.nav_bar', default:'1', label:L('底部导航栏','Bottom navigation'),
	  note:L('关闭后仍可左右滑动切页，顶部菜单可访问全部页面','Swipe between pages or use the top menu when hidden') },
	{ id:'ui_accent', type:'choice', uci:'e5-infoscreen.main.ui_accent', default:'mint', label:L('主题色','Accent'),
	  options:[{value:'mint',label:L('薄荷绿','Mint')},{value:'blue',label:L('冰川蓝','Blue')},{value:'violet',label:L('鸢尾紫','Violet')}] },
	{ id:'ui_density', type:'choice', uci:'e5-infoscreen.main.ui_density', default:'comfortable', label:L('内容密度','Density'),
	  options:[{value:'comfortable',label:L('舒适','Comfortable')},{value:'compact',label:L('紧凑','Compact')}] },
	{ id:'ui_motion', type:'toggle', uci:'e5-infoscreen.main.ui_motion', default:'1', label:L('过渡动画','Transitions') },
	{ id:'lock_enabled', type:'toggle', uci:'e5-infoscreen.main.lock_enabled', default:'1', label:L('亮屏后锁屏','Lock on wake'),
	  confirm:true, note:L('上滑解锁用于防误触，不是密码锁','Swipe protects against accidental touches; this is not a password lock') },
	{ id:'lock_daily', type:'toggle', uci:'e5-infoscreen.main.lock_daily', default:'1', label:L('锁屏显示今日流量','Daily usage on lock screen') },
	{ id:'lock_monthly', type:'toggle', uci:'e5-infoscreen.main.lock_monthly', default:'1', label:L('锁屏显示本月流量','Monthly usage on lock screen') },
	{ id:'lock_speed', type:'toggle', uci:'e5-infoscreen.main.lock_speed', default:'1', label:L('锁屏显示实时网速','Live speed on lock screen') },
	{ id:'unlock_distance', type:'choice', uci:'e5-infoscreen.main.unlock_distance', default:'standard', label:L('上滑距离','Swipe distance'),
	  options:[{value:'standard',label:L('标准','Standard')},{value:'long',label:L('更长 · 防误触','Longer · fewer accidental unlocks')}] }
]);
