# WSL Tray Bridge

<p align="center"><img src="assets/icon.png" alt="WSL Tray Bridge icon" width="128" height="128"></p>

把 Linux GUI 应用的托盘图标接到 Windows 通知区域。Windows 端使用原生托盘图标和菜单；Linux 服务负责两端的启动与退出。

**实验版本，已在 Windows 11 ARM64 + WSLg + Ubuntu 24.04 上验证。** 尚不保证所有 Linux 应用都能完整兼容，也未验证其他架构的完整安装流程。

## 特性

- 现代托盘：常见 KDE/Qt StatusNotifierItem、AppIndicator。
- Windows 原生图标、提示文字、左键与中键激活。
- DBusMenu：右键菜单、子菜单、分隔线、禁用与勾选状态、点击回传。
- 旧式 XEmbed 托盘：通过 Ubuntu 官方 KDE `xembedsniproxy` 转换。
- Ubuntu 启动时自动启动；Linux 服务停止时 Windows 托盘端退出。
- 不安装 Windows 登录启动项，不使用 Windows 常驻轮询器，不监听网络端口。

## 安装

前提：Windows 已安装并启用 WSLg；Ubuntu 已启用 systemd，默认用户可使用 `systemctl --user`。安装脚本针对 Ubuntu 24.04。

在 Windows PowerShell 中进入仓库目录：

```powershell
.\build.ps1
.\install.ps1 -Distro Ubuntu
```

脚本会安装所需 Ubuntu 依赖，下载官方 `plasma-workspace` 包并只提取托盘转换程序，**不会安装 KDE 桌面**。程序路径按当前 Windows/Linux 用户自动生成，不需要修改源码中的用户名。

只使用现代托盘、不需要旧式 X11 兼容时：

```powershell
.\install.ps1 -Distro Ubuntu -NoLegacy
```

依赖来自已配置的 Ubuntu APT 软件源；仓库不附带 KDE 二进制。安装时默认通过 `wsl.exe -u root` 安装依赖，请先阅读脚本。

## 使用

安装后由 Ubuntu 用户服务自动管理：

```bash
systemctl --user status wsl-tray-bridge.service
systemctl --user start wsl-tray-bridge.service
systemctl --user stop wsl-tray-bridge.service
journalctl --user -u wsl-tray-bridge.service
```

桌面和开始菜单中的 **WSL Tray Bridge** 快捷方式可以手动恢复服务。

Windows 新托盘图标可能出现在右下角 **隐藏图标（∧）** 中，可手动拖到通知区域。左键激活应用，中键转发备用动作，右键打开菜单。桥接管理图标的 **Exit bridge** 会退出桥接，保留其他 Linux 应用。

管理图标右键菜单的 **Exit bridge and stop Ubuntu...**（名称随配置的发行版变化）会先弹出确认，再退出桥接并执行 `wsl.exe --terminate <发行版>`。这会停止该发行版中的全部应用、终端和后台服务，请先保存工作。它只停止当前配置的发行版；不是关闭所有发行版和 WSL 虚拟机的 `wsl --shutdown`。独立的 Windows 辅助进程会等托盘清理完毕再执行命令；若关闭失败会显示错误。

应用先于桥接启动时通常能重新注册；没有出现图标的应用可完全退出后重新打开。应用本身必须提供托盘功能。

### 生命周期

Linux 的 `systemd --user` 服务启动 `lifecycle.py`，再由它启动 Windows 托盘端和 Linux D-Bus 端，通过私有标准输入输出管道通信。没有长期运行的 Windows → `wsl.exe` 客户端。Linux 服务停止会关闭管道，Windows 端收到 EOF 后移除图标并退出。

关闭单个终端窗口不一定意味着 Ubuntu 实例停止。若默认用户的用户服务管理器不会随实例启动，需要检查该用户的 systemd/linger 设置；安装脚本不会擅自更改全局 WSL 启动配置。

## 已验证与限制

本机验证过：Windows `Shell_NotifyIcon` 接受图标、原生菜单生成、左键激活、菜单点击回到 Linux、GTK 旧式 X11 测试图标、真实 Fcitx5 图标，以及停止 Linux 服务后 Windows 进程退出。

以下场景仍有限制：

- 没有专门演练整个 `wsl --shutdown` 或冷启动场景；服务启停和清理已测试。
- 没有保证微信登录后的托盘、未读提醒或所有软件的行为。
- 旧式 XEmbed 应用若不提供 DBusMenu，右键菜单仍由 Linux 应用通过 WSLg 弹出，位置可能不准确。
- 同时发布现代与旧式图标的应用可能出现重复图标。
- 尚未转发滚轮动作或桌面通知；动画图标、叠加徽章、特殊动态子菜单也未全面验证。
- 每个 Windows 用户当前只运行一个桥接实例；多发行版并发桥接尚不支持。
- Windows Explorer 重启后的托盘恢复依赖 .NET NotifyIcon，未单独验证。

## 文件位置

- Windows 程序：`%LOCALAPPDATA%\Programs\WSLTrayBridge`。
- Windows 状态及日志：`%LOCALAPPDATA%\WSLTrayBridge`。
- Linux 文件：`~/.local/share/wsl-tray-bridge`。
- 用户服务：`~/.config/systemd/user/wsl-tray-bridge.service`。

`host.json` 和 `config.json` 由安装脚本生成，属于本机配置，不提交到仓库。

## 卸载

```powershell
.\uninstall.ps1 -Distro Ubuntu
```

停止并禁用服务，移除 Windows 程序和快捷方式；保留日志、Linux 辅助文件和共享依赖。

## 开发

- `linux/agent.py`：SNI watcher/host、图标及 DBusMenu 桥接。
- `linux/lifecycle.py`：由 Linux 管理两端进程和退出清理。
- `windows/TrayBridge.cs`：.NET Framework/WinForms 原生托盘端。
- `scripts/configure_linux.py`：安装 Linux 文件、提取可选代理、启用用户服务。
- `tests/integration_fixture.py`：生成临时 SNI 与旧式 X11 测试托盘，需要图形会话和 D-Bus；不是无界面单元测试。
- `tests/test_shutdown.ps1`：验证关闭命令、退出顺序和失败分支，使用替代执行器，不会关闭实际 WSL。

Windows 构建使用系统自带的 Windows PowerShell 5.1 和 .NET Framework 编译器，不要求额外安装 .NET SDK。PowerShell 7 调用构建脚本时会转交给 Windows PowerShell。

## 第三方组件

旧式托盘代理来自 KDE，运行时从 Ubuntu 官方包提取，其许可证和版权文件会一起保存。详见 [THIRD_PARTY.md](THIRD_PARTY.md)。

- [StatusNotifierItem 规范](https://specifications.freedesktop.org/status-notifier-item/latest-single/)
- [KDE XEmbed/SNI 代理源码](https://invent.kde.org/plasma/plasma-workspace/-/tree/Plasma/5.27/xembed-sni-proxy)
- [WSL systemd 说明](https://learn.microsoft.com/windows/wsl/systemd)
