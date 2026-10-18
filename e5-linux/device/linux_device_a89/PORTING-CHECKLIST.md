---
AIGC:
  ContentProducer: '001191110102MAD55U9H0F10002'
  ContentPropagator: '001191110102MAD55U9H0F10002'
  Label: '1'
  ProduceID: '1bd21370-fe31-4282-8914-b10baaf87bf7'
  PropagateID: '1bd21370-fe31-4282-8914-b10baaf87bf7'
  ReservedCode1: '5def0219-fadf-4bba-b445-24a258492f6d'
  ReservedCode2: '5def0219-fadf-4bba-b445-24a258492f6d'
---

# A89 移植清单（真机到手后逐项核对）

这份清单是“脚手架 → 可日用固件”之间必须由**你的 A89 实机**决定的事项。
任何一项没核对就刷，都等于拿猜测刷机——上游 M8 的经验是：每一项都要有实测证据。

## 第一批：采集后立即可做（无刷机风险）

- [ ] 1. **核对 identity.json**：`dumps/a89-stock/identity.json` 里的
      model/device/brand 是否真的是你的百合 A89（对照机身、包装、设置页）。
      把最终值填进 README.md 的设备信息表，并作为后续所有校验的依据。
- [ ] 2. **分区布局**：看 `partitions.txt`。确认存在 boot_a/boot_b（A/B 双槽）、
      misc、以及是否有独立 dtb/dtbo 分区。如果 **不是 A/B**，本仓库的
      试启动/回退设计不适用，需要回到上游社区重新设计（在动手前停下来）。
- [ ] 3. **屏幕与背光**：用 `dtc -I dtb -O dts dumps/a89-stock/live.dtb` 反编译，
      找 panel 节点（驱动 IC 型号、MIPI 初始化序列、背光 PWM）。
      与 M8 的 `lcd_st7796u_yihua_mipi_hvga` 对比；不同则在
      prepare-kernel.py 追加 A89 面板节点覆盖（CONFIG_OF_OVERLAY 已开）。
- [ ] 4. **充电芯片**：看 `i2c.txt`（0x6b 一带）与 `power.txt`。
      确认是否 BQ2560x 家族：
      - 是 → build-probe.sh 保持 `CONFIG_CHARGER_BQ2560X_SPRD=m`；
      - 否 → 记录实际芯片型号，改 build-probe.sh，并在社区 issue 提问是否已有驱动。
- [ ] 5. **电池与电量计**：power.txt 里的 design_capacity、电压；确认
      ump96xx_fuel_gauge 是否适用。终止电压按原厂 DT 向下取整（参考 M8 的 4248mV 教训）。
- [ ] 6. **模块顺序**：用 `dumps/a89-stock/modules-load.txt` 重新生成
      `probe-module-order.list`（当前文件头标注为 M8 猜测值，别偷懒沿用；
      注意保持 .list 扩展名——它是逐行执行的运行时数据文件）。
- [ ] 7. **触摸**：live.dtb 里找触摸节点（地址、IC）；同类是 TLSC6x。
- [ ] 8. **键盘矩阵**：A89 有实体 T9 键盘。live.dtb 的 keypad 节点 +
      inputs.txt 确认；`sprd_keypad.ko` 已在模块顺序中。
- [ ] 9. **内核 cmdline**：`cmdline.txt` 里确认 earlycon/console 地址
      （build-probe.sh 沿用了 M8 的 0x20210000/ttyS1；不一致就改）。

## 第二批：probe1 试启动后（每次都走“刷→等→回Android→收日志”）

- [ ] 10. probe1 目标：内核起来、eMMC 分区可见、USB NCM/串口可用。
       M8 曾因 `sprd,ump962x-regulator` vs `sprd,ump9620-regulator` 兼容名
       差异导致 eMMC/USB 起不来——A89 大概率遇到同类问题，看 dmesg
       里的 probe 失败记录，在 prepare-kernel.py 打 DT 兼容补丁。
- [ ] 11. 逐轮复测并记录：电源/充电、背光亮屏、触摸坐标（inputs）、
       温度传感器、cpufreq 三簇频率表。
- [ ] 12. 屏幕显示：display-test.c 编译后经 make-probe.py --display-test 打包，
       看实机是否有色条（M8 曾“背光亮但无画面”，是 DPU IOMMU 32 位 DMA 问题）。

## 第三批：进入完整 OpenWrt 前置

- [ ] 13. 固件提取：collect-files.py 产物检查（wcnmodem.bin、gnssmodem.bin、
       wifi_board_config*.ini、MAC、音频 AGDSP 镜像、audio_structure）。
       **严禁**使用 M8/其他机器的固件文件。
- [ ] 14. 基带：ModemManager + sipc/sipa 数据通道；A89 是手机形态，
       参考 M8 的 AT 通道与 `e5-modemd` 启动链。
- [ ] 15. openwrt_device_a89/overlay：按真机确认的结果补齐
       device-model、device-hostname、receiver-output（A89 是否独立听筒？）、
       radio-defaults.json（运营商频段优先级，移动定制机注意）。
- [ ] 16. make-trial.py 全量试运行（openwrt-a89.ext4，不重分区，
       8 分钟自动回退）；确认 LuCI/SSH/热点/蜂窝数据/短信逐项可用。
- [ ] 17. 每项功能都以实测为准更新 README——上游的原则：
       “各项必须以实测结果更新，不能仅凭成功编译标记完成”。

## 任何时候

- [ ] 原厂备份 `dumps/a89-stock/` 是唯一恢复手段之一，**离线再备份一份**。
- [ ] 保留 SPD（展锐下载模式）救砖工具与流程说明在电脑上，先演练到能进
      下载模式再刷第一次。
- [ ] 遇到 M8 没有的新问题，带着 `collect-logs.py` 的日志到
      sprd-linux-devs/e5-linux 的 Issues 提问（英文/中文均可，附 dmesg 段落）。

> AI生成