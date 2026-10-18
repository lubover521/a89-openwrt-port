# 2026-10-10 修复与功能记录

本记录覆盖 `feat/t551m-openwrt` 分支相对于上一提交 `edbc146` 的全部功能改动，
与本批实现一起提交。内容包括双卡、屏幕与看板、短信、充电、USB/OTG、
KVM/Docker、内核工具，以及蓝牙通话、音量、声音质量和切换延迟。

实机验证对象为 T551M，最终内核系列为 `6.18.54-t551m-usb7`。
共享部分仍放在通用后端；板级充电、Type-C 和 MUSB 适配放在设备目录。
E5 尚未完成这批新增硬件功能的实机验证。

## 1. 双卡显示、控制与流量统计

- 信号页同时展示 SIM1/SIM2 的运营商、注册状态、当前制式、RSRP 和数据卡标记。
  无卡、锁卡、搜网、漫游、拒绝注册、射频关闭、查询错误与过期状态分别处理。
- 增加独立双卡状态服务，通过已有 nr6/nr7 AT owner 每 5 秒采集；卡槽寻址与查询
  放在同一条命令内，不切换上网卡，也不在 HTTP 请求里等待整轮采集。
- 修复共享 ModemManager 缓存混入另一卡信息、实际 4G 却显示 5G 的问题。
  屏幕与网页遵循相同的 NR 服务小区优先、LTE/AcT 回退逻辑；缓存附带卡槽，
  数据卡切换期间完成的旧采集丢弃。
- 修复 LTE SINR 空值：从同一卡槽的 PHY 工程数据读取，复用既有采集周期；
  NR 沿用同卡 CESQ。失败时只留空相应指标，不借用另一卡的数据。
  屏幕指标顺序调整为 RSRP、SINR、RSRQ。
- 注册详情未上报、但有运营商和有效信号时显示“已驻网／注册详情未上报”，
  不推断成已注册或漫游。
- 状态栏改为主卡信号条在上、副卡小点在下；随数据卡排序，单卡时恢复单排。
  增加轻微圆角并收紧两排间距。
- 网页看板、网络锁定、AT 终端和流量页共用本浏览器标签页的查看卡槽选择。
  选择框可收起，带过渡动画、键盘操作和减少动画偏好支持。
- 切换查看只改变 RPC 卡槽参数；终端历史、无线缓存、锁定任务及保存值按卡隔离。
  定向 AT 请求校验卡槽并阻止命令覆盖已有卡槽范围。
- 网络模式、LTE/NR 频段和小区锁定支持两卡分别设置。共享写锁防止并发修改
  `SPTESTMODE` 时覆盖另一卡字段；副卡射频重连不重启主卡 WAN。
  非上网卡的数据连接按钮明确禁用，不通过该按钮暗中切换上网卡。
- 开机回放分别处理两卡已启用的保存值，继续放在 AT 可用、首次拨号之前，
  不增加拨号后的重复回放。
- 流量账本升级为双卡结构，分别采样两张卡的接口；用量、套餐、结算日和手动
  校准各自独立，保留 10 秒统计周期。屏幕读取当前数据卡对应的日/月流量。
- 旧账本保留为 `state-v1.json`；历史合并量归入旧账本最后统计的卡槽，
  不复制到另一卡。此前混合历史无法事后准确拆分。

代码入口：[`sim-status.py`](../devices/t551m/infoscreen/sim-status.py)、
[`sims.uc`](../devices/t551m/infoscreen/sims.uc)、
[`mu300dash`](../openwrt/luci-app-t551m/root/usr/libexec/rpcd/mu300dash)、
[`lock-control`](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/lock-control)、
[`traffic`](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/traffic)。

## 2. 屏幕与看板体验

- 屏幕 LTE 候选频段与网页共用平台配置；当前配置为 B1/B3/B5/B8/B34/B39/B40/B41。
  NR 候选动态读取基带能力，不写死列表。保存时按同一候选校验，恢复默认频段
  也走相同来源；网页能力变化后清理失效选择。
- 概览网速卡片的 `LIVE CONNECTION` 改为本次开机运行时长，标签和值均靠左，
  使用系统 uptime，不再让该位置含义与蜂窝拨号时长混淆。
- 重绘恢复默认频段、重新连接网络、刷新和底部导航设置图标，同一图标的使用处
  一起更新。
- 网页网络锁定页将配置、信号与邻小区拆成独立请求，并禁止 LuCI 合批等待。
  已返回的数据先显示，慢邻区查询不阻塞整个页面。
- 采集器按核心信号、工程信号、邻区和身份资料分阶段原子发布；刷新期间保留
  已有完整数据，避免临时空字段擦掉页面内容。
