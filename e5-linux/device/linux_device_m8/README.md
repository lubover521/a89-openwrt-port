# VIPME M8 / T157

适配分支：`feat/vipme-m8-openwrt`。目前为硬件启动阶段，尚不是可日用的完整 OpenWrt 固件。

## 实机确认

| 项目 | 原厂实机数据 |
| --- | --- |
| 型号 / 产品 | VIPME M8 / ums9157_2h10_native |
| SoC 平台 | T157，UMS9620 / qogirn6pro |
| Android 内核 | 5.4.210，2024-01-18 |
| 启动格式 | Android boot v4，A/B；已解锁 |
| 存储 | userdata 为未加密 F2FS，GPT 动态识别 |
| 内存 | bootloader 报告 3 GiB，Android 可见约 2.38 GiB |
| 屏幕 | lcd_st7796u_yihua_mipi_hvga，PWM 背光 |
| 触控 | TLSC6x，I²C 3-002e；保留设备内原厂固件 |
| 无线 | Marlin3lite SDIO，使用本机提取的固件及配置 |
| USB | Android 使用 25100000.dwc3；不是 E5/T551M 的 MUSB 路径 |
| 充电 | 6-006b，BQ2560x 家族；不直接套用其他机型充电配置 |
| 电池 | 原厂 DT：3075 mAh、终止电压 4.25 V |
| 扬声器功放 | AW87xxx，I²C 6-0058 |

## 启动证据（2026-10-12）

第一轮 `6.18.54-m8-probe1` 已进入 `/init`，并自动回到 Android A。
CPU、内存、主要时钟、ADI、PMIC、RTC、GPIO 和 SoC 温度传感器已出现驱动日志。
eMMC 与 USB PHY 因主 PMIC 稳压器未匹配而延迟初始化：M8 DT 使用
`sprd,ump962x-regulator`，现有驱动只匹配 `sprd,ump9620-regulator`。
第二轮增加原厂兼容名后，eMMC 全部分区正常出现，USB NCM/ACM 可用，
Android A 控制区恢复读回通过，自动回退成功。eMMC 保留本机 HS400ES，
不沿用已取消的 FM_U20 限制。

第一轮没有挂载 userdata、没有加载基带、没有读取或修改原始 NV。
本机身份校验因为 eMMC 未出现而主动拒绝分区写入，随后重启，A/B 回退正常。
完整日志留在被 git 忽略的 `out/m8/probe1-logs/`。

第三轮已注册 TLSC6x、PWM 背光及电量计；CPU 调频和显示主设备尚未绑定，
USB PHY 未通知 BC1.2，导致电池管理误报未接电。第四轮分别修正：

- 使用本机 `cpufreq-data-v1` 三簇绑定，固件返回 policy0/4/7 的频率、电压表；
  调度器调频、电压偏移与原厂 CPU 温控已接入公共控制后端，详见
  [CPU 电压与温控](cpu-controls.md)。
- 显示主设备不再等待未编译的 DPU1/DP，`card0-DSI-1`、320×480 fb0 已注册。
  最小探测时用户反馈只有背光；第五轮色条窗口未观察到。随后完整 OpenWrt
  首轮试运行中，**用户已确认屏幕能够正常显示**，日志也记录到触控坐标。
- USB3 PHY 接入本机 PMIC BC1.2，电脑口识别 SDP；电池管理显示 Charging，
  输入上限 500 mA、电池电流约 430 mA。充电器高电流及 OTG 尚未验证。
- 充电芯片原厂 ko 使用 REG0E[7:1] 的 3856 + 8×code mV 编码，保留 bit0，
  终止电压按照原厂 4250 mV 向下取整为 4248 mV；不能套用 T551M 的 REG04 设置。

第五轮并入公共 Wi-Fi 发送路径修复，并默认关闭无线固件调试日志。
所有短时探测均已自动返回 Android A；第四轮回读时 USB 重新枚举中断过一次，
`probe4-logs/persist.bin` 长度不足，以此前完整的 `probe4-live.txt` 和 pstore 为准。
第五轮持久日志完整（4 MiB）。触控日志已记录实际手指坐标。

完整系统首次试运行使用 `/data/e5linux/openwrt-m8.ext4` 文件，不重分区。
本机固件单独提取，原始 NV 只读，基带服务使用本机隔离工作副本。
网页和屏幕程序已离线同步，**部署不等于功能验证完成**。
临时试运行服务 8 分钟后重启回 Android；手动创建 `/run/m8-keep-running` 可延长。
试运行 USB DHCP 不向开发电脑发布默认网关和 DNS，避免抢走现有网络。

