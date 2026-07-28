# Tyty Windows 核心在 Ubuntu 上运行

## 项目用途

```
记录日期：2026-07-28

- Ubuntu Tyty 客户端版本：4.5.3
- Windows Tyty 客户端版本：4.8.17
```

[Tyty](https://tyty.click/) 新版已经停止提供 Linux 客户端，而旧版 Linux 核心无法兼容大部分当前节点。本目录通过 Wine 直接运行 Tyty Windows 4.8.17 自带的私有 `mihomo.exe`，在 Ubuntu 本机提供 HTTP/SOCKS 代理。

实测 Windows 私有核心可连接 46/48 个节点；相同配置使用公开 Linux Mihomo 时只有 1/48 个节点可用。因此这里运行的是 Windows 核心，而不是完整的 Tyty 图形客户端。

仓库保留 `mihomo.exe`，以确保克隆后具备与 Windows Tyty 4.8.17 相同的核心兼容性。该文件约 31 MB，来源于 Windows Tyty 4.8.17 安装包，不包含个人账号或节点配置；个人节点凭据仅保存在被 `.gitignore` 排除的 `config.yaml` 中。

## 实现方式

1. 从 Tyty Windows 4.8.17 安装包提取 `mihomo.exe`。
2. 从 Windows Tyty 用户目录提取并解密实际运行配置。
3. 使用 64 位 Wine 在 Ubuntu 中运行该 Windows 核心。
4. 核心优先在 `127.0.0.1:29674` 提供 HTTP/SOCKS 混合代理；Wine socket 尚未释放时自动切换备用端口。
5. `start.sh` 自动修改 GNOME 网络代理设置，`stop.sh` 自动关闭。
6. 本地 WebUI 通过 Mihomo 控制 API 查询、测速和切换节点。

## 依赖

- Ubuntu 22.04 GNOME
- `wine64`
- Node.js
- `curl`、`flock`、`pgrep` 和 `timeout`
- `gsettings`
- Python 3 和 `python3-yaml`
- `python3-gi`、GTK 3 和 Ayatana AppIndicator
- `xdg-open`（由 `xdg-utils` 提供）

Wine 使用纯 64 位安装，不需要运行完整的 Tyty Windows 界面，也不依赖 Windows TUN 驱动。

在新的 Ubuntu 22.04 电脑上可安装基础依赖：

```bash
sudo apt update
sudo apt install --no-install-recommends wine64
sudo apt install nodejs curl util-linux procps coreutils xdg-utils python3 python3-yaml
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1
```

GNOME 自带 `gsettings`。如果使用其他桌面环境，代理核心仍能运行，但 `start.sh` 可能无法自动修改桌面系统代理。

## 使用说明

```text
tyty-wine-core/
├── README.md       # 使用说明
├── config.yaml     # 解密后的 Mihomo 配置，包含节点凭据
├── indicator.py    # Ubuntu右上角状态指示器
├── install-desktop.sh # 安装Ubuntu应用菜单入口
├── mihomo.exe      # Tyty Windows 私有代理核心
├── start.sh        # 启动核心、WebUI和Ubuntu系统代理
├── stop.sh         # 关闭系统代理、WebUI和Wine核心
├── test.sh         # 测试代理是否能够访问外网
├── update-config.sh # 从Windows导出文件更新节点配置
├── webui.js        # 本地节点选择WebUI
├── tyty-wine.desktop.in # Desktop入口模板
└── runtime/        # 自动生成的Wine环境、日志、缓存和PID
```

`config.yaml` 包含服务器地址和节点密码，请勿上传、公开或发送给其他人。

### 启动

```bash
./start.sh
```

启动脚本会自动完成以下操作：

- 启动 Wine 和 Tyty Windows Mihomo 核心；
- 默认选择已验证的“新加坡02_NF/GPT”；
- 启动本地节点选择 WebUI；
- 启动 Ubuntu 右上角 AppIndicator；
- 将 Ubuntu 网络代理设置为手动模式；
- 将 HTTP、HTTPS 和 SOCKS 代理设置为当前实际使用的本地端口。

### 选择节点

浏览器打开：

```text
http://127.0.0.1:29100
```

WebUI 支持：

- 查看和切换当前节点；
- 测试单个节点；
- 并发测试全部节点；
- 按延迟或名称排序；
- 搜索节点。

WebUI 和 Mihomo 控制接口都只监听 `127.0.0.1`，不会向局域网开放。

### Ubuntu 状态指示器

`start.sh` 会自动在 Ubuntu 顶栏右侧启动 Tyty AppIndicator。单击图标可查看：

- 核心运行状态；
- 当前选择的节点；
- 打开状态窗口；
- 打开节点选择 WebUI；
- 测试代理连接；
- 停止代理。

GNOME AppIndicator 的主单击按桌面规范打开菜单。选择“打开状态窗口”会显示 GTK 状态窗口；中键单击图标可直接打开该窗口。

### 检查连接

```bash
./test.sh
```

输出 `Tyty Wine proxy is working` 表示代理工作正常。

## 从 Windows 导出并更新配置

本项目的 `config.yaml` 是一次节点配置快照，不会自动登录 Tyty 账号更新。出现以下情况时，建议重新从 Windows 导出：

- Windows Tyty 出现新节点或删除旧节点；
- Ubuntu 上大量节点突然不可用；
- 账号续费、套餐变更或重新登录；
- 作为例行检查，可每月更新一次。

### 1. 在 Windows 刷新配置

1. 启动 Windows Tyty 4.8.17 并登录账号。
2. 在客户端中刷新节点，确认 Windows 上能够正常连接。
3. 从系统托盘完全退出 Tyty，避免复制到尚未写完的文件。
4. 按 `Win + R`，输入：

```text
%APPDATA%\tyty\work
```

如果该目录不存在，再尝试：

```text
%APPDATA%\Tyty\work
```

5. 复制其中的 `config.yaml`。这是 Windows 客户端实际交给私有 Mihomo 核心的加密运行配置。

### 2. 复制到 Ubuntu

在仓库目录中创建 `windows-export/`，并将文件保存为：

```text
windows-export/config.yaml
```

`windows-export/` 已加入 `.gitignore`。该文件同样包含节点凭据，不要上传或分享。

### 3. 自动更新

```bash
cd <仓库目录>
./update-config.sh windows-export/config.yaml
```

也可以指定任意导出路径：

```bash
./update-config.sh /path/to/windows/config.yaml
```

使用默认的 `windows-export/config.yaml` 路径时，可直接运行：

```bash
./update-config.sh
```

更新脚本会自动完成：

1. 解密 Windows Tyty 的 Base64/XOR 配置；
2. 保留最新节点、密码、SNI和策略组；
3. 调整为 Wine 使用的本地端口并关闭 TUN；
4. 使用 Windows 私有核心校验新配置；
5. 将旧配置备份到 `runtime/config.backup.yaml`；
6. 如果代理原本正在运行，自动停止并重新启动。

只有校验成功后才会替换现有 `config.yaml`。

## 停止

```bash
./stop.sh
```

停止脚本会先关闭 Ubuntu 系统代理，再停止 WebUI、Mihomo 和 Wine，避免系统保留一个已经失效的代理地址。

## 端口

| 地址 | 用途 |
| --- | --- |
| `127.0.0.1:29674` | 首选 HTTP/SOCKS 混合代理，备用为 `29675`、`29676` |
| `127.0.0.1:29090` | 首选 Mihomo 控制 API，备用为 `29091`、`29092` |
| `127.0.0.1:29100` | 节点选择 WebUI |

实际选中的核心端口记录在 `runtime/ports.env`。Indicator、WebUI、连接测试和 GNOME 系统代理会自动使用同一组端口，无需手动修改。

## 在另一台电脑上使用

1. 克隆仓库并进入目录：

```bash
git clone <repository-url>
cd tyty-wine-core
```

2. 按“从 Windows 导出并更新配置”章节，将 Windows Tyty 的加密运行配置复制到：

```text
windows-export/config.yaml
```

3. 生成本机使用的明文配置：

```bash
./update-config.sh windows-export/config.yaml
```

4. 启动代理：

```bash
./start.sh
```

首次启动时，Wine 会在被 `.gitignore` 排除的 `runtime/wine-prefix/` 中自动初始化本机运行环境。

## 安装到 Ubuntu 应用菜单

在仓库目录执行：

```bash
./install-desktop.sh
```

脚本会根据当前仓库的实际位置生成 Desktop 文件并安装到：

```text
~/.local/share/applications/tyty-wine.desktop
```

安装后可在 Ubuntu 应用菜单中搜索“Tyty VPN”。打开应用会执行 `start.sh`，自动启动核心、WebUI、Indicator并设置系统代理。

在支持 Desktop Actions 的应用菜单中，还可以使用：

- `Open Node WebUI`：打开节点选择页面；
- `Stop Tyty VPN`：关闭系统代理和全部 Tyty 进程。

仓库使用 `tyty-wine.desktop.in` 模板而不是写死路径的 `.desktop` 文件，因此 clone 到任意目录后都可以重新安装。

## 故障排查

查看核心日志：

```bash
tail -n 100 runtime/mihomo.log
```

查看 WebUI 日志：

```bash
tail -n 100 runtime/webui.log
```

如果刚停止后需要重新启动，请等待 `stop.sh` 完成。脚本会清理该项目的 Wine prefix，并对 Windows socket 错误 `10048` 自动重试一次。Wine 退出等待设置了超时，不会因残留进程无限卡住。
