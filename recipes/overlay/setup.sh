#!/bin/bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (c) 2026 B5-Software
#
# CIBYP-VM-OS 出厂配置脚本（在 debos chroot 内执行，幂等）。
#
# 设计约定（宿主 App 依赖这些不变量）：
#   - 用户名 cibyp，NOPASSWD sudo，仅密钥登录
#   - /workspace 属主 cibyp（宿主工作区映射点）
#   - sshd 只允许 cibyp，关闭密码/root 登录；host key 首启重建
#   - cloud-init 数据源限定 NoCloud + None，避免 clouds 探测拖慢启动
#   - 网络不依赖 cloud-init：自带 systemd-networkd 的 eth0 DHCP 配置
#   - 串口 ttyS0 可登录（cibyp 自动登录），供宿主 Splash 排障面板使用
#   - 内核/initramfs 走宿主机直接引导（-kernel/-initrd），镜像内不需要引导器
#   - 出厂即干净：清空 machine-id、SSH host key、cloud-init 状态
#
# 注意：本脚本不写 Debian 商标相关内容以外的品牌；Debian 商标归属 SPI。
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

CIBYP_VERSION="${CIBYP_VERSION:-0.4.1}"
CIBYP_BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
CIBYP_BASE_SUITE="$(. /etc/os-release && echo "${VERSION_CODENAME:-unknown}")"

echo "[cibyp] provisioning CIBYP-VM-OS ${CIBYP_VERSION} (base: Debian ${CIBYP_BASE_SUITE})"

# ---------------------------------------------------------------- 主机名与 hosts
echo "cibyp-vmos" > /etc/hostname
cat > /etc/hosts <<'EOF'
127.0.0.1   localhost
127.0.1.1   cibyp-vmos
::1         localhost ip6-localhost ip6-loopback
EOF

# ---------------------------------------------------------------- 品牌化
cat > /etc/os-release <<EOF
PRETTY_NAME="CIBYP-VM-OS ${CIBYP_VERSION} (based on Debian GNU/Linux ${CIBYP_BASE_SUITE})"
NAME="CIBYP-VM-OS"
VERSION_ID="${CIBYP_VERSION}"
VERSION="${CIBYP_VERSION}"
VERSION_CODENAME="${CIBYP_BASE_SUITE}"
ID=cibyp-vmos
ID_LIKE=debian
HOME_URL="https://github.com/B5-Software/Could-I-Be-Your-Partner"
SUPPORT_URL="https://github.com/B5-Software/Could-I-Be-Your-Partner/issues"
BUG_REPORT_URL="https://github.com/B5-Software/Could-I-Be-Your-Partner/issues"
CIBYP_BASE_DISTRO="debian"
CIBYP_BASE_VERSION_ID="13"
CIBYP_BUILD_DATE="${CIBYP_BUILD_DATE}"
EOF

# dpkg vendor hook：派生发行版的标准做法，让 dpkg-vendor 能识别派生关系
mkdir -p /etc/dpkg/origins
cat > /etc/dpkg/origins/cibyp-vmos <<EOF
Vendor: CIBYP
Vendor-URL: https://github.com/B5-Software/Could-I-Be-Your-Partner
Bugs: https://github.com/B5-Software/Could-I-Be-Your-Partner/issues
Parent: Debian
EOF

cat > /etc/issue <<'EOF'
CIBYP-VM-OS \n \l
(based on Debian GNU/Linux; Debian is a trademark of Software in the Public Interest, Inc.)

EOF
cp /etc/issue /etc/issue.net

cat > /etc/motd <<'EOF'

  CIBYP-VM-OS  ——  由 Could I Be Your Partner 托管的隔离开发环境
  ------------------------------------------------------------------
  基础系统 : Debian GNU/Linux（未修改的官方二进制包）
  工作区   : /workspace（与宿主工作区同步）
  查看信息 : cibyp-vmos-info
  免责声明 : 本系统基于 Debian 构建，与 Debian 项目无隶属或背书关系。
             Debian 是 Software in the Public Interest, Inc. 的注册商标。

EOF

# ---------------------------------------------------------------- 用户与工作区
if ! id cibyp >/dev/null 2>&1; then
  useradd -m -s /bin/bash -G sudo cibyp