完整试运行一：USB SSH、网页和屏幕启动成功，基带 AT 能响应。用户未插 SIM，
两槽均报未插卡符合实际，不能据此声称蜂窝上网、短信或通话已验证。
本机 NV 隔离校验九个原始分区全部通过。约 564 秒 Panfrost 在 GEM 对象查找后
遇到空指针并 panic，自动返回 Android A；详见 `out/m8/full-trial1-logs/`。
目前只增加拒绝异常提交及错误记录，**根因和稳定性仍待查证**。

完整试运行二：修正 WCN 对旧设备树 GNSS 调试字段的强制要求后，本机无线
固件下载、SDIO 枚举成功；热点启动时出现 `cmd_tx.c:2352` 固件断言，尚未可用。
手机声卡去除未编译 DisplayPort 的两条独立音频链路后，继续暴露旧设备树缺少
新版音频驱动需要的 genpd 绑定，约 32 秒访问音频寄存器触发 SError。已自动
返回 Android A，证据在 `out/m8/full-trial2-logs/`。

完整试运行三：在内存中的设备树补齐旧 `agdsp-access` 到 genpd 的绑定及九类
消费者，不写入原厂 dtb/dtbo。声卡、DSP 启动成功，用户确认短信提示音清晰。
同步修正屏幕 RPC 被 DSP 就绪等待阻塞的问题。

发现并处理的后续问题（不能与首次成功显示混为一谈）：

- Wi-Fi 原厂根据 IPD efuse 选择普通/XPE 配置，移植驱动却把 AB 芯片全部当作
  XPE。当前芯片原厂使用普通配置；临时恢复同机普通配置后 AP 加密启动成功。
  `wifi.py` 按原厂模块的寄存器读取序列恢复选择逻辑，读取失败不猜配置。
  该轮早期多次 assert 后出现 TX 队列超时，需新启动继续验证数据传输。
- 第三轮实物灰屏，但读取 DRM 帧缓冲可见完整锁屏。启动 39 秒日志显示
  DPU IOMMU invalid read（0x15600000），驱动的 64 位 DMA mask 与 32 位显示层
  地址字段不一致。`display.py` 改为 32 位 DMA mask 并记录完整 DMA 地址，
  待第四轮实物验证；不将截图正常当作实屏已修复。
- 上轮异常退出遗留一份无效 `nr_fixnv2_a` 隔离副本，配对主副本有效。
  NV 启动代码原先在配对恢复之前检查变化来源，导致提前退出；现先恢复已追踪、
  未挂载的工作副本配对。未知副本、双份损坏仍拒绝启动，不改原始分区。
  恢复后 AT、ModemManager、联通注册及外网 ping 通过，九个原始分区校验通过。
- M8 加入独立 AT 通道路由；`cp_diskserver` 就绪等待改为 BusyBox 支持的整秒，
  避免不支持小数 sleep 的镜像立即耗尽重试；补齐 `e5-modemd` 启动链接。

完整试运行四：32 位 DMA 分配后 DPU 内存访问错误消失，用户确认画面和多次
息屏/亮屏正常；热点连接、网页及外网上网正常。基带、三路 AT 和声卡均自动
启动，九个原始 NV 分区再次校验通过。蓝牙另发现原厂 `btmac.txt` 全零，改为
从同机 Android 的 `[Adapter] Address` 恢复本机地址（不迁移配对密钥）；
控制器注册和发现附近设备通过，通话/耳机音频尚未验证。干净根文件系统须创建
`/etc/bluetooth/keys`，供持久配对目录链接使用。

内核和全部模块必须完整构建后一起安装，禁止把新 BTF 模块和旧 Image 混用。
`package-kernel.py` 生成的 `module-links.sh ROOT` 必须在解包 modules.tar 后执行，
供 OpenWrt kmodloader 和音频 helper 使用，不能只安装 canonical 模块目录。

## 代码来源与隔离

- 内核基线：`linux-lts-e5` 的 `020b970e351e`。
- UMS9620 时钟、IPA 电源域、USB PHY 和温度驱动来自 MU300 已提交版本；
  提交及逐文件 SHA256 见 [port/sources.json](port/sources.json)。保留原许可证。
