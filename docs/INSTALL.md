# Windows 安装与接管

## 依赖

Windows 10/11 桌面、Python 3.10+、Git、AutoHotkey v2。输入辅助按 AHK v2 语法验证，不兼容 v1。地图配准可选 OpenCV/NumPy。离线检查不需要启动游戏或 AHK。Windows MCP 0.8.8 的 PyPI wheel 元数据要求 Python 3.14+，可由 uv 管理独立解释器，与离线脚本的 Python 分开。

宿主须提供原生 CUA Windows 窗口截图和正常控制归属查询。项目实测宿主是 Codex 原生 CUA，加 Windows MCP 0.8.8 的 `ControlStatus`。先使用宿主的插件/MCP 配置入口安装和连接，按其官方说明核版本与工具清单。不同宿主不保证有相同接口；没有 CUA 或可靠归属查询时，仍可离线检查，现场复测标记为未具备条件。

Windows MCP 可通过[官方仓库](https://github.com/CursorTouch/Windows-MCP)和 [0.8.8 包说明](https://pypi.org/project/windows-mcp/0.8.8/)给出的方式设置。以实际包元数据和宿主支持方式为准；版本变更后重测截图租约。CUA 为宿主原生功能，不能用安装 Windows MCP 代替。

需要 stdio MCP 的宿主可使用以下配置片段；只在任务使用时启动，不添加开机任务：

```json
{"mcpServers":{"windows-mcp":{"command":"uvx","args":["--python","3.14","--from","windows-mcp==0.8.8","windows-mcp","serve","--transport","stdio"]}}}
```

包内入口 `windows-mcp` 和 `serve --transport stdio` 已按该 wheel 核对；本发布没有启动服务器。宿主连接后先核 `ControlStatus` 实际返回 state 为 ready / ai / user，未知结构或状态即停。

原生 Codex CUA 的窗口观察顺序是：先 `await cua.getState()` 选真实游戏窗口，再 `await cua.getApp({windowId: 已观察的窗口ID})`，随后独立调用 `await app.getScreenshot()`。绑定时返回的文档优先于示例。截图之后由 agent 调正常 `ControlStatus`，再通过其允许的执行工具使用桥；不要在 CUA 专用 REPL 中调用未提供的系统 I/O。每次截图独立返回，供离线日志识别；多帧仍属于同一观察批。

## 本地配置

在仓库根目录设置 `REPO_ROOT` 的本地登记，供 agent 找到 docs 和 tools。复制配置示例到被忽略的本地文件，再编辑：

```powershell
Copy-Item config.example.ini config.local.ini
```

`GamePath` 填实际 `StarRail.exe` 绝对路径，`ExpiresAt` 填本次明确获准会话的本地结束时间 `yyyyMMddHHmmss`，`RuntimeDir` 填独立本地运行目录。脚本在缺配置、过期、路径错误或旧单槽文件存在时拒绝启动。新的会话配置不改变旧桥的授权或期限。运行目录不要与另一个桥共享。

```powershell
$ahk = (Get-Command AutoHotkey64.exe).Source  # 若未在 PATH，填官方安装的可执行文件路径
& $ahk /Validate /ErrorStdOut=UTF-8 tools/bridge.ahk
& $ahk /Validate /ErrorStdOut=UTF-8 tools/rewind-cue.ahk
```

离线解析通过后，现场使用前先确认宿主允许 AHK，唯一操作者、用户交回控制、游戏真实路径和当前前台均正确。通过正常入口启动 `tools/bridge.ahk`，参数为本地配置路径；原项目桥需要管理员权限，发布桥同样保留该条件。不自行提升进程权限，若宿主允许且确需管理员，走正常 Windows UAC。配置文件和 `--live` 都不代表授权。

## 首次现场最小验收（由实际操作者执行）

1. 停止其他 sender 和输入辅助，核运行目录无旧 `command.txt` / `claimed-command.txt`。有遗留先调查本次状态，不自动删除或重放。
2. 通过正常宿主 CUA 绑定游戏窗口，取当前画面；记录游戏版本、窗口客户区、DPI、缩放、角色、模型、宿主、控制工具版本和电源/性能设置。
3. 启动桥，读本次新增 READY，并按 BRIDGE 协议发 `ping`，只接受本次新增 PONG。这一步不操作游戏。
4. 通过 ControlStatus 核 ready，并核游戏前台与用户交还控制。在探索状态发一次 `keys|M|80`，用新画面确认地图实际打开，再用 `keys|Escape|80` 返回。菜单未响应时停止，查模式、焦点、权限与回执。
5. 选安全空地做一次短移，核小地图背景与实景位移；同位置再做已知直路批次。按 PERFORMANCE 记录首帧、控制检查、实际派发和回执，菜单与走位分组。
6. 由用户明确接管或正常停止时停止提交，清查待发状态，确认按键释放。紧急停止为 Ctrl+Alt+F12。写下地图、层、位置、未完成目标、设置与待确认奖励。

本次公开发布只执行离线检查。公开包的可配置版本尚未在干净机器跑完整现场回归；历史成功范围见 EVIDENCE。
