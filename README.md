---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'dd87b573-bfd1-4b85-aa8b-03e0e25153bf'
  PropagateID: 'dd87b573-bfd1-4b85-aa8b-03e0e25153bf'
  ReservedCode1: 'b9f69921-7321-41cd-9a45-cebe679a50ff'
  ReservedCode2: 'b9f69921-7321-41cd-9a45-cebe679a50ff'
---

# 百合 A89 · OpenWrt 刷机包移植工作区

> 目标：参考 [sprd-linux-devs/e5-linux](https://github.com/sprd-linux-devs/e5-linux)
> （荣悦 E5，展锐 T158/UMS9621 上的 Debian + OpenWrt），为**百合 A89**
> （展锐 **T157/UMS9157**，Android 13，3.5 英寸老人机）适配 OpenWrt。
>
> **当前状态：阶段 0 完成（脚手架就绪）。手机不在手边，所有依赖真机的
> 步骤都已准备好，等手机回来即可开跑。本工作区没有任何经过 A89 实机
> 验证的内容——这是诚实的现状，不是缺点：上游 M8（同芯片）也是从
> 同样的脚手架起步、用 11 轮"刷→测→回退→改"才到达可用状态。**

---

## 1. 为什么这条路走得通（调研结论）

| 关键事实 | 来源 |
|---|---|
| A89 芯片是展锐 **T157（UMS9157）**，同款机型还有 TCL T508N、小黄蜂 10A、HMD Pocket Link | IT之家/百度百科等公开报道 |
| e5-linux 项目的内核仓库 `sprd-linux-devs/linux` 明确覆盖 **T157/T158** | 仓库描述 "Linux stable for T157/T158" |
| **VIPME M8 与 A89 同为 T157 平台**，社区已完成 M8 的完整移植（含 11 轮 probe 实测记录、充电/屏幕/触摸/无线/基带逐项打通） | `linux_device_m8` README |
| M8 与 A89 硬件高度同类：3.5 英寸 480×320 屏、T9 实体键盘、Android 13、A/B 分区 | 双方公开参数 |
| A89 **网上没有公开原厂 ROM**，但这不挡路：本项目流程用的是**你自己手机上 dump 的原厂 boot/DTB**，网上 ROM 本来就不能用（射频校准 NV 每台机器唯一） | `devices/m8/collect.py` 设计 |
| 你的手机已解锁 BL、已 root、已装 Magisk —— 满足全部前置条件 | 你确认 |

## 2. 工作区结构

```
a89-openwrt-port/
├── README-A89移植指南.md        ← 本文件
├── cloud-build/
│   ├── a89-probe-kernel.yml     ← GitHub Actions 云端编译探测内核（现在就能跑）
│   └── README.md                ← 云端编译使用说明 + 阶段 B 配方
└── e5-linux/                    ← 上游主项目（含全部构建系统，MIT）
    ├── boot/ upstream/ openwrt/ rootfs/ kernel/ tools/ docs/ installer/ magisk/
    ├── devices/                 ← 上游多机型参考（e5 / m8 / t551m / common）
    └── device/
        ├── linux_device_m8 / openwrt_device_m8      ← 同芯片参考实现（勿改）
        ├── linux_device_a89 / openwrt_device_a89    ★ A89 脚手架（本工作区新增）
        └── ...其余上游设备仓库
```

★ `linux_device_a89` 的关键设计：**不写死任何未经证实的机型字符串**。
`collect.py` 首次运行时把真机的 model/device/CID 记进 `identity.json`，
之后 make-probe / flash-probe / make-trial 全部强制校验"连着的必须是
采集过备份的那台 A89"，保留上游"拒绝刷别的机器"的安全底线。

## 3. 安全设计（为什么这套流程变砖风险低）

上游（E5/M8）的防砖机制，A89 脚手架完整继承：

1. **只写两个地方**：`boot_b` 分区 + `misc` 分区偏移 2048 处的 32 字节
   A/B 启动控制块。Android A 槽、GPT 分区表、userdata、NV 校准**全部不动**。
2. **原厂 DTB 保留**：试启动镜像用你手机自己 dump 的原厂 boot 打包，
   设备树在内存里打补丁（`CONFIG_OF_OVERLAY`），不写回原厂 dtb/dtbo。
3. **先恢复、后探测**：init 第一步把 Android A 设回默认槽并读回校验，
   超时（默认约 4 分钟）或内核 panic 自动重启回 Android A。
4. **刷前五重校验**：机型身份 + eMMC CID（同一台物理机）+ 解锁状态
   （`verifiedbootstate=orange`）+ 电量（≥5%、≥3.5V、接电中）+
   镜像哈希/大小与目标分区一致；写入后再读回验证，失败自动恢复原控制块。
5. **第二轮起**：`--previous-image` 校验 boot_b 当前内容必须是上一轮
   已知镜像，拒绝覆盖未知状态。

就算彻底失败，A89 还有**展锐 SPD 下载模式**可线刷救砖（拿到工具和
对应固件前，先在手机上确认能进下载模式再刷第一次——见第 6 节）。

## 4. 路线图（四阶段）

```
阶段 0  脚手架 + 云端编译环境          ✅ 已完成（本工作区）
阶段 A  云端编译探测内核               ⬜ 手机不需要在身边，现在就能做
阶段 B  手机采集 + probe1..N 试启动    ⬜ 需要手机（每次 15 分钟）
阶段 C  完整 OpenWrt 试运行           ⬜ 需要手机 + 阶段 B 结论
阶段 D  持久化开机 + 日常使用          ⬜ 最后一步
```

### 阶段 A（现在就能做，不需要手机）

按 `cloud-build/README.md`：把本工作区推到你自己的 GitHub 仓库，
触发 Actions，下载 `a89-probe-kernel` 产物（`Image.lk` 等）。

### 阶段 B（手机回来后）

```bash
# 1) 电脑装好 adb + Python3，手机开 USB 调试并授权
# 2) 采集原厂备份（只读）——生成 identity.json + 全部原厂分区备份
python3 device/linux_device_a89/collect.py --serial <序列号> --out dumps/a89-stock

# 3) 提取本机固件（Wi-Fi/音频，只读）
python3 device/linux_device_a89/collect-files.py --serial <序列号> \
  --out work/a89-device-files --backup dumps/a89-stock

# 4) 对照 device/linux_device_a89/PORTING-CHECKLIST.md 第 1~9 项
#    （确认 A/B 分区、充电芯片、屏幕/触摸节点、模块顺序……）

# 5) 组装试启动镜像（在电脑上，纯 Python，无需编译环境）
python3 device/linux_device_a89/make-probe.py \
  --backup dumps/a89-stock --kernel out/a89/probe \
  --busybox work/busybox/ext/usr/bin/busybox --out out/a89/boot-probe.img

# 6) 刷试启动 → 手机会重启进 probe，~4 分钟后自动回 Android
python3 device/linux_device_a89/flash-probe.py --serial <序列号> \
  --backup dumps/a89-stock --image out/a89/boot-probe.img

# 7) 收日志、看证据，按 M8 的 11 轮经验逐项排障
python3 device/linux_device_a89/collect-logs.py --serial <序列号> \
  --out out/a89/probe1-logs --backup dumps/a89-stock
```

预计迭代点（M8 踩过的坑，A89 大概率遇到类似的）：
- PMIC 稳压器 compatible 名不匹配 → eMMC/USB 起不来（M8 probe1-2）
- DPU IOMMU 32 位 DMA mask → 背光亮但黑屏（M8 probe5-7）
- WCN 无线固件 AB/XPE 配置选择错误 → 热点起不来（M8 试运行二）
- Type-C VBUS/CC extcon 顺序 → OTG 没电（M8 probe9-10）

### 阶段 C（探测通过后）

云端编译 OpenWrt rootfs（`cloud-build/README.md` 阶段 B 配方）+
`make-trial.py` 组装完整试运行镜像（`openwrt-a89.ext4` 放
`/data/e5linux/`，**不重分区**，8 分钟自动回退），逐项验证：
SSH/LuCI、热点、蜂窝数据、短信、通话、充电。

### 阶段 D

`make-trial.py --persistent`：Linux 成为默认系统，启动失败仍自动回
Android A；随时 `e5-next-boot android` 切回安卓。

## 5. 手机不在身边时，你还能做的准备

- [ ] 注册 GitHub，建仓库，跑通阶段 A 云端编译（不花钱）
- [ ] 电脑装 Python 3 + platform-tools（adb）
- [ ] 下载 arm64 静态 busybox（上游 README 第 2 步的命令）
- [ ] 找到 A89 的 SPD 线刷工具与官方固件渠道（救砖保险，最好有备机心态）
- [ ] 通读 `device/linux_device_a89/README.md` 和 `PORTING-CHECKLIST.md`

## 6. 风险声明（请务必读完）

1. 本工作区**没有经过 A89 实机验证**；A89 的充电芯片、屏幕驱动 IC、
   触摸 IC、分区布局都是"同类产品推断"，采集后必须逐项核对。
2. 如果采集发现 A89 **不是 A/B 分区**（无 boot_b），整套试启动/回退
   机制不适用，需回上游社区重新设计——这是第一个要确认的硬前提。
3. 刷机有变砖风险。虽然设计上只写 boot_b + 32 字节控制块、失败自动回退，
   但**没有任何方案是零风险的**；原厂备份 `dumps/a89-stock/` 和 SPD
   救砖手段缺一不可。
4. 未经网络锁/运营商验证，可能出现"刷完 Linux 后无法拨打紧急电话"等情况；
   老人机如仍在服役，别拿唯一在用的机器做实验。
5. 上游社区（sprd-linux-devs）的规则：**不许把别机的固件/NV/校准数据
   混用**；遇到问题带 `collect-logs.py` 日志去 e5-linux 的 Issues。

## 7. 上游资源

- 主项目：https://github.com/sprd-linux-devs/e5-linux（中文 README）
- T157 同芯片参考：`device/linux_device_m8`（VIPME M8 完整移植记录）
- 稳定内核：https://github.com/sprd-linux-devs/linux（T157/T158）
- 发布工作流参考：https://github.com/sprd-linux-devs/release
- 方法论源头：dikeckaan/mu300-linux（MIT）

---

*本工作区由 TeleAgent 基于上述上游开源项目（MIT/GPL）搭建；A89 脚手架
部分以 MIT 许可发布，与上游保持一致。*

> AI生成