- `prepare-kernel.py` 适配不同版本的 PLL、复合时钟及 reset 锁接口。
- 使用独立 kernel worktree / object 目录，不修改 E5、T551M 的构建目录。
- M8 电压使用本机已核验 SML 接口；不复制 T551M 的 152 网络模式或 E5 音量表。

## 可复现流程

先以 `collect.py --serial SERIAL --out NEW_DIRECTORY` 留存启动相关原厂镜像，
每个分区都与设备端 SHA256 比对。该工具不备份 NV。
`collect-files.py` 提取本机 Android 固件及依赖，不使用其他设备的配置。

注意：本机 Magisk 的 `su` 即使通过 `adb exec-out` 仍会启用 ONLCR；
读取二进制前必须执行 `stty -onlcr`，不能事后用替换 CRLF 的方式修补。
当前验证有效的原始备份是 `dumps/m8-stock/`；早期 `m8-original/` 不可用于恢复。

```sh
M8_KERNEL=/home/kano/m8-port/linux \
M8_BUILD=/home/kano/m8-port/build \
bash device/linux_device_m8/build-probe.sh

python3 device/linux_device_m8/make-probe.py \
  --backup dumps/m8-stock --kernel out/m8/probe \
  --busybox work/t551m/busybox --out out/m8/boot-probe.img
```

`flash-probe.py` 校验型号、设备名、eMMC CID、启动槽、镜像完整性和上传读回，
只写 boot_b 和 misc 的 32 字节 A/B 控制区。后续试验必须显式指定已知的
`--previous-image` 并通过前 56 MiB 校验，不能覆盖未知 boot_b。
试验 init 验证身份后先恢复 Android A，短时采集日志并自动重启。
试验期间保留未使用时钟和电源域，仅用于定位，不代表正式版省电策略。

## 公共通知音冷启动修复（2026-10-12）

M8 首次试听偏大、第二次正常，是公共 `e5-volume prepare` 仍用
`t551m|e5` 白名单，导致新机跳过 FAST_P 静音预热。现已取消机型判断：
默认输出为 `speaker` 且处于 `SUSPENDED` 时先播放 100 ms 全零 PCM，
随后恢复用户保存的音量。蓝牙输出与热播放不增加预热，普通音量调整仍不唤醒声卡。
共享 staging 会给 E5、T551M 及新机使用同一脚本，不增加常驻服务。

已在 M8 部署并确认预热顺序、原音量 6 档保留，以及结束后恢复 `SUSPENDED`；
11 项回归测试通过，覆盖新/未知机型、蓝牙、静音及被动音量更新。
首次与后续试听的实际音量一致性尚待用户单独确认。

### 内置铃声数字杂音：已定位并实机确认修复

用户确认上传的来电音频正常，只有内置电话铃声和短提示音出现数字撕裂声。
`prepare-root.py` 原先对除少数归档外的所有文件执行 CRLF → LF，误处理 WAV：
`call.wav` 从 180524 字节变成 180523，`beep.wav` 从 88364 变成 88363；
两者均与仓库原文件执行该替换的结果完全一致。少掉一个字节后，后续 PCM16
采样错位，而 WAV 头仍声明原长度。`ding.wav` 无此字节组合，校验正常。

公共 `device/linux_device_common/staging.py` 保留含 NUL 或非 UTF-8 的二进制内容，仅规范化文本换行；
M8 根目录生成、E5 文件复制及共享网页部署采用同一逻辑。共享屏幕 staging
重新按二进制复制全部三个内置声音，因此后续 E5/T551M/M8 更新也能修复旧资产。
回归测试覆盖含 CRLF 的真实 WAV、PCM 长度、未知二进制与脚本文本换行。

M8 已重新部署三个声音文件，逐一 SHA256 与仓库一致；原上传音频和音量 6 档保留。
**用户已确认内置电话铃声与短提示音都正常。**
先前 `mmap=0` 对照不能消除杂音，现已撤回，恢复原 `tsched=0`/mmap 播放路径；
播放结束仍正常进入 SUSPENDED。历史 POLLOUT 空间不足提示不是本次杂音根因证据，
未据此修改 DMA 驱动、DSP 参数或功放增益。

## 通话共用喇叭路由（2026-10-12）

