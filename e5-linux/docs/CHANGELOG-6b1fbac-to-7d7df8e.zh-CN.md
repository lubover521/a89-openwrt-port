# 从 6b1fbac 到 7d7df8e 的完整更改记录

整理日期：2026-10-10。分支：`feat/t551m-openwrt`。

## 1. 覆盖范围与阅读说明

本记录**包含起始提交本身**，覆盖以下闭区间内的全部 14 个提交：

- 起始：`6b1fbac00ed2c7e7f68e8250760ab4d79e084114`，首次集中提交 T551M 适配与手机式界面。
- 截止：`7d7df8e`，离线 Wi-Fi 报文解码与 BA 分析修正；完整 SHA 见文末清单。
- Git 对比基线为起始提交的父提交，即 `6b1fbac^..7d7df8e`，不是 `6b1fbac..7d7df8e`。
- 工作区在整理开始时干净。本文自身不计入上述提交、文件及行数统计。

区间净改动为 **257 个文件：新增 227 个、修改 30 个，文本新增 34355 行、删除 119 行**。
其中 67 个路径为测试文件，另有 KVM、Docker、BPF 实机验证工具。二进制文件不计文本行数。
逐提交涉及文件的并集同样为 257 个，没有在区间内新增又删除而被净差异漏掉的路径。

正文按功能记录最终行为，也说明重要的后续修正；第 20 节逐项列出全部文件及涉及提交。
“已验证”引用该区间内文档和提交记录中的历史验证，**本次文档整理没有重新刷机、压测、
切卡、拨号或进行硬件测试**。本地忽略目录中的镜像、固件、日志和维护备份不作为源码提交内容。

## 2. 逐提交索引

时间为 Git 记录的 UTC+08:00。文件数是该次提交的数量，同一文件可能出现在多次提交中，不能相加当作总文件数。

| 编号 | 提交 | 时间 | 文件数 | 更改内容 |
| --- | --- | --- | ---: | --- |
| C01 | `6b1fbac` | 10-09 00:35 | 111 | T551M 启动、rootfs、硬件与 NV 隔离；Aurora 和 MU300 看板；多通道 AT；屏幕导航、锁屏、壁纸、实体按键；启动和联网提速。 |
| C02 | `edbc146` | 10-09 03:13 | 51 | 网络锁定异步任务与拨号前回放；Android 往返后 NV 工作副本处理；移除未配置 WAN 模式时的额外设置；关机充电动画与拔线关机；DTMF、息屏来电、短信布局。 |
| C03 | `962114f` | 10-10 01:09 | 117 | 双卡显示/控制/流量；后台开销与加载体验；短信满卡保护；充电/OTG/USB 网卡及共享模式；KVM、Docker、BTF；蓝牙通话、音量、音质与延迟。 |
| C04 | `0c1c937` | 10-10 02:10 | 7 | loading 移到标题栏中央、概览主页图标、状态栏间距；记录 F2FS/ext4 维护与界面持久化恢复。 |
| C05 | `ed57a9d` | 10-10 04:32 | 83 | 网页和屏幕 CPU 调频、调速器、电压偏移及温控；跨界面功能同步；蜂窝菜单内持久上网卡切换；中英土翻译与更新兼容保护。 |
| C06 | `cec3112` | 10-10 07:13 | 3 | 屏幕流量查看选择框匹配明暗主题、壁纸透明度、焦点及大字号布局。 |
| C07 | `85e8244` | 10-10 07:30 | 4 | 放宽锁屏起手区域、惯性和自然弧线，改善亮屏保护与松手回抖；新增手势回归。 |
| C08 | `b026b49` | 10-10 07:38 | 8 | 按 AT 字符集解码 UCS2 运营商名称；屏幕与看板同步；补充六组实机软件输入链路的解锁验证。 |
| C09 | `4d3f06c` | 10-10 08:59 | 4 | 修复 SDIO 发送线程饥饿、ARP/DNS 命令队列占用和 skb 所有权；记录热点压测与持久部署。 |
| C10 | `95451ed` | 10-10 09:07 | 1 | 对比原机 Android 驱动 BA 清理路径；仅文档。 |
| C11 | `813eba0` | 10-10 09:11 | 1 | 分清历史 KPM 的全 peer 重协商与常规 DELTXBA 清理；仅文档。 |
| C12 | `e707a72` | 10-10 09:24 | 2 | 记录接入顺序吞吐差异、逐客户端恢复设计及验证边界；仅文档。 |
| C13 | `8caf7d4` | 10-10 09:35 | 3 | 增加固件文本日志离线解析器、测试和速率/聚合控制分析。 |
| C14 | `7d7df8e` | 10-10 09:58 | 3 | 增加二进制报文离线解析器、测试；修正速率字段截断和 BA 竞争推断，补充 F50 固件对比。 |

## 3. 设备适配、启动与镜像构建

主要提交：C01，后续扩展 C02/C03/C05/C09。

- 新增 `devices/t551m/` 设备层，基于本机 `boot_b` 模板和 `dtb_b/dtbo_b/vendor_boot_b` 生成启动镜像，不套用 E5 的启动控制块或硬件参数。
- 为 UMS9621 的 32 位 Android/vendor 用户态启用 COMPAT，启动包装器按 ELF class 选择 linker 和库，保留主线 ARM64 Linux。
- 适配 320×480 ILI94887 面板、GPIO 脉冲背光、TLSC6x 触控、本机 WCN 固件/校准与 GPIO 功放；移除 E5 的 AW87xxx 硬依赖，避免强制解绑声卡和自动写入 E5 触控固件。
- 新增内核准备/构建、设备文件收集、rootfs 配置、启动镜像制作、ADB/串口采集工具；设备专属输入与通用源码分开。
- 区分试启动和持久安装：试启动带超时回退；`--persistent` 配套生成启动和根镜像，停用试用超时，默认进入 Linux，保留失败回到 Android 的机制。
- 支持查看及设置默认/下次启动系统，成功启动重置尝试次数；屏幕“切换 Android”为持久默认切换并重启。
- 显式指定内置 OpenWrt 镜像时，提前从 userdata 只读加载固件，省去无用 TF 搜索等待；缺失/损坏仍回退 TF。普通 TF 启动保留完整检测窗口、注册、选择、试运行和失败回退。
- 修复 WCN 异步固件请求与 `switch_root` 删除 initramfs 的竞争：切根前等待 PHY 就绪，已就绪或无对应模块时不等待，硬件异常最多等待 15 秒。
- PHY MAC 全零时，使用已验证的接口单播地址配置 AP BSSID；不覆盖用户显式地址，设备未就绪可后续重试。
- 后续模块打包覆盖同一内核的完整模块、依赖、BTF 和哈希，保留硬件服务所需路径；启动 initramfs 与 rootfs 中的 Wi-Fi 模块同步更新。

历史同机重启样本中，进入 OpenWrt 从约 21.56s 降至 11.60s，厂商基带进程启动从约 35.65s 降至 25.14s。
这些不是完整断电冷启动统计，TF 路径保留也不代表每批都重新完成实体 TF 启动测试。

入口：[设备说明](../devices/t551m/README.md)、[内核准备](../devices/t551m/prepare-kernel.py)、[启动 init](../boot/init)、[rootfs 配置](../devices/t551m/configure-rootfs.py)。

## 4. NV 工作数据与“无模组”修复

主要提交：C01/C02。

- 厂商进程启动前按 GPT 名称找到九个相关原始 NV 分区，设置并验证块设备只读状态。
- OpenWrt 使用自己的校验工作副本，通过 loop 提供块设备语义；不继承 E5 将 B 槽指向 A 槽的方式，不把 Linux 的运行写入同步回 Android。
- 修复普通文件被 `cp_diskserver` 的 `O_TRUNC` 截断的问题；工作副本必须通过 loop 访问。
- 修复“主备各自校验有效但内容不同”导致增量更新后备用失效：启动前在同组内全量一致化，优先有效主份，必要时从有效备份恢复；不跨 A/B 槽复制。
- 两份均无效、活动厂商进程存在或待替换文件仍被 loop 使用时拒绝操作，不修改校验字段掩盖错误。
- 关机在 NV 写入事务之间停止厂商进程，等待退出、刷新和卸载 loop，再继续关闭系统。
- Android 修改来源 fixnv/runtimenv 后，只要已有隔离副本仍有效就继续使用，避免仅因来源哈希变化拒绝启动而显示“无模组”。校验失败、缺失以及不可校验数据的来源变化仍单独处理。
- 持久来源记录与每次启动的只读核验基线分开；显式刷新仅在厂商进程停止、loop 未挂接时进行。新增只读核验入口。
- 修复充电启动中 PM 已在线、NR/CH 未启动却被 loader 当作全基带已启动的问题；为已核对哈希的 ARM32/Thumb loader 生成临时补丁副本，只加载 NR/CH，不重启 PM；未知版本拒绝套补丁。