- 屏幕短信、流量、应用、二维码、详细信息及设置查询增加统一 loading 和失败提示。
  请求超过 150ms 才显示动画，避免闪烁；重复请求合并，25 秒超时后可重新进入重试。
- loading 放在面包屑下方的内容区；后台详细信息查询及 AT 结果等待也有反馈。
  页面离开、锁屏、息屏时暂停不可见动画。
- 网页状态刷新最低和默认均为 2 秒，可调至 60 秒；旧的过小配置也按 2 秒处理。
  请求耗时纳入刷新间隔，不再在请求结束后额外等待完整周期。
- 上下行网速独立每 1 秒直接读取所查看卡槽的接口计数，不等待 AT 或整页采集。
  使用带小数的 uptime 算速率，接口重建、卡槽改变和计数回退时重置基线。
- 服务小区／详细小区缓存刷新阈值调整为 1／5 秒，保留在途请求合并和锁定期间
  的保护；网页隐藏时暂停查询，离开后清理定时器。
- 短信转发页“最近的转发”设置最大高度，超过后在区域内滚动，并支持键盘聚焦，
  避免记录累计后把整页不断拉长。

代码入口：[`app.js`](../devices/t551m/infoscreen/base/app.js)、
[`mobile.js`](../devices/t551m/infoscreen/mobile.js)、
[`home.js`](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/home.js)、
[`locks.js`](../openwrt/luci-app-t551m/htdocs/luci-static/resources/view/mu300/locks.js)。

## 3. 后台开销与待机相关优化

- 桌面只绘制当前可见页面，切页、关闭应用和解锁时补上最新状态。
  配置、时钟、流量数字未变化时不重复修改 DOM；息屏继续接收数据，亮屏再绘制。
- 触控守护缓存设备路径及 UCI 结果，同时检查已提交配置和暂存修改；路径异常后
  重新发现。继续每 100ms 校正背光与触控，保持息屏禁触、亮屏恢复的原有语义。
- 通话观察器使用常驻 GIO D-Bus 连接，减少每轮启动 `mmcli` 的开销；保留状态事件
  唤醒和 500ms 兜底查询，临时读失败不误判挂断。缺少 GIO 时仍有原路径回退。
- 来电与通话音量配置按文件变化刷新，避免持续启动 UCI 或重复写配置。
- 参考 MU300 上游开启 `NO_HZ_IDLE`，保留高精度定时器；WCN 固件调试日志默认关闭，
  仍可通过 sysfs 手动开启。未照搬不适用于集成 WCN 的 PCIe 休眠补丁。
- 原有桌面、触控、来电及流量采集周期保持；未采用自动关闭热点、降低射频模式
  或限制 CPU 频率的策略。

此前同机各 20 秒采样：亮屏 CPU 忙碌比例约 4.10%→1.90%，息屏约 3.37%→1.50%；
通话观察器及子进程息屏 CPU 约单核 5.38%→0.65%。这些是 USB 连接下的有限 CPU
采样，不是电池功耗或续航提升比例。

## 4. 短信满卡保护

- 修复 SIM/模组短信存储接近满额后无法持续接收的问题：先将完整短信和原始 PDU
  持久保存、落盘并核验，再重新核对 SIM 身份及相应存储位置的 PDU，逐条释放空间。
- 保存失败、SIM 改变、位置已被复用、长短信未收完整时不删除对应短信。
- 归档过程中断后，不用 SIM 上剩余的部分分片覆盖本地已完整保存的长短信。
- 归档短信继续保留在本地收件箱；删除已全部归档的本地记录不再操作旧 SIM 位置。
- 归档异常单独报告，保留双卡收件、通知和转发流程。

代码入口：[`e5-sms-receive`](../openwrt/overlay/usr/libexec/e5-sms-receive)、
[`sms_pdu.py`](../openwrt/overlay/usr/lib/e5/sms_pdu.py)。

## 5. 充电与 USB-C 快速拔插

- 定位到 A/B 槽充电配置差异：用户此前修改的 Android A 槽支持 DCP 3 A，
  B 槽仍限制为 1 A。适配仅在电池参数、原有限流和 JEITA 表精确匹配时，
  将 DCP 常温档对齐到 3 A。
- 保留低温／高温限流、停止充电阈值、回差、终止电压和输入压降保护；
  电脑 SDP 仍限制为 500 mA，CDP 与未知电源沿用传入的设备树策略。
- 修复快速拔插时插入／拔出中断合并、旧识别结果覆盖新连接等时序问题；
  先清理旧连接，再按最终硬件状态上报，保留检测期间的断开事件。
