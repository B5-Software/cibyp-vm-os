#!/usr/bin/env node
/*
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright (c) 2026 B5-Software
 *
 * This file is part of Could I Be Your Partner.
 *
 * CIBYP-VM-OS boot 冒烟测试（CI 用，零第三方依赖）。
 *
 * 验证内容：
 *   1. 内核/initrd 直接引导可用（无需引导器）
 *   2. cloud-init（NoCloud-net over HTTP）完成首启配置
 *   3. 出厂契约：cibyp 用户 + NOPASSWD sudo + /workspace + sshd 仅密钥 + os-release 品牌
 *   4. 网络不依赖 cloud-init（systemd-networkd 起 eth0）
 *   5. 持久化：同一 overlay 重启后 /workspace 数据仍在
 *   6. 重置：删除 overlay 后重启回到出厂态（数据消失）
 *
 * 用法：
 *   node vm-os/tests/boot-smoke.js --image <qcow2> --kernel <vmlinuz> --initrd <initrd.img>
 *        --arch amd64|arm64 --variant base [--work <dir>] [--timeout 900]
 *
 * 退出码：0 全部通过；1 失败（打印失败项与串口尾部）。
 */

'use strict';

const fs = require('fs');
const os = require('os');
const net = require('net');
const http = require('http');
const path = require('path');
const { spawn, spawnSync } = require('child_process');

const QEMU_BIN = { amd64: 'qemu-system-x86_64', arm64: 'qemu-system-aarch64' };
const QEMU_MACHINE = { amd64: 'q35', arm64: 'virt' };
const GUEST_CONSOLE = { amd64: 'ttyS0', arm64: 'ttyAMA0' };

/**
 * 加速后端 → CPU 模型（与 App 侧 src/main/vm/qemu-runtime.js 同策略）。
 * 实测坑：WHPX 不支持 -cpu max/host（`WHPX: Unexpected VP exit code 4`，vCPU 死而进程活），
 * 因此 WHPX 一律不传 -cpu（用 QEMU 默认模型）。
 */
function cpuModelFor(accel) {
  if (accel === 'whpx') return null;
  if (accel === 'kvm' || accel === 'hvf') return 'host';
  return 'max';
}

function parseArgs(argv) {
  const out = {
    image: null, kernel: null, initrd: null, arch: 'amd64', variant: 'base',
    work: null, timeout: 900, mem: 2048, smp: 2,
  };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    const val = () => argv[++i];
    if (a === '--image') out.image = val();
    else if (a === '--kernel') out.kernel = val();
    else if (a === '--initrd') out.initrd = val();
    else if (a === '--arch') out.arch = val();
    else if (a === '--variant') out.variant = val();
    else if (a === '--work') out.work = val();
    else if (a === '--timeout') out.timeout = parseInt(val(), 10);
    else if (a === '--mem') out.mem = parseInt(val(), 10);
    else if (a === '--smp') out.smp = parseInt(val(), 10);
    else throw new Error('未知参数: ' + a);
  }
  for (const k of ['image', 'kernel', 'initrd']) if (!out[k]) throw new Error('缺少必填参数 --' + k);
  if (!QEMU_BIN[out.arch]) throw new Error('不支持的架构: ' + out.arch);
  if (!out.work) out.work = path.join(os.tmpdir(), `vmos-smoke-${out.variant}-${out.arch}`);
  return out;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (...a) => console.log(`[${new Date().toISOString().slice(11, 19)}]`, ...a);

function freePort() {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.on('error', reject);
    s.listen(0, '127.0.0.1', () => {
      const p = s.address().port;
      s.close(() => resolve(p));
    });
  });
}

function which(bin) {
  const r = spawnSync(process.platform === 'win32' ? 'where' : 'which', [bin], { encoding: 'utf8' });
  return r.status === 0 && !!(r.stdout || '').trim();
}

// ---------------------------------------------------------------- SSH