本段记录的是隔离工作数据机制，不是新增用户 NV 备份功能。历史首次试启动曾出现 NV 校验故障并由机主恢复，之后的隔离验证不能倒推故障前从未写坏过数据。
提交不含 NV 内容、设备访问凭据或私有固件。详细经过见[设备 NV 说明](../devices/t551m/README.md#nv-隔离)。

## 5. AT 通道、基带初始化与联网等待

主要提交：C01/C02/C03/C05/C08。

- 参考 MU300 的常驻多通道方式：nr0/nr3 留给内核 URC，nr1 留给 ModemManager 拨号/短信，nr2 处理交互 AT 和控制，nr6/nr7 组成独立采集池。
- 每通道单一持有者、独立串行队列、超时和锁；看板故障切换只使用另一采集通道，不挤占 nr2。没有再启动第二个 URC 读取者。
- 使用 root 专用 Unix socket、flock 和静态 ARM64 C 客户端，替代每次启动 Python、FIFO/回复文件轮询等开销。
- 每通道发送间隔降为 100ms；完整终止响应返回后不追加一秒排空。截断响应报错，排队请求有截止时间，过期写命令不会延迟执行。
- 超时后等待旧命令结束，不自动重发写命令、不随意重开 SIPC 通道；只有 I/O 故障或内核端口重建才重新连接。
- 保留显式双卡短信事务和 MM 的虚拟 `E5SMS` 路径，避免破坏字符集、存储选择与发送事务。
- 启动协议引入初始 EPS bearer 的 `keep` 选项，避免注册后再次 CFUN 关闭/开启引发二次搜网；仅迁移旧默认值，保留用户自定义 APN、认证、IP 类型及专用初始 APN 选择。
- WAN 未配置网络模式时不再默认设置 `allowed-modes=any`；显式配置继续生效。
- SIM 寻址与查询放在同一事务，卡槽参数校验，禁止用户指令突破指定卡槽范围；终端历史按卡隔离，内部查询不写入用户历史。
- 运营商查询把 `CSCS?` 与 `COPS?` 放在同一只读事务，按实际字符集解码 UCS2；普通文本、数字 PLMN、异常编码分别保留，不改写基带字符集。

历史验证包括三通道合计 2700 次只读查询全部匹配；连续查询中位约 300.12ms→100.05ms，空闲单次约 136.36ms→2.57ms。
启用联网优化的重启样本从约 98s 降到 54–56s；加上必要 WCN 交接等待后约 59–60s。启用具体锁定回放的启动另有等待，不能承诺所有配置都固定在同一时间联网。

入口：[AT 服务](../devices/t551m/atd.py)、[原生客户端](../devices/t551m/at-client.c)、[联网初始化](../devices/t551m/network-startup.py)。

## 6. Aurora 主题、网页看板与重复功能整理

主要提交：C01，后续扩展 C02/C03/C05/C08。

- 从 MU300 仓库移植 Aurora 主题、主题配置插件和 LuCI 看板；固定包版本与哈希，保留许可证与来源。默认安装 Aurora 1.4.0、配置插件 1.2.5 及对应翻译。
- 新包名 `luci-app-t551m`，内部 `mu300` JS/RPC/翻译命名保留以兼容引用，不代表直接沿用 MU300 硬件接口。
- 默认主页切换到新看板，旧状态总览隐藏重复菜单并跳转；删除旧 E5 短信页面、重复转发程序和 Argon/配置插件。Bootstrap 作为 LuCI 依赖的备用主题保留。
- 保留信息屏、蓝牙、系统日志及网络管理等独立功能，修正 Aurora 登录页的 String.format 初始化兼容和信息屏 UCI 读取 ACL。
- 看板适配本机 AT、LTE 工程字段、信号、邻区、热点、设备/USB、网络锁定、双卡短信、流量池与系统切换。
- 设备名称读取系统 board 信息；电源菜单去掉固定机型文案，通用界面不硬编码机型。
- 国内移动、联通、电信、广电常见名称按语言映射；其他运营商保留原文。后续补上 UCS2 解码，解决显示十六进制名称。
- 状态刷新最低及默认 2 秒，可调至 60 秒；请求耗时计入周期，降低不必要的缓存等待。
- 上下行网速独立每 1 秒按所查看 SIM 的接口计数计算，不等待 AT 或整页数据；接口重建、切卡、计数回退时重设基线。
- 小区资料按类别使用 1/5 秒刷新阈值；合并在途查询、锁定写入期间保护，网页隐藏时暂停、退出时清理定时器。

入口：[看板说明](../openwrt/luci-app-t551m/README.md)、[看板首页](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/home.js)。

## 7. 手机式屏幕界面、外观与导航

主要提交：C01/C02/C03/C04/C06。

- 默认增加状态栏、标题栏和底部导航；默认五项为**概览、信号、流量、短信、设置**，底栏缩至 52px。
- 五个入口分别可从九个页面选择；配置移到独立“底部导航”页面，网页也可调整。重复点击当前 tab 返回该页顶层，顶部菜单仍可访问全部页面。
- 概览左上角改为主页房子图标，其他页面保留返回；修复进入电话后返回的焦点/按键监听异常，避免跨应用残留监听。
- 右上角菜单加入开合过渡，修正关闭叉号、总览和底部图标；重绘重启、Android 切换、默认频段恢复、重新连接及设置分类图标。
- 统一状态栏元素尺寸，去掉时间额外边距，右侧间距统一；充电时电池增加闪电指示，亮色模式下卡槽数字可读。
- 概览网速卡片适当降低高度；`LIVE CONNECTION` 改为系统本次运行时长，标签和值均靠左。
- 信号顶部卡片缩短，运营商/制式/频段横排，运营商与 4G/5G 同字号，频段稍小。
- 热点名称左对齐，优化二维码布局；二维码保持黑白和静区，避免通用 SVG 描边导致一片白。
- 增加 85%/100%/120%/140% 显示大小，文字、图标和控件一起缩放；密度单独控制留白，大内容纵向滚动。
- 修正声音设置间隔、拨号键高度及数字越界、SIM“再按一次确认”挤压、AT 列表/输出贴边；统一短信详情、应用列表、长字段换行和弹窗避让。
- 设置分类、选项和操作增加统一线条图标，跟随主题；移除内置计算器。
- 音量浮层置于锁屏、菜单和电话应用上方；实体音量键不播放滴滴反馈。
- loading 起初加入内容区，C04 **最终统一移至标题栏正中央**，不顶动列表；保留旧内容，慢请求超过 150ms 才显示，错误留在内容区并允许重试。
- 后台页迟到响应不覆盖当前页，等待状态随页面生命周期管理；息屏、锁屏及全屏来电暂停不可见动画。
- 流量页 select 使用主题底色、圆角、箭头和焦点色，跟随壁纸透明度；展开项采用实色主题底色，大字号/中英文自动换行。

入口：[屏幕说明](../devices/t551m/infoscreen/README.md)、[移动界面](../devices/t551m/infoscreen/mobile.js)、[样式](../devices/t551m/infoscreen/mobile.css)、[标题栏修复记录](FIXLOG-2026-10-10-screen-toolbar.zh-CN.md)。

## 8. 壁纸、明暗模式、锁屏与触控

主要提交：C01/C03/C06/C07/C08。

- 网页分别更换桌面/锁屏壁纸，预览、应用、恢复默认；浏览器裁剪为 320×480 PNG，设备校验尺寸、CRC、数据长度及解压上限。
- 改为 12KiB 原始数据分块上传/预览，解决大图片触发 HTTP/ubus 限制和 `XHR request aborted by browser`；有进度、原子替换、过期清理和重复块处理。
- 壁纸持久保存并随配置刷新生效，不重启屏幕；升级保留目录，访问受现有认证/本机接口约束。
- 增加暗色/亮色模式和卡片不透明度。默认 70%，屏幕以 5% 步进调整、网页可填 0–100%；覆盖导航、菜单、列表、电话和锁屏卡片，文字和二维码保持清晰。
- 首次进入及息屏唤醒默认锁屏，展示日/月流量和实时网速，布局保持简洁；比特模式默认按 bps/Kbps/Mbps/Gbps 自动进位，字节模式按 B/s/KB/s/MB/s/GB/s 自动进位。
- 上滑跟手、释放带惯性减速和过渡；后续放宽起手到屏高 25% 以下，普通阈值 20%/至少 88px，更长模式 30%/至少 132px。
- 最近约 140ms 的速度用于惯性；快速短滑至少 48px/更长模式 72px，可接受自然拇指弧线和约 16px 松手回抖；明确回拉、多指、取消和慢速短滑不解锁。
- 亮屏保护期内也跟踪位移，松手距亮屏至少 180ms 才允许解锁；解锁后拦截 450ms 合成点击，避免穿透。
- 背光和触控在同一锁中协调：先禁触再息屏，亮屏前恢复触控；用户主动关闭触控时保持关闭。独立守护每 100ms 校正外部背光变化，不解绑/重刷触控芯片。
- 主动关闭触控时可通过实体确认键二次确认解锁，网页也可重新启用触控；停止信息屏关闭背光/触控，启动走同一恢复入口。
- 45 组确定性手势用例通过；C08 补齐六组 evdev→合成器→WPE 实机软件输入验证。软件注入不能代替真实手指手感验证。锁屏用于防误触，不是密码认证。

## 9. 电源菜单、关机充电与背光

主要提交：C01/C02，充电驱动扩展 C03。

- 长按电源约 1.2 秒震动 80ms，弹出关机/重启/持久切换 Android 菜单；锁屏、息屏、应用中都可呼出，松手不再附带一次息屏。危险操作沿用二次确认。
- 修复亮屏调亮度先拉低 50ms 导致黑屏闪烁：按原机 16 档环形计数器发送增量脉冲，同档不操作；只在初始化/息屏恢复复位。
- USB 插着时关机后硬件可能进入 charger 启动；S14 在热点、基带和桌面之前门控，提供最小关机充电界面。
- 增加独立 fbdev 充电动画、实时电量/充电状态；15 秒后灭背光，短按再显示，长按约 1.5 秒才继续正常启动。画面不接收触控。
- 检测从原始 DT 的启动参数读取，避免被 Linux 替换后的 cmdline 丢失充电启动原因；普通重启不进入等待。
- 拔线连续确认 0.5 秒后关闭画面、同步文件系统并尝试只读化，使用此早期阶段专用的强制关机路径，解决 rcS 尚未结束时调用常规关机而卡住的问题；失败记录并重试。
- 充电等待保持原厂电压和温控，重置必要的启动尝试次数，尊重默认系统选择；不将 TF 试运行误标记为成功。
- 构建端预渲染充电文字和图像，设备端仅需 Python 标准库；字体文件和设备私有数据不进包。

历史验证覆盖动画帧变化、短/长按、普通重启、充电门控和模拟拔线后的实际内核关机。
旧记录中的“纯黑等待”已被动画替代；物理拔线后持续断电的证据边界仍按专项记录，不把模拟检测当成人工拔线确认。

## 10. 双卡状态、信号、频段、小区与上网卡

主要提交：C02/C03/C05/C08。

- 屏幕显示两卡运营商、注册状态、当前制式、信号和数据卡标记；区分无卡、锁卡、搜网、漫游、拒绝注册、射频关闭、过期/查询失败。
- 独立服务每 5 秒通过 nr6/nr7 采集两卡；HTTP 不等待整轮查询，查询不切换上网卡。
- 修正 MM 共享缓存混入另一卡、实际 LTE 却显示 5G；两端采用同卡 NR 服务小区优先、LTE/AcT 回退，并丢弃切卡期间旧结果。
- LTE SINR 从同卡 PHY 工程信息获取，NR 沿用同卡 CESQ；页面顺序改为 RSRP、SINR、RSRQ。缺失字段不借另一卡数据填充。
- 状态栏主卡信号条在上、副卡圆点在下，数据卡优先；增加轻微圆角、缩小行距，单卡自动变单排。
- 网页看板、网络锁定、AT、流量共用当前浏览器标签页的查看/控制卡槽，支持可收起动画；只改变操作对象，不暗中切换数据卡。
- LTE 候选与网页平台配置一致：B1/B3/B5/B8/B34/B39/B40/B41；NR 从基带能力动态读取。修正数量字段被当成 n6、固件拒绝 B38 仍显示候选等问题。
- 网络模式、LTE/NR 频段、小区锁定按卡保存，支持共享互斥和目标卡固定；写 `SPTESTMODE` 保留另一卡字段，副卡重连不重启主卡 WAN。
- 锁定操作改为独立异步任务 ID，校验 AT 返回和实际读回后才报成功；不再靠浏览器/设备时间比较猜测完成，清理残留转圈。
- 配置、信号、邻区独立获取，禁用导致合批等待的方式；核心、工程、邻区、身份资料分阶段发布，先到先显示，旧完整数据保留。
- 开机流程为 AT 就绪→回放/核验→启动 MM→首次射频初始化/拨号，每次启动只尝试一次；后台仅复核，不再二次 SFUN/回放。
- 屏幕与网页共用回放开关、完整网络模式/组网配置；空频段/小区列表按解除锁定回放，迁移后不重复读旧平铺备份。
- 仅早期回放中特定无最终 OK 的情况，允许只读探测恢复分帧再核验；不重发设置、不重开端口、不把普通 AT ERROR 当成功。
- 新增**蜂窝→SIM 卡管理**，明确区分“查看卡槽”和“切上网卡”；复用 `e5-sim` 持久保存默认数据卡，异步互斥、确认、状态回读和错误反馈。同卡选择不动作。

LTE 模式/小区锁定与重启回放已有历史实机记录；5G SA/NSA 等未在当前 LTE 条件下完整驻网验证。
新增网页切卡入口完成模拟和实机只读/取消/同卡检查，没有为验证该入口额外实际切换生产上网卡。

## 11. 双卡流量池与跨界面同步

主要提交：C01/C03/C05/C06。

- 屏幕、锁屏和网页共用 `unisoc.traffic`，日用量、自然月、历史、套餐周期、校准和计量方向采用统一口径，避免旧 vnstat 与新流量池各算一套。
- 账本升级为双卡结构，分别读取 `sipa_eth0/sipa_eth8`；额度、结算日、历史和手动校准互不覆盖。
- 保留旧 `state-v1.json`；合并历史归入旧账本最后统计的卡，不能复制给两张卡，也不能准确反推历史分摊。
- 流量页支持跟随上网卡或查看 SIM1/SIM2；锁屏始终跟随实际数据卡。切卡使旧缓存失效，异步旧响应不能污染新卡页面。
- 接口离线仍可显示历史；读取失败明确处理，不继续展示错误旧值。
- 屏幕“清空流量记录”支持单卡/双卡，网页提供清空当前卡，两端共用同一确认和清空事务。
- 清空日/月/历史及套餐校准，保留套餐额度、结算日和计量方向；建立当前接口基线，后续只累计新增量，不重新计入清空前流量。
- “本次网卡累计”独立显示，不冒充已被清空的历史；保存失败回滚/报错，事务版本避免重启恢复旧缓存。
- 保持每 10 秒采样、每 60 秒保存，清空/套餐变更立即落盘；比特/字节网速设置不改变累计流量单位。

与此同期还统一热点 AP/radio 开关、短信本地可见性、AT 分卡历史、锁定和回放、USB 自动配置、默认系统及设置错误反馈。
具体交互和数据保留验证见[功能同步复查](../devices/t551m/infoscreen/README.md#功能同步复查2026-10-10)。

## 12. 短信、转发与通话界面

主要提交：C01/C02/C03/C05。

- 网页短信接入原有双卡后端，支持按卡查看、来源标记、发送卡选择、本地收件箱和 SIM 同步；整理桌面/窄屏的收件人、过滤、操作区、会话与消息布局。
- 删除/隐藏本地记录在屏幕和网页同步，未读数和打开的消息随原刷新更新；默认保留 SIM 副本，明确删除 SIM 时仍核对身份和位置。
- 独立短信转发页复用已有双卡配置；最近转发区域设置最大高度和内部滚动，避免整页无限增长。
- 修复 SIM 短信满卡后无法继续收件：完整短信与原始 PDU 持久化、fsync、读回核验后，复核 SIM 身份及存储位内容，再逐项释放空间。
- 保存失败、SIM 改变、位置被复用或长短信未完整时不删除；中断后不拿残留分片覆盖已归档长短信，删除纯本地归档不操作过期 SIM 槽位。
- 电话页面适配实体拨号键直接进入；返回、应用切换和焦点处理避免监听残留。
- 增加通话中 DTMF 屏幕键盘及实体数字键；只允许 `0–9/*/#`，对当前 ACTIVE Call 串行发送，失败不自动重发，挂断/换通话清除队列。
- `/phone/live` 轻量查询与概览慢轮询分离，通话/来电界面 350ms 刷新，后端 D-Bus 事件配合 500ms 兜底；临时查询失败不误判挂断。
- 息屏来电使用独立全屏电话 frame 唤醒，前 600ms 防误触；底层锁屏不解除，来电结束恢复锁屏，遵守用户禁触与来电亮屏设置。

测试覆盖模拟发送/删除/DTMF 和界面状态；并非为了回归测试真实发送、删除用户短信或拨号。
历史接口响应 7.5ms 中位不等于运营商挂断到界面的端到端耗时。

## 13. 媒体音量、蓝牙通话、音质与切换延迟

主要提交：C01/C02/C03。

- 修正媒体音量映射与显示，避免只有 0 档静音有效；音量按键/设置接入共享后端。
- 新增独立 HFP Audio Gateway 服务，使用 BlueZ Profile1/RFCOMM 处理耳机控制，通话音频通过 ALSA/DSP 硬件路径传输，媒体蓝牙仍由 PulseAudio 管理。
- 提供手机听筒、蓝牙耳机、扬声器三种通话输出，默认选可用通话耳机，当次手动选择保持；断开/协商失败回退手机。
- 支持耳机按键接听、挂断、DTMF 及 `+VGS` 音量同步；连接耳机本身不会自动接听，多卡 Call 目标不明确时拒绝猜测。
- 修复 HFP 响应格式、原厂 IIS 路由和采样率恢复；解决连接蓝牙后全路由无声及约 25 秒断话。
- 切路由先开启新后端再关闭旧后端，避免共享 DSP 语音会话引用归零；通话保持 PCM，SCO 协商可异步取消，结束恢复媒体和混音器状态。
- 通话音量与媒体音量独立；听筒/扬声器使用原厂 `VBC_VOLUME` AS/CVS 索引及本机曲线映射 1–15 档，0 档明确静音，过滤高于原最大档的非单调点。
- 蓝牙避免耳机与 DSP 双重衰减，麦克风静音不被耳机音量报告覆盖；切换过程保留静音选择。
- 听筒/扬声器模拟增益从本机 `codec.xml` 读取，纠正沿用其他板卡而高一档的增益；恢复 24-bit IIS 与左右时序，非零调音量不反复静音，同档不重复写，改善断续/爆音。
- 运行阶段串口控制台降到高优先级日志，避免 115200 串口同步打印大量音频调试引发秒级卡顿；完整 dmesg 与早期启动日志保留。
- 使用常驻 libasound 句柄，缓存控件元数据，状态仍实时读取；蓝牙协商与 PCM 初始化并行，事件及时唤醒，不提高空闲轮询率。
- 固定 dbus-next 0.2.3 依赖及许可证随镜像分发，设备无需联网安装。

同机历史基准：PCM 启动约 6087→230ms，听筒→扬声器 3365→115ms，扬声器→听筒 3488→145ms，
手机→蓝牙路由 3813→89ms，蓝牙→听筒 6129→220ms。蓝牙项不含 SCO 协商，所有值不代表完整电话接听时间。
用户最后一次实际听音/接听/切换反馈“没毛病，完全可以了”；后续内核回归中的“语音服务运行”不等同于再次实听。

详见[音频及延迟记录](CHANGELOG-2026-10-10.zh-CN.md#8-蓝牙通话音量和声音质量)。

## 14. 充电、USB-C、OTG 和 USB 共享

主要提交：C01/C03/C05。

- 按原机 REG0B=0x12 分支恢复充电编码、读回及 4.4V 终止上限；不根据 `bq2560x` 模块名误套其他芯片电流公式。
- 核对 A/B 槽策略差异，仅在原电池、限流和 JEITA 参数完整匹配时，将 B 槽 DCP 常温 1A 对齐用户此前 Android A 槽的 3A 配置。
- 保留低/高温降流、回差、停止阈值及输入压降保护；电脑 SDP 仍 500mA，CDP/未知电源沿用设备树。
- 硬件输入寄存器最高可设 3.2A，不能实现 USB 输入 4A；配置值与电池端电流都不能当成实际 USB 输入电流。
- 修复快速拔插中断合并、断开事件丢失、旧连接检测覆盖新连接；按最终硬件状态重报，清除旧状态。
- 没有 PD 策略引擎时交还硬件 CC 管理，取消额外断开脉冲；初识别 Source 时有限探测 Sink，兼顾充电器识别与 OTG。
- OTG→充电先等待升压与 D+/D− 下拉退出、输入稳定，再触发 BC1.2，避免锁存 SDP 导致 0.5A/误提示电脑；正常系统和关机充电共用，不增加常驻重试轮询。
- 修复 `dr-mode`/`dr_mode` 属性处理，恢复 DRP 和真实 `otg-vbus` 供电；提供自动/主机/设备策略及实际角色回读，不伪造已连接状态。
- 网页设备管理和屏幕 USB 设置使用同一后端，支持角色、开机策略、自动配置、USB 网卡自动加入 LAN；提交异步反馈并回读错误。
- 补充 USB 存储、SCSI、UAS、exFAT、NTFS3 和常见 Realtek/ASIX/CDC/RNDIS/SMSC 网卡支持，U 盘不自动挂载/改盘。
- USB 网卡热插拔/网桥重建后恢复 LAN 归属，保留用户关闭选项；不接管 gadget、USB Wi-Fi、WAN 或其他网桥接口，重复事件不重复写配置。
- 修复“网卡有千兆链路但电脑拿不到 IP、收包为 0”：接通 SPRD DMA 与 MUSB host 描述符启动、TX/RX 完成、后续队列、FIFO/toggle 和失败清理。
- NCM/ECM/RNDIS 改为真实 gadget 配置，保留 ACM 串口、MAC 和桥归属；RNDIS 补 Windows OS 描述符，各协议独立产品 ID，失败尝试恢复。
- 共享模式支持永久/仅下次启动；保存不立即断开管理连接，一次性选择成功应用后才消费。后续修复保存模式时误覆盖自动配置开关。
- 屏幕首页提示实际电脑数据连接或 OTG 外设，识别多级 hub 和 USB 网卡，不依赖网线/DHCP；纯充电器不弹 USB 供电/电脑提示。

历史已验证 RTL8153 自动 LAN、电脑 DHCP、ping、双向各 16MiB 哈希及蜂窝 DNS/HTTPS 转发；三协议枚举往返、Windows RNDIS 传输及一次性启动恢复通过。
ECM 的 Linux/macOS 主机完整数据面、千兆吞吐、PD/高压快充未因此完成验证。用户最后一轮充电/OTG 插拔反馈正常。

## 15. KVM、Docker、BTF 与内核工具

主要提交：C03，后续 CPU/Wi-Fi 构建保留。

- 开启 ARM64 KVM、vhost-net/vsock、namespace、cgroup、seccomp、overlayfs、PSI 和容器所需网络支持。
- 补充桥接过滤、IPVS、dummy/macvtap/ipvlan/vxlan、FUSE 等按需模块；新增 FQ/HTB/TBF/PRIO/NETEM、u32/flower/matchall、BPF/mirred/police/CT 等 tc 功能，以及 IFB、IPVTAP、Geneve、socket 诊断。
- 开启 `DEBUG_INFO_DWARF_TOOLCHAIN_DEFAULT`、内核/模块 BTF、Ftrace/函数图/系统调用、Kprobes/Uprobes、Perf/ARM PMU、BPF JIT/events/stream parser、KALLSYMS_ALL。
- 默认不启动追踪会话或 BPF 程序，非特权 BPF 默认关闭；发布模块保留 BTF，构建环境补齐 pahole。
- OpenWrt 支持 `E5_DOCKER=1`，安装官方 Docker 组件及 nft 兼容 iptables，默认镜像增至 2GiB；构建时不执行 Docker 启动脚本，运行时默认停止/禁用自启。
- 增加 cgroup 启动包装器、overlay2、fw4 LAN→Docker→WAN 转发及有界日志；API 仅本机 Unix socket，不用泛化 `br-*` 接管现有 LAN。
- 模块平铺适配 OpenWrt kmodloader，原硬件目录保留符号链接；构建验证配置、vermagic、哈希和 `container-support.json`，避免同版本不同构建混装。
- 新增 KVM 实际执行 ARM64 指令及 MMIO 退出测试、Docker 无需拉外网镜像的功能测试、BPF 加载/JIT 测试。

上述验证已有实机记录，Docker 测后恢复关闭。**KVM 支持不等于嵌套虚拟化支持**；本区间没有完成二级 KVM 或安装完整虚拟机系统。
详见[容器说明](CONTAINERS.zh-CN.md)。

## 16. CPU 频率、电压和温控设置

主要提交：C05。

- 新增网页“系统→CPU 设置”和屏幕“设置→系统→CPU 设置”，共用校验后端，按实际 CPU policy/供电域动态发现，不写死核数和频率上限。
- 可设置各域最小/最大频率及 governor，相等上下限可请求固定频率；默认 schedutil，保留内核温控进一步收紧范围的权力。
- 区分用户请求范围与当前有效范围，新增只读 requested min/max，避免把临时热降频保存成长期配置。
- 通过原厂 SIP/SML DVFS ABI 读取频率和电压表，保留分档、温度切表和时序；只对核验过的 SoC/固件开放调压。
- 每供电域支持 −50～+25mV、3.125mV 步进的**启动电压偏移**，CPU 与匹配 SRAM 表一起应用；显示当前/待生效偏移、固件电压表及 PMIC 读值。
- 电压保存后重启生效，不直接强写 PMIC，不提供新增超频档位、任意 OPP 或逐频点独立改压；修正固件 domain 与 PMIC 名称后缀并非一一对应的问题。
- 非零电压启动前写入 armed 标记，正常关机清除；异常重启留标记时拒绝再次应用，移为 rejected 配置并恢复原厂电压。关机充电始终使用原厂偏移。
- cpufreq 模块在 S13、关机充电门控前初始化，每次启动只初始化一次，不提供运行中重置 DVFS 或卸载重绑入口。
- 温控按实际 zone、可写 passive 阈值及 CPU cooling 绑定处理，区分监测起点与真正降频点；可写范围/阈值顺序受后端校验，保留回差、hot/critical 和原厂温度电压策略。
- 调频/温控默认仅本次启动，可选择开机应用；保存前完整校验、按顺序写范围并回读，失败回滚。拓扑不匹配配置拒绝并归档，恢复默认清除持久配置。

历史实机验证三个频率域的 governor/限频、被动温控触发/恢复、配置跨重启保存；全部 31 档在 −3.125mV 下固件电压表同步变化，最高档 PMIC 读值也各降 3.125mV。
交付恢复原厂范围、schedutil、零电压偏移和原温控；这些有限测试不证明最大降压长期稳定或续航提升。
详见[CPU 设置说明](CPU-CONTROL.zh-CN.md)。

## 17. 后台开销、翻译与更新保护

主要提交：C03/C05。

- 桌面只绘制可见页，值未变不反复修改 DOM；息屏继续接收必要状态，亮屏/解锁/切页补绘，暂停不可见动画。
- 触控守护缓存 sysfs 路径与 UCI 结果，路径失效重新发现，保留暂存配置检查和 100ms 校正频率。
- 语音观察使用常驻 GIO D-Bus 连接，保留事件和 500ms 兜底，缺 GIO 可回退；配置按文件变化刷新，不持续启动 UCI 或重复写盘。
- 参考 MU300 开启 `NO_HZ_IDLE`，保留高精度定时器；WCN 默认关闭固件调试输出，手动诊断入口仍在。未照搬集成 WCN 不适用的 PCIe 省电补丁。
- 不通过降低现有业务轮询率、自动关闭热点、削减射频或默认限 CPU 来取得上述开销改善。
- 网页补齐中文/英文/土耳其语，屏幕补齐中文/英文；CPU/SIM 菜单 PO/LMO 同步，共享错误映射在构建时嵌入屏幕，保留底层诊断原文。
- 信息屏发布描述/压缩包须带匹配 `ADAPTATION` 标记，电话插件保留 `device_integration`，防止普通上游更新覆盖设备适配；匹配包和其他应用照常更新。
- `stage.py` 固定上游版本并幂等生成屏幕包，保留信息屏/电话的许可证与来源摘要；构建/打包自动安装相应 RPC、ACL、服务和配置迁移。

历史 USB 连接下有限 CPU 采样：亮屏约 4.10%→1.90%，息屏约 3.37%→1.50%，通话观察器约单核 5.38%→0.65%。
这些是 CPU 开销样本，不是电池功耗或续航提升百分比。

## 18. 存储维护和 Wi-Fi 故障修复/研究

### 18.1 F2FS/ext4 与界面持久化

C04 记录部署时 userdata 的 F2FS SSA/SIT 不一致、停止 checkpoint，继而承载的 ext4 镜像 journal 中止/只读。
在保存本地恢复副本后，维护环境卸载文件系统再修复 F2FS 和 ext4，将界面文件写入真实镜像，核对 20 项 UCI 配置不变，完成离线只读 fsck 和普通重启后的持久性验证。
这属于历史维护动作及文档，不是新增的开机自动 fsck/格式化功能；原始损坏根因尚未查明，不能声称永久解决了 F2FS 损坏。

### 18.2 热点大流量卡死、自行重启

主要提交：C09。

- AP/GO 的 ARP、普通 UDP DNS 回包走数据队列，减少固件命令通路占用；保留 DHCP、认证、VoWiFi、RTSP 和原组播策略。
- `iface_prepare_xmit()` 使用 `skb_cow_head()` 保留 skb 所有权，避免扩头释放原 skb 后遇到 `NETDEV_TX_BUSY`，网络栈重试已释放对象。
- 在 SC2355 TX 循环加 `cond_resched()`，修复 PREEMPT_NONE 下 completion 积压使等待不睡眠、发送线程长期霸占 CPU、接收线程得不到调度并触发 watchdog 的问题。
- 不增加固定发送延迟、不限速、不以扩大命令超时或屏蔽断言规避故障；Wi-Fi 准备脚本可重复应用。
- 构建、热加载、启动镜像/rootfs/模块清单同步及重启运行 build-id 核验均有记录；启动逻辑、TF 和 NV 不因该修复改变。

三轮各 50 秒真实客户端反向 TCP 共约 5.09GiB，平均 258/308/308Mbit/s，后两轮零 TCP 重传，无新卡死/断言/重启。
这不是一次连续 180 秒或长期耐久测试。中间尝试的组播分流未解决问题，最终撤回，没有作为最终策略保留。
一次 iperf3 连接失败是临时服务端未运行，记录中与无线故障区分。

### 18.3 后接客户端低速：仍在分析，未交付修复

主要提交：C10–C14。

- 对比原机 Android ko、既有源码和历史 KPM，区分常规 DELTXBA 清理与全 peer 清软件位图后触发重协商；未把旧补丁直接加载到当前固件。
- 用户换序确认同一客户端第一个接入可以跑满；现场记录后接约 166Mbps、先接约 285Mbps，两者软件 BA 位图持续为 `0x53`。
- 指出网页 `get_station` 为接口级统计、忽略 MAC，不能当作逐客户端 HT/VHT/带宽证据；此区间没有交付该接口的逐客户端统计修复。
- 离线文本解析器核对固件速率编码、算法带宽倍率、硬件成功/尝试计数、聚合控制和 peer 归属，避免把空闲另一卡省电切换归到测试卡。
- 离线报文解析器发现 8 位速率字段截断：433Mbps 会编码成看起来像 49Mbps 的值；慢/快测速记录约 98.705%/99.498% 对应表内 VHT80/MCS9/NSS1/短 GI。
- 明确记录并非完整空口抓包，部分头部重构/固定、聚合描述符可能被省略、详细日志本身明显拖慢测速，不能由该比例证明所有实际帧都用 80MHz。
- 将基础 BA 池与 A-MSDU 相关资源池分开；正常主机 ADDBA 已持锁等待响应，单个 pending 区不足以证明请求覆盖；flag=0 在旧恢复满速日志里也存在。
- 对照更晚 F50 固件，记录相似控制路径与差异；没有把未解释的参数 2→3 宣称为多客户端修复。
- 收窄到每客户端聚合配置、关联/激活过程及 AP 生命周期保留的状态；提出失败回退和单 peer/TID 受控恢复方案，**尚未实施/部署新的 BA 恢复策略，也未确认唯一根因**。
- 两个解析器只读本地文件，限定固件 SHA，保留多解和截断边界，不访问设备；合计 8 项测试通过，不随源码分发原始固件/现场日志。

专项记录：[热点卡死与原版驱动对比](WIFI-BURST-20261010.zh-CN.md)、[接入顺序与离线分析](WIFI-JOIN-ORDER-20261010.zh-CN.md)。

## 19. 验证索引、当前限制与可移植范围

下列是已有测试入口和历史证据定位，不表示这次文档整理重新跑完全部测试。

| 范围 | 主要入口/记录 |
| --- | --- |
| 启动、TF 回退与 WCN 交接 | `boot/tests/early-firmware.py`、`boot/tests/wcn-handoff.py`、`rootfs/tests/modem-coldboot.py` |
| NV、背光、AT、联网 | `devices/t551m/test_nv.py`、`test_backlight.py`、`test_at.py`、`test_at_client.py`、`test_network_startup.py` |
| 屏幕、壁纸、loading、手势、电话 | `test_screen_browser.py`、`test_wallpaper.py`、`test_loading_browser.py`、`test_unlock_browser.py`、`test_unlock_live.py`、`test_phone_browser.py` |
| 双卡、锁定、回放、流量、功能同步 | `test_sim_status.py`、`test_locks.py`、`test_boot_replay.py`、`test_dual_traffic.py`、`test_api_sync.py`、`test_settings_sync_browser.py`、相关 ucode/JS 测试 |
| CPU、网页切卡、翻译、更新 | `test_cpu_control.py`、`test_cpu_browser.py`、`test_data_sim.py`、`test_data_sim_browser.py`、`test_feature_i18n.js`、`test_update_compat.py` |
| 充电/USB/OTG DMA | `test_charge_mode.py`、`test_charge_screen.py`、`test_charger.py`、`test_usb_charger.py`、`test_usb_charge_*.py`、`test_host_dma.py`、`test_device_usb*.py` |
| 音频、HFP、短信 | `openwrt/tests/hfp.py`、`call-volume.py`、`voice-audio.py`、`volume.py`、`dual-sms.py`；`rootfs/tests/voice-*.py` |
| KVM/Docker/BTF/模块 | `upstream/check-container-support.py`、`tools/kvm-smoke.c`、`tools/docker-smoke.py`、`tools/bpf-smoke.c` |
| Wi-Fi 所有权及离线日志 | `devices/t551m/test_wifi_tx.py`、`tools/tests/test_wcn_rate_analyze.py`、`tools/tests/test_wcn_packet_analyze.py` |

表中未带目录前缀的设备测试位于 `devices/t551m/`，音频表项的省略前缀沿用该行明确目录。
需要 Linux、准备后的内核、浏览器/WPE、硬件或测试夹具的入口不能只凭源码存在就宣称已实测。

截至 C14，以下边界必须保留：

- 后接客户端低速和 F2FS 原始损坏根因仍未解决；前者与已修复的突发流量 watchdog 卡死是两个问题。
- 不支持所请求的 USB 输入 4A；当前匹配配置为 DCP 常温 3A，硬件寄存器上限 3.2A。
- CPU 支持现有频率档、调速器和按域启动偏移，不支持任意超频/逐频点改压；大幅降压、长期续航未验证。
- KVM/Docker 已有实际运行验证，嵌套虚拟化没有；5G 驻网、所有外设/耳机/充电器组合没有完整覆盖。
- TF 启动保留且有逻辑回归，不将每批启动脚本一致视为该批实体 TF 实测；ECM 完整收发等未覆盖项目见对应专项说明。
- 旧 `docs/STATUS.md` 是更早的 E5/Debian 状态，不能拿它覆盖本记录中的 T551M 后续结果；专项文档内早期“未验证”段落也须结合后续日期阅读。

可供 E5 再适配的共享部分包括移动界面、主题/看板、双卡业务、流量账本、短信、通话后端、CPU 管理界面、容器构建和诊断工具。
本机 DT/boot 模板、GPIO 背光、触控、充电编码/JEITA、Type-C/MUSB、ARM32 loader 哈希补丁、SIP/SML 电压 ABI、NV 映射和 codec 校准必须按 E5 实际硬件重新核对。
Wi-Fi 补丁也依赖匹配的 SDIO 驱动代码和内核配置；**代码可复用不代表 E5 已完成实机适配**。

## 20. 完整提交与文件清单

以下内容直接根据本记录固定范围的 Git 历史生成。文件动作是相对 C01 父提交的净状态；“涉及提交”列列出范围内实际修改该文件的全部提交编号。
除文本之外，也包含充电动画 ZIP、LMO 翻译和固定版本 Python wheel。清单不含本文自身。

### 20.1 完整提交标识

| 编号 | 完整 SHA | 提交时间（UTC+08:00） | 原始标题 |
| --- | --- | --- | --- |
| C01 | `6b1fbac00ed2c7e7f68e8250760ab4d79e084114` | 2026-10-09 00:35:11 | t551m: add OpenWrt device support and mobile interface |
| C02 | `edbc146ce359c946b1117f43d39f3ee7ab2baa01` | 2026-10-09 03:13:10 | t551m: fix modem startup and charging shutdown, improve calls and SMS UI |
| C03 | `962114f5681f84b5622c0ad2781dec23068150de` | 2026-10-10 01:09:35 | t551m: improve dual-SIM, USB, power and call audio support |
| C04 | `0c1c9372879e84de1860dfeaaccde4ab25ba3f67` | 2026-10-10 02:10:02 | t551m: center screen loading and refine header navigation |
| C05 | `ed57a9ddb00e217787e03318c5085072013fbe77` | 2026-10-10 04:32:52 | t551m: add CPU controls and synchronize web and screen features |
| C06 | `cec31124847ac68a91d899fa3e9d0db3f60c4753` | 2026-10-10 07:13:35 | fix:styles |
| C07 | `85e8244cc72da4534e38aae483103ec5ba8f05e6` | 2026-10-10 07:30:00 | fix(screen): make swipe unlock more forgiving |
| C08 | `b026b49cc6a16fa1799b493af3794b824befa9bb` | 2026-10-10 07:38:05 | fix(modem): decode UCS2 operator names for screen and dashboard |
| C09 | `4d3f06cc2ff7efbe1a194f14cdb26f500eb370ff` | 2026-10-10 08:59:00 | fix(wifi): prevent SDIO TX starvation and hotspot stalls |
| C10 | `95451edf1fe8c61ccc10214642f7d004ee4dcb8d` | 2026-10-10 09:07:54 | docs(wifi): compare stock Android BA cleanup paths |
| C11 | `813eba040d825c163de231a7405cae386d19ce18` | 2026-10-10 09:11:18 | docs(wifi): distinguish all-peer BA rearm from DELTXBA cleanup |
| C12 | `e707a72eadc7551c72d7753472de887da2c95d16` | 2026-10-10 09:24:35 | docs(wifi): record join-order slowdown and per-peer recovery design |
| C13 | `8caf7d41e22798ca2d1261c2471fc8a980e60b93` | 2026-10-10 09:35:26 | docs(wifi): decode per-peer rate and BA control evidence |
| C14 | `7d7df8ea901748f22611ab69eb04fa87f1b8cff3` | 2026-10-10 09:58:19 | tools(wifi): decode offline packet rates and refine BA analysis |

### 20.2 全部文件

“新增/删除行”是区间净文本差异，不是各次提交行数相加。二进制文件单独标记；文件链接指向仓库当前内容，历史版本以 20.1 的提交为准。

#### 仓库入口（2 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 修改 | [README.md](../README.md) | +4 / −0 | C01 |
| 修改 | [README.zh-CN.md](../README.zh-CN.md) | +3 / −0 | C01 |

#### 启动环境（3 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 修改 | [boot/init](../boot/init) | +61 / −14 | C01 |
| 新增 | [boot/tests/early-firmware.py](../boot/tests/early-firmware.py) | +138 / −0 | C01 |
| 新增 | [boot/tests/wcn-handoff.py](../boot/tests/wcn-handoff.py) | +63 / −0 | C01 |

#### 设备层：启动、硬件与服务（47 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 新增 | [devices/t551m/README.md](../devices/t551m/README.md) | +625 / −0 | C01, C02, C03 |
| 新增 | [devices/t551m/at-client.c](../devices/t551m/at-client.c) | +134 / −0 | C01 |
| 新增 | [devices/t551m/at-service](../devices/t551m/at-service) | +17 / −0 | C01 |
| 新增 | [devices/t551m/atd.py](../devices/t551m/atd.py) | +272 / −0 | C01, C02 |
| 新增 | [devices/t551m/build-at-client.py](../devices/t551m/build-at-client.py) | +39 / −0 | C01 |
| 新增 | [devices/t551m/build-charge-art.py](../devices/t551m/build-charge-art.py) | +85 / −0 | C02 |
| 新增 | [devices/t551m/build-kernel.sh](../devices/t551m/build-kernel.sh) | +55 / −0 | C01, C03, C05 |
| 新增 | [devices/t551m/charge-art.zip](../devices/t551m/charge-art.zip) | 二进制 | C02 |
| 新增 | [devices/t551m/charge-mode-service](../devices/t551m/charge-mode-service) | +8 / −0 | C02 |
| 新增 | [devices/t551m/charge-mode.py](../devices/t551m/charge-mode.py) | +252 / −0 | C02 |
| 新增 | [devices/t551m/charge-profile.h](../devices/t551m/charge-profile.h) | +36 / −0 | C03 |
| 新增 | [devices/t551m/charge-screen.py](../devices/t551m/charge-screen.py) | +125 / −0 | C02 |
| 新增 | [devices/t551m/collect-files.py](../devices/t551m/collect-files.py) | +35 / −0 | C01 |
| 新增 | [devices/t551m/configure-rootfs.py](../devices/t551m/configure-rootfs.py) | +175 / −0 | C01, C02, C03 |
| 新增 | [devices/t551m/cpufreq.py](../devices/t551m/cpufreq.py) | +31 / −0 | C05 |
| 新增 | [devices/t551m/cpufreq/README.md](../devices/t551m/cpufreq/README.md) | +62 / −0 | C05 |
| 新增 | [devices/t551m/cpufreq/config](../devices/t551m/cpufreq/config) | +13 / −0 | C05 |
| 新增 | [devices/t551m/cpufreq/sprd-cpufreq-v2-driver.c](../devices/t551m/cpufreq/sprd-cpufreq-v2-driver.c) | +1216 / −0 | C05 |
| 新增 | [devices/t551m/cpufreq/sprd-cpufreq-v2.h](../devices/t551m/cpufreq/sprd-cpufreq-v2.h) | +114 / −0 | C05 |
| 新增 | [devices/t551m/cpufreq/sprd_sip_svc.c](../devices/t551m/cpufreq/sprd_sip_svc.c) | +823 / −0 | C05 |
| 新增 | [devices/t551m/cpufreq/sprd_sip_svc.h](../devices/t551m/cpufreq/sprd_sip_svc.h) | +206 / −0 | C05 |
| 新增 | [devices/t551m/make-boot.py](../devices/t551m/make-boot.py) | +73 / −0 | C01 |
| 新增 | [devices/t551m/musb-sprd-host.h](../devices/t551m/musb-sprd-host.h) | +83 / −0 | C03 |
| 新增 | [devices/t551m/network-startup-defaults](../devices/t551m/network-startup-defaults) | +16 / −0 | C01 |
| 新增 | [devices/t551m/network-startup.py](../devices/t551m/network-startup.py) | +87 / −0 | C01, C02 |
| 新增 | [devices/t551m/nv-prepare.py](../devices/t551m/nv-prepare.py) | +224 / −0 | C01, C02 |
| 新增 | [devices/t551m/nv-stop.py](../devices/t551m/nv-stop.py) | +77 / −0 | C01 |
| 新增 | [devices/t551m/nv-verify.py](../devices/t551m/nv-verify.py) | +35 / −0 | C01, C02 |
| 新增 | [devices/t551m/otg.py](../devices/t551m/otg.py) | +99 / −0 | C03 |
| 新增 | [devices/t551m/prepare-kernel.py](../devices/t551m/prepare-kernel.py) | +227 / −0 | C01, C03, C05, C09 |
| 新增 | [devices/t551m/t551m-backlight.h](../devices/t551m/t551m-backlight.h) | +49 / −0 | C01 |
| 新增 | [devices/t551m/trial-service](../devices/t551m/trial-service) | +18 / −0 | C01 |
| 新增 | [devices/t551m/trial.py](../devices/t551m/trial.py) | +89 / −0 | C01 |
| 新增 | [devices/t551m/ui-cleanup.py](../devices/t551m/ui-cleanup.py) | +49 / −0 | C01 |
| 新增 | [devices/t551m/ui-compat.py](../devices/t551m/ui-compat.py) | +31 / −0 | C01 |
| 新增 | [devices/t551m/ui-defaults](../devices/t551m/ui-defaults) | +29 / −0 | C01, C05 |
| 新增 | [devices/t551m/ui.py](../devices/t551m/ui.py) | +133 / −0 | C01, C05 |
| 新增 | [devices/t551m/usb-charge-role.h](../devices/t551m/usb-charge-role.h) | +23 / −0 | C03 |
| 新增 | [devices/t551m/usb-host-network.modules](../devices/t551m/usb-host-network.modules) | +8 / −0 | C03 |
| 新增 | [devices/t551m/usb-host-storage.modules](../devices/t551m/usb-host-storage.modules) | +3 / −0 | C03 |
| 新增 | [devices/t551m/usb-policy.h](../devices/t551m/usb-policy.h) | +92 / −0 | C03 |
| 新增 | [devices/t551m/usb-role.h](../devices/t551m/usb-role.h) | +103 / −0 | C03 |
| 新增 | [devices/t551m/usb-service](../devices/t551m/usb-service) | +19 / −0 | C01 |
| 新增 | [devices/t551m/usb_charger.py](../devices/t551m/usb_charger.py) | +330 / −0 | C03 |
| 新增 | [devices/t551m/usb_host.py](../devices/t551m/usb_host.py) | +74 / −0 | C03 |
| 新增 | [devices/t551m/wifi-address-defaults](../devices/t551m/wifi-address-defaults) | +28 / −0 | C01 |
| 新增 | [devices/t551m/wifi.py](../devices/t551m/wifi.py) | +88 / −0 | C09 |

#### 设备层：屏幕界面与电话（39 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 新增 | [devices/t551m/infoscreen/LICENSE](../devices/t551m/infoscreen/LICENSE) | +21 / −0 | C01 |
| 新增 | [devices/t551m/infoscreen/README.md](../devices/t551m/infoscreen/README.md) | +391 / −0 | C01, C02, C03, C04, C05, C06, C07, C08 |
| 新增 | [devices/t551m/infoscreen/base/api.uc](../devices/t551m/infoscreen/base/api.uc) | +1625 / −0 | C01, C03, C05 |
| 新增 | [devices/t551m/infoscreen/base/app.js](../devices/t551m/infoscreen/base/app.js) | +2076 / −0 | C01, C03, C04, C05 |
| 新增 | [devices/t551m/infoscreen/base/index.html](../devices/t551m/infoscreen/base/index.html) | +267 / −0 | C01, C03, C05, C06 |
| 新增 | [devices/t551m/infoscreen/base/luci-settings.js](../devices/t551m/infoscreen/base/luci-settings.js) | +52 / −0 | C01, C05 |
| 新增 | [devices/t551m/infoscreen/base/plugin](../devices/t551m/infoscreen/base/plugin) | +171 / −0 | C05 |
| 新增 | [devices/t551m/infoscreen/base/sdk.js](../devices/t551m/infoscreen/base/sdk.js) | +181 / −0 | C02 |
| 新增 | [devices/t551m/infoscreen/base/service](../devices/t551m/infoscreen/base/service) | +69 / −0 | C05 |
| 新增 | [devices/t551m/infoscreen/base/settings.uc](../devices/t551m/infoscreen/base/settings.uc) | +587 / −0 | C01, C03, C05 |
| 新增 | [devices/t551m/infoscreen/base/style.css](../devices/t551m/infoscreen/base/style.css) | +326 / −0 | C01 |
| 新增 | [devices/t551m/infoscreen/base/update](../devices/t551m/infoscreen/base/update) | +127 / −0 | C05 |
| 新增 | [devices/t551m/infoscreen/base/updates.uc](../devices/t551m/infoscreen/base/updates.uc) | +117 / −0 | C05 |
| 新增 | [devices/t551m/infoscreen/calls.js](../devices/t551m/infoscreen/calls.js) | +55 / −0 | C02 |
| 新增 | [devices/t551m/infoscreen/cpu-settings.uc](../devices/t551m/infoscreen/cpu-settings.uc) | +86 / −0 | C05 |
| 新增 | [devices/t551m/infoscreen/details-radio.py](../devices/t551m/infoscreen/details-radio.py) | +91 / −0 | C01, C05 |
| 新增 | [devices/t551m/infoscreen/details.uc](../devices/t551m/infoscreen/details.uc) | +18 / −0 | C01, C05 |
| 新增 | [devices/t551m/infoscreen/mobile-phone.css](../devices/t551m/infoscreen/mobile-phone.css) | +65 / −0 | C01, C02 |
| 新增 | [devices/t551m/infoscreen/mobile.css](../devices/t551m/infoscreen/mobile.css) | +376 / −0 | C01, C02, C03, C04, C05, C06 |
| 新增 | [devices/t551m/infoscreen/mobile.js](../devices/t551m/infoscreen/mobile.js) | +629 / −0 | C01, C02, C03, C04, C05, C07 |
| 新增 | [devices/t551m/infoscreen/navigation.js](../devices/t551m/infoscreen/navigation.js) | +20 / −0 | C01 |
| 新增 | [devices/t551m/infoscreen/phone/LICENSE](../devices/t551m/infoscreen/phone/LICENSE) | +21 / −0 | C02 |
| 新增 | [devices/t551m/infoscreen/phone/UPSTREAM.json](../devices/t551m/infoscreen/phone/UPSTREAM.json) | +13 / −0 | C02 |
| 新增 | [devices/t551m/infoscreen/phone/backend.uc](../devices/t551m/infoscreen/phone/backend.uc) | +107 / −0 | C02, C03 |
| 新增 | [devices/t551m/infoscreen/phone/index.html](../devices/t551m/infoscreen/phone/index.html) | +75 / −0 | C02, C03 |
| 新增 | [devices/t551m/infoscreen/phone/manifest.json](../devices/t551m/infoscreen/phone/manifest.json) | +75 / −0 | C02, C05 |
| 新增 | [devices/t551m/infoscreen/phone/phone.css](../devices/t551m/infoscreen/phone/phone.css) | +90 / −0 | C02, C03 |
| 新增 | [devices/t551m/infoscreen/phone/phone.js](../devices/t551m/infoscreen/phone/phone.js) | +316 / −0 | C02, C03 |
| 新增 | [devices/t551m/infoscreen/phone/voice.uc](../devices/t551m/infoscreen/phone/voice.uc) | +79 / −0 | C02 |
| 新增 | [devices/t551m/infoscreen/power-menu.js](../devices/t551m/infoscreen/power-menu.js) | +116 / −0 | C01 |
| 新增 | [devices/t551m/infoscreen/power-service](../devices/t551m/infoscreen/power-service) | +12 / −0 | C01 |
| 新增 | [devices/t551m/infoscreen/screen-power.py](../devices/t551m/infoscreen/screen-power.py) | +105 / −0 | C01, C03 |
| 新增 | [devices/t551m/infoscreen/sim-service](../devices/t551m/infoscreen/sim-service) | +12 / −0 | C03 |
| 新增 | [devices/t551m/infoscreen/sim-status.py](../devices/t551m/infoscreen/sim-status.py) | +162 / −0 | C03, C08 |
| 新增 | [devices/t551m/infoscreen/sims.uc](../devices/t551m/infoscreen/sims.uc) | +45 / −0 | C03 |
| 新增 | [devices/t551m/infoscreen/stage.py](../devices/t551m/infoscreen/stage.py) | +339 / −0 | C01, C02, C03, C04, C05 |
| 新增 | [devices/t551m/infoscreen/ui-settings.uc](../devices/t551m/infoscreen/ui-settings.uc) | +41 / −0 | C01 |
| 新增 | [devices/t551m/infoscreen/wallpaper-rpc.py](../devices/t551m/infoscreen/wallpaper-rpc.py) | +199 / −0 | C01 |
| 新增 | [devices/t551m/infoscreen/wallpapers.js](../devices/t551m/infoscreen/wallpapers.js) | +108 / −0 | C01 |

#### 设备层：回归测试（54 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 新增 | [devices/t551m/test_api_sync.py](../devices/t551m/test_api_sync.py) | +38 / −0 | C05 |
| 新增 | [devices/t551m/test_at.py](../devices/t551m/test_at.py) | +145 / −0 | C01, C02 |
| 新增 | [devices/t551m/test_at_client.py](../devices/t551m/test_at_client.py) | +87 / −0 | C01 |
| 新增 | [devices/t551m/test_backlight.py](../devices/t551m/test_backlight.py) | +106 / −0 | C01 |
| 新增 | [devices/t551m/test_boot_replay.py](../devices/t551m/test_boot_replay.py) | +87 / −0 | C02, C03, C05 |
| 新增 | [devices/t551m/test_cell_progressive.py](../devices/t551m/test_cell_progressive.py) | +97 / −0 | C03, C08 |
| 新增 | [devices/t551m/test_charge_mode.py](../devices/t551m/test_charge_mode.py) | +169 / −0 | C02 |
| 新增 | [devices/t551m/test_charge_profile.py](../devices/t551m/test_charge_profile.py) | +70 / −0 | C03 |
| 新增 | [devices/t551m/test_charge_screen.py](../devices/t551m/test_charge_screen.py) | +51 / −0 | C02 |
| 新增 | [devices/t551m/test_charger.py](../devices/t551m/test_charger.py) | +146 / −0 | C01 |
| 新增 | [devices/t551m/test_cpu_browser.py](../devices/t551m/test_cpu_browser.py) | +128 / −0 | C05 |
| 新增 | [devices/t551m/test_cpu_control.py](../devices/t551m/test_cpu_control.py) | +242 / −0 | C05 |
| 新增 | [devices/t551m/test_dashboard_rates.py](../devices/t551m/test_dashboard_rates.py) | +63 / −0 | C03 |
| 新增 | [devices/t551m/test_dashboard_refresh.py](../devices/t551m/test_dashboard_refresh.py) | +64 / −0 | C03 |
| 新增 | [devices/t551m/test_data_sim.py](../devices/t551m/test_data_sim.py) | +98 / −0 | C05 |
| 新增 | [devices/t551m/test_data_sim_browser.py](../devices/t551m/test_data_sim_browser.py) | +76 / −0 | C05 |
| 新增 | [devices/t551m/test_device_usb.py](../devices/t551m/test_device_usb.py) | +114 / −0 | C03 |
| 新增 | [devices/t551m/test_device_usb_browser.py](../devices/t551m/test_device_usb_browser.py) | +63 / −0 | C03 |
| 新增 | [devices/t551m/test_dual_traffic.py](../devices/t551m/test_dual_traffic.py) | +113 / −0 | C03, C05 |
| 新增 | [devices/t551m/test_feature_i18n.js](../devices/t551m/test_feature_i18n.js) | +24 / −0 | C05 |
| 新增 | [devices/t551m/test_host_dma.py](../devices/t551m/test_host_dma.py) | +144 / −0 | C03 |
| 新增 | [devices/t551m/test_loading_browser.py](../devices/t551m/test_loading_browser.py) | +176 / −0 | C03, C04 |
| 新增 | [devices/t551m/test_locks.py](../devices/t551m/test_locks.py) | +235 / −0 | C02, C03, C05 |
| 新增 | [devices/t551m/test_locks_frontend.js](../devices/t551m/test_locks_frontend.js) | +95 / −0 | C02, C03 |
| 新增 | [devices/t551m/test_network_startup.py](../devices/t551m/test_network_startup.py) | +126 / −0 | C01, C02 |
| 新增 | [devices/t551m/test_nv.py](../devices/t551m/test_nv.py) | +131 / −0 | C01, C02 |
| 新增 | [devices/t551m/test_operator_names.py](../devices/t551m/test_operator_names.py) | +56 / −0 | C08 |
| 新增 | [devices/t551m/test_phone_browser.py](../devices/t551m/test_phone_browser.py) | +153 / −0 | C02, C03 |
| 新增 | [devices/t551m/test_phone_voice.uc](../devices/t551m/test_phone_voice.uc) | +27 / −0 | C02 |
| 新增 | [devices/t551m/test_screen.py](../devices/t551m/test_screen.py) | +93 / −0 | C01, C03 |
| 新增 | [devices/t551m/test_screen_bands.uc](../devices/t551m/test_screen_bands.uc) | +34 / −0 | C03, C05 |
| 新增 | [devices/t551m/test_screen_browser.py](../devices/t551m/test_screen_browser.py) | +472 / −0 | C01, C02, C03, C07 |
| 新增 | [devices/t551m/test_screen_cpu.uc](../devices/t551m/test_screen_cpu.uc) | +26 / −0 | C05 |
| 新增 | [devices/t551m/test_screen_details.py](../devices/t551m/test_screen_details.py) | +33 / −0 | C01, C05 |
| 新增 | [devices/t551m/test_screen_sims.uc](../devices/t551m/test_screen_sims.uc) | +43 / −0 | C03 |
| 新增 | [devices/t551m/test_screen_traffic.uc](../devices/t551m/test_screen_traffic.uc) | +21 / −0 | C05 |
| 新增 | [devices/t551m/test_screen_usb.uc](../devices/t551m/test_screen_usb.uc) | +31 / −0 | C03, C05 |
| 新增 | [devices/t551m/test_screen_usb_devices.py](../devices/t551m/test_screen_usb_devices.py) | +81 / −0 | C03 |
| 新增 | [devices/t551m/test_settings_sync.uc](../devices/t551m/test_settings_sync.uc) | +21 / −0 | C05 |
| 新增 | [devices/t551m/test_settings_sync_browser.py](../devices/t551m/test_settings_sync_browser.py) | +60 / −0 | C05 |
| 新增 | [devices/t551m/test_sim_at_scope.py](../devices/t551m/test_sim_at_scope.py) | +27 / −0 | C03, C05 |
| 新增 | [devices/t551m/test_sim_status.py](../devices/t551m/test_sim_status.py) | +78 / −0 | C03, C08 |
| 新增 | [devices/t551m/test_traffic_browser.py](../devices/t551m/test_traffic_browser.py) | +100 / −0 | C05 |
| 新增 | [devices/t551m/test_ui.py](../devices/t551m/test_ui.py) | +92 / −0 | C01 |
| 新增 | [devices/t551m/test_unlock_browser.py](../devices/t551m/test_unlock_browser.py) | +107 / −0 | C07 |
| 新增 | [devices/t551m/test_unlock_live.py](../devices/t551m/test_unlock_live.py) | +84 / −0 | C08 |
| 新增 | [devices/t551m/test_update_compat.py](../devices/t551m/test_update_compat.py) | +105 / −0 | C05 |
| 新增 | [devices/t551m/test_usb_charge_redetect.py](../devices/t551m/test_usb_charge_redetect.py) | +67 / −0 | C03 |
| 新增 | [devices/t551m/test_usb_charge_restart.py](../devices/t551m/test_usb_charge_restart.py) | +59 / −0 | C03 |
| 新增 | [devices/t551m/test_usb_charge_transition.py](../devices/t551m/test_usb_charge_transition.py) | +71 / −0 | C03 |
| 新增 | [devices/t551m/test_usb_charger.py](../devices/t551m/test_usb_charger.py) | +276 / −0 | C03 |
| 新增 | [devices/t551m/test_wallpaper.py](../devices/t551m/test_wallpaper.py) | +80 / −0 | C01 |
| 新增 | [devices/t551m/test_wifi_address.py](../devices/t551m/test_wifi_address.py) | +63 / −0 | C01 |
| 新增 | [devices/t551m/test_wifi_tx.py](../devices/t551m/test_wifi_tx.py) | +105 / −0 | C09 |

#### OpenWrt：镜像构建与依赖（5 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 修改 | [openwrt/README.zh-CN.md](../openwrt/README.zh-CN.md) | +3 / −0 | C03 |
| 修改 | [openwrt/build-rootfs.sh](../openwrt/build-rootfs.sh) | +21 / −5 | C03 |
| 修改 | [openwrt/bundle/collect-device-files.sh](../openwrt/bundle/collect-device-files.sh) | +8 / −0 | C01 |
| 修改 | [openwrt/bundle/flash.py](../openwrt/bundle/flash.py) | +2 / −1 | C03 |
| 修改 | [openwrt/image-add-modules.sh](../openwrt/image-add-modules.sh) | +6 / −0 | C03 |

#### OpenWrt：看板插件（53 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 新增 | [openwrt/luci-app-t551m/Makefile](../openwrt/luci-app-t551m/Makefile) | +91 / −0 | C01, C02, C05 |
| 新增 | [openwrt/luci-app-t551m/README.md](../openwrt/luci-app-t551m/README.md) | +56 / −0 | C01, C05 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/mu300/common.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/mu300/common.js) | +1839 / −0 | C01, C02, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/mu300/data-sim.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/mu300/data-sim.js) | +85 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/at.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/at.js) | +137 / −0 | C01, C03 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/cpu.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/cpu.js) | +175 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/device.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/device.js) | +220 / −0 | C01, C03 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/forward.css](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/forward.css) | +68 / −0 | C01, C03 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/forward.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/forward.js) | +166 / −0 | C01, C03 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/home.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/home.js) | +618 / −0 | C01, C02, C03 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/locks.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/locks.js) | +429 / −0 | C01, C02, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/settings.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/settings.js) | +60 / −0 | C01, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/sim.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/sim.js) | +34 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/sms.css](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/sms.css) | +60 / −0 | C02 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/sms.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/sms.js) | +296 / −0 | C01, C02 |
| 新增 | [openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/traffic.js](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/traffic.js) | +165 / −0 | C01, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/lmo/mu300.en.lmo](../openwrt/luci-app-t551m/lmo/mu300.en.lmo) | 二进制 | C01, C05 |
| 新增 | [openwrt/luci-app-t551m/lmo/mu300.tr.lmo](../openwrt/luci-app-t551m/lmo/mu300.tr.lmo) | 二进制 | C01, C05 |
| 新增 | [openwrt/luci-app-t551m/po/en/mu300.po](../openwrt/luci-app-t551m/po/en/mu300.po) | +37 / −0 | C01, C05 |
| 新增 | [openwrt/luci-app-t551m/po/tr/mu300.po](../openwrt/luci-app-t551m/po/tr/mu300.po) | +37 / −0 | C01, C05 |
| 新增 | [openwrt/luci-app-t551m/root/etc/config/unisoc_modem](../openwrt/luci-app-t551m/root/etc/config/unisoc_modem) | +22 / −0 | C01, C02, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/root/etc/hotplug.d/iface/90-unisoc-usb-host](../openwrt/luci-app-t551m/root/etc/hotplug.d/iface/90-unisoc-usb-host) | +5 / −0 | C01 |
| 新增 | [openwrt/luci-app-t551m/root/etc/hotplug.d/net/90-unisoc-usb-host](../openwrt/luci-app-t551m/root/etc/hotplug.d/net/90-unisoc-usb-host) | +6 / −0 | C01 |
| 新增 | [openwrt/luci-app-t551m/root/etc/init.d/e5-cpu](../openwrt/luci-app-t551m/root/etc/init.d/e5-cpu) | +11 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/root/etc/init.d/unisoc-modem-ui](../openwrt/luci-app-t551m/root/etc/init.d/unisoc-modem-ui) | +20 / −0 | C01, C02 |
| 新增 | [openwrt/luci-app-t551m/root/etc/init.d/unisoc-traffic](../openwrt/luci-app-t551m/root/etc/init.d/unisoc-traffic) | +18 / −0 | C01 |
| 新增 | [openwrt/luci-app-t551m/root/lib/upgrade/keep.d/e5-cpu](../openwrt/luci-app-t551m/root/lib/upgrade/keep.d/e5-cpu) | +3 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/root/lib/upgrade/keep.d/unisoc-traffic](../openwrt/luci-app-t551m/root/lib/upgrade/keep.d/unisoc-traffic) | +1 / −0 | C01 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/rpcd/e5-cpu](../openwrt/luci-app-t551m/root/usr/libexec/rpcd/e5-cpu) | +8 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/rpcd/mu300dash](../openwrt/luci-app-t551m/root/usr/libexec/rpcd/mu300dash) | +393 / −0 | C01, C02, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/action](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/action) | +101 / −0 | C01, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/at](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/at) | +70 / −0 | C01, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/boot-replay](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/boot-replay) | +61 / −0 | C01, C02, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/cell](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/cell) | +493 / −0 | C01, C03, C08 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/cpu-control](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/cpu-control) | +439 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/dashboard-info](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/dashboard-info) | +382 / −0 | C01, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/data-sim](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/data-sim) | +151 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/device-usb](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/device-usb) | +417 / −0 | C01, C03 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/hotspot](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/hotspot) | +7 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/hotspot.uc](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/hotspot.uc) | +23 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/lock](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/lock) | +3 / −0 | C01, C02 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/lock-control](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/lock-control) | +454 / −0 | C02, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/operator.uc](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/operator.uc) | +25 / −0 | C08 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/t551m-at](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/t551m-at) | +5 / −0 | C01 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/t551m-radio-restart](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/t551m-radio-restart) | +19 / −0 | C01, C03 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/t551m-registration](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/t551m-registration) | +26 / −0 | C01, C03 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/t551m-sms](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/t551m-sms) | +117 / −0 | C01, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/traffic](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/traffic) | +165 / −0 | C01, C03, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/traffic-core.uc](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/traffic-core.uc) | +142 / −0 | C01, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/share/luci/menu.d/e5-cpu.json](../openwrt/luci-app-t551m/root/usr/share/luci/menu.d/e5-cpu.json) | +8 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/share/luci/menu.d/luci-app-mu300.json](../openwrt/luci-app-t551m/root/usr/share/luci/menu.d/luci-app-mu300.json) | +124 / −0 | C01, C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/share/rpcd/acl.d/e5-cpu.json](../openwrt/luci-app-t551m/root/usr/share/rpcd/acl.d/e5-cpu.json) | +7 / −0 | C05 |
| 新增 | [openwrt/luci-app-t551m/root/usr/share/rpcd/acl.d/luci-app-mu300.json](../openwrt/luci-app-t551m/root/usr/share/rpcd/acl.d/luci-app-mu300.json) | +43 / −0 | C01, C05 |