- 无 PD 策略引擎时交还硬件 CC 管理，移除正常充电拔插中的额外强制断开脉冲。
- 首次识别为 Source 时先进行有限的 Sink 探测，避免 USB-C 充电器被误判成 OTG；
  确认为外设后仍允许主机模式，不以永久固定 UFP 换取充电成功。
- 修复 OTG 切回充电时的 0.5 A 误识别：等待主机升压、D+/D− 下拉退出和输入稳定，
  再重新触发 BC1.2 检测，丢弃 OTG 期间锁存的结果；避免状态机相互等待。
- 这些修复由正常系统和关机充电共用，不增加常驻充电重试轮询。

用户已反馈最后一轮充电器／OTG 插拔复测正常。硬件输入限流寄存器最高为 3.2 A，
无法写入 4 A；本次恢复的 DCP 策略是 3 A。寄存器限值不等于实测 USB 输入电流，
此前采集到的电池端电流也不能当成 USB 输入电流。
上述适配在内核内存中生效，不改写 A/B DT、DTBO 或 NV 分区。

代码入口：[`usb_charger.py`](../devices/t551m/usb_charger.py)、
[`charge-profile.h`](../devices/t551m/charge-profile.h)、
[`usb-role.h`](../devices/t551m/usb-role.h)、
[`usb-charge-role.h`](../devices/t551m/usb-charge-role.h)。

## 6. OTG、USB 网卡和共享协议

- 恢复 DRP 自动角色识别；正确区分供应商遗留 `dr-mode` 与标准 `dr_mode` 属性。
  将 USB 控制器连接到充电芯片真实的 `otg-vbus` 供电，支持外设升压与拔出后的关闭。
- 驱动提供自动／设备／主机策略及实际角色回读。手动切换改变 CC 策略，
  只有确认真实受电外设后才开启供电，不伪造已连接状态。
- 网页设备管理替换占位实现，异步提交、回读结果并显示错误；屏幕 USB 设置共用
  同一后端，支持角色、开机主机策略和网卡自动加入 LAN 等选项。
- 增加 USB 存储、SCSI、UAS、exFAT、NTFS3，以及 Realtek、ASIX、CDC、RNDIS、
  SMSC 等常见 USB 网卡驱动和所需固件。U 盘接入可识别，但不自动挂载或修改磁盘。
- USB 网卡按配置自动保存并加入 LAN；重新插入或网桥重建后恢复连接。
  不接管 gadget 网卡、USB Wi-Fi 或已属于 WAN／其他网桥的接口；重复事件不反复写配置。
- 修复 USB 网卡能枚举、PHY 有千兆链路却没有 DHCP/数据收发的问题：接回 SPRD DMA
  与上游 MUSB 主机调度的完整链路，包括描述符启动、TX/RX 完成、后续队列及失败清理。
  保留 FIFO、bulk toggle 和回调后的队列有效性检查。
- 实现 NCM、ECM、RNDIS 三种真实 gadget 配置。网页和屏幕可保存永久或仅下次启动
  的选择；保存不打断当前连接，一次性选择只在成功应用后消耗。
- 三种协议保留 ACM 串口、MAC 与网桥归属；RNDIS 增加 Windows OS 描述符，
  各协议使用独立产品 ID。切换失败尝试恢复原协议。串口工具识别这三种产品 ID。
- 首页显示已建立数据连接的电脑或实际 OTG 外设；支持扩展坞多级设备和 USB 网卡，
  网卡提示不依赖网线或 DHCP。充电器／纯供电不再弹“连接电脑”或供电提示。

实机 RTL8153 自动加入 LAN、电脑 DHCP、ping、双向各 16 MiB SHA-256 对照以及
经蜂窝 WAN 的 DNS/HTTPS 转发通过。NCM/ECM/RNDIS 枚举往返、Windows RNDIS DHCP
与数据传输、一次性 RNDIS 启动后回到 NCM 均验证通过。ECM 尚未验证 Linux/macOS
主机上的完整收发；上述数据完整性验证也不代表千兆吞吐测试。

代码入口：[`device-usb`](../openwrt/luci-app-t551m/root/usr/libexec/unisoc-modem/device-usb)、
[`otg.py`](../devices/t551m/otg.py)、[`usb_host.py`](../devices/t551m/usb_host.py)、
[`musb-sprd-host.h`](../devices/t551m/musb-sprd-host.h)。

## 7. KVM、Docker、BTF 与常用内核能力

