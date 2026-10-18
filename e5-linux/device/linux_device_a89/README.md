---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '086b2dd3-9a4d-47ef-b45d-e2732f2210a9'
  PropagateID: '086b2dd3-9a4d-47ef-b45d-e2732f2210a9'
  ReservedCode1: '8a682600-e0dd-4391-b389-5a51a46daa8c'
  ReservedCode2: '8a682600-e0dd-4391-b389-5a51a46daa8c'
---

# 百合 A89（Unisoc T157 / UMS9157）Linux/OpenWrt 移植 — 脚手架

> **状态：脚手架（scaffold），尚未在任何 A89 实机上验证。**
> 本目录由 [linux_device_m8](https://github.com/sprd-linux-devs/linux_device_m8)
> （VIPME M8，同为 Unisoc T157 / UMS9620 qogirn6pro 平台）的实测脚本适配而来，
> 适配方式与上游 `devices/m8`、`devices/t551m` 的多机型模式一致。
> 所有依赖真机数据的部分都改为**运行时从 identity.json 强制校验**，
> 而不是写死未经证实的机型字符串。

## 设备信息（来自公开资料，待真机确认）

| 项目 | 百合 A89 | 参考：VIPME M8（已实测） |
|---|---|---|
| 型号 / 板号 | 百合 A89（深圳众鑫百合，移动定制）——getprop 值**待采集** | VIPME M8 / `ums9157_2h10` |
| SoC | 紫光展锐 T157（UMS9157，UMS9620 / qogirn6pro，4×A76+4×A55） | 同为 T157 |
| 系统 | Android 13 | Android 13（内核 5.4.210） |
| 屏幕 | 3.5 英寸 480×320 IPS | ST7796U MIPI HVGA，PWM 背光 |
| 触控 | 未知（同类机型多为 TLSC6x） | TLSC6x，I2C 3-002e |
| 充电 | 未知（同类多为 BQ2560x） | BQ2560x 家族 |
| 无线 | 未知（同类多为 Marlin3lite SDIO） | Marlin3lite SDIO |
| 存储 | 3+32GB | 3GB RAM |
| 分区 | 推测 A/B（待 misc dump 确认） | A/B，Android boot v4 |

## 与 M8 适配的差别（必须真机确认后再改）

1. **机型身份**：M8 版本把 `VIPME M8` / `ums9157_2h10` 写死在脚本里；A89 版本
   由 `collect.py` 首次运行时把真机的 model/device/brand/platform/CID 记录进
   `dumps/a89-stock/identity.json`，此后所有脚本（make-probe / flash-probe /
   make-trial / collect-*）都会拒绝身份不符的手机。
2. **probe-module-order.list**：当前是 M8 的模块顺序（同为 T157 的合理起点），
   **必须**用 A89 自己的 `modules-load.txt`（采集自 `/vendor/lib/modules/modules.load*`）重新生成。
   （文件用 `.list` 扩展名：它是逐行执行的运行时数据，不能是会被注入水印的 .txt）
3. **build-probe.sh**：沿用 M8 的 T157 内核配置（UMS9620 时钟、qogirn6pro
   pinmux、DWC3 双角色 USB、BQ2560x 充电驱动）。充电芯片型号必须用 A89 的
   `i2c.txt` 采集结果确认；若不是 BQ2560x，改 `CONFIG_CHARGER_BQ2560X_SPRD`。
4. **prepare-kernel.py / package-kernel.py**：直接复制自 M8（平台级内核接口
   适配器）。若 A89 的 live.dtb 与 M8 的 DT 存在差异（背光、面板初始化、
   按键矩阵），需要在这里追加设备树补丁。
   同时依赖的平台文件也一并来自 M8（同为 T157 平台共享）：`port/`
   （UMS9620 时钟、qogirn6pro pinctrl、BQ2560x、SSPHY 等固定源码+完整性清单）、
   `charger.py / usb.py / usb-role.py / audio.py / gpu.py / display.py / wifi.py`
   （各子系统补丁运行器）、`sprd_virtual_thermal.c`、`dwc3-role.h`。
5. **固件**：WCN 无线固件、AGDSP 音频镜像等**只能从你自己的 A89 上提取**
   （collect-files.py），不能用 M8 或任何其他机器的。

## 使用流程（真机到手后）

```bash
# 0) 手机：开发者选项打开 USB 调试，插电脑，确认 adb devices 可见、Magisk 授权

# 1) 采集（只读，含 identity.json 生成；先备份再谈刷机）
python3 device/linux_device_a89/collect.py \
  --serial <序列号> --out dumps/a89-stock

# 2) 提取本机固件（Wi-Fi/音频等，仍然只读）
python3 device/linux_device_a89/collect-files.py \
  --serial <序列号> --out work/a89-device-files --backup dumps/a89-stock

# 3) 构建探测内核（Linux 主机/容器；见顶层 README-A89移植指南.md 的云端编译方案）
A89_KERNEL=<linux 内核树> A89_BUILD=<构建目录> \
  bash device/linux_device_a89/build-probe.sh

# 4) 生成试启动镜像（用 A89 自己的原厂 boot_b 备份，保留原厂 DTB）
python3 device/linux_device_a89/make-probe.py \
  --backup dumps/a89-stock --kernel out/a89/probe \
  --busybox work/busybox/ext/usr/bin/busybox --out out/a89/boot-probe.img

# 5) 刷试启动（只写 boot_b + misc 里 32 字节；手机需在充电、电量 ≥5%）
python3 device/linux_device_a89/flash-probe.py \
  --serial <序列号> --backup dumps/a89-stock --image out/a89/boot-probe.img

# 6) 设备试运行 ~4 分钟后自动回 Android A；回来看证据
python3 device/linux_device_a89/collect-logs.py \
  --serial <序列号> --out out/a89/probe1-logs --backup dumps/a89-stock
```

## 安全设计（继承自 E5/M8 上游）

- 只写 `boot_b` 和 `misc` 偏移 2048 处的 32 字节 A/B 启动控制块；
  `boot_a`、GPT、userdata、NV 全部不动。
- 试启动 init 第一步就是把 Android A 槽设回默认并读回校验，之后才做硬件探测；
  超时/panic 自动重启回 Android A。
- flash 前强制校验：机型身份 + eMMC CID（同一台物理机）+ 解锁状态
  （`verifiedbootstate=orange`）+ 电量 ≥5% / ≥3.5V / 接电 + 镜像哈希与分区大小。
- `--previous-image`：后续每一轮试刷前校验 boot_b 当前内容，不覆盖未知状态。

## 许可与致谢

- 本目录脚本以 MIT 许可修改自 sprd-linux-devs/linux_device_m8（MIT）。
- 上游方法学与安全设计来自 sprd-linux-devs/e5-linux 及 dikeckaan/mu300-linux。

> AI生成