#### OpenWrt：系统服务与配置（17 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 修改 | [openwrt/overlay/etc/config/e5-audio](../openwrt/overlay/etc/config/e5-audio) | +1 / −0 | C03 |
| 新增 | [openwrt/overlay/etc/init.d/e5-hfp](../openwrt/overlay/etc/init.d/e5-hfp) | +13 / −0 | C03 |
| 修改 | [openwrt/overlay/etc/init.d/e5-pulseaudio](../openwrt/overlay/etc/init.d/e5-pulseaudio) | +15 / −0 | C01 |
| 新增 | [openwrt/overlay/etc/sysctl.d/10-e5-printk.conf](../openwrt/overlay/etc/sysctl.d/10-e5-printk.conf) | +6 / −0 | C03 |
| 新增 | [openwrt/overlay/usr/lib/e5/e5_call_volume.py](../openwrt/overlay/usr/lib/e5/e5_call_volume.py) | +74 / −0 | C03 |
| 修改 | [openwrt/overlay/usr/lib/e5/sms_pdu.py](../openwrt/overlay/usr/lib/e5/sms_pdu.py) | +2 / −2 | C03 |
| 新增 | [openwrt/overlay/usr/lib/e5/vendor/README](../openwrt/overlay/usr/lib/e5/vendor/README) | +8 / −0 | C03 |
| 新增 | [openwrt/overlay/usr/lib/e5/vendor/dbus-next.LICENSE](../openwrt/overlay/usr/lib/e5/vendor/dbus-next.LICENSE) | +19 / −0 | C03 |
| 新增 | [openwrt/overlay/usr/lib/e5/vendor/dbus_next-0.2.3-py3-none-any.whl](../openwrt/overlay/usr/lib/e5/vendor/dbus_next-0.2.3-py3-none-any.whl) | 二进制 | C03 |
| 新增 | [openwrt/overlay/usr/libexec/e5-call-volume](../openwrt/overlay/usr/libexec/e5-call-volume) | +34 / −0 | C03 |
| 新增 | [openwrt/overlay/usr/libexec/e5-container-setup](../openwrt/overlay/usr/libexec/e5-container-setup) | +89 / −0 | C03 |
| 新增 | [openwrt/overlay/usr/libexec/e5-dockerd](../openwrt/overlay/usr/libexec/e5-dockerd) | +27 / −0 | C03 |
| 新增 | [openwrt/overlay/usr/libexec/e5-hfp](../openwrt/overlay/usr/libexec/e5-hfp) | +463 / −0 | C03 |
| 修改 | [openwrt/overlay/usr/libexec/e5-sms](../openwrt/overlay/usr/libexec/e5-sms) | +8 / −2 | C05 |
| 修改 | [openwrt/overlay/usr/libexec/e5-sms-receive](../openwrt/overlay/usr/libexec/e5-sms-receive) | +54 / −2 | C03 |
| 修改 | [openwrt/overlay/usr/libexec/e5-voice-audio](../openwrt/overlay/usr/libexec/e5-voice-audio) | +437 / −12 | C02, C03 |
| 修改 | [openwrt/overlay/usr/libexec/e5-volume](../openwrt/overlay/usr/libexec/e5-volume) | +31 / −11 | C01, C03 |

