# Campus 原生 Wayland 桌面

桌面以 Sway 管理窗口，以 GTK 4 / PyGObject 提供原生应用，以 layer-shell 提供桌面和底部任务栏。Cairo 绘制校园插画与统一矢量图标；终端使用 GTK 4 VTE 的真实 PTY。Chromium 保留浏览器及 CDP 自动化功能。

## 已实现

- 原生窗口框架：拖动、关闭、最小化、最大化与恢复、左右贴靠、标题栏右键菜单。
- 底部任务栏：固定应用、多个窗口分组、恢复最小化窗口、开始菜单搜索、时钟日历、工作区与显示桌面。
- 文件管理器：异步浏览、地址栏、历史、搜索、排序、隐藏文件、新建、复制/剪切/粘贴、拖放、重命名、回收站与恢复、属性和右键菜单。
- 编辑器：UTF-8、多标签、查找替换、撤销重做、原子保存、另存为、未保存提示与外部改动检测。
- 终端：真实工作目录、多标签、搜索、复制粘贴、滚动历史与运行中终端换色。
- 计算器：受限语法计算、科学运算、角度模式、记忆与历史。
- 图片查看器：异步读取、前后切换、缩放、旋转、幻灯片、属性与定位文件。
- 设置：深浅色、强调色、背景色、校园壁纸、桌面图标、固定应用、快捷键和真实显示器模式。
- App 联动：App 配色实时传递到桌面、任务栏及已打开的内置应用；离线设置在下次连接时恢复。

## 结构

`campus_core.py` 独立负责配置、原子文件操作、复制、受限数学表达式和窗口树解析。`cibypui.py` 提供共享主题、控件、菜单、对话框与窗口框架。`campus_windows.py` 把用户窗口操作转换为 Sway IPC，保存恢复几何信息。各 `campus_*.py` 按应用划分，`bin/cibyp-*` 为小型入口。

`session/campus-session.py` 为进程监督器，记录自己的会话环境与进程，结束时只清理自己创建的进程组；不会按名称批量结束其他桌面或浏览器。无头测试同样使用独立 HOME、配置和运行目录。

配置在 XDG 配置目录的 `cibyp/desktop.json`。连接 App 后 `appearance_source=app`，`theme`、`accent_color`、`background_color` 由 App 统一管理；壁纸与任务栏等 OS 偏好保留。目录监控支持原子替换，更新现有窗口。没有 App 时可独立使用本地外观设置。

## 开发与验证

在具有 GTK 4、GTK4 layer-shell、VTE 3.91、Sway、wayvnc、grim、Cairo 和中文字体的 Linux 中：

```sh
python3 tests/test_desktop.py
python3 tests/desktop_smoke.py
```

第一项覆盖真实文件操作、并发配置、保存失败、回收站恢复、数学输入和任务栏窗口保留。第二项建立原生 Wayland 会话，通过 RFB 鼠标和键盘驱动界面，检查实际文件及像素结果。相邻 App 仓库可用时，额外检查生产 App 外观同步通道。

单独预览：

```sh
python3 tests/desktop-preview.py --duration 600 --port 5909
```

生成图标：

```sh
python3 scripts/generate-icons.py
```

桌面源码由本 OS 仓库构建进镜像，App 不携带或安装桌面更新包。`VERSION` 和配方默认版本为 `0.3.0`，推送 `vm-os-v0.3.0` 标签触发现有六组构建和 QEMU 冒烟；成功后发布系统盘、内核、校验和与运行时清单到 `vm-os-latest`。App 通过既有镜像下载/安装入口使用该版本。

镜像内使用 `cibyp-desktop-smoke --geometry 1280x800 --out-png /tmp/cibyp-desktop.png` 检查完整桌面、任务栏、开始菜单和七个原生应用。该脚本保留既有 CI 结果标记协议，同时使用独立临时会话。完整系统盘发布状态以对应版本 CI 与 Release 为准，原生 WSL 验证不替代 QEMU 系统盘检查。