function sshRun(key, port, knownHosts, cmd, timeoutMs = 120000) {
  const r = spawnSync('ssh', [
    '-i', key, '-p', String(port),
    '-o', 'StrictHostKeyChecking=no',
    '-o', `UserKnownHostsFile=${knownHosts}`,
    '-o', 'LogLevel=ERROR',
    '-o', 'ConnectTimeout=10',
    '-o', 'BatchMode=yes',
    '-o', 'ServerAliveInterval=15',
    'cibyp@127.0.0.1', cmd,
  ], { encoding: 'utf8', timeout: timeoutMs, maxBuffer: 16 * 1024 * 1024 });
  return { code: r.status, out: (r.stdout || '').trim(), err: (r.stderr || '').trim() };
}

async function sshWaitFor(key, port, knownHosts, cmd, timeoutMs, intervalMs = 3000) {
  const deadline = Date.now() + timeoutMs;
  let last = null;
  while (Date.now() < deadline) {
    last = sshRun(key, port, knownHosts, cmd, 30000);
    if (last.code === 0) return last;
    await sleep(intervalMs);
  }
  return last || { code: -1, out: '', err: 'timeout' };
}

// ---------------------------------------------------------------- 加速器真实探测

/**
 * 加速器可用性硬探测：真实拉起一只空机器，存活且无致命签名才算可用。
 * 背景：CI runner 的 QEMU 二进制"支持"kvm（-accel help 会列出），但 /dev/kvm 不可访问时
 * 会立刻退出（exit 1、串口零输出）——只查列表会误判（实测踩坑）。
 */
function probeAccelReal(accel, arch) {
  const args = ['-accel', accel, '-machine', QEMU_MACHINE[arch], '-display', 'none', '-nodefaults', '-m', '256'];
  const cpu = cpuModelFor(accel);
  if (cpu) args.push('-cpu', cpu);
  const r = spawnSync(QEMU_BIN[arch], args, { timeout: 5000, encoding: 'utf8' });
  const alive = !!r.error && /ETIMEDOUT|timed out/i.test(r.error.message || '');
  const combined = ((r.stderr || '') + (r.stdout || '') + (r.error ? r.error.message : '')).trim();
  const fatal = /WHPX: Unexpected VP exit code|Could not access KVM|KVM: not found|kvm_init_vcpu failed|hvf: failed|Permission denied|Operation not permitted/i.test(combined);
  return { ok: alive && !fatal, detail: combined.split('\n').filter(Boolean).slice(0, 2).join(' | ').slice(0, 200) };
}

/** 按平台优先级挑选真实可用的加速器 */
function pickAccel(arch) {
  const list = spawnSync(QEMU_BIN[arch], ['-accel', 'help'], { encoding: 'utf8', timeout: 20000 });
  const text = ((list.stdout || '') + (list.stderr || '')).trim();
  const prefer = process.platform === 'linux' ? ['kvm', 'tcg'] : process.platform === 'darwin' ? ['hvf', 'tcg'] : ['whpx', 'tcg'];
  for (const accel of prefer) {
    if (!text.includes(accel)) { console.log('  [accel] ' + accel + ' 不在二进制支持列表'); continue; }
    const r = probeAccelReal(accel, arch);
    console.log('  [accel] ' + accel + ' 真实探测: ' + (r.ok ? '可用' : '不可用' + (r.detail ? '（' + r.detail + '）' : '')));
    if (r.ok) return { accel, detail: r.detail };
  }
  return { accel: 'tcg', detail: '无硬件加速可用，回退 TCG' };
}

// ---------------------------------------------------------------- QEMU 进程

class Vm {
  constructor(opts, work) {
    this.opts = opts;
    this.work = work;
    this.child = null;
    this.exit = null;
    this.serialFile = path.join(work, 'serial.log');
    this.serialBuf = '';
    this.qemuLog = path.join(work, 'qemu.log');
  }

  detectAccel() {
    const help = spawnSync(QEMU_BIN[this.opts.arch], ['-accel', 'help'], { encoding: 'utf8', timeout: 20000 });
    const text = ((help.stdout || '') + (help.stderr || '')).trim();
    const list = text.split(/\s+/).filter(Boolean);
    // 宿主平台优先级
    const pref = process.platform === 'linux' ? ['kvm', 'tcg'] : process.platform === 'darwin' ? ['hvf', 'tcg'] : ['whpx', 'tcg'];
    const chosen = pref.find((a) => list.includes(a)) || 'tcg';
    return { chosen, list, text };
  }