#### OpenWrt：回归测试（5 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 新增 | [openwrt/tests/call-volume.py](../openwrt/tests/call-volume.py) | +74 / −0 | C03 |
| 修改 | [openwrt/tests/dual-sms.py](../openwrt/tests/dual-sms.py) | +44 / −1 | C03 |
| 新增 | [openwrt/tests/hfp.py](../openwrt/tests/hfp.py) | +266 / −0 | C03 |
| 修改 | [openwrt/tests/voice-audio.py](../openwrt/tests/voice-audio.py) | +124 / −1 | C02, C03 |
| 新增 | [openwrt/tests/volume.py](../openwrt/tests/volume.py) | +48 / −0 | C01 |

#### 通用 rootfs 与厂商适配（10 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 修改 | [rootfs/overlay/opt/e5/android-run](../rootfs/overlay/opt/e5/android-run) | +7 / −1 | C01 |
| 修改 | [rootfs/overlay/opt/e5/e5-at](../rootfs/overlay/opt/e5/e5-at) | +13 / −0 | C01 |
| 修改 | [rootfs/overlay/opt/e5/e5-call-audio.py](../rootfs/overlay/opt/e5/e5-call-audio.py) | +312 / −38 | C03 |
| 修改 | [rootfs/overlay/opt/e5/e5-modem-coldboot](../rootfs/overlay/opt/e5/e5-modem-coldboot) | +20 / −5 | C01 |
| 修改 | [rootfs/overlay/opt/e5/vendor-start.sh](../rootfs/overlay/opt/e5/vendor-start.sh) | +8 / −2 | C01 |
| 修改 | [rootfs/pull-audio-firmware.sh](../rootfs/pull-audio-firmware.sh) | +2 / −1 | C03 |
| 修改 | [rootfs/tests/modem-coldboot.py](../rootfs/tests/modem-coldboot.py) | +23 / −8 | C01 |
| 新增 | [rootfs/tests/voice-controls.py](../rootfs/tests/voice-controls.py) | +76 / −0 | C03 |
| 修改 | [rootfs/tests/voice-state.py](../rootfs/tests/voice-state.py) | +68 / −0 | C03 |
| 新增 | [rootfs/tests/voice-volume.py](../rootfs/tests/voice-volume.py) | +50 / −0 | C03 |

