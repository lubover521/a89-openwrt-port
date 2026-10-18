# 拨出电话误退回键盘：IMS 通知与短暂空通话列表

## 实机证据

用户报告 E5 拨出电话时，通话界面偶尔退回拨号键盘。
2026-10-10 22:46:29（设备时间）的 ModemManager 日志记录：

```text
call7: unknown -> dialing (outgoing-started)
couldn't start call: Couldn't start the call: Unhandled response '+SPIMSPDPINFO: 17,0,1,0'
call7: dialing -> terminated (unknown)
voice snapshot SIM2: 1 parsed call(s), error=none
```

这个样本中，拨号响应混入了 IMS PDN 通知。AT 命令虽然收到了最终结果，
`call_start_ready()` 仍因响应正文不为空而报错，将该通话标为 terminated。
与此同时 CLCC 仍列出 SIM2 的通话，因此“界面消失”不等同于无线端已经挂断。
屏幕只显示 live 状态，收到 terminated 后退回键盘符合现有逻辑；本次修复
状态误判源头，不延长挂机显示，也不自动重新拨号。

## 第一处修正：IMS 通知（r11）

共用 Unisoc 插件的已有 vendor URC 处理器增加 `SPIMSPDPINFO`，按完整行
移除该异步通知，使其不再混进拨号响应。仍保留最终 OK、BUSY、NO CARRIER、
CME ERROR，以及 CLCC/CPIN 等查询正文；未知响应不被笼统忽略。
未修改通话控制、SIM 网络模式、NV、音频路由、轮询间隔或屏幕布局。

OpenWrt 构建修订号 E5REV 升至 11，源码校验清单和构建流程加入 URC 回归测试。
新增 `openwrt/tests/voice-urc.py` 使用实际插件正则与 GLib，覆盖捕获到的失败
响应、混合 CDU、忙线/挂断/错误、查询正文、分段和未知通知共 9 个样本。
原双卡通话身份匹配、拨号中快照保护及 SIM 上电计划测试也通过。

## 构建与交付

本地缺少之前的 OpenWrt 25.12 包构建缓存，本次从 ModemManager 1.24.0
源码重建 daemon，应用 OpenWrt 25.12 的 0001–0004 补丁及本仓库 01–09
补丁。使用已有 aarch64/musl GCC 13.3 工具链和 GLib 2.82 开发库，保留
内置插件、LTO、AT D-Bus 支持及原有功能开关。实机使用已有 libmm-glib 和
GLib 库，未替换系统库；通过目标机加载及版本检查后才替换 daemon。
这是经过校验的 daemon 更新，并未生成新的 APK 包或更改包数据库版本。

- 源码归档 SHA256：`50e166bb24acb00bcaed814483920dfbc5b26d5424faee974b54c702e425a7c7`
- OpenWrt packages 25.12 归档 SHA256：`f04d1e1fca61c914caf9b4b31b71c08bc2937c18dcd40b66287139c883db16b5`
- daemon 版本：`1.24.0-e5-ims-urc-r11`
- daemon SHA256：`41c7f8b5b622f2fe8020b7a362f1412b34289475f4a4b3036c42147065f6a67e`
- 本地输出：`out/e5/modemmanager-ims-r11/ModemManager`
- E5 回退副本：`/root/mm-ims-r11-rollback/ModemManager`

部署前确认 E5 身份、当前无通话和旧文件哈希。原子替换 daemon 后重启服务，
没有重启整机。第一次服务重启遇到旧进程尚未释放 D-Bus 名称；等旧进程退出，
停止临时诊断实例，再恢复 procd 管理的正常 INFO 日志服务。
E5 离线 rootfs 的 daemon 同步更新；T551M 共用源码已经包含修复，但本轮
没有连接 T551M，其实机和离线镜像尚未部署这个 daemon 更新。

用户最初反馈正常，随后撤回：仍会退回键盘，再按拨号可“续上”。因此 r11
只修复了一个已抓到的错误，不能记为整体问题已解决。

## 第二处根因与修正：空列表误判、已有外呼丢失（r12）

22:58:05 call3 开始拨号，22:58:06 SIM2 的 CLCC 有一条通话；22:58:08
一次查询返回零条，MM 立即将 dialing 改为 terminated。同一秒后续查询又
返回一条 active 通话，之后 22:58:11、22:58:14 仍返回一条。MM 却一直报
`unexpected outgoing call`，没有恢复已终止对象，也没有新建对象。
22:58:15 用户再按拨号，call4 才重新关联到这个 active 通话。这与用户描述
吻合；不是单纯的画面闪烁，更不能靠再次发送 ATD 来恢复。

新增 `modemmanager-10-unisoc-call-recovery.patch`：

- 已知某卡有 live 通话而 CLCC 返回空时，在同一查询任务、同一卡槽下等待
  250 毫秒复查一次；保留原快照开始时间。第二次仍空才发布空列表；复查错误
  返回读取失败，保留现有状态。正常轮询及空闲槽位不增加查询。
