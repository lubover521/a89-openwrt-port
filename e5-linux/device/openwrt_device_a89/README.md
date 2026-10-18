---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '465f8ed6-ecff-4ed5-a1e5-ced39a6498a9'
  PropagateID: '465f8ed6-ecff-4ed5-a1e5-ced39a6498a9'
  ReservedCode1: '67431359-5308-4fed-87eb-4bf0159f5077'
  ReservedCode2: '67431359-5308-4fed-87eb-4bf0159f5077'
---

# openwrt_device_a89

OpenWrt 设备层脚手架：百合 A89（展锐 T157 / UMS9157）。

由 [openwrt_device_m8](https://github.com/sprd-linux-devs/openwrt_device_m8)
（同 SoC 平台、已实测）的 overlay 结构复制而来，作为
`e5-linux/device/openwrt_device_a89` 使用。

## 当前 overlay 内容与待办

| 文件 | 状态 | 说明 |
|---|---|---|
| `etc/e5/device-model` | 占位 `百合A89` | 真实 getprop 值采集后替换 |
| `etc/e5/device-hostname` | 占位 `Baihe-A89` | 同上 |
| `etc/e5/device-profile` | `a89` | 机型标识 |
| `etc/e5/receiver-output` | `speaker`（占位） | **A89 是否有独立听筒未知**；M8 是共用喇叭。真机通话验证后改 |
| `etc/e5/radio-defaults.json` | 空 `{}` | 移动定制机：确认 5G 频段/NR 优先级后填 |
| `etc/config/unisoc_modem` | 复制自 M8 | AT 端口（stty_nr2）、sipa_eth0 等需按 A89 实机探测结果调整 |

> 每一项都要以 A89 实测为准更新（见 linux_device_a89/PORTING-CHECKLIST.md
> 第 15 条）。设备固件（wcnmodem.bin 等）不属于本仓库，按上游规则
> 放在父项目 `work/`，从你自己的手机提取。

> AI生成