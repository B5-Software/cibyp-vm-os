# CIBYP-VM-OS

**CIBYP-VM-OS 是基于 Debian GNU/Linux 的再打包系统（remix）**，由本仓库的 CI 构建、
发布到本仓库的 Release，供「Could I Be Your Partner」的 QEMU 虚拟机沙盒按需下载。
它**不随应用安装包分发**（安装包体积零增长），运行时由应用内下载并做 sha256 校验。

> CIBYP-VM-OS is based on Debian GNU/Linux. Debian is a registered trademark owned by
> Software in the Public Interest, Inc. CIBYP-VM-OS is not affiliated with or endorsed by
> the Debian project.

本仓库同时构建 **QEMU 运行时包**（裁剪后的官方 QEMU 二进制 + 依赖闭包 + 固件 + 许可）。

---

## 1. 为什么单独一个仓库

- 镜像/运行时包的构建很重（debootstrap + 6 变体作业 + boot 冒烟），不该和主应用的
  发布流水线混在一起（主仓 push 会触发四平台打包）
- 产物归属清晰：镜像与运行时包都是**可独立分发**的 GPL 合规产物（含 COPYING / 源码链接）
- 便于外部验证与复现：本仓库自带配方、工具与冒烟测试，任何 Linux 机器（含 WSL/容器）都能构建

## 2. 产物

### 2.1 CIBYP-VM-OS 镜像（release: `vm-os-latest`）

| 变体 | 定位 | 体积门禁 | 磁盘 |
|---|---|---|---|
| `base` | Agent 默认执行环境：shell/python/node/编译基础 + 沙盒接入 | ≤ 520MB | 8G |
| `desktop` | 图形化 / computer-use：base + Xorg + x11vnc + Chromium + CJK 字体 | ≤ 950MB | 12G |
| `full` | 完整开发环境：base + clang/调试器 + PostgreSQL/MariaDB/Redis + Docker + ffmpeg + Playwright 依赖 | ≤ 1.6GB | 16G |

每个变体 × 架构（amd64/arm64）产出：

```
cibyp-vmos-<version>-<variant>-<arch>.qcow2   + .sha256   系统盘（整盘 ext4，zstd 压缩）
vmlinuz-<arch> / initrd-<arch>.img           + .sha256   内核与 initramfs（宿主直接引导）
runtime-manifest.json                                    应用消费的清单（URL/sha256/大小/兼容性/许可声明）
```

### 2.2 QEMU 运行时包（release: `vm-runtime-latest`）

官方 QEMU 安装包解包后 1.25GB/3387 文件 → 裁剪为：

```
cibyp-qemu-<platform>-<arch>.zip    # 实测 win32-x64：511MB 解包后 / 80.6MB zip
runtime-pack-manifest.json          # 应用消费的清单
```

保留：`qemu-system-{x86_64,aarch64,xtensa}`（xtensa 供 ESP32 固件模拟）、`qemu-img`、
`share/` 固件（缺失会导致启动失败）、PE/ldd/otool 依赖闭包、COPYING。
裁剪靠 `tools/vm-pack.js`：Windows 解析 PE 导入表做 DLL 闭包，Linux 用 ldd+patchelf，
macOS 用 dylibbundler 改写 dylib 路径。

## 3. 构建方式（无需 loop / mount / 特权容器）

```
debos --disable-fakemachine          # debootstrap + apt + overlay 出厂配置 + finalize 清理 + pack rootfs
  → tools/assemble-image.js          # mke2fs -d 免挂载写入整盘 ext4 → qemu-img convert -c -o compression_type=zstd
  → tests/boot-smoke.js              # QEMU -kernel/-initrd 直接引导 + cloud-init over HTTP + SSH 契约断言
```

为什么不用 `image-partition`：那套需要 loop 设备与 mount 特权，容器/WSL 里 parted 刷新分区表
必然失败（`unable to inform the kernel of the change`）。整盘 ext4 + 宿主直接引导既简单又稳，
还能省掉引导器与 UEFI 固件依赖。

本地复现（Linux 或 WSL，需 root）：

```bash
sudo apt-get install -y debos debootstrap e2fsprogs util-linux zstd qemu-utils
sudo debos --disable-fakemachine --artifactdir out \
  -t version:0.1.0 -t architecture:amd64 recipes/base.yaml
sudo -E env "PATH=$PATH" node tools/assemble-image.js \
  --rootfs out/cibyp-vmos-0.1.0-base-amd64-rootfs.tar.gz --out out \
  --version 0.1.0 --variant base --arch amd64 --size 8G
node tests/boot-smoke.js --image out/cibyp-vmos-0.1.0-base-amd64.qcow2 \
  --kernel out/vmlinuz-amd64 --initrd out/initrd-amd64.img --arch amd64 --variant base
```

## 4. 出厂契约（应用依赖的不变量）

| 契约 | 值 |
|---|---|
| 用户 | `cibyp`（NOPASSWD sudo，仅密钥登录） |
| 工作区 | `/workspace` |
| 配置注入 | cloud-init NoCloud（宿主经 `-smbios type=1,serial=ds=nocloud-net;s=http://10.0.2.2:<port>/`） |
| 网络 | systemd-networkd 静态配置（**不依赖 cloud-init**，云配置失败也能连上） |
| 引导 | 无引导器：宿主 `-kernel vmlinuz -initrd initrd.img -append "root=LABEL=cibyp-root rw console=ttyS0,115200 net.ifnames=0"` |
| 出厂态 | 首启重建 machine-id / SSH host key；实例改动落在 qcow2 overlay，"重置"= 删 overlay |
| 品牌 | `ID=cibyp-vmos` / `ID_LIKE=debian`；motd/issue/`cibyp-vmos-info` 均为 CIBYP 品牌 |

## 5. 实测数据（本机 WSL 构建 → Windows 引导）

| 项 | 数值 |
|---|---|
| debos 构建（base/amd64） | 5m10s（debootstrap + 全部 apt + 打包） |
| 镜像 | **457.8MB** qcow2（zstd）；rootfs 1.2GB（tar.gz 456MB，组装后即删） |
| 首启到 SSH | 56.4s（含 cloud-init；仍有优化空间：initramfs 体积 / cloud-init 模块） |
| boot 冒烟 | **12/12**（cloud-init 契约 / 品牌 / cibyp+sudo+/workspace / 静态网络 / qemu-ga / 直接引导 / **持久化** / **重置回出厂态**） |
| QEMU 裁剪 | win32-x64：1.25GB → 511MB（zip 80.6MB），裁剪包启动 VM 8/8 |

## 6. 许可与合规

- QEMU：GPLv2，随包提供 `COPYING`，源码见 <https://www.qemu.org/download/#source>（本仓库只做未修改的官方二进制重打包 + 依赖闭包）
- 镜像：仅使用 Debian 官方二进制包，未修改；源码可得性由 Debian 官方归档满足
  （<https://deb.debian.org/debian/> / <https://snapshot.debian.org/>）
- 本仓库构建脚本：GPL-3.0-or-later（见 LICENSE）
- 商标：产品名不含 "Debian"；不使用 Debian swirl logo；三处（镜像内 `/usr/share/doc/cibyp-vmos/`、
  Release 说明、应用关于页）均含免责声明