fi
# ----------------------------------------------------------------
# 桌面输入：cibyp-input / seatd / uinput
# ----------------------------------------------------------------
# seatd 的 socket 属 root:video；/dev/input/* 属 root:input —— cibyp 不在组里就打不开：
#   → sway 看不到任何输入设备（get_inputs 为空）、libseat 报 Permission denied（实测 CI 红）
getent group input >/dev/null || groupadd -r input
getent group video >/dev/null || groupadd -r video
usermod -aG input,video cibyp 2>/dev/null || true
# uinput：自研鼠标注入器（守护以 root 运行，这里给设备节点一个稳妥权限）
install -d -m 0755 /etc/udev/rules.d /etc/modules-load.d
cat > /etc/udev/rules.d/99-cibyp-uinput.rules <<'EOF'
KERNEL=="uinput", GROUP="input", MODE="0660"
EOF
echo uinput > /etc/modules-load.d/cibyp-uinput.conf
# seatd：SSH 会话没有 logind session，libseat 必须走 seatd（桌面镜像已装 seatd）
systemctl enable seatd 2>/dev/null || true
passwd -l cibyp >/dev/null 2>&1 || true
install -d -o cibyp -g cibyp -m 0755 /workspace
cat > /etc/sudoers.d/cibyp <<'EOF'
cibyp ALL=(ALL) NOPASSWD:ALL
EOF
chmod 0440 /etc/sudoers.d/cibyp

# ---------------------------------------------------------------- locale
# 生成中英文 locale（cloud-init 的 locale 模块要求目标 locale 已生成，否则首启报错）
if [ -f /etc/locale.gen ]; then
  sed -i 's/^# *\(en_US.UTF-8 UTF-8\)/\1/; s/^# *\(zh_CN.UTF-8 UTF-8\)/\1/' /etc/locale.gen
  locale-gen >/dev/null 2>&1 || true
fi
cat > /etc/default/locale <<'EOF'
LANG=en_US.UTF-8
LANGUAGE=en_US:zh_CN
LC_ALL=
EOF
update-locale LANG=en_US.UTF-8 >/dev/null 2>&1 || true

# ---------------------------------------------------------------- 强制 UTF-8（避免 guest 内 unzip/tar 把中文名写成乱码）
cat > /etc/profile.d/00-cibyp-locale.sh <<'EOF'
export LANG=C.UTF-8
export LC_ALL=C.UTF-8
EOF
chmod 0644 /etc/profile.d/00-cibyp-locale.sh
cat > /etc/environment <<'EOF'
LANG=C.UTF-8
LC_ALL=C.UTF-8
EOF

# ---------------------------------------------------------------- SSH
install -d -m 0755 /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/10-cibyp.conf <<'EOF'
# CIBYP-VM-OS：仅密钥登录，仅允许 cibyp
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PermitEmptyPasswords no
AllowUsers cibyp
X11Forwarding yes
ClientAliveInterval 30
EOF
# 首启重建 host key（Debian 的 ssh.service 会 ssh-keygen -A）
rm -f /etc/ssh/ssh_host_*

# ---------------------------------------------------------------- 串口控制台
systemctl enable serial-getty@ttyS0.service >/dev/null 2>&1 || true
mkdir -p /etc/systemd/system/serial-getty@ttyS0.service.d
cat > /etc/systemd/system/serial-getty@ttyS0.service.d/autologin.conf <<'EOF'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin cibyp --keep-baud 115200,38400,9600 %I $TERM
EOF

# ---------------------------------------------------------------- 网络（不依赖 cloud-init）
cat > /etc/systemd/network/10-cibyp-eth0.network <<'EOF'
[Match]
Name=eth0 en* ens* enp* eno*

[Network]
DHCP=yes
IPv6AcceptRA=yes

[DHCPv4]
UseDNS=yes
EOF
ln -sf /run/systemd/resolve/stub-resolv.conf /etc/resolv.conf
systemctl enable systemd-networkd.service >/dev/null 2>&1 || true
systemctl enable systemd-resolved.service >/dev/null 2>&1 || true

# ---------------------------------------------------------------- cloud-init
install -d -m 0755 /etc/cloud/cloud.cfg.d
cat > /etc/cloud/cloud.cfg.d/99-cibyp.cfg <<'EOF'
# CIBYP-VM-OS：限定数据源，避免首次启动探测云元数据造成 2 分钟延迟
datasource_list: [ NoCloud, None ]
datasource:
  NoCloud:
    dsmode: net
ssh_deletekeys: true
ssh_genkeytypes: [ ed25519, rsa ]
# 镜像为"整盘 ext4、无分区表"：只做文件系统扩容（growfs），不尝试扩分区
growpart:
  mode: growfs
  devices: ['/']
resize_rootfs: true
EOF
mkdir -p /var/lib/cloud/seed

# ---------------------------------------------------------------- fstab（整盘 ext4，无分区表）
cat > /etc/fstab <<'EOF'
# CIBYP-VM-OS：整盘 ext4，由宿主 QEMU 直接内核引导（root=LABEL=cibyp-root）
LABEL=cibyp-root  /  ext4  defaults,noatime  0 1
EOF