#### 内核配置与构建（7 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 修改 | [upstream/Dockerfile](../upstream/Dockerfile) | +1 / −1 | C03 |
| 修改 | [upstream/build-native.sh](../upstream/build-native.sh) | +2 / −0 | C03 |
| 修改 | [upstream/build.sh](../upstream/build.sh) | +1 / −0 | C03 |
| 新增 | [upstream/check-container-support.py](../upstream/check-container-support.py) | +106 / −0 | C03 |
| 修改 | [upstream/e5-mainline.config](../upstream/e5-mainline.config) | +90 / −0 | C03 |
| 修改 | [upstream/root-modules.sh](../upstream/root-modules.sh) | +2 / −12 | C03 |
| 新增 | [upstream/stage-root-modules.py](../upstream/stage-root-modules.py) | +85 / −0 | C03 |

#### 诊断工具与测试（9 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 新增 | [tools/bpf-smoke.c](../tools/bpf-smoke.c) | +53 / −0 | C03 |
| 新增 | [tools/docker-smoke.py](../tools/docker-smoke.py) | +94 / −0 | C03 |
| 新增 | [tools/kvm-smoke.c](../tools/kvm-smoke.c) | +76 / −0 | C03 |
| 新增 | [tools/t551m-collect.py](../tools/t551m-collect.py) | +62 / −0 | C01 |
| 新增 | [tools/t551m-console.py](../tools/t551m-console.py) | +42 / −0 | C01, C03 |
| 新增 | [tools/tests/test_wcn_packet_analyze.py](../tools/tests/test_wcn_packet_analyze.py) | +80 / −0 | C14 |
| 新增 | [tools/tests/test_wcn_rate_analyze.py](../tools/tests/test_wcn_rate_analyze.py) | +53 / −0 | C13 |
| 新增 | [tools/wcn-packet-analyze.py](../tools/wcn-packet-analyze.py) | +164 / −0 | C14 |
| 新增 | [tools/wcn-rate-analyze.py](../tools/wcn-rate-analyze.py) | +139 / −0 | C13 |

