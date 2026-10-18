# userdata 故障恢复、充电器插拔亮屏与 E5 OTG 部署

## 自动修复的边界

按用户补充要求，TF 启动默认跳过。普通 userdata 启动仍直接 mount；只有已选择
userdata 根系统、正常 F2FS 挂载失败后，才加载修复脚本和执行检查。没有每次
开机 fsck、全盘扫描、新增 sleep 或额外等待。早期固件读取和启动选择的只读
mount 失败也不触发修复，避免为了 TF 启动而写 Android userdata。

故障流程：确认块设备的 PARTNAME 为 userdata、F2FS magic 正确、没有挂载
（按设备号检查，含别名）和 holders，且非块设备只读；先只读 dry-run。
仅文件系统错误返回码 1/4 允许执行修复；工具/参数/I/O 类错误及干净检查不会
进入写修复。每次启动最多尝试一次。修复后再设块设备只读，复查必须返回 0，
日志不能含 Fail/ASSERT。通过后保存诊断日志、指定下一次 Linux，重启一次，
让之前可能失败的 WiFi/蓝牙早期固件加载也重新进行。

不格式化，不处理 ext4 镜像内部，不触碰物理 NV。失败保留原有救援/回退路径。
原来的 600 秒启动保护计时器会等待正在执行的检查/修复，避免中途重启打断写入。
日志进入启动镜像原有保留区域；正常 TF / userdata 启动不创建修复日志。

这是遇到已知元数据错误时的恢复措施，不能证明 F2FS 反复损坏根因已消除，也
不能恢复已经被覆盖的文件内容。正常路径没有 fsck 开销；initramfs 增加约
0.56 MiB 压缩工具包，不承诺物理加载耗时绝对为零。

## 构建

从已有 OpenWrt ARM64/musl rootfs 或工具目录准备 fsck.f2fs 及动态库：

```sh
python3 boot/prepare-f2fs-tools.py --root /path/to/arm64-openwrt-root
```

默认输出 `out/boot/f2fs-tools`。构建器校验 bundle 的 SHA256，缺失则报错，
避免发布声称支持恢复但缺工具的镜像。可用 `--f2fs-tools` 或环境变量
`E5_F2FS_TOOLS` 指定目录。必须使用兼容 ARM64/musl 的整套工具与库，不能
混入宿主机库。本次使用已用于前次人工恢复的 OpenWrt fsck.f2fs 1.16.0。
工具放在独立 `/repair` 目录，不替换正常 initramfs 的运行库。

## 充电器插入和拔出亮屏

共享屏幕 UI 根据已有状态轮询中的 `battery.online` 的布尔边沿唤醒屏幕，
插入和拔出都生效。首个状态样本只建立基线；Charging / Full / Not charging、
电流变化、充电阈值暂停均不单独触发。未增加轮询。

复用现有亮屏流程：保持锁屏、保持用户手动禁用触控的设置；正常触控随背光
恢复。屏幕已亮时只重置原有息屏计时，不弹出充电器连接通知。

## 验证

- BusyBox ash 执行真实启动函数：6 项恢复边界测试通过；既有早期固件 7 项、
  WCN handoff 6 项回归通过。
- 在 `/tmp` 中构造 128 MiB F2FS 普通文件，修改 checkpoint 节点计数并保持
  CRC 正确。在 E5 上执行即将嵌入的 ARM64 工具：dry-run 返回 1 且文件哈希
  不变，修复返回 1，复查返回 0、无 Fail/ASSERT。没有破坏实机分区来测试。
- 专项 Chromium 测试通过：四次供电边沿均亮屏且锁屏保持；满电/暂停不唤醒；
  用户关闭触控时仍保持关闭；初始化样本不误唤醒；无 JS 错误。
- 既有全量屏幕浏览器测试在 DOM mutation 断言处失败；对 HEAD 原版脚本和
  原版 mobile.js 复测得到相同结果（unchanged=200, dark=10），属于既有断言
  与当前 UI 行为不一致，不能记为本次全量测试通过。专项测试覆盖本次行为。

## E5 部署