# ---------------------------------------------------------------- 内核与 initramfs（直接引导）
cat > /etc/initramfs-tools/conf.d/10-cibyp.conf <<'EOF'
# 宿主 QEMU 直接引导内核，initramfs 必须包含 virtio 全栈与 ext4
MODULES=most
COMPRESS=zstd
EOF
cat > /etc/initramfs-tools/modules <<'EOF'
virtio
virtio_ring
virtio_pci
virtio_blk
virtio_net
virtio_console
ext4
EOF
cat > /etc/modules-load.d/cibyp.conf <<'EOF'
virtio_pci
virtio_blk
virtio_net
EOF
# 静态网络名，便于宿主 -append 与文档统一使用 eth0
if [ -f /etc/default/grub ]; then
  sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT=.*/GRUB_CMDLINE_LINUX_DEFAULT="console=ttyS0,115200 net.ifnames=0"/' /etc/default/grub
fi
update-initramfs -u -k all >/dev/null 2>&1 || update-initramfs -c -k all >/dev/null 2>&1 || true

# 镜像自带期望的内核命令行（供宿主/排障参考；实际由 QEMU -append 提供）
install -d -m 0755 /etc/kernel
echo "console=ttyS0,115200 net.ifnames=0 root=LABEL=cibyp-root rw rootwait" > /etc/kernel/cmdline

# ---------------------------------------------------------------- apt / 维护
cat > /etc/apt/apt.conf.d/99-cibyp <<'EOF'
Acquire::Retries "3";
APT::Install-Recommends "false";
EOF
cat > /etc/apt/apt.conf.d/50unattended-upgrades-cibyp <<'EOF'
Unattended-Upgrade::Origins-Pattern {
        "origin=Debian,codename=${distro_codename},label=Debian-Security";
};
Unattended-Upgrade::Remove-Unused-Dependencies "true";
EOF
systemctl enable unattended-upgrades.service >/dev/null 2>&1 || true
systemctl enable apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true

# zram：小内存实例编译/装包时缓冲
if [ -f /etc/default/zramswap ]; then
  cat > /etc/default/zramswap <<'EOF'
ALGO=zstd
PERCENT=25
PRIORITY=100
EOF
  systemctl enable zramswap.service >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------- QGA
systemctl enable qemu-guest-agent.service >/dev/null 2>&1 || true

# ---------------------------------------------------------------- 启动优化
# cloud-init 等 network-online.target，而 networkd-wait-online 会额外等"所有链路就绪"，
# 在单网卡 VM 里纯属浪费（实测首启 SSH 就绪 58s）。我们的 networkd 配置本身秒级就绪。
systemctl mask systemd-networkd-wait-online.service >/dev/null 2>&1 || true
systemctl mask NetworkManager-wait-online.service >/dev/null 2>&1 || true
# 不需要的定时任务（减少首启与运行期抖动）
systemctl disable e2scrub_reap.service >/dev/null 2>&1 || true
systemctl disable apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true