用户确认 M8 没有独立听筒，“手机”和“扬声器”共用外放单元；原共用后端
把手机模式接到 EAR_HPL，导致手机无下行声音，外放与麦克风正常。
M8 staging 现写入 `/etc/e5/receiver-output` 为 `speaker`。公共通话后端
按这一硬件能力选择实际输出，而不检查机型名；缺少配置时仍使用独立听筒。

逻辑 receiver/speaker 选择保留，M8 两者均使用物理喇叭路径及其 codec 增益，
但手机模式必须保留原厂 Handset DSP profile 和低音量曲线，只有免提使用
Handsfree profile。首次部署误将手机的 DSP profile 也切到 Handsfree，用户
立即反馈声音过大；现已纠正并部署，临时将通话音量降至 1 档，等待听音确认。
本机 WB 音量表满档系数 Handset 为 1029，Handsfree 为 23034；不能因为
共用发声单元就共用免提音量表。蓝牙优先走独立通路，
返回手机时恢复共用喇叭；保留麦克风静音、通话音量、零音量静音和挂断后的
混音器恢复。E5/T551M 无此能力配置，原独立听筒行为不变。

已部署 M8，服务重新启动正常，读取确认逻辑 phone 对应物理 speaker。
通话状态、音量与 OpenWrt 通话控制回归测试通过。用户进一步确认媒体最小音量
正常、通话最小音量仍过大，因此增加下述通话低档范围调整。

## 通话低档范围与手机模式上限（2026-10-12）

媒体由 PulseAudio 做软件衰减，通话由 CP/DSP 直接输出，不能直接套用媒体音量。
通过驱动 `/dev/vbc_turning0` 在 RAM 内调整本机 `audio_structure` 后，
**用户确认通话最低档明显变小**。最低原生档额外衰减约 30 dB，之后逐档减小
额外衰减，到最高档为 0 dB；只改 Handset/Handsfree 的 NB/WB/SWB/FB 下行
七档系数，其他字节（含麦克风、DTMF、蓝牙）保持原样。

公共 helper `e5_call_profiles.py` 由通话后端启动时调用，M8 通过
`/etc/e5/call-low-volume-attenuation-db=30` 启用。它校验本机固件布局、长度和
当前驱动表，单次完整写入并读回验证；重复启动直接复用相同结果，不叠加衰减。
原 `/lib/firmware/audio_structure` 及 NV 不改，无额外守护进程或轮询。
无此配置的 E5/T551M 不访问调参设备。

按用户要求，M8 另设 `/etc/e5/receiver-volume-ceiling=5`：手机模式音量条
仍为 0–15，但最高仅等效于未限幅时的第 5 档，中间范围重新映射；扬声器和
蓝牙保留各自完整范围，并非强制当前音量始终最大。WB 实测满音量手机选择
DSP step 3，免提选择 step 7；不能把用户界面的第 5 档误当作 DSP step 5。

已实机验证“重新加载原厂表 → 启动通话服务 → 自动恢复调整后 RAM 表”，
无需依赖前一轮临时调参；原文件 SHA256 不变，服务正常。回归测试覆盖
其他字段逐字节不变、最高档不变、未知布局拒绝、重复启动、手机上限及
免提/蓝牙不受上限影响。未为验证而重启整机或中断通话。

## Type-C 充电与 OTG（2026-10-12，probe9–11）

用户反馈 C-C 充电器有时需重复插拔、已可达到约 10 W；OTG 外设完全没有供电。
probe8 只编译了 `USB_DWC3_GADGET`，原厂 DT 把 Type-C extcon 和 VBUS supply
放在 DWC3 父节点，通用 of-simple glue 没有处理。日志已出现 attached-source
（CC state 5），而 boost 仍关闭，说明识别了主机连接但执行链缺失。

probe9 启用 DWC3 dual-role、XHCI，并在 QogirN6Pro glue 连接原厂 extcon、
真实 VBUS regulator 和 child role switch。该 DT 的 usb-phy[0] 是 dummy，
真正的组合 PHY 是 usb-phy[1]，不能只依赖 DWC3 原有 usb2 PHY 的 set_vbus。
先停止 BC1.2 检测、切换 PHY 和控制器，再核对 CC 状态并开启升压；退出时
先关升压再恢复外部充电检测。拔插由通知驱动，只有启动等待角色节点时有界重试，
没有常驻角色轮询。充电电流、截止电压和温控参数不因本次修复改变。

