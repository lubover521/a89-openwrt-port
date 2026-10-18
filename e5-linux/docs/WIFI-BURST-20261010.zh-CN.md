# 热点突发流量与自动重启修复（2026-10-10）

## 结论

本次捕获到 Wi-Fi 发送线程在不可抢占内核中长时间不让出 CPU，最终引发
soft lockup 看门狗重启。给发送循环增加 `cond_resched()` 后，配合下述
ARP/DNS 分流及 skb 所有权修正，真实手机客户端完成三轮各 50 秒的反向
TCP 压测，共约 5.09 GiB；平均速率依次为 258、308、308 Mbit/s，后两轮
零 TCP 重传，未重现热点卡死、固件断言或自动重启。原故障版本在约 2–10 秒
内停止传输。这里记录的是三轮测试，不能等同于一次连续 180 秒或长期稳定性验证。

## 故障范围与上游核对

实机使用 SC2355/Marlin3 lite 的 SDIO 通路。原始故障日志中，热点发送期间
`CMD_GET_STATION` 超时，驱动调用 `sc2355_assert_cmd`，WCN 断电复位后留下
`hif->exit`，随后 `NETDEV WATCHDOG` 持续报告发送队列超时。USB 管理连接及
蜂窝接口仍可用，不能据此归为基带或 NV 故障。

已核对：

- E5 系统上游 `Enceka/e5-linux` 的 `fd89c05eff02` 已在当前分支历史中。
- 内核上游 `Enceka/linux-lts-e5` 的 `e5-6.18` 仍为 `020b970e351e`，
  与当前构建基线相同；没有遗漏更新的 Wi-Fi 提交。
- 该内核 Wi-Fi 驱动来自 `2984a2381621`，WCN SDIO 来自 `b639d8804107`。
- E5 上游 `docs/FINDINGS.md` 第 38 节记录的蓝牙关电后仍发送 HCI，导致
  SDIO 锁阻塞的问题已有修复；本次复现前未出现相同的蓝牙关电过程。
- MU300 的 PCIe RX DMA 修复不能代替本机 SDIO 排查，当前 Wi-Fi 源码中对应
  的 `dma_sync_single_for_cpu()` 也已经存在。

## 改动

`devices/t551m/wifi.py` 由 `prepare-kernel.py` 调用，重复执行不重复打补丁。

1. 参考 MU300 的 `7e0acce0a01b` 和 `f4f5e760cfa6`：AP/GO 的 ARP、普通
   UDP DNS 回包走数据队列，避免它们占用固件命令通路。DNS 在修改校验和之前
   返回数据通路；保留 DHCP、EAPOL/WAPI、VoWiFi、RTSP 和原有组播策略。
2. 修正上游 `iface_prepare_xmit()` 的 skb 所有权：原实现不足 headroom 时
   新建 skb 并释放原对象，后续若消息池满而返回 `NETDEV_TX_BUSY`，网络栈会
   重试已经释放的原对象。改用 `skb_cow_head()`，保留 skb 对象，并为桥接或
   TCP 克隆包取得可写的独立头部。分配失败正常释放并计入丢包；独占且空间
   足够的报文不额外分配。不修改发送队列大小、频率、带宽上限或查询周期。
3. 在 `sc2355_tx_thread()` 每轮处理之后调用 `cond_resched()`。高流量下每个
   报文/信用通知会增加 completion，而一轮批量发送仅消费一次；积压时
   `wait_for_completion_interruptible()` 不会睡眠。当前 `CONFIG_PREEMPT_NONE=y`
   内核中，信用耗尽后的忙轮询可能长期不给接收线程运行机会；补上调度点，
   只在内核需要重新调度时让出 CPU，不加入固定延迟或限速。

依据内核 `Documentation/networking/driver.rst`，返回 `NETDEV_TX_BUSY`
不能释放原 skb；`include/linux/skbuff.h` 定义了 `skb_cow_head()` 的语义。

## 已验证与尚未验证

- `test_wifi_tx.py --expect-bug` 对原始 C 函数复现释放原 skb 后仍返回可发送
  状态的问题；修正版通过所有权、共享头部、无需分配及四条失败路径测试。
  测试编译实际提取的函数，使用 ASan/UBSan，skb/分配器由测试替身提供。
