# KVM 与 Docker

主线内核参照 MU300 的配置启用 KVM、vhost、cgroup v2、namespace、seccomp、
overlayfs 及容器网络模块。硬件相关的启动模块顺序不变，新增模块按需加载。
TF 卡选择、Android 切换、基带启动和 NV 处理没有在此功能中修改。

## 构建

原有主线内核构建命令会检查 KVM/容器配置、模块 vermagic、完整性和构建哈希，
生成 `container-support.json`。`upstream/root-modules.sh` 将同一构建的全部模块
打包到 `root-modules.tar`，保留音频、基带服务使用的路径。OpenWrt 的 kmodloader
只扫描版本目录里的 `.ko`，因此模块放在该目录，原硬件子目录使用符号链接。

默认只提供内核容器支持和安装后的适配工具，**不预装 Docker、containerd 或
runc**。构建 OpenWrt 时使用匹配的模块：

```sh
E5_DOCKER=0 E5_ROOT_MODULES=/path/to/root-modules.tar openwrt/build-rootfs.sh
```

其余固件、独立镜像、信息屏等构建参数沿用原流程。只有明确需要预装时才设置
`E5_DOCKER=1`，此时镜像默认扩为 2048 MiB；也可用 `E5_IMAGE_MB` 指定。
原厂 5.15 内核不适用本构建选项。
Docker 使用 OpenWrt 官方仓库的 docker、dockerd、containerd、runc 和
iptables-nft 软件包；APK 依赖附带的 armsr 内核模块不能替代本仓库匹配内核的模块。

安装过程不执行 Docker 软件包的启动脚本。`e5-container-setup` 配置 nft 兼容
iptables、fw4、Docker 日志大小和 cgroup 启动包装器，并禁用自动启动。
升级 dockerd 软件包后重新运行 `/usr/libexec/e5-container-setup`，以恢复启动钩子。
该命令会禁用开机自启；需要自启时再执行下方 enable 命令。

## 自行安装与使用

需要 Docker 时，在设备上执行：

```sh
apk update
apk add --no-scripts docker dockerd iptables-nft ip6tables-nft
/usr/libexec/e5-container-setup
/etc/init.d/firewall reload
```

内核及匹配模块已随镜像提供，不需要重新刷内核。适配工具在安装后才配置
Docker 的 cgroup 启动钩子、数据目录和防火墙；未安装时不创建 Docker 网络。
不要用官方 armsr 的内核或模块替换本机内核及其版本目录。

```sh
/etc/init.d/dockerd start       # 本次启动
docker info
/etc/init.d/dockerd stop
/etc/init.d/dockerd enable      # 用户需要时才开启开机自启
/etc/init.d/dockerd disable
```

默认数据目录 `/opt/docker` 位于持久化根镜像内；装满前应扩容镜像或将
`/etc/docker/daemon-openwrt.json` 的 `data-root` 改到足够大的 ext4 文件系统。
Docker API 只使用本机 Unix socket。日志使用 local 驱动，每个容器最多两份 5 MiB 日志。

默认桥为 `docker0`（172.22.0.0/24），另预留 172.23.0.0/16 给自建网络。
fw4 放行 LAN → Docker、Docker → WAN；不改变现有 LAN/WAN 地址和转发策略。
自建 Docker bridge 网络还需将其实际桥名加入 fw4 的 docker 区域，不能用
`br-*` 通配符，因为它也会匹配 `br-lan`。例如：

```sh
docker network create --opt com.docker.network.bridge.name=docker-app apps
uci add_list firewall.docker.device=docker-app
uci commit firewall
/etc/init.d/firewall reload
```

启动包装器先启用 procd 服务 cgroup 的上级控制器，再执行 dockerd，
避免第一次启动误判不支持 swap 限制。不会为现有桌面、基带服务添加资源限额。
本次不安装完整虚拟机系统；可用 `/dev/kvm` 运行支持 ARM64 KVM 的虚拟机工具。
启用 KVM 不代表支持嵌套虚拟化；本次没有启用或验证虚拟机内的二级 KVM。

## 实机验证工具

`tools/kvm-smoke.c` 创建 KVM VM/vCPU，实际执行 ARM64 指令并检查 MMIO 退出值；
并非只检查设备节点是否存在。

```sh
aarch64-linux-gnu-gcc -O2 -static -Wall -Wextra -Werror -o kvm-smoke tools/kvm-smoke.c
# 将 kvm-smoke 传到设备，chmod +x 后运行
python3 tools/docker-smoke.py  # 在设备上运行，Docker 需已启动
```

Docker 测试从设备现有静态 BusyBox 构造镜像，不依赖 Docker Hub；检查实际
cgroup 内存/CPU/进程/swap 限制、seccomp、桥接端口映射、DNS/NAT 出网、
fw4 重载后的端口可达性、容器重启后的 overlay 写入保留，并清理自己创建的镜像和容器。

2026-10-09 实机验证：T551M、Linux 6.18.54-t551m-kvm2、Docker 29.6.1，
上述 KVM 和 Docker 测试全部通过。系统镜像扩至 2 GiB，重启后屏幕服务运行、
蜂窝 WAN 已连接、Wi-Fi 接口和 USB 网络正常。E5 尚未做这组实机验证。
同日 USB 充电修复内核 `6.18.54-t551m-usb2` 重启后重复上述 KVM/Docker 实机测试，
全部通过；验证结束后 Docker 恢复停止且禁用自动启动。
恢复 OTG 的 `6.18.54-t551m-otg` 同样完成重启与上述 KVM/Docker 回归，全部通过，
测试后 Docker 恢复停止且禁用自动启动；TF 启动 init 与前版逐字节一致。
