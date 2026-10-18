# MU300 上游公共修复适配（2026-10-12）

范围：E5、T551M、VIPME M8。按当前 Linux 6.18 SDIO 驱动和独立 AT 服务适配，
不合并 MU300 的整套 PCIe 驱动、恢复看门狗或网络管理实现。

## 六项改动

| 项目 | 本仓库处理 |
| --- | --- |
| Wi-Fi 初始化失败清理 | misc、IPv4、IPv6、reset notifier 逐级注册并反向撤销；reset notifier 最后注册。wiphy/接口创建失败时补充 vendor/TCP ACK 清理。 |
| 卸载时同步关闭定时器 | 注销 reset 回调后同步取消其工作；scan timer 在销毁工作队列/VIF 前 shutdown；TCP ACK timers 在释放自旋锁后同步 shutdown，避免锁内等待死锁。WCN 上电失败仍清理主机侧资源。 |
| Wi-Fi 日志降噪 | survey、正常重排丢弃、短帧复制、碎片缓存、重复 ACK、EAPOL 发送等日常日志降为 debug；逐包日志限速。命令失败、异常长度、分配失败及未知 BAR 会话仍报错。本驱动的组播 LUT/过期 DELBA 路径原本已安静，不套用不同版本的改动。 |
| 看板请求隔离 | 所有按 SIM 分槽的 RPC 及 sysinfo 显式 nobatch，防止慢 AT 所在 HTTP 批次阻塞状态/网速。保留请求发出时的槽位、现有缓存、轮询间隔与页面防重入；不重试写操作。 |
| 升级互斥 | userdata 镜像更新、TF 镜像更新、Debian 目录更新共用 `/run/e5-upgrade/lock`。在修改文件之前非阻塞加锁；锁目录 root:700，拒绝符号链接、不安全目录和锁文件；缺少 flock 时停止。文件描述符随进程退出释放，锁文件不删除，避免新旧 inode 同时加锁。 |
| 热点客户端指标与 DFS | station dump 保留完整关联列表；缺失信号/速率按合法 MAC 后台 station get 补查，单轮总预算 1 秒、单台最多 300 ms，5 秒内不重复补查，慢客户端轮转。已返回的实时值优先，0 dBm/0 速率视为未知，不补造客户端。根据 wiphy 雷达检测能力识别不可用 DFS，自动模式排除这些信道；手选不可用 DFS 时固定回退到 **36 信道**，原样保留 htmode（如 VHT80），不搜索候选信道、不自动缩小带宽。hostapd/nl80211 原有带宽及监管校验保持。 |

客户端缓存仅限 station dump 缺失的指标，位于 `/run`，按接口及 ifindex 隔离。
没有增加常驻进程、后台轮询或 flash 写入；后台查询不等待 AT，也不改变热点关联。
首次缺失的数值可能要到下一次看板刷新才显示；驱动确实不提供时保持未知。
看板状态最低刷新仍为 **2 秒**，上下行网速仍为 **1 秒**。

共享入口分别为 `devices/t551m/wifi.py` → `devices/wifi-common.py`、
`devices/t551m/network-startup.py` 和公共 LuCI 包。三个机型的构建/更新流程均使用
这些入口。保留 TF 启动及更新，未更改 NV、充电、CPU、温控或屏幕功能。

## 来源

参考 dikeckaan/mu300-linux，保留其修复思路并按本仓库实现调整：

- [bd1d471f：初始化清理](https://github.com/dikeckaan/mu300-linux/commit/bd1d471f)
- [f34bf501：卸载与定时器](https://github.com/dikeckaan/mu300-linux/commit/f34bf501)
- [48a9c432：日常日志降级](https://github.com/dikeckaan/mu300-linux/commit/48a9c432)
- [2e5bc22c：看板请求隔离](https://github.com/dikeckaan/mu300-linux/commit/2e5bc22c)
- [1f6db8cc](https://github.com/dikeckaan/mu300-linux/commit/1f6db8cc)、[7106ed99：升级互斥与锁路径](https://github.com/dikeckaan/mu300-linux/commit/7106ed99)
- [2e0fe025：客户端指标](https://github.com/dikeckaan/mu300-linux/commit/2e0fe025)
- [47d9463d：DFS 能力过滤](https://github.com/dikeckaan/mu300-linux/commit/47d9463d)

## 验证与边界

- 三个机型现有配置分别编译 `sprd_wlan_combo.ko`，均通过，包括 BTF 生成。
- `devices/test_wifi_lifetime.py` 提取实际 C 函数，注入各级注册失败，验证 IPv4/IPv6、
  两种 reset 模式的完整回收及注销/取消顺序。
- `devices/test_upgrade_lock.py` 验证同时升级拒绝、SIGKILL 后释放、锁 inode 稳定、
  符号链接/不安全权限/缺少 flock 时拒绝执行。
- `devices/test_wifi_metrics.py` 验证实际 awk 解析、未知值、错误 MAC、缓存优先级、
  客户端退出、共享超时预算、慢客户端轮转、真实后台查询和继承文件锁。
- `devices/test_wifi_capabilities.py` 在 OpenWrt chroot 中执行实际 ucode，覆盖 DFS
  能力、固定 36 信道、htmode 原样保留、频率数据不完整、自动模式与 2.4 GHz 保持、
  监管标志不修改；完整 hostapd.uc 模块编译、旧策略迁移和补丁幂等检查通过。
- `devices/t551m/test_rpc_isolation.py` 用真实公共 JS 与可阻塞批次模拟器确认慢 AT
  不拖住状态/网速/sysinfo，SIM 槽位不串用，写请求不重复。
- 原有刷新频率/防重入/卸载测试、SIM 视图同步、TX skb 所有权和网速后端回归通过。

源码合入后已部署到 T551M 和 E5，均已重启并核对运行 Wi-Fi 模块；M8 后续
已同步公共用户态文件，Wi-Fi 驱动仍待部署。未重打完整刷机包。
编译与故障注入不能代替实际反复加载/卸载、DFS CAC 或多客户端吞吐测试；
此前“后接客户端速率下降”问题不据此宣称已经解决。

### T551M 实机部署

已核对设备 profile、eMMC CID 和现有内核版本，将 `2b2a9168` 对应的公共网页、
客户端指标、DFS 固定 36/保留带宽策略及新 Wi-Fi 模块部署到 T551M。驱动在
initramfs 加载，因此同时更新 boot_b 和根文件系统中的模块；解包对比确认启动
镜像只有 `sprd_wlan_combo.ko` 变化，内核、启动脚本、F2FS 恢复及其他模块一致。
更新了根模块校验清单，回读 boot_b 前 56 MiB 校验通过，保留后 8 MiB 日志区。
升级互斥属于主机下发的安装脚本，仓库中的两种安装入口已更新，无需在机器上
执行一次真正的根系统升级。未写 NV，也未更改无线配置或默认 OpenWrt 启动。

重启后核对运行模块的 GNU build-id 与新模块一致；网页静态资源、补丁后
hostapd.uc、根模块和启动镜像均通过校验。hostapd 为 ENABLED，当前用户配置
149/VHT80 保持；手动选择不可用 DFS 时才使用 36，未为测试改动现用信道。
USB SSH、WAN、基带、网速 RPC、屏幕 API 和 cog 进程正常；蜂窝接口外网 ping
3/3、平均约 56 ms，DNS 正常。设备侧和主机侧均保存本次文件及启动镜像回退副本，
本地记录位于 `out/t551m/shared-fixes-20261012/`。
