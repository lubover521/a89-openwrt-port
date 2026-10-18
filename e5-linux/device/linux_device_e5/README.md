# E5 功能移植

本目录把截至 `37c5e7b` 的 T551M 通用功能移植到荣悦 E5；独立分支为
`feat/e5-feature-port`。使用 E5 自己的内核基础、设备树、固件和校准数据，
不把 T551M 的整机镜像或设备树刷给 E5。内部 `t551m-*` 文件名暂作为兼容接口保留，
不代表界面固定显示该机型。

## 已纳入的功能

| 范围 | 内容 |
| --- | --- |
| 网页 | Aurora 主题及设置、蜂窝看板、短信及转发、设备管理、CPU 设置；移除重复旧入口 |
| 双卡 | 查看/控制槽位与实际上网卡分离；切换上网卡后同步查看槽位；分别查询信号、锁频/小区、AT 和流量池 |
| 基带 | 三个独立 AT 工作通道；拨号前回放；未设置 WAN 模式时不额外改模式；国内运营商及编码名称处理 |
| 流量/短信 | 网页与屏幕统一流量池和清零；按 SIM 统计；接收短信及时归档并释放 SIM 存储；转发历史滚动布局 |
| 屏幕 | 状态栏、标题栏加载动画、可配置底部导航、锁屏惯性上滑、壁纸/透明度/明暗主题、字号、网速单位、图标和间距修复 |
| 通话 | DTMF、息屏来电、HFP 按键与音频路由、通话音量和切换延迟修复的软件实现 |
| USB | 自动/主机/设备角色、NCM/RNDIS 等共享模式、外设提示、网卡自动 LAN 绑定；共用控制器 DMA/角色切换修复 |
| 电源 | 长按电源菜单、充电动画、拔线关机、息屏触控联动；保留 E5 原生 PWM 背光和触摸固件 |
| CPU/内核 | 调频、调速器、温控接口；KVM、容器、BTF、BPF、跟踪与性能分析配置；Docker 按需启动 |
| 无线 | 共享 SDIO TX 所有权/错误处理修复；默认关闭固件调试日志；使用 E5 自己的 WCN 固件 |
| NV/启动 | 厂商服务使用本机隔离工作副本；物理 NV 分区只读；保留 TF 启动和原有默认系统设置 |

