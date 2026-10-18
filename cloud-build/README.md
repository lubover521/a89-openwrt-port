---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: 'c176d805-99c1-4d7b-8794-5ef08ec04ead'
  PropagateID: 'c176d805-99c1-4d7b-8794-5ef08ec04ead'
  ReservedCode1: '8c445f21-5e0b-45ec-847e-bd072d9504b2'
  ReservedCode2: '8c445f21-5e0b-45ec-847e-bd072d9504b2'
---

# 云端编译方案（A89）

## 为什么是“云端编译”

- 你的电脑是 Windows，没有 Linux 内核编译环境；装 WSL 也能做，但
  GitHub 的 ARM64 runner（公开仓库免费）编译一次探测内核大约
  20–40 分钟，不占你机器。
- 所有“必须来自你手机”的数据（原厂 boot、DTB、固件、NV）**不进云端**，
  云端只编译通用代码；真正的刷机镜像在**你的电脑上**用一条命令组装
  （make-probe.py，纯 Python，无需编译环境）。

## 阶段 A：探测内核（现在就能跑）

工作流文件：`.github/workflows/a89-probe-kernel.yml`（已就位，随仓库推送后
自动出现在 Actions 页面，无需手动放置）。

1. 在 GitHub 建一个你自己的仓库（公开仓库才能免费用 ARM64 runner；
   如果坚持私有仓库，Actions 有每月免费额度，够用）。
2. 把 `a89-openwrt-port/` 的内容原样推上去（`dumps/`、`work/`、`out/`
   已被 `.gitignore` 挡住，不会误传）。
3. Actions 页面 → “Build A89 probe kernel” → Run workflow。
4. 跑完后在 run 页面下载 artifact `a89-probe-kernel`，解压得到：
   `Image.lk`（给 make-probe.py 用）、`config`、`kernel.release`、`SHA256SUMS`。

## 阶段 B：完整 OpenWrt rootfs / 刷机包（等真机探测通过后）

阶段 B 的配方**不能提前写死**：设备树补丁、充电芯片驱动选择、模块列表
都取决于 A89 真机的 probe 结果（M8 用了 11 轮 probe 才定型）。拿到
probe1 日志后，按下面经过上游验证的命令组合写工作流：

```
# 1) 打过补丁的 ModemManager / BlueZ（结果进 out/openwrt/*.apk）
bash openwrt/build-modemmanager.sh
bash openwrt/build-bluez.sh

# 2) 主线内核的 root 模块包（配合阶段 A 的内核）
#    参考 upstream/root-modules.sh + stage-root-modules.py

# 3) OpenWrt rootfs 镜像（standalone + 通用，不含设备专有文件）
E5_STANDALONE=1 E5_ROOT_MODULES_ONLY=1 E5_DEVICE_FILES=0 \
  bash openwrt/build-rootfs.sh
#    产出 out/openwrt/e5-openwrt-<版本>.ext4.gz
#    推到手机后改名为 /data/e5linux/openwrt-a89.ext4（配合 make-trial.py）

# 4) 刷机包（通用主线包，安装器从手机现场提取设备文件）
E5_MAINLINE=1 bash openwrt/make-flash-bundle.sh
```

> 注意 4) 是 E5 的发布通道，其中 installer 的“设备选择”列表是否收录
> A89 需要看 `installer/` 的设备注册方式；M8 的完整试用走的是
> `make-trial.py` + `openwrt-a89.ext4` 路线（不重分区、8 分钟自动回退），
> 建议先走这条，稳定后再考虑接入通用安装器。

## 本地需要的一次性准备（Windows）

- 安装 Python 3（make-probe.py / flash-probe.py 用）
- 安装 platform-tools（adb），手机插电脑后能 `adb devices`
- busybox 静态 arm64 二进制一次下载（上游 README 有命令）：
  `work/busybox/ext/usr/bin/busybox`
- 原厂备份 `dumps/a89-stock/`（collect.py 产出）+ 离线备份一份

> AI生成