- 开启 ARM64 KVM、vhost、必要的 cgroup/namespace/seccomp/overlayfs 和容器网络支持，
  补齐桥接过滤、IPVS、虚拟网络及 FUSE 等按需模块。
- OpenWrt 构建增加 `E5_DOCKER=1`；安装官方 Docker 相关软件包，默认镜像增至 2 GiB。
  构建阶段不启动 Docker；实机默认按需启动，未强制开机常驻。
- 配置 Docker cgroup 启动包装器、overlay2、nft 兼容 iptables 和 fw4 转发；
  限制容器日志大小，API 保持本地 Unix socket，避免宽泛网桥匹配误接管 LAN。
- 打包当前内核的完整模块、依赖索引及原硬件服务需要的路径别名，兼容 OpenWrt
  kmodloader 的平铺目录；防止同版本号的不同构建混装。
- 构建增加配置、模块 vermagic、哈希及 `container-support.json` 校验；
  离线镜像工具保留模块符号链接，清理旧输出避免混入上一次构建的模块。
- 开启 DWARF、内核与模块 BTF、动态 Ftrace/函数图/系统调用追踪、Kprobes/Uprobes、
  Perf/ARM PMU、eBPF JIT/events/stream parser；发布模块去调试节但保留 BTF。
- 增加 FQ/HTB/TBF/NETEM、常见 tc 分类与动作、IFB、IPVTAP、Geneve 和 socket 诊断模块。
  默认不启用追踪会话、不加载 BPF 程序，非特权 BPF 默认关闭。
- 本机及容器构建流程补齐 `pahole` 依赖。内核和 split BTF 模块必须成套更新。

KVM 已实际执行 ARM64 客体并验证 MMIO 退出；Docker 已验证资源限制、seccomp、
端口映射、DNS/NAT、fw4 重载、容器重启后存储保持；BPF 测试已实际加载并 JIT 执行。
测试后 Docker 恢复停止且禁用自启。启用 KVM 不等于支持嵌套虚拟化，本次未启用或
验证二级 KVM。TF 启动与原有系统切换路径保留。

操作和构建说明见 [KVM 与 Docker](CONTAINERS.zh-CN.md)。

## 8. 蓝牙通话、音量和声音质量

- 新增 HFP Audio Gateway 服务，支持 CVSD/mSBC 协商；通话通过基带 DSP 的 IIS3/SCO
  硬件路径传输，媒体蓝牙仍由 PulseAudio 管理。
- 电话界面支持手机听筒、扬声器、蓝牙三种输出。默认使用已连接通话耳机，
  当次通话的手动选择保持；耳机断开或 SCO 失败时回退手机。
- 支持耳机按键接听、挂断和 DTMF。对现有 Call 对象重新核验状态及目标卡槽，
  多卡目标不明确时不猜测；连接耳机本身不会自动接听。
- 修复 HFP 响应帧格式，补齐本机原厂 IIS 路由及协商采样率恢复。
- 修复蓝牙无声、切回手机仍无声并约 25 秒自动断线的问题：切换时先开启新后端，
  再关闭旧后端，避免共享 DSP 语音会话引用计数归零；整个通话保持 PCM。
- SCO 协商异步执行，支持取消和失败清理；不阻塞来电、挂断与界面观察。
  切换保留麦克风静音，结束后恢复媒体及混音器原状态。
- 通话音量与媒体音量分离，声音设置及按键浮层显示独立通话档位；非通话时仍调媒体。
  配置缓存和写入锁避免重复写盘及并发覆盖。
- 修复听筒／扬声器只有 0 档静音有效的问题：改用原厂 `VBC_VOLUME` 的 AS/CVS 音量
  索引，按本机曲线映射 UI 的 1–15 档，过滤高于原最大档的非单调点；0 档明确静音。
- 蓝牙支持远程 `+VGS` 与耳机按键同步，避免耳机和 DSP 重复衰减；麦克风控制不被
  耳机音量报告覆盖。
- 针对断续和扬声器爆音，模拟增益改读本机私有 `codec.xml`；修正此前沿用其他板卡
  而高一档的听筒／扬声器增益。非零音量调节不重复下发静音命令，相同硬件档位不写控制。
- 启动及从蓝牙返回后恢复 codec 的 24-bit IIS 格式和左右声道时序；
  固件收集流程补齐 `codec.xml`，校准数据本身不纳入 Git。
- 随镜像提供固定版本及哈希的 dbus-next 0.2.3 和许可证，不需要设备在线安装依赖。

