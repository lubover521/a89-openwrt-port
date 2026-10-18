# 各机型共享的异步 AT 偏好设置

按用户指定的值发送 `AT+CEUS=1`、`AT+CEMODE=2`。不在此重新解释或更改
这两个值；旧版 BASEBAND-CONTRACTS.md 对其业务含义有不同描述，需与实机
固件行为分开看待。

## 行为

- ModemManager 的 Unisoc 插件在**初始化结束**、成功开启射频后启动独立
  后台任务。不在早期 SIM 探测过程中调用，不等待任务完成。
- 已经联网也允许执行，不断开 PDP，不切换数据卡，不发 SFUN/CFUN 设置。
- 每条设置必须成功通信，最后非空行是 `OK`，且没有 ERROR/CME/CMS 错误。
  不额外发送查询回读；这里确认的是设置命令的 OK。
- 未确认成功时，每条最多重试 3 次，即首次加重试共 4 次；成功立即停止
  该条重试。失败重试之间仅后台任务休息 1 秒，避免连续快速失败冲击 AT。
- 第一条耗尽后仍处理第二条。耗尽或启动任务失败只记日志，不阻断拨号。
- 每卡独立非阻塞 flock，合并重叠任务，崩溃自动释放；不写永久完成标记，
  重启、重新初始化、切换 SIM 后可重新设置。日志标签 `e5-data-priority`。

## 机型与通道

E5、T551M 共享 `devices/t551m/ui.py` 的装配入口和同一份平台任务。
任务存在 `/opt/e5/t551m-at` 时使用已部署的 nr2 AT owner，与 MM 的 nr1
拨号通道分离；即便该 owner 临时不可用，也不改走拨号口或直接打开 tty。
每条命令携带当前 SIM 的 SPACTCARD 前缀，启动任务时固定所选 SIM。

未带独立 owner 的基础 Debian/OpenWrt 镜像通过 `e5-at` 请求现有
ModemManager/unisoc-cpd owner；这种旧布局没有独立通道，命令仍经过 owner
的共享队列，不能宣称完全没有通道竞争。旧 `mobile-data` 路径也接入后台
任务；如果旧环境只有已弃用 FIFO daemon，而 `e5-at` 不支持该 owner，
会记录未确认而非自行打开串口，需更新到支持的 owner 环境。

## 构建与验证

- OpenWrt 基础 rootfs、三种机型装配、UI 更新归档都带入可执行任务；
  Debian overlay 安装时也显式赋予可执行权限。
- 新增 `modemmanager-12-unisoc-data-priority.patch`，OpenWrt E5REV 从 13
  升至 14；Debian 的通配补丁列表也自动包含它。
- 沿用并扩展 OpenWrt 构建的 MM 包来源校验，不能用旧 APK 冒充包含新钩子。
  **仅替换脚本不等于新 MM 钩子已经生效**，还需重建/安装 ModemManager。
- `python3 rootfs/tests/data-priority.py -v`：两张 SIM、成功停止重试、
  失败上限、后台异步、并发合并、三机型装配、补丁链及真实 C 钩子隔离编译。
- MM 包构建内运行 `openwrt/tests/data-priority-hook.py`，并纳入来源哈希。

本次仅修改仓库并做离线验证，未刷机、未切换网络、未制作新安装包。
