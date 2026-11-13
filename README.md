# 司聆（SiLing）

独立的 Windows 中文语音助手，当前 **0.4.0 RC / R2 → R3 → R4 候选版**。
本地「你好司聆」唤醒、中文转写、可选 AI 与中文播报，支持受控应用/目录/音量工具。
项目与司忆及其他仓库独立。

**Windows 11 麦克风/扬声器硬件验收：NOT_VERIFIED。** CI 软件结果见 [QA 矩阵](docs/qa-matrix.md)。

## Windows 安装与首次启动

从 [Releases](https://github.com/AureliusWu/SiLing/releases) 获取已发布候选版；开发构建见
[Actions](https://github.com/AureliusWu/SiLing/actions/workflows/ci.yml)。Artifact 需登录并保留 30 天。
候选包未签名，包含便携版、`installer/` 内 NSIS 安装程序、样本、证据和 SHA-256。

便携包解压后运行 `Install-Voice-Models.cmd`，再双击 `SiLing.exe`。
也可在包目录打开 PowerShell：

```powershell
.\SiLing-Voice.exe models download
.\SiLing-Voice.exe doctor
.\SiLing.exe
```

NSIS 安装版也需在安装目录执行 `SiLing-Voice.exe models download`。
首次模型下载约 197 MB；安装包不包含权重。运行时不静默下载。
默认保持静音、关闭 AI/播报/自启动。点击「开始监听」，等待模型加载完毕，说「你好司聆」，
提示音后说一句中文；仅转写模式会显示文本后恢复待机。
按住说话可绕过 KWS；鼠标/触摸或聚焦按钮后按空格，松开结束录音。
只检查界面、不使用麦克风：`SiLing-Voice.exe serve --demo`，界面明确标注模拟。

## AI、中文播报与工具

1. 在「AI 与播报设置」选择服务。Ollama 使用本机 OpenAI 兼容地址，例如
   `http://127.0.0.1:11434/v1`，模型 ID 必须是你已安装的模型。司聆不会安装 Ollama 或其模型。
   OpenAI 兼容云服务填写 HTTPS 地址与模型 ID，并同意发送转写文本/上下文，可能产生费用。
   API Key 在 Windows 用当前用户 DPAPI 加密保存；也可显式设置 `SILING_API_KEY`。
   Key 不返回界面、不写设置或诊断包。`.env.example` 仅为说明，不自动加载。
2. 中文神经网络播报：运行 `Install-Chinese-TTS.cmd` 或 `SiLing-Voice.exe tts download`，
   额外下载约 147 MB，设置中选择 Kokoro。系统 TTS 模式需要已安装中文语音；
   Kokoro 失败时会尝试系统中文语音，无可用声音时保留文字并显示错误。
   mock 服务/播报只用于测试，不代表真实 AI 回复或声卡播放。
3. 工具默认「逐次确认」。加入 VS Code 的实际 `Code.exe` 或项目目录，设置 ID 和语音名称，
   保存白名单。例如说「打开VS Code」「打开项目目录」「音量设为30%」「查看系统信息」。
   应用和目录只接受已配置 ID，模型不能提交任意路径、命令、脚本或提升权限。
   只有你主动选择信任白名单后，允许的工具才免逐次确认；随时可以关闭工具。

支持有限多轮上下文、请求超时、取消与错误恢复。播报时点「取消」或按住说话可中断。
采用半双工：思考/工具/播报时释放麦克风，完成后恢复；**播报时免按键语音打断尚未实现**。
没有连接日历、待办、邮箱，不能代你查询这些信息。

## 托盘、隐私与诊断

- 关窗隐藏到托盘，状态、静音、悬浮窗和退出可从托盘操作。完全退出会清理整棵语音进程树。
  异常 sidecar 至多重启三次，恢复后保持静音。第二桌面实例退出并尝试聚焦已有窗口。
- 自启动默认关闭，用户主动开启后只写当前用户 Run 项，后台启动保持静音；卸载删除该项。
- 配置/模型默认在 `%LOCALAPPDATA%\SiLing`；可用 `SILING_CONFIG_DIR` / `SILING_MODEL_DIR` 覆盖。
  音频只在内存，单次默认最长 15 秒。待机 KWS、VAD、ASR、Kokoro 均在本机；云 AI 只发送文本。
- 历史默认不写磁盘；启用后保存在本机 `history.json`。「清空」会删除历史；静音清理内存正文。
  工具审计仅记录类型、成功与耗时，不记录参数/路径。API 使用 loopback 和每次启动随机令牌。
- 点击「导出脱敏诊断包」：桌面版保存到下载目录，浏览器模式触发下载。
  只含版本、架构、依赖版本、白名单错误码和耗时，不含音频、正文、Key、URL、路径或设备名。
- 卸载保留用户主动下载的模型、设置、Key 和历史；完全清理时退出后删除 `%LOCALAPPDATA%\SiLing`。
  Tauri 窗口偏好存于 `%APPDATA%\io.siling.desktop`。请先确认是否需要保留这些数据。

## 从源码启动

目标 Windows 11 x64，Python 3.12、Node 22+。无需 Rust 可先测试相同网页界面和语音服务。

```powershell
git clone https://github.com/AureliusWu/SiLing.git
cd SiLing
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
npm ci
npm run build
.\.venv\Scripts\python.exe -m siling_voice models download
.\.venv\Scripts\python.exe scripts/run_dev.py
```

后续用 `scripts/run-dev.ps1`（演示：`-Demo`）。如果系统禁止 ps1，直接用上述 Python 命令。
Tauri 构建还需 Rust MSVC、C++ Build Tools、WebView2；先 `python scripts/package_windows.py`，
再 `npm run tauri -- build`。完整 Windows CI 会实际打包、启动、重启并安装/卸载候选程序。

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m ruff check services tests scripts
.\.venv\Scripts\python.exe -m ruff format --check services tests scripts
.\.venv\Scripts\python.exe -m mypy services/voice/src
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/r2_smoke.py
npm run typecheck
npm run build
```

真实模型测试需安装模型并设置 `SILING_TEST_MODELS=1`、`SILING_TEST_TTS=1`、
`SILING_TEST_FIXTURES` 指向 CI 合成样本。缺失时明确 SKIP，不能据此声称模型通过。
样本来自 Kokoro 合成；[Windows 实机步骤](docs/windows-acceptance.md) 单独记录硬件结果。

## 常见故障

| 现象 | 处理 |
|---|---|
| 模型缺失/损坏 | `models verify`；损坏时删除 `.downloads` 对应归档后重新显式下载 |
| 下载 403/失败 | 检查官方 GitHub Release 网络；离线安装方式见第三方说明 |
| 麦克风无法打开 | 检查 Windows 桌面应用麦克风权限、设备选择和其他应用独占 |
| 无声音 | 检查输出设备、Kokoro 模型与系统中文语音；mock 不发声 |
| AI 超时/401/404 | 核对用户所选地址、模型、Key 和网络；可取消并继续操作 |
| 工具不能执行 | 检查白名单、逐次确认、实际绝对路径；脚本/解释器禁止启动 |
| Linux 无音频 | 容器没有硬件；本机需 PortAudio，不把容器测试作为声卡验收 |

[架构](docs/architecture.md) · [路线](docs/roadmap.md) · [QA](docs/qa-matrix.md) ·
[第三方说明](THIRD_PARTY_NOTICES.md) · [变更记录](CHANGELOG.md)