代码入口：[`e5-hfp`](../openwrt/overlay/usr/libexec/e5-hfp)、
[`e5-voice-audio`](../openwrt/overlay/usr/libexec/e5-voice-audio)、
[`e5-call-audio.py`](../rootfs/overlay/opt/e5/e5-call-audio.py)、
[`e5_call_volume.py`](../openwrt/overlay/usr/lib/e5/e5_call_volume.py)。

## 9. 接听和输出切换延迟

- 定位到 OpenWrt 根文件系统遗漏了 Debian 已有的控制台日志策略，仍以级别 7
  同步向 115200 波特率串口输出大量音频驱动日志，造成秒级阻塞。
- 补齐持久 `10-e5-printk.conf`，系统运行阶段控制台只输出错误等高优先级消息；
  完整日志继续保留在内核环形缓冲区，早期启动诊断保持原样。
- 使用常驻 libasound 控制句柄，取代每个混音器控制都启动一次命令。
  只缓存类型／枚举元数据，状态快照仍实时读取；保留原厂裸索引、顺序、回滚和恢复。
- 接听时蓝牙协商与 PCM 初始化并行；SCO 完成、屏幕切换设置和耳机意图变化立即
  唤醒处理，保留 500ms 兜底，不提高空闲轮询频率。初始化失败释放已开始的协商。

同机空闲音频后端基准如下，单位为毫秒：

| 操作 | 修复前 | 修复后 |
|---|---:|---:|
| 通话 PCM 启动 | 6086.7 | 230.2 |
| 听筒 → 扬声器 | 3364.5 | 115.1 |
| 扬声器 → 听筒 | 3488.2 | 144.8 |
| 手机 → 蓝牙路由，不含 SCO 协商 | 3813.0 | 89.3 |
| 蓝牙 → 听筒 | 6129.5 | 220.1 |

这些数值不包含基带接听和屏幕反馈耗时，SCO 协商仍随耳机变化；保留 codec 原有
防爆音延时。51 项混音器读回与旧工具一致，完整状态恢复、音量及静音检查通过。
2026-10-10 用户实际复测当前版本的蓝牙接听、三种输出切换及声音后确认：
“没毛病，完全可以了”，并要求提交本批修改。

## 10. 验证、交付和回归入口

开发过程中已完成对应模拟、浏览器及实机验证；下表给出主要可重复运行的入口。
涉及模拟内核的测试需要准备后的内核源码，浏览器测试需要本地页面和 Playwright，
不能把文件存在或配置选中代替硬件实测。

| 范围 | 主要测试入口 |
|---|---|
| 双卡状态、频段及定向 AT | `test_sim_status.py`、`test_sim_at_scope.py`、`test_screen_sims.uc`、`test_screen_bands.uc` |
| 锁定、回放、双卡流量 | `test_locks.py`、`test_boot_replay.py`、`test_locks_frontend.js`、`test_dual_traffic.py` |
| 分批加载、刷新、屏幕 | `test_cell_progressive.py`、`test_dashboard_refresh.py`、`test_dashboard_rates.py`、`test_loading_browser.py`、`test_screen.py`、`test_screen_browser.py` |
| 短信归档与满卡 | `openwrt/tests/dual-sms.py` |
| 充电、角色和检测时序 | `test_charge_profile.py`、`test_usb_charger.py`、`test_usb_charge_redetect.py`、`test_usb_charge_transition.py`、`test_usb_charge_restart.py` |
| OTG DMA、网页／屏幕 USB | `test_host_dma.py`（含 ASan/UBSan）、`test_device_usb.py`、`test_device_usb_browser.py`、`test_screen_usb.uc`、`test_screen_usb_devices.py` |
| 通话、音量及控制 | `openwrt/tests/hfp.py`、`openwrt/tests/voice-audio.py`、`openwrt/tests/call-volume.py`、`openwrt/tests/volume.py`、`rootfs/tests/voice-state.py`、`rootfs/tests/voice-volume.py`、`rootfs/tests/voice-controls.py`、`test_phone_browser.py` |
| 内核与容器 | `upstream/check-container-support.py`、`tools/kvm-smoke.c`、`tools/docker-smoke.py`、`tools/bpf-smoke.c` |

表中未带目录前缀的测试位于 `devices/t551m/`。实机部署、离线 rootfs、压缩镜像及
持久镜像校验已同步；最后一轮音频包的 13 项文件哈希、gzip 和 SHA-256 校验通过。
功能已验证后，本次提交收尾只整理文档和 Git，不再重复刷机或操作真实通话。

本提交不包含私有固件、NV 数据、设备访问凭据、用户短信／联系人、实机截图或镜像。
详细构建及硬件验证沿革见 [设备说明](../devices/t551m/README.md) 和
[屏幕说明](../devices/t551m/infoscreen/README.md)。