# ---------------------------------------------------------------- 出厂干净化
: > /etc/machine-id
rm -f /etc/ssh/ssh_host_* 2>/dev/null || true
rm -rf /var/lib/cloud/* /var/lib/cloud/seed 2>/dev/null || true
rm -f /etc/resolv.conf.bak
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/* 2>/dev/null || true
find /var/log -type f -exec truncate -s 0 {} \; 2>/dev/null || true

# ---------------------------------------------------------------- 自研 Wayland 桌面
# 镜像内布局：
#   /usr/local/lib/cibyp-desktop/lib  共享主题与绘制（cibypui.py）
#   /usr/local/bin/cibyp-*            外壳、基础软件、会话与冒烟脚本
#   /etc/cibyp/sway/config            sway 配置（同时写入 skel 与 cibyp 用户）
#   /usr/share/wayland-sessions       Wayland 会话入口（供 display manager 识别）
if [ -d /opt/cibyp-overlay/desktop ]; then
  echo "[cibyp] 安装自研 Wayland 桌面（外壳/基础软件/sway 配置）"
  install -d -m 0755 /usr/local/lib/cibyp-desktop/lib /usr/local/lib/cibyp-desktop/bin /usr/local/lib/cibyp-desktop/session /usr/local/lib/cibyp-desktop/config /etc/cibyp/sway
  cp -a /opt/cibyp-overlay/desktop/lib/. /usr/local/lib/cibyp-desktop/lib/ 2>/dev/null || true
  cp -a /opt/cibyp-overlay/desktop/bin/. /usr/local/lib/cibyp-desktop/bin/ 2>/dev/null || true
  cp -a /opt/cibyp-overlay/desktop/bin/. /usr/local/bin/ 2>/dev/null || true
  cp -a /opt/cibyp-overlay/desktop/session/. /usr/local/lib/cibyp-desktop/session/
  cp -a /opt/cibyp-overlay/desktop/config/. /usr/local/lib/cibyp-desktop/config/
  [ -f /opt/cibyp-overlay/desktop/session/cibyp-session ] && install -m 0755 /opt/cibyp-overlay/desktop/session/cibyp-session /usr/local/bin/cibyp-session
  [ -f /opt/cibyp-overlay/desktop/session/cibyp-desktop-smoke ] && install -m 0755 /opt/cibyp-overlay/desktop/session/cibyp-desktop-smoke /usr/local/bin/cibyp-desktop-smoke
  chmod 0755 /usr/local/bin/cibyp-* 2>/dev/null || true
  chmod 0755 /usr/local/lib/cibyp-desktop/bin/cibyp-* /usr/local/lib/cibyp-desktop/session/cibyp-* 2>/dev/null || true
  if [ -f /opt/cibyp-overlay/desktop/config/sway/config ]; then
    cp /opt/cibyp-overlay/desktop/config/sway/config /etc/cibyp/sway/config
    install -d -m 0755 /etc/skel/.config/sway /home/cibyp/.config/sway
    cp /etc/cibyp/sway/config /etc/skel/.config/sway/config
    cp /etc/cibyp/sway/config /home/cibyp/.config/sway/config
    chown -R cibyp:cibyp /home/cibyp/.config 2>/dev/null || true
  fi
  install -d -m 0755 /usr/share/applications
  cp -a /opt/cibyp-overlay/desktop/applications/. /usr/share/applications/ 2>/dev/null || true
  install -d -m 0755 /usr/share/icons/hicolor/scalable/apps
  cp -a /opt/cibyp-overlay/desktop/icons/. /usr/share/icons/hicolor/scalable/apps/
  gtk-update-icon-cache -f -t /usr/share/icons/hicolor >/dev/null 2>&1 || true
  install -d -m 0755 /usr/share/wayland-sessions
  cat > /usr/share/wayland-sessions/cibyp.desktop <<'EOF'
[Desktop Entry]
Name=CIBYP 桌面
Comment=CIBYP 自研 Wayland 桌面（sway + 自研外壳）
Exec=/usr/local/bin/cibyp-session
Type=Application
DesktopNames=CIBYP
EOF
fi

# ---------------------------------------------------------------- 信息脚本
cat > /usr/local/bin/cibyp-vmos-info <<'EOF'
#!/bin/sh
# CIBYP-VM-OS 信息
. /etc/os-release
echo "CIBYP-VM-OS   : ${VERSION}"
echo "Base          : Debian GNU/Linux ${VERSION_CODENAME}"
echo "Build date    : ${CIBYP_BUILD_DATE}"
echo "Architecture  : $(dpkg --print-architecture)"
echo "Kernel        : $(uname -r)"
echo "Cmdline       : $(cat /proc/cmdline)"
echo "Workspace     : /workspace"
echo "Desktop       : CIBYP 自研 Wayland 桌面（sway + cibyp-shell）"
echo "远程桌面      : wayvnc（应用侧 VM 桌面窗口自动拉起）"
echo "SSH user      : cibyp (key-only)"
echo
echo "本系统基于 Debian GNU/Linux 构建，与 Debian 项目无隶属关系。"
echo "Debian 是 Software in the Public Interest, Inc. 的注册商标。"
EOF
chmod 0755 /usr/local/bin/cibyp-vmos-info

# 合规材料（GPL 源码可得性 + 商标声明）
install -d -m 0755 /usr/share/doc/cibyp-vmos
cat > /usr/share/doc/cibyp-vmos/README.Debian-derived <<EOF
CIBYP-VM-OS ${CIBYP_VERSION}
====================================================================

本镜像是基于 Debian GNU/Linux 的再打包系统（remix），由 B5-Software 生成，
供 "Could I Be Your Partner" 应用的虚拟机沙盒使用。

- 镜像内的全部软件包均来自 Debian 官方归档（deb.debian.org），未做修改。
- 因此这些软件的对应源代码可从 Debian 官方归档获取：
  https://deb.debian.org/debian/  以及  https://snapshot.debian.org/
- 本镜像的构建配方（debos recipe）与其上的品牌化脚本位于：
  https://github.com/B5-Software/Could-I-Be-Your-Partner/tree/main/vm-os
- 构建日期：${CIBYP_BUILD_DATE}
- 基础发行版：Debian GNU/Linux 13 (${CIBYP_BASE_SUITE})

商标声明：
  CIBYP-VM-OS 基于 Debian GNU/Linux 构建。Debian 是 Software in the Public
  Interest, Inc. 的注册商标。CIBYP-VM-OS 与 Debian 项目无隶属、赞助或背书关系。

许可：
  CIBYP-VM-OS 的构建脚本以 GPL-3.0-or-later 发布；镜像内各软件包的许可
  见 /usr/share/doc/<package>/copyright。
EOF

echo "[cibyp] provisioning done"