- Wi-Fi 模块编译通过，vermagic 与现有 CPU5 内核一致，实机模块 BTF 加载正常。
- 第一版仅包含 ARP/DNS 分流，仍能在 iperf3 下复现，**不足以解决全部掉网**。
  新一轮现场显示 SDIO RX 持有传输锁时停滞，随后查询超时；没有将延长命令
  超时或强制忽略断言当作修复。
- 第二版包含 skb 修复，已热加载；5 秒内发送 5,000 个局域网 ARP 探测帧，
  无新断言。探测的发送 IP 为 0.0.0.0、目标为文档保留地址，不更新客户端的
  网关缓存，不通过蜂窝 WAN。
- 第二版的 rootfs 模块及启动 initramfs 已同步到实机，157 个 rootfs 模块
  校验通过，启动分区尾部保持不变；随后自动重启时通过模块 build-id 确认
  实际加载第二版，之后再热加载第四版进行下述压测。
- 复测期间另有一次 iperf3 无法连接：当时手机仍与热点关联，热点有正常收发，
  但设备上没有 iperf3 进程或 5201 监听。已重新启动仅绑定
  `192.168.9.1:5201` 的临时服务端并记录测试日志；此现象不能当作驱动再次掉网。
- 第二版真实客户端反向 TCP 测试仍失败：手机 `192.168.9.122` 从设备接收，
  前两秒分别约 290 / 313 Mbit/s，随后降为 0。最后一条 `CMD_TX_DATA`
  为 IPv4 UDP 组播（目标端口 5353），3 秒后命令响应超时。该次 SDIO 传输锁
  的最后进入/退出均已完成，MMC 没有新增 CRC、ADMA 或超时错误；不能仅凭
  第一版的栈认定根因是 SDIO 锁死。ARP/DNS 分流与 skb 修复仍不足以解决故障。
- 现场 trace、dmesg、线程栈及 iperf3 输出已保留到 `logs/t551m/wifi2-*`；
  临时探针已自动清理，随后重新加载 Wi-Fi 模块恢复热点。
- 第三版尝试将普通组播也转入 SDIO 数据通路，反向 TCP 在约 10 秒后仍停。
  此时只有少量认证/DHCP 命令，后续 `CMD_SET_IE` 超时；这一实验没有解决问题，
  **组播改动已撤回，保留原先处理方式**。
- 在随后本地 UDP 与客户端流量并发测试中，提前捕获到 SDIO 主控保持 active、
  收发中断不再增长，发送线程持续 runnable、接收线程等待调度。机器随后自行
  重启；pstore 明确记录 `SC2355_TX_THREA` 连续占用 CPU 45 秒触发 soft lockup，
  栈位于发送线程反复清理/打印路径。该记录对应上述缺失调度点的问题。
- 第四版恢复第二版的报文分类，只增加发送循环的 `cond_resched()`，已编译、
  热加载，真实客户端三轮反向 TCP 测试完成，详见结论。第一轮前半段存在
  重传、合计 1057 次，后两轮均为零；没有通过限速消除故障。测试结果保存在
  `logs/t551m/wifi4-iperf-completed.log`，断言跟踪和内核日志保存在
  `wifi4-before-reboot.trace` / `wifi4-before-reboot.dmesg`。这些现场日志属于
  本地诊断资料，不随源码提交；重启证据为 `wifi3-panic.dmesg`。

无硬件测试可在 Linux 中执行：

```sh
python3 devices/t551m/test_wifi_tx.py /path/to/prepared/kernel
```

原始源码加 `--expect-bug` 可复现旧问题；运行 `wifi.py` 后再执行正常测试。
上述真实客户端测试的等价命令为 `iperf3 -c 192.168.9.1 -R -t 50`，服务端
只监听 LAN 地址。

测试电脑不得连接设备热点：它保留原有网络，调试使用 USB/串口，压力流量来自
另一台测试设备。临时 kprobe 只记录命令报文头及故障时的栈，最多运行 15 分钟，
退出删除自身事件和 trace 实例；不增加常驻轮询服务。

## 部署边界