- 若完整 CLCC 中出现软件未跟踪的外呼，只在 Unisoc 双卡插件、明确槽位和
  索引、live 外呼状态下恢复对象，保留卡槽/索引/方向/状态和通话音频设置。
  不发送 ATD，不复活旧 terminated 对象，不把真正结束的通话重新显示。
- 明确的用户挂断仍走原流程；远端挂机因空列表确认增加一次 250 毫秒等待
  和 AT 往返，而非等下一个三秒周期。

新增 `voice-recovery.py` 直接抽取编译生产回调和恢复函数，验证空后恢复、
连续空确认挂机、复查错误、空闲不重查、四种外呼 live 状态恢复及卡槽/方向/
状态保护。URC、双卡身份、SIM 上电测试继续通过。干净源树按 01–10 补丁
重新应用后与实际编译源码逐字节相同。构建修订号升至 12，补丁枚举和源码
校验清单已包含两位编号（防止遗漏新增的 10 号补丁）。

r12 已在确认 E5 无通话后部署，等旧 daemon 完全退出再启动新服务。
版本 `1.24.0-e5-voice-r12`，SHA256：
`733f5e3d920ebc83ce0fa8de9c5997589620ffcad2856747f5d818decd5fbf36`。
本地输出 `out/e5/modemmanager-voice-r12/ModemManager`，r11 回退副本在设备
`/root/mm-voice-r12-rollback/ModemManager`，更早原版副本仍保留。
用户确认 r12 未再退回键盘。23:03:28 的空 CLCC 在复查后恢复一条 active 通话，实机日志验证了该保护；随后用户提出反复拨挂需要节流。


## 挂断时序保护与 T551M 同步（r13）

E5 r12 日志另有 23:03:36 的时序：用户挂断 call2 后，一份此前发出的 CLCC
仍报告 active，恢复逻辑据此创建 call3；下一次拨号因此被“已有通话”拒绝。
这说明恢复已有外呼还必须区分主动挂断前的旧快照。

新增 `modemmanager-11-unisoc-hangup-settle.patch`：

- 挂断期间在 modem 上记录进行中状态，拒绝重复挂断及新的拨出请求。
- 挂断回调结束时记录单调时间，再等待 2 秒允许新拨出；即使挂断报告错误，
  也给基带同样的收尾时间。屏幕、耳机或直接 D-Bus 控制共用此保护。
- 外呼恢复忽略挂断期间、挂断之前启动、无可靠开始时间，以及挂断完成后
  2 秒内的快照。过后如果新的完整快照仍有实际外呼，可以恢复，不发送 ATD。
- 屏幕拨号/挂断请求结束后，拨号键显示“请稍候…”约 2 秒；尚未确认拨号
  对象时沿用最多 6 秒的状态等待，避免界面再次提交。中文/英文已补齐。
- 挂断键不需要等待拨出冷却，来电接听不受冷却限制。

验证：生产回调/保护代码抽取执行测试涵盖重复挂断、挂断中重拨、2 秒间隔、
旧快照/缺少时间/新快照恢复；GLib URC 9 个样本、双卡身份、SIM 上电测试通过。
01–11 干净补丁栈与实际编译的三份生产源码逐字节一致。屏幕浏览器测试覆盖
连续拨号与挂断点击、冷却绕过尝试、冷却释放、DTMF、息屏来电、锁屏和触控
偏好，全部通过；模拟远端挂断界面响应约 0.08 秒（不是实机基带延迟测量）。
包源码状态检查两项通过。构建修订号升至 13。

T551M 身份按 profile 和 eMMC CID 核验，在无通话时替换 daemon 和电话 JS，
等旧进程退出再启动服务；屏幕在空闲时重载。运行日志确认版本
`1.24.0-e5-voice-r13`，daemon SHA-256：
`734d1c3c32054893878719aa8a85336a68aa5124f9efe70919fc0bdef80a3a32`。
回退文件 `/root/mm-voice-r13-rollback/{ModemManager,phone.js}`。
WAN 已恢复到 `sipa_eth0`，语音 API 无错误、音频服务正常，默认/下次启动仍为 Linux。

T551M 离线 `openwrt-t551m.ext4` 同步 daemon、phone.js 及此前主页确认资源，
执行该文件系统的 `sync -f` 后正常卸载。没有重刷内核、修改物理 NV 或启动项。
构建输出与输入清单位于 `out/e5/modemmanager-voice-r13/`（共用二进制，目录名
不代表仅支持 E5），此次未生成 APK。

用户明确不再进行 T551M 实际通话复测；本轮结论限于部署及自动化/服务检查。
E5 实机和 E5 离线根目录仍为 r12，未把 T551M 的 r13 部署状态写成 E5 已更新。