#### 专项文档（6 个文件）

| 动作 | 文件 | 新增/删除行 | 涉及提交 |
| --- | --- | ---: | --- |
| 新增 | [docs/CHANGELOG-2026-10-10.zh-CN.md](../docs/CHANGELOG-2026-10-10.zh-CN.md) | +269 / −0 | C03 |
| 新增 | [docs/CONTAINERS.zh-CN.md](../docs/CONTAINERS.zh-CN.md) | +82 / −0 | C03 |
| 新增 | [docs/CPU-CONTROL.zh-CN.md](../docs/CPU-CONTROL.zh-CN.md) | +127 / −0 | C05 |
| 新增 | [docs/FIXLOG-2026-10-10-screen-toolbar.zh-CN.md](../docs/FIXLOG-2026-10-10-screen-toolbar.zh-CN.md) | +53 / −0 | C04 |
| 新增 | [docs/WIFI-BURST-20261010.zh-CN.md](../docs/WIFI-BURST-20261010.zh-CN.md) | +261 / −0 | C09, C10, C11, C12 |
| 新增 | [docs/WIFI-JOIN-ORDER-20261010.zh-CN.md](../docs/WIFI-JOIN-ORDER-20261010.zh-CN.md) | +418 / −0 | C12, C13, C14 |

### 20.3 复核命令

以下命令使用固定起止提交，即使后续继续提交，范围也不会随 HEAD 改变。基线 `fd89c05` 是起始提交的父提交，等价于 `6b1fbac^`，因此包含起始提交自身。

```sh
git log --reverse --format=fuller fd89c05eff02df823ee73384ae706196cd7e91a3..7d7df8ea901748f22611ab69eb04fa87f1b8cff3
git diff --stat fd89c05eff02df823ee73384ae706196cd7e91a3 7d7df8ea901748f22611ab69eb04fa87f1b8cff3
git diff --name-status fd89c05eff02df823ee73384ae706196cd7e91a3 7d7df8ea901748f22611ab69eb04fa87f1b8cff3
git diff --numstat fd89c05eff02df823ee73384ae706196cd7e91a3 7d7df8ea901748f22611ab69eb04fa87f1b8cff3
```