启动 initramfs 也携带 `sprd_wlan_combo.ko`，只替换 rootfs 模块不会让重启生效。
发布时须同步启动镜像、rootfs、模块归档及校验清单，并保持同一内核/BTF 基线。
启动镜像仅写 `boot_b` 前 56 MiB，保留尾部 8 MiB 日志；不写 NV、misc、
Android 启动镜像，不修改 TF 启动逻辑及已有网络配置。

第四版已写入实机启动镜像，写后校验全部通过且尾部未变。模块 SHA-256：
`315842e016135f89801f0ab62b9ce0500c6917db5ec78111679399ec4d28f67c`，
build-id：`abf9bbe05d566213af34402d63db8899ad469773`。
离线 ext4 镜像完成 157 个模块校验及只读 e2fsck 检查。
主动重启后的复验已通过：运行中模块 build-id 与上述值一致，157 个 rootfs
模块及启动分区前 56 MiB 校验正确；热点桥接、USB SSH、蜂窝 WAN、屏幕、
网页、语音服务及 KVM 可用，没有新 Wi-Fi 断言或 soft lockup。这里的语音
检查为服务状态，不代表本次重新进行了实听通话测试。

正式产物 `out/t551m/kernel`、`openwrt-persistent-boot.img`、
`openwrt-t551m-persistent.ext4.gz` 及校验清单已同步；旧产物保留于
`out/t551m/before-wifi4-20261010`，未加入源码提交。没有新增开机诊断服务。

## Android 原版 BA 清理对比

本节仅比较两份原厂实现中的常规清理。用户随后提供的历史 KPM 证明还存在
本节未涵盖的“全 peer TX BA rearm”补丁，当前驱动缺少该机制，详见下一节。
不能把“常规 DELTXBA 已有”概括成“多客户端 BA 恢复已经完整”。

2026-10-10 从本机 `super` 的 `vendor_dlkm_a` extent 只读提取
`lib/modules/sprd_wlan_combo.ko`，未切换 Android，也未卸载正在运行的驱动。
模块保存于本地 `work/t551m/stock-sprd_wlan_combo.ko`，大小 39,199,704 字节，
SHA-256 为 `89c2f8f983c9e87f2ff7b3308293d2104a9e83876c110c2f23f68a80228ff8ba`。
其 vermagic 为 `5.15.123-android13-8-g2054f18da766-ab10`；模块保留 DWARF、
符号表和 BTF，可以结合反汇编核对，结论不依赖原厂发布源码。最初采集的系统
属性记录 Android 版本 `551MCM08`、构建日期 2024-10-31，不能把它当成未知的
“最新版驱动”。

对比的是本机实际使用的 **SC2355 SDIO** 路径，未把同一组合模块内的 PCIe、
SC2332 或其他 `sprdwl_*` 实现当成本机实现。

| 处理 | Android 原版 ko | 当前 OpenWrt 源码 |
| --- | --- | --- |
| 固件 DELTXBA 事件（type 6） | 按 LUT/TID 原子清除 `ba_tx_done_map` 对应位 | 同样处理 |
| ADDBA 返回拒绝/失败状态 | 清对应位，允许后续重新协商 | 同样处理，并有 LUT/TID 范围检查 |
| 客户端删除/更新 | 清理接收重排序节点；删除/加入时清发送 BA bitmap | 同样处理，另有分片恢复清理 |
| 再建发送 BA | HT、报文计数超过 9、对应位未置位，重试间隔约 3 秒 | 相同主要条件；时间表示方式不同 |
| DELBA_ALL（type 5） | BA 事件跳转表指向 default | 头文件定义该编号，事件分派没有对应 case |
| 两三台客户端触发统一清 BA | 已检查的 BA、STA LUT 路径未发现 | 对应路径也未发现 |

原版二进制定位（ELF `.text` 相对地址，不是运行中的内核地址）：

- `sc2355_wlan_ba_session_event`：`0x2b470`。其 `.rodata+0x1bdb8`
  跳转表中 type 5 落到 `0x2b850` 的 default，type 6 落到 `0x2b5b4`。
  后者计算指定 peer/TID 的 bitmap 地址，在 `0x2bc18` 的 LL/SC 分支或
  `0x2b5ec` 的 LSE 分支完成原子清位。并非只有日志字符串而没有执行代码。
