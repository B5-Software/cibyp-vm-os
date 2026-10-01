# Code-OSS 远程工作台后端

所有镜像变体内置完整 VSCodium Remote Extension Host：Node、内置扩展、远程文件服务、文件监听、PTY 与扩展宿主。桌面 Electron 工作台由 CIBYP App 提供，工作区扩展、Git、终端、语言服务、调试及构建在 VM 中运行。

`recipes/overlay/codeoss/runtime-lock.json` 固定版本、commit 和两种 Linux 架构的下载校验和，与 App 仓库的同名文件保持一致。保留 MIT 许可证和第三方声明。构建阶段安装后端，运行中的 App 只连接，不下载或安装软件。扩展来源沿用 Open VSX 和 VSIX；各扩展仍受自己的许可证约束。

App 通过已认证的 SSH 执行 `cibyp-codeoss-server --cibyp-start <commit> <token>`。服务只监听 127.0.0.1，返回 JSON 中的端口由 App 建立 SSH 转发。启动锁防止并发重复拉起；连接令牌和状态目录仅当前用户可读。客户端 commit 不匹配时拒绝启动，更新 OS 镜像后连接。重连返回原进程的有效令牌，不把新令牌错误传给仍在运行的服务。

服务数据位于 `~/.local/state/cibyp/codeoss/<commit>/data`。宿主和 VM 的扩展按 Code-OSS 的 UI/workspace 类型分别加载；VM 的工作区扩展使用 VM 文件系统。App 中的 CIBYP UI 扩展同步个性化并接入既有 Agent 和预算体系。

本机可用 `python3 tests/codeoss-server-smoke.py <已解压的 REH 目录>` 检查真实服务。镜像 CI 的 boot 检查会验证启动、版本匹配、loopback 监听和重连，六组镜像通过后发布。