  start({ accel, sshPort, serialPort, ciPort, overlay }) {
    this.exit = null;      // 关键：新一轮启动必须清掉上一轮的退出状态
    this.serialBuf = '';
    // 内核命令行同时携带 cloud-init 种子（ARM virt 的 SMBIOS 不可靠：实测回退 DataSourceNone）
    const cmdline = `root=LABEL=cibyp-root rw console=${GUEST_CONSOLE[this.opts.arch]},115200 net.ifnames=0 rootwait ds=nocloud-net;s=http://10.0.2.2:${ciPort}/`;
    const argv = [
      '-name', `vmos-smoke-${this.opts.variant}`,
      '-machine', QEMU_MACHINE[this.opts.arch],
      '-accel', accel,
      '-smp', String(this.opts.smp),
      '-m', String(this.opts.mem),
      '-kernel', this.opts.kernel,
      '-initrd', this.opts.initrd,
      '-append', cmdline,
      '-drive', `file=${overlay},if=virtio,format=qcow2,cache=writeback,discard=unmap`,
      '-netdev', `user,id=n0,hostfwd=tcp:127.0.0.1:${sshPort}-:22`,
      // romfile= 关闭 option ROM：部分发行版不带 efi-virtio.rom（缺失会直接启动失败）
      '-device', 'virtio-net-pci,netdev=n0,romfile=',
      '-chardev', `socket,id=ser0,host=127.0.0.1,port=${serialPort},server=on,wait=off`,
      '-serial', 'chardev:ser0',
      '-smbios', `type=1,serial=ds=nocloud-net;s=http://10.0.2.2:${ciPort}/`,
      '-device', 'virtio-rng-pci',
      '-display', 'none',
      '-monitor', 'none',
    ];
    if (accel === 'kvm' || accel === 'hvf') argv.push('-cpu', 'host');
    else {
      const cpu = cpuModelFor(accel); // whpx → null（默认模型），tcg → max
      if (cpu) argv.push('-cpu', cpu);
    }

    const out = fs.createWriteStream(this.qemuLog, { flags: 'w' });
    out.write(`# ${QEMU_BIN[this.opts.arch]} ${argv.join(' ')}\n`);
    this.child = spawn(QEMU_BIN[this.opts.arch], argv, { windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    this.child.stdout.on('data', (d) => out.write(d));
    this.child.stderr.on('data', (d) => out.write(d));
    this.child.on('exit', (code, signal) => { this.exit = { code, signal }; out.end(); });

    // 串口采集（QEMU 为 server，我们连它）
    const ser = fs.createWriteStream(this.serialFile, { flags: 'w' });
    const connect = () => {
      if (this.exit) return;
      const sock = net.connect({ host: '127.0.0.1', port: serialPort });
      // error 与 close 可能同时触发：用一次性闸门，避免重连指数分裂（实测导致 OOM）
      let retried = false;
      const retry = () => {
        if (retried) return;
        retried = true;
        if (!this.exit) setTimeout(connect, 1000);
      };
      sock.on('data', (d) => { this.serialBuf = (this.serialBuf + d.toString('utf8')).slice(-128 * 1024); ser.write(d); });
      sock.on('error', retry);
      sock.on('close', retry);
    };
    connect();
    return argv;
  }

  async waitSshReady(port, timeoutMs) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      const alive = await new Promise((resolve) => {
        const s = net.connect({ host: '127.0.0.1', port });
        let settled = false;
        const finish = (v) => { if (settled) return; settled = true; clearTimeout(hard); try { s.destroy(); } catch { /* ignore */ } resolve(v); };
        // 硬超时 + end/close 兜底：slirp 在 guest sshd 未就绪时会直接关连接（FIN），
        // 只监听 data/error/timeout 会永久挂住（实测踩坑，与 p0 spike 同因）
        const hard = setTimeout(() => finish(false), 6000);
        s.setTimeout(4000);
        s.once('data', () => finish(true));
        s.once('error', () => finish(false));
        s.once('timeout', () => finish(false));
        s.once('end', () => finish(false));
        s.once('close', () => finish(false));
      });
      if (alive) return { ok: true, ms: Date.now() - t0 };
      if (this.exit) return { ok: false, ms: Date.now() - t0, reason: `qemu 提前退出 code=${this.exit.code}` };
      await sleep(1000);
    }
    return { ok: false, ms: Date.now() - t0, reason: '超时' };
  }