- `sdio_tx_ba_mgmt`：`0x41ad0`。确认 ADDBA 命令、命令返回成功且固件状态
  非成功后，`0x41bec` / `0x41c5c` 两条原子分支清对应 bitmap 位。
  传输本身报错时不会走这条清位路径；当前实现也有这个边界，不能据此认定
  存在仅原版具有的异常恢复修复。
- `sc2355_event_sta_lut`：`0x41754`；`tx_prepare_addba`：`0x303a8`。
  已核对新增、更新、删除客户端及再建 BA 的条件，没有以客户端数 2 或 3
  为阈值的清 BA 分支。

当前源码对应 `sc2355/reorder.c` 的 `SPRD_DELTXBA_EVENT`、`sc2355/tx.c`
的 `sc2355_tx_prepare_addba()` / `sc2355_tx_ba_mgmt()`，以及 `sc2355/sdio.c`
的 `sc2355_event_sta_lut()`。公开基线可参见
[BA 事件处理](https://github.com/Enceka/linux-lts-e5/blob/2984a23816213abe9001fa944203bb0ea3f56fdd/drivers/unisoc_platform/sprd_wlan_combo/sc2355/reorder.c)。

因此，**常规清 BA 的功能原版和当前版本都有；尚无证据表明原版 ko 里有一个
被本次适配漏掉的多客户端专用修复**。这不等于证明用户提到的新版本不存在
该修复，也不等于本次三轮单客户端压力测试已经覆盖多客户端问题。

固件也是需要单独区分的部分：当前 `/lib/firmware/wcnmodem.bin` 与从本机
Android 提取的版本 SHA-256 一致，均为
`ac8f2d97278cfff1aa5dce29ba5a0c3366767f7d0bcf3e9f03b194c361aa4f5a`，运行版本
为 `MARLIN3_20A_RLS2_W24.13.3`。仅比较 Linux ko，不能排除新版本的多客户端
BA 资源管理或带宽选择修复位于闭源 WCN 固件内。

同时发现现有速率上报的限制：`sprd_cfg80211_get_station()` 没有使用传入的
客户端 MAC，字节/包计数取整个 netdev，`sc2355_get_station()` 发送的
`CMD_GET_STATION` 不携带客户端 MAC。现场两个客户端的计数和速率读数确实
相同，发送速率还会返回全零；此时源码默认填写 20 MHz 带宽。因此，不能
仅凭 AP 侧这份显示确认所有客户端真实退到 VHT20。`iwinfo` 的 VHT80 也只
能辅助说明配置，不能证明每个客户端每次发包的实际带宽。确认多客户端降级
仍需客户端侧协商信息或空口证据，并区分 BA 聚合状态与 20/40/80 MHz 带宽。

本轮只做读取、反汇编和文档记录，没有加入定时清 BA、强制重协商或切换带宽
的实验行为。证据文件保留在 `work/t551m/stock-wifi-*` 和
`logs/t551m/wifi-ba-*`，没有将原厂二进制加入 Git。

## 用户历史 V4 KPM 的新证据

参考文件为用户提供的
`D:\随身WiFi\荣悦E5刷机\热点速率研究\saved_versions\20260722_SC2355_BA_V4_Runtime_KPM_universal\sc2355_ba_v4_universal_test.kpm`。
大小 8,144 字节，SHA-256 为
`8308221f3c16d0ed255f47a3041b59280adee08cb77fa6f46749f9824e7730c5`。
同目录保留了 `module_sc2355_ba_v4_universal.c`、`verify_layout.py` 和 README。
已经同时读取源码与 KPM 反汇编，以下关键行为相符，而不是仅根据文件名判断。

### 与常规 DELTXBA 不同的机制

1. `event_sta_lut_after()` 在 STA LUT **ADD/UPDATE**（action 1/2）之后，
   遍历 32 个 peer，将全部 `ba_tx_done_map` 清零。它不要求客户端数达到 3，
   不主动发送 DELBA、不清接收重排序缓冲、不强制 80 MHz；目的是让仍有流量
   的旧客户端也能重新进入原驱动的 ADDBA 条件，而不是只重置刚加入的客户端。
   KPM `.text+0x50` 装入计数 32，`+0x64` 执行清零循环，`+0x6c` 写屏障。
2. `tx_prepare_addba_before()` 在原来的 HT、流量计数、位图及约 3 秒重试
   条件满足后，再加全局 **120 ms** 的 ADDBA 准入间隔。未获准时直接跳过
   本次 BA 建立，后续报文再尝试，不通过 sleep/忙等暂停数据发送。
   它限制的是重新协商请求，不是每个数据包的发送间隔。
3. 这个通用 KPM 的准入时间戳采用原子 CAS；反汇编 `+0x220` 起可见
   `LDAXR/STLXR`，`tx_prepare_addba_after()` 在原函数没有置位时尝试撤销
   本次准入。不可把这个通用 KPM 称为 non-atomic 版本。

**当前 OpenWrt 缺少第 1、2 项**：`sc2355_event_sta_lut()` 的 ADD/UPDATE
只清 `peer_entry[i]`，`sc2355_tx_prepare_addba()` 只有单个 peer/TID 的重试
间隔。前一节确认的 DELTXBA 是依赖固件 type 6 通知的单 peer/TID 清理，
不能替代这里由客户端关联事件触发的全 peer 重建。前次聊天将两者混在一起
回答“已有清 BA”，结论不完整；这份补丁提供了具体缺失机制的证据。

### 本机与历史样本的对应关系

运行用户提供的只读 `verify_layout.py` 检查本机 Android ko，结果为：

```text
valid=True stride=0x98 ba=0x30e8 tx_num=0x43d0
```

进一步比较归档内 `sprd_wlan_combo_e5_stock.ko`（完整文件 SHA-256 为
`e3595237cbbaad642d7ab0c70a7d3dc8b8a7bbc22fc0ed0a429b03944f893b6d`）：
它与本机原版的完整文件哈希不同，但 `.text` 内容哈希相同；
`sc2355_event_sta_lut`、`tx_prepare_addba`、`sdio_tx_ba_mgmt`、
`sc2355_wlan_ba_session_event` 的偏移、长度与机器码哈希均相同。
这说明参考补丁直接针对相同的 BA 代码，而不是仅因 SoC 名称相同而推测。
该检查不代表完整 ELF、重定位、模块 ABI 或其他平台配置全部兼容。
证据保存于 `logs/t551m/wifi-ba-reference-comparison.json`。

### 历史验证范围与源码移植边界

同一研究目录的 `E5_WIFI_RESEARCH_FINAL_ARCHIVE_20260723.md` 明确将问题
分成两层：全 peer rearm 对“第三台加入后全体约 70 Mbps”的退化有改善；
部分后关联客户端即使 BA 建立成功，仍只有约 70–200 Mbps，归档将其进一步
指向固件内部 AP/vdev 聚合、速率或调度状态。前者有已验证的驱动侧办法，
不能因此宣称后者也已解决，也不能将约 70 Mbps 直接等同于实际 VHT20。
这些是用户旧设备的历史测试记录，本轮未在 T551M 上重新复现或验证。

归档最终推荐的是 `20260723_E5_rollback_to_v4_nonatomic_gate120` 中的
静态版本：全 peer rearm + non-atomic、非阻塞 120 ms 间隔，保持原厂 WCN。
原子 120 ms、450 ms、force-awake 和 WCN single-flight 均未成为该归档的
日用首选；因此后续移植应区分本次给出的通用 KPM 与后来实测选定的基线。

在当前 6.18 源码中落地时，应使用结构体成员与正常驱动生命周期，并核对
AP/GO 上下文、并发和重试语义。当前 `peer_entry.time[]` 是 `s64`，旧版
KPM 假定每个时间戳为 16 字节的 `timespec64`，函数名、ABI、编译布局也有
变化；不应将这份运行时二进制或 Android 地址偏移直接套到现有 OpenWrt。
本轮完成补丁机制与缺口核对，未加载 KPM、未改变实机 BA/带宽策略。

用户随后确认当前主要问题是接入顺序导致的单客户端低速，而非集体降速。
两台保持关联的现场对照、固件采样及修订方案见
[接入顺序与恢复方案](WIFI-JOIN-ORDER-20261010.zh-CN.md)。