以 CID、设备 profile、AW322 驱动和 TF 根挂载核对本机。写入 E5 mobile4
内核及匹配模块、更新 mobile.js；仅覆盖 boot_b 前 56 MiB，保留启动日志尾部。
原启动头和 mobile.js 保存在设备 `/root/e5-otg4-rollback`。
userdata 始终只读；未写物理 NV。原来的默认 Android 选择保留，指定单次
OpenWrt 用于实机验证。第一次重启因 --rearm 在默认 Android 下为 no-op 而
进入 Android；已通过本机 ADB 校验 CID，仅重设下一次启动为 slot B。

E5 启动镜像：`out/e5/boot-mobile4-recovery.img`，SHA256
`676f8d88409eabf500fd97262ac0b0e059182d71a10f0f3786852cef35c5287d`。
T551M 对应镜像：`out/t551m/boot-otg10-recovery.img`；E5 验证时仅完成构建，
随后已按用户要求部署，结果见下文。

### 最终实物验证与离线同步

用户完成三轮 OTG 网卡插拔及熄屏后充电器插入、拔出测试，回复“没问题”。
`work/e5-port/otg4-charge-replugs.txt` 记录三次 host 接入、三次 carrier on、
三次向电脑 192.168.9.43 的 DHCPACK，设备时间为 22:21:00、22:21:28、
22:21:46；`musb_suspend_busy` 为 0。接回电脑后 gadget configured，
无残留主机总线。日志捕获到一次拔线后背光由 0 恢复 255；两种边沿的屏幕
效果及保持锁屏由用户实测确认。临时日志采集已停止。

TF 根文件系统、只读 userdata 及 `/run` 无修复记录再次核对通过。
E5 离线 rootfs、匹配模块、正式 `out/e5/kernel` 和 `out/e5/boot-mobile.img`
已同步；旧输出保存在 `out/e5/release-before-otg4`。历史初次移植用的
features-update.tar.gz 不是本次重新打包的发布物。
T551M 离线 rootfs 候选为 `out/t551m/openwrt-t551m-recovery-wake.ext4.gz`，
完成 ext4 五阶段检查及压缩文件校验；随后随 T551M 部署提升为正式输出。

### T551M 后续部署

核对设备 profile、eMMC CID、OTG10 内核、userdata 内 ext4 根镜像路径及
当前 boot_b 校验值后部署。现有模块逐个校验通过，内核及模块无需更换；
只更新启动镜像和 mobile.js。旧启动头与屏幕文件保存在设备
`/mnt/e5-data/e5linux/recovery-wake-rollback`，boot_b 尾部日志区保留。
没有操作 NV，默认及下次启动均保持 Linux。

重启后读取 boot_b 前 56 MiB 和 mobile.js 校验一致，boot ID 已改变。
启动日志显示 userdata checkpoint 为 clean-unmount，10.47 秒直接挂载成功，
16.33 秒 switch-root，45 个早期模块全部加载成功；没有 f2fs 检查/修复阶段，
`/run` 没有修复标记或日志。健康 userdata 启动未执行 fsck。
电脑 USB DHCP 恢复后 SSH 正常；蜂窝 WAN 的 sipa_eth0 为 up、热点为 AP，
USB gadget configured，无残留主机总线，全局 autosuspend 仍为 2。
屏幕 API 返回供电状态布尔值，cog/WPE 进程正常，新 mobile.js 已加载部署。
验证记录：`work/t551m/recovery-wake-verified.txt`。

本轮没有再次进行 T551M 的物理充电器插拔或 OTG 网卡三轮测试；OTG10 内核
保持此前已通过实物测试的版本，共享亮屏逻辑已在 E5 实测及浏览器专项测试通过。
没有人为破坏 T551M 分区来触发恢复。

正式 `out/t551m/openwrt-persistent-boot.img`、对应 manifest/init、离线
`openwrt-t551m-persistent.ext4.gz` 及 `SHA256SUMS-persistent` 已同步。
旧正式产物保存在 `out/t551m/release-before-recovery-wake`。
新启动镜像 SHA256 为
`64c14981b48587aca97d41a9ce4b1baec6dc10466c4595b69ac02977ab4b6a24`。

## 2026-10-12：孤立节点导出询问导致无人值守恢复中断

T551M 本次停留在 initramfs 救援系统，并非仍在后台慢慢修复。userdata 挂载
报 `SIT is corrupted node# 7138 vs 6750`，约 19.49 秒进入检查，22.37 秒
以 255 退出，随后走原有 Android 回退。检查报告另有 NAT 与目录项错误。