  async poweroff(ssh, sshPort, knownHosts) {
    sshRun(ssh, sshPort, knownHosts, 'sudo systemctl poweroff', 15000);
    const deadline = Date.now() + 45000;
    while (!this.exit && Date.now() < deadline) await sleep(300);
    if (!this.exit) { try { this.child.kill('SIGKILL'); } catch {} }
    await sleep(500);
  }
}

// ---------------------------------------------------------------- cloud-init

function writeCloudInit(work, pubKey) {
  const dir = path.join(work, 'cloud-init');
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, 'meta-data'), 'instance-id: vmos-smoke-0001\nlocal-hostname: cibyp-vmos\n');
  fs.writeFileSync(path.join(dir, 'user-data'), [
    '#cloud-config',
    'users:',
    '  - name: cibyp',
    '    groups: [sudo]',
    '    shell: /bin/bash',
    '    lock_passwd: true',
    '    sudo: ALL=(ALL) NOPASSWD:ALL',
    '    ssh_authorized_keys:',
    `      - ${pubKey.trim()}`,
    'ssh_pwauth: false',
    'disable_root: true',
    'growpart: { mode: auto, devices: ["/"] }',
    'resize_rootfs: true',
    'timezone: UTC',
    'runcmd:',
    '  - [ sh, -c, "install -d -o cibyp -g cibyp /workspace && touch /workspace/.cibyp-ready" ]',
    '',
  ].join('\n'));
  return dir;
}