Type-C 不再用软件 500 ms 计数器丢弃已由硬件去抖的 attach；attach/detach
同时锁存时按当前 CC 状态重建 partner。修正 partner 错误指针检查及工作项
初始化顺序。BC1.2 保留被合并的拔出事件，重新插入先清旧检测结果，并将
D+/D- 交回检测器，避免快速拔插后沿用上一根线的充电类型。
屏幕 USB 状态读取标准 usb_role，并兼容自动角色驱动隐藏 role 文件时的
Type-C extcon 状态，支持 DWC3 的 OTG 提示。

已部署 `6.18.54-m8-probe9` / `boot-openwrt-trial5.img`。完整构建、125 个匹配
模块及容器支持检查通过；实机 USB NCM、串口、AT、热点启动和屏幕 HTTP 正常。
debugfs 确认 device 模式，regulator_summary 确认控制器绑定实际 vddvbus，
电脑模式下 boost 关闭。屏幕 API 实机 ucode 编译通过。
probe9 用户实测：C-C 第一次不充电，之后正常；OTG 仍没电。回读实际 phandle
确认父节点 extcon 顺序为 **GPIO VBUS（0x116）、Type-C（0x64）**，初版 glue
误订阅 index 0，因而一直没有收到 USB-HOST=1。probe10 按 provider compatible
选择 Type-C 节点，不再假定它是第一个。重新部署验证前不能宣称 OTG 已修复。

probe10 已部署，用户确认本轮充电正常，网卡仍不能联网。日志确认主机切换、
升压开启成功，并枚举了 USB2.1 Hub、USB 10/100/1000 LAN 和 USB3.0 Card Reader；
拔出后 boost 关闭，主机总线注销，回到电脑模式正常。因早期 M8 kernel 未启用
USB 网卡/存储类驱动，尚无网卡接口；probe11 增加 RTL8152、ASIX、CDC/NCM、
RNDIS host、SMSC、USB storage/UAS 及 HID 驱动。

probe11 / trial7 已部署，实机确认上述驱动注册、正确 Type-C provider 绑定，
USB NCM、串口、AT、充电和屏幕 HTTP 正常。**用户确认 OTG 网卡完全工作正常。**
日志确认 r8152 创建 eth0、热插拔自动加入 br-lan、carrier on、DHCP 成功分配
192.168.9.43；采样收发计数持续增长，rx_errors/tx_errors 均为 0。拔出后 boost
关闭并恢复 device 模式，重新接回电脑后 NCM 再次获取地址、SSH 可访问。
此次是实际网卡连接和通信验证，不代表所有 USB 外设或长期吞吐均已测试。

## 剩余完整适配

持久启动：`make-trial.py --persistent` 保留本机 CID 校验、M8 镜像选择和
早期 Android A 回退，但不再在 initramfs 中强制把 default-boot 写回 android。
现有根镜像需设置 `/etc/e5linux/default-boot` 为 `linux`，并禁用
`S99m8-trial` 的 8 分钟试运行重启。正常启动由 e5-boot-ok 重新设置 B 槽，
启动失败仍可回退 Android。未指定 --persistent 时仍保持原来的试运行行为。

机型显示：stage 提供 `device-model=VIPME M8`、`device-hostname=VIPME-M8`，
公共身份钩子更新系统显示型号，网页沿用 ubus 元数据。默认主机名迁移保留用户
自定义名称；SoC board id、设备树兼容串和系统发行版名称不变。

2026-10-12 热点 IPv6：试运行配置不再禁用整个 LAN 的 RA/DHCPv6。
实机蜂窝 IPv6 外网可达，热点客户端已获得公网 SLAAC 地址并可由设备 ping 通；
用户随后确认手机端 IPv6 外网测试正常。需要避免开发电脑经 USB 改变上网路径时，
请在测试电脑的对应 USB 网卡禁用 IPv6 路由器发现，不要关闭热点的 IPv6 通告。
中文 SSID 沿用公共 UTF-8 链路，实机中文名称保存和广播正常，长度上限 32 字节。

- 存储、USB gadget / OTG 和可靠回退实测。
- 本机基带依赖、独立 NV 工作副本、双卡和蜂窝数据。
- Wi-Fi、蓝牙及本机校准数据接入。
- 屏幕、触控、背光、实体键、音频、充电及电量。
- CPU 调频、温控和有证据支持的电压控制。
- 公共网页插件、屏幕面板、短信、通知音、开关机策略及独立刷机包。

各项必须以实测结果更新，不能仅凭成功编译标记完成。