具体通用功能设计见 [屏幕说明](https://github.com/Enceka/infoscreen/blob/main/docs/device-ui.zh-CN.md) 及仓库内已有修复记录。
2026-10-11的[屏幕内存与低唤醒修复](https://github.com/sprd-linux-devs/e5-linux/blob/main/docs/SCREEN-MEMORY-FIX-20261011.zh-CN.md)
使用同一构建入口，E5同时包含通话事件推送、共用长连接读取及插件SDK配套修改。
“纳入”表示软件实现已移植，不等于每项外设、通话和无线压力场景均通过 E5 实物测试。

## E5 专属差异

- 从固定内核 `020b970e351e` 的独立工作树构建。拒绝含 T551M 充电、背光和电池配置补丁的源码树。
- 保留 AW32257 充电、AW87xxx 功放、TLSC6x 触摸及 E5 原生设备树。
- LTE 候选保留 E5 的 B38：`1,3,5,8,34,38,39,40,41`；NR 仍动态查询。
- E5 的 64 位厂商程序在 cmdline 后还会解析 bootconfig。选择 A 槽时，两处输入保持一致，
  且 cp_diskserver 等待准备完成再启动，防止抢先加载 B 槽旧 NV。所有 NV 名称仍指向各自隔离的 loop 设备。
- CPU 开机电压偏移已核验 E5 原厂 SML 的原生接口，网页与屏幕均可设置。
  三个供电域的 31 个频率档位与 PMIC 实测通过，范围 −50～+25 mV、步进 3.125 mV，
  保存后重启生效；仍校验 SoC 与双槽固件，未知或混用固件不开放调压。
  交付恢复原厂电压，详见 [调压验证](https://github.com/sprd-linux-devs/e5-linux/blob/main/docs/CPU-CONTROL.zh-CN.md)。
- 不复制 T551M 固件、NV、MAC、密码、热点配置及默认启动选择。
- 多客户端无线速率问题仍需专项验证，本移植不宣称已解决该问题。

## 3A 充电目标与实际能力

用户目标是 **USB 输入 3A**。本机 AW32257 的 REG01[7:4] 为保留位，不能把它当作
BQ24158 的输入限流寄存器；驱动过去混用了定义，并把电池电流限制在约 1.2A。
按 [AW32257 v1.5 芯片资料](https://doc.awinic.com/doc/202311/e1bf1d63-1a92-4bd2-9043-6357d7e236de.pdf)
修正全部 16 档电流编码与回读、补齐充电管理器的输入预算及启停接口。

仅在原厂 E5 电池参数完整匹配时，把普通温区 DCP 策略设为输入预算 3A、电池充电
上限 2.48A（板上 33mΩ 采样电阻对应的芯片最高档）。这两个数不是同一种电流。
驱动没有独立的硬件输入 3A 档位，预算读数也不是 USB 实测电流，不能承诺一定吸取 3A。
SDP/CDP、原厂电压、低温/高温 JEITA 和芯片安全寄存器保持原有边界；OTG 退出只修改
必要位，避免覆盖充电电压与终止电流。实际电流取决于电量、温度、电源和线材。

## 构建与安装

在 Linux/WSL 中使用独立的干净 E5 内核工作树；LLVM、交叉工具链和支持 BTF 的 pahole
需提前安装。不要指向 T551M 的构建目录。

```sh
E5_KERNEL_TREE=/path/to/clean-e5-linux \
E5_OUTDIR=/path/to/e5-objects \
  bash device/linux_device_e5/build-kernel.sh

# 对已有的离线 E5 rootfs 安装功能；不会写入正在运行的系统。
python3 device/openwrt_device_e5/stage.py --root /path/to/offline-e5-root
python3 upstream/stage-root-modules.py out/e5/kernel --root /path/to/offline-e5-root
```

`stage.py` 要求已有 E5 屏幕基础包和厂商服务。重复执行保留用户设置；主题 APK 校验
固定 SHA-256，首次启动默认脚本负责安装主题。模块与 boot 必须来自同一次构建。

通用镜像入口支持 `E5_FEATURES=1`，并要求匹配的 E5 模块与 infoscreen 基础仓库。
例如完成既有 BlueZ/ModemManager 构建及基础依赖后：

```sh
E5_FEATURES=1 E5_DOCKER=0 E5_INFOSCREEN=/path/to/e5-infoscreen \
E5_ROOT_MODULES="$PWD/out/e5/kernel/root-modules.tar" E5_ROOT_MODULES_ONLY=1 \
E5_STANDALONE=1 E5_DEVICE_FILES=0 bash openwrt/build-rootfs.sh
```

默认仅保留内核的容器支持，不预装 Docker/containerd/runc。用户可在刷入后
按 [容器说明](https://github.com/sprd-linux-devs/e5-linux/blob/main/docs/CONTAINERS.zh-CN.md) 自行安装；只有明确需要预装时
才将 `E5_DOCKER` 设为 `1`。

实机更新使用本机原 rootfs 制作并逐文件校验的私有差异包，配合本机 boot 头构建的新
boot_b；不是可公开分发的通用镜像。本次没有完整执行通用镜像发布流水线。

## 验证

构建启动镜像前需准备早期 F2FS 工具包：
`python3 boot/prepare-f2fs-tools.py --root /path/to/arm64-openwrt-root`。
使用 OpenWrt ARM64/musl 的 fsck.f2fs 1.16.0 及配套库，默认写入
`out/boot/f2fs-tools`。仅 userdata 根挂载失败时自动检查、修复并复查；
TF 启动跳过，正常启动不执行 fsck。详见
[恢复与插拔亮屏记录](https://github.com/sprd-linux-devs/e5-linux/blob/main/docs/F2FS-RECOVERY-AND-CHARGER-WAKE-20261010.zh-CN.md)。

```sh
python3 device/linux_device_e5/test_charger.py /path/to/prepared-e5-linux
python3 device/linux_device_e5/test_charge_profile.py
python3 device/openwrt_device_e5/test_stage.py /path/to/offline-e5-root
python3 upstream/check-container-support.py out/e5/kernel
```

充电测试执行生成的 C setter/getter，覆盖所有档位、向下取档、SDP 降流、DCP 恢复、
零电流、I2C 错误及保留位。电池配置测试覆盖温度、电压和非匹配设备；staging 测试覆盖
重复安装、用户设置保护及拒绝其他机型。另已执行共享 AT、启动回放、CPU、USB、
双卡、屏幕交互/加载动画及翻译测试。

2026-10-10 实机更新时，原 TF 系统分区仅约 1GB，安装后剩余 22MB；已保留起点、UUID、
分区名与内容，利用未分配空间扩展至 4GB，ext4 在线扩容后剩余约 3GB。没有改写 eMMC
userdata，也没有删除 TF 启动功能。

实机结果：

- 新内核 `6.18.54-e5-mobile1-g020b970e351e-dirty`，匹配的完整模块与模块 BTF。
- SIM2 已连接移动网络，AT 返回 OK；热点 AP、USB NCM、DHCP 和 SSH 正常。
- Aurora 看板完成真实浏览器登录/渲染，无页面脚本异常；网页和屏幕的状态/设置接口正常。
  同时补充 E5 返回的 `CHN-TELECOM` 别名，网页和屏幕统一显示中国电信。
- 三个 CPU policy 使用 schedutil；KVM API 版本 12，创建空 VM 成功。
- Docker 29.6.1 启动成功：overlay2、cgroupfs、cgroup v2；检查后已停止并保持按需启动。
- 九个原厂 NV 分区与本次启动前的校验值一致、均为只读，工作设备均指向私有 loop。
- 充电管理器无原先启停接口 `-EINVAL` 报错；电脑口识别 SDP，预算 500mA，
  对应有效电池电流档 496mA。电池满电，用户决定稍后再测充电器高电流与拔插。
- 待实物确认：充电器持续高电流、OTG 外设、通话/耳机听感、关机充电插拔及无线压力测试。
  默认启动系统仍保留用户原来的 Android；TF 内更新永久保存，本次验证单次进入 OpenWrt。