function serveCloudInit(dir, port) {
  const server = http.createServer((req, res) => {
    const name = (req.url || '/').split('?')[0].replace(/^\/+/, '') || 'index';
    const file = path.join(dir, name);
    if (fs.existsSync(file) && fs.statSync(file).isFile()) {
      res.writeHead(200, { 'Content-Type': 'text/plain' });
      res.end(fs.readFileSync(file));
    } else {
      res.writeHead(404);
      res.end('not found');
    }
  });
  return new Promise((resolve, reject) => {
    server.on('error', reject);
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

// ---------------------------------------------------------------- 断言

class Checks {
  constructor() { this.items = []; }
  assert(name, ok, detail = '') {
    this.items.push({ name, ok: !!ok, detail: String(detail).slice(0, 400) });
    log(`${ok ? '✓' : '✗'} ${name}${detail ? ' — ' + String(detail).slice(0, 160) : ''}`);
    return ok;
  }
  get failed() { return this.items.filter((i) => !i.ok); }
}

// ---------------------------------------------------------------- 主流程

async function main() {
  const opts = parseArgs(process.argv);
  const work = opts.work;
  fs.rmSync(work, { recursive: true, force: true });
  fs.mkdirSync(work, { recursive: true });

  for (const [label, f] of [['镜像', opts.image], ['内核', opts.kernel], ['initrd', opts.initrd]]) {
    if (!fs.existsSync(f)) throw new Error(`${label}不存在: ${f}`);
  }
  if (!which(QEMU_BIN[opts.arch])) throw new Error(`找不到 ${QEMU_BIN[opts.arch]}（CI 需 apt install qemu-system-*）`);
  if (!which('ssh-keygen')) throw new Error('找不到 ssh-keygen');

  const checks = new Checks();
  const key = path.join(work, 'id_ed25519');
  const g = spawnSync('ssh-keygen', ['-t', 'ed25519', '-q', '-N', '', '-C', 'vmos-smoke', '-f', key], { encoding: 'utf8' });
  if (g.status !== 0) throw new Error('ssh-keygen 失败: ' + (g.stderr || g.error));
  const knownHosts = path.join(work, 'known_hosts');
  const pubKey = fs.readFileSync(key + '.pub', 'utf8');
  const ciDir = writeCloudInit(work, pubKey);
  const ciPort = await freePort();
  const ciServer = await serveCloudInit(ciDir, ciPort);

  const overlay = path.join(work, 'overlay.qcow2');
  const createOverlay = () => {
    fs.rmSync(overlay, { force: true });
    const r = spawnSync('qemu-img', ['create', '-f', 'qcow2', '-b', path.resolve(opts.image), '-F', 'qcow2', overlay], { encoding: 'utf8' });
    if (r.status !== 0) throw new Error('qemu-img create 失败: ' + (r.stderr || r.error));
  };

  const vm = new Vm(opts, work);
  const picked = pickAccel(opts.arch);
  const accel = { chosen: picked.accel, list: [picked.accel], detail: picked.detail };
  log(`架构=${opts.arch} 变体=${opts.variant} 加速器=${accel.chosen}（${picked.detail || ''}）`);

  /** 启动一轮：返回 ssh 端口与就绪信息 */
  async function boot(roundLabel, { recreateOverlay = false } = {}) {
    const sshPort = await freePort();
    const serialPort = await freePort();
    // 只有"首轮/重置"才重建 overlay；持久化轮必须复用同一份实例磁盘
    if (recreateOverlay) createOverlay();
    if (!fs.existsSync(overlay)) createOverlay();
    const t0 = Date.now();
    vm.start({ accel: accel.chosen, sshPort, serialPort, ciPort, overlay });
    const ready = await vm.waitSshReady(sshPort, Math.min(opts.timeout * 1000, 600000));
    if (!ready.ok) {
      const qemuLogTail = (() => { try { return fs.readFileSync(vm.qemuLog, 'utf8').slice(-1500); } catch { return ''; } })();
      log(`[${roundLabel}] 启动失败：${ready.reason}；串口尾部：\n${vm.serialBuf.slice(-2000)}`);
      if (qemuLogTail) log(`[${roundLabel}] qemu.log 尾部：\n${qemuLogTail}`);
      throw new Error(`[${roundLabel}] SSH 未就绪（${ready.reason}）`);
    }
    const auth = await sshWaitFor(key, sshPort, knownHosts, 'true', 180000, 3000);
    if (auth.code !== 0) {
      // 认证失败通常意味着 cloud-init 没把密钥装进去 —— 串口里有 cloud-init 的报错
      log(`[${roundLabel}] 串口尾部（排障用）：\n${vm.serialBuf.slice(-3000)}`);
      throw new Error(`[${roundLabel}] SSH 认证失败: ${auth.err}`);
    }
    log(`[${roundLabel}] SSH 就绪（banner ${ready.ms}ms）`);
    return { sshPort, ready, t0 };
  }

  // ============ 第一轮：出厂契约 ============
  const r1 = await boot('第1轮', { recreateOverlay: true });
  const ci = await sshWaitFor(key, r1.sshPort, knownHosts, 'cloud-init status --wait >/dev/null 2>&1; echo ok', 300000, 5000);
  checks.assert('cloud-init 完成', ci.code === 0 && ci.out.includes('ok'), ci.err);

  const readyFile = await sshWaitFor(key, r1.sshPort, knownHosts, 'test -f /workspace/.cibyp-ready && echo ok', 60000, 3000);
  checks.assert('cloud-init runcmd 生效（/workspace 就绪）', readyFile.code === 0, readyFile.err);

  const probe = (cmd) => sshRun(key, r1.sshPort, knownHosts, cmd, 60000);
  const osr = probe(". /etc/os-release && echo \"$ID|$ID_LIKE|$VERSION_ID\"");
  checks.assert('os-release 品牌（ID=cibyp-vmos, ID_LIKE=debian）',
    osr.code === 0 && /^cibyp-vmos\|debian\|/.test(osr.out), osr.out);

  const sudo = probe('sudo -n true && echo ok');
  checks.assert('cibyp 具备 NOPASSWD sudo', sudo.code === 0 && sudo.out === 'ok', sudo.err);

  const ws = probe('echo smoke > /workspace/persist.txt && cat /workspace/persist.txt && stat -c %U /workspace');
  checks.assert('/workspace 可写且属主 cibyp', ws.code === 0 && ws.out.includes('cibyp') && ws.out.includes('smoke'), ws.out + ws.err);

  const netd = probe('systemctl is-active systemd-networkd');
  checks.assert('systemd-networkd 运行（网络不依赖 cloud-init）', netd.out === 'active', netd.out);

  const qga = probe('test -x /usr/sbin/qemu-ga -o -x /usr/bin/qemu-ga && echo present || echo absent');
  checks.assert('qemu-guest-agent 已安装', qga.out === 'present', qga.out);

  const info = probe('cibyp-vmos-info | head -3');
  checks.assert('cibyp-vmos-info 可用', info.code === 0 && info.out.includes('CIBYP-VM-OS'), info.out + info.err);

  const pwdAuth = probe("sudo sshd -T 2>/dev/null | grep -E '^passwordauthentication' || grep -i '^PasswordAuthentication' /etc/ssh/sshd_config.d/*.conf");
  checks.assert('sshd 关闭密码认证', /no/i.test(pwdAuth.out), pwdAuth.out);

  const kernel = probe('uname -r');
  checks.assert('内核由宿主直接引导可用', kernel.code === 0 && kernel.out.length > 3, kernel.out);
  log('guest 内核: ' + kernel.out);

  const disk = probe("df -h / | tail -1 | awk '{print $2, $4}'");
  log('根分区容量/可用: ' + disk.out);

  // ============ 桌面会话（desktop/full 变体）：Wayland + 自研外壳 ============
  if (opts.variant === 'desktop' || opts.variant === 'full') {
    const comps = probe('command -v sway && command -v grim && command -v wayvnc && command -v cibyp-session && command -v cibyp-shell && command -v cibyp-desktop && command -v cibypctl && echo ok || echo missing');
    checks.assert('桌面组件齐备（sway/wayvnc/grim + 自研外壳与基础软件）', comps.out.includes('ok'), comps.out + comps.err);

    const bind = probe("python3 -c \"import gi; gi.require_version('Gtk4LayerShell','1.0'); from gi.repository import Gtk4LayerShell; print('layershell-ok')\" 2>&1 | tail -1");
    checks.assert('GTK4 layer-shell 绑定可用', bind.out.includes('layershell-ok'), bind.out);

    const apps = probe("for a in cibyp-files cibyp-editor cibyp-settings cibyp-calc cibyp-viewer cibyp-about; do command -v $a >/dev/null || echo missing-$a; done; echo apps-ok");
    checks.assert('自研基础软件已安装（文件/编辑器/设置/计算器/图片查看器/关于）', apps.out.includes('apps-ok') && !apps.out.includes('missing-'), apps.out);

    const desktopEntries = probe("ls /usr/share/applications/cibyp-*.desktop | wc -l");
    checks.assert('桌面菜单项（.desktop）已安装', parseInt(desktopEntries.out, 10) >= 7, desktopEntries.out);

    log('开始桌面会话冒烟（无头 Wayland，可能需要 1-3 分钟）…');
    const dsmoke = sshRun(key, r1.sshPort, knownHosts,
        'CIBYP_GEOMETRY=1280x800 cibyp-desktop-smoke --geometry 1280x800 --out-png /tmp/cibyp-desktop.png 2>&1 | tail -200', 480000);
    if (!(dsmoke.code === 0 && /结果：全部通过/.test(dsmoke.out))) {
      // 失败：回读 guest 侧的完整诊断（会话日志 / 进程 / 环境），避免被 tail 截断
      const diag = sshRun(key, r1.sshPort, knownHosts,
        'tail -c 6000 /tmp/cibyp-desktop-smoke-$(id -u).log 2>/dev/null; echo "---- ps ----"; ps -eo user,pid,args | grep -E "cibyp|sway|wayvnc" | grep -v grep | head -15', 60000);
      log('桌面冒烟失败，guest 诊断如下：\n' + diag.out);
    }
      const dsmokeFail = (String(dsmoke.out || '').match(/^.*FAIL.*$/gm) || []).join(' | ');
      checks.assert('桌面会话冒烟（sway + 自研外壳 + 截图 + 开始菜单）',
        dsmoke.code === 0 && /结果：全部通过/.test(dsmoke.out), (dsmokeFail || String(dsmoke.out || '').slice(-400)));

    const ver = process.env.VMOS_VERSION || '';
    const localPng = path.join(work, `cibyp-vmos-${ver ? ver + '-' : ''}${opts.variant}-${opts.arch}-desktop.png`);
    const scp = spawnSync('scp', ['-P', String(r1.sshPort), '-i', key, '-o', 'StrictHostKeyChecking=no',
      '-o', `UserKnownHostsFile=${knownHosts}`, 'cibyp@127.0.0.1:/tmp/cibyp-desktop.png', localPng], { encoding: 'utf8' });
    const pngOk = scp.status === 0 && fs.existsSync(localPng) && fs.statSync(localPng).size > 20000;
    checks.assert('桌面预览图已生成（PNG ≥ 20KB）', pngOk, (scp.stderr || '').slice(0, 200));
    if (pngOk) {
      log(`桌面预览图: ${path.basename(localPng)}（${Math.round(fs.statSync(localPng).size / 1024)} KB）`);
      // amd64/desktop 额外产出一份稳定文件名，供 README / 发布说明直接引用
      if (opts.variant === 'desktop' && opts.arch === 'amd64') {
        try { fs.copyFileSync(localPng, path.join(work, 'desktop-preview.png')); } catch { /* ignore */ }
      }
    }
  }

  // ============ 第二轮：同一 overlay 重启 → 数据持久 ============
  await vm.poweroff(key, r1.sshPort, knownHosts);
  const r2 = await boot('第2轮');
  const persist = await sshWaitFor(key, r2.sshPort, knownHosts, 'cat /workspace/persist.txt', 120000, 3000);
  checks.assert('持久化：同一 overlay 重启后数据保留', persist.code === 0 && persist.out.includes('smoke'), persist.err);

  // ============ 第三轮：删除 overlay（重置）→ 回出厂态 ============
  await vm.poweroff(key, r2.sshPort, knownHosts);
  const r3 = await boot('第3轮（重置后）', { recreateOverlay: true });
  const afterReset = await sshWaitFor(key, r3.sshPort, knownHosts, 'test -f /workspace/persist.txt && echo exists || echo gone', 120000, 3000);
  checks.assert('重置语义：删除 overlay 后回到出厂态', afterReset.out === 'gone', afterReset.out);

  await vm.poweroff(key, r3.sshPort, knownHosts);
  ciServer.close();

  const report = {
    ts: new Date().toISOString(),
    arch: opts.arch,
    variant: opts.variant,
    accel: accel.chosen,
    qemuAccelAvailable: accel.list,
    sshReadyMs: r1.ready.ms,
    checks: checks.items,
    passed: checks.items.length - checks.failed.length,
    failed: checks.failed.length,
  };
  fs.writeFileSync(path.join(work, 'smoke-report.json'), JSON.stringify(report, null, 2));

  console.log('\n================ boot 冒烟结果 ================');
  console.log(`架构 ${opts.arch} / 变体 ${opts.variant} / 加速器 ${accel.chosen}`);
  console.log(`通过 ${report.passed} / 失败 ${report.failed}`);
  if (report.failed) {
    for (const f of checks.failed) console.log(`  ✗ ${f.name} — ${f.detail}`);
    console.log(`串口尾部:\n${vm.serialBuf.slice(-3000)}`);
    process.exit(1);
  }
  console.log('全部通过 ✅');
}

main().catch((e) => {
  console.error('\n[冒烟失败]', e.message);
  process.exit(1);
});