核对所用 f2fs-tools 1.16.0 的 `fsck_verify()`：非 Android 构建发现孤立
节点后会询问是否导出到当前工作目录的 `./lost_found/`。`-f`、`-y` 和
`--dry-run` 均不跳过这个询问；原脚本输入来自 `/dev/null`，`scanf` 遇到
EOF 触发断言。因此不能把返回 255 加入允许写修复的列表，也不能仅加 `-y`。

公共恢复脚本的检查、修复、复查三次调用均提供一次 `n`，明确拒绝可选的
宿主目录文件导出，不关闭文件系统元数据修复。有限的一次输入保留意外询问
时失败退出的行为，避免无限 `yes` 掩盖工具流程变化。TF 跳过、健康 userdata
直接挂载、每次启动最多一次修复、分区身份与未挂载检查、只读检查及修复后
复查条件全部保持。没有新增后台进程、轮询或正常启动等待。

新增回归覆盖三阶段均回答孤立节点询问，以及出现第二次意外询问时退出 255、
不写修复、不重启；共 8 项 BusyBox 测试通过。T551M 使用实际 ARM64 工具和
块设备只读设置复现，修正后的初次检查约 3.34 秒完成并返回 1，不再因 EOF
断言退出。该结果仅说明恢复分支可继续，不代表磁盘当时已经修好。

这项修正进入 E5、T551M、M8 共用的启动镜像构建路径。现存设备必须更新
boot 镜像才会采用它，仅更新 LuCI / 根文件系统不改变 initramfs。
本次修复的是恢复流程，F2FS 原始损坏原因仍未确定。

### T551M 实际恢复与镜像同步

在任何写修复前，将未挂载 userdata 的完整 23,467,130,880 字节压缩保存到
电脑，并在接收时解压校验 gzip CRC、原始字节数及 SHA256。原始分区 SHA256
为 `b5d5f0c62003146f237ef3e3858419a8398bc3c996e618c519e9b54716f23264`。
另保存原 boot_b 和全部故障日志；这些私有备份不进入仓库。

随后用同一份公共脚本在救援系统执行，三阶段返回 1 → 1 → 0，耗时约 9.12 秒。
复查中的不可达 NAT、SIT 位图、节点/块/段计数均通过。userdata 只读挂载成功，
原来的 2 GiB OpenWrt 根镜像仍在，profile=t551m、默认启动=linux。
对根镜像使用只读 loop 和 `e2fsck -fn` 完成五阶段检查，返回 0；没有写修复
内部 ext4，也没有替换根镜像、刷 NV 或恢复出厂设置。

新 boot_b 仅写前 56 MiB，保留尾部启动日志；完整回读 SHA256 一致后才重设
下次 B 槽。E5 / M8 仅重新构建离线镜像，本次未连接、未实机部署。
三款镜像逐项解包对比：kernel、init、45 个模块及工具库完全一致，唯一变化
都是 `etc/f2fs-repair.sh`。

| 机型 | 修正版镜像 | SHA256 |
| --- | --- | --- |
| T551M | `out/t551m/boot-otg10-recovery2.img`，已同步正式 `openwrt-persistent-boot.img` | `ffdaef0b77b80c7d57626fb4739f5ba1c76a91132a70e7dbf52d7e67d8cd6d65` |
| E5 | `out/e5/boot-mobile4-recovery2.img`，已同步正式 `boot-mobile.img` | `01dc9d382ac8ef8cf865dc7d5af4a8431dba3faa124c8e3978a3ba2da7057d37` |
| M8 | `out/m8/boot-openwrt-persistent4.img` | `92e87e2cb7ff7542a944c573900b05b209111d0a7cec7d7a5279af74594eb42e` |

修复会按 fsck 规则处理损坏目录项与不可达节点，并不保证全部旧文件内容无损；
完整故障快照已保留，可用于后续追查或文件恢复。不会把全分区备份加入日常开机。

更新后启动实测：userdata 在 9.79 秒直接挂载，15.75 秒 switch-root，45 个
早期模块全部加载成功；没有 F2FS 检查/修复阶段或 attempted 标记。userdata
和 ext4 根均为读写，boot_b 前 56 MiB 回读与新镜像一致。USB gadget configured，
SSH、热点 AP、屏幕页面和 WPE 进程正常；基带自动注册联通并拨号成功，约
67.8 秒 WAN up，外网定向 ping 3/3 通过。本次未改变基带启动策略或调压设置。
