# 司聆（SiLing）

独立的 Windows 中文语音助手。当前候选版本 **0.1.0 / R0 + R1**。

说「你好司聆」，听到短提示音后说一句中文；司聆在本机结束录音、转写并回到待机。
当前版本不调用大模型、不执行电脑指令。AI 对话安排在 R2。

**硬件验收：NOT_VERIFIED。** Linux 和 Windows CI 的软件测试不能代替 Windows 11 麦克风实测。
详见 [QA 矩阵](docs/qa-matrix.md)。本仓库与司忆、Game1、Game2 无依赖、无修改关系。

## Windows 候选构建

前往 [Actions](https://github.com/AureliusWu/SiLing/actions/workflows/ci.yml)，打开通过的运行，下载
`SiLing-0.1.0-windows-x64-<commit>`。产物包含便携 ZIP 与 NSIS 安装程序；候选构建未签名。
下载 Artifact 需要登录 GitHub，保留期为 30 天。是否构建成功，以对应运行的实际结果为准。

便携版解压后，在所在目录打开 PowerShell：

```powershell
.\SiLing-Voice.exe models download
.\SiLing-Voice.exe doctor
.\SiLing.exe
```

`SiLing.exe` 是桌面窗口；`SiLing-Voice.exe serve` 可单独启动同一套界面和语音服务。
NSIS 安装后，也需先从安装目录运行 `SiLing-Voice.exe models download`。
进入界面后点击「开始监听」。应用启动时保持静音，避免意外采集音频。
只测试界面、不接触麦克风：`SiLing-Voice.exe serve --demo`。

首次显式下载的三个官方模型共 **196,532,436 字节（约 197 MB）**，本地缓存与解压额外占用空间。
模型不塞进安装包；下载前阅读 [模型与第三方说明](THIRD_PARTY_NOTICES.md)。
只有 `models download` 会访问模型下载源，正常识别不访问网络。

## 从源码启动（Windows 11 x64 / Python 3.12 / Node 22+）

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

之后可直接运行 `scripts/run-dev.ps1`（演示：`scripts/run-dev.ps1 -Demo`）。
如果 PowerShell 的本机策略不允许执行 `.ps1`，使用上面的逐行命令，无需修改系统策略。
前端单独启动：`npm run dev`；另开终端运行
`python -m siling_voice serve --ui-url http://127.0.0.1:1420`，由启动器打开授权页面。
无需 Rust 即可测试语音闭环。开发 Tauri 外壳额外需要 Rust MSVC、C++ Build Tools 与 WebView2。
`python scripts/package_windows.py` 准备 sidecar，`npm run tauri -- build` 构建安装程序。

## 模型、配置与隐私

- 默认缓存：`%LOCALAPPDATA%\SiLing\models`；配置：`%LOCALAPPDATA%\SiLing\settings.json`。
  可用 `SILING_MODEL_DIR` / `SILING_CONFIG_DIR` 覆盖。`.env.example` 仅作模板，不自动加载。
- 支持 2–12 个汉字的自定义唤醒词。保存设置后需要重新开始监听；拼音必须存在于模型词表。
  多音字可能需要调整用词，发音相同的词无法可靠区分。
- 16 kHz 本地推理；设备不支持时使用原生采样率，通过连续重采样转换。
- 音频只在内存，单次最长 15 秒；转写只在当前界面和有限内存事件中，静音或退出即清理。
  CLI 的 `wav --output` 是用户显式要求保存的测试文本，注意不要把私人样本提交入库。
- API 只绑定 `127.0.0.1`，录音与配置接口要求每次启动随机生成的令牌，不启用任意 shell 或云端接口。
- 桌面版关窗后进入托盘；「完全退出」或托盘退出会终止语音进程并释放麦克风。
  浏览器模式关闭网页不会自动停止后台进程；请点击「完全退出」或在启动终端按 Ctrl+C。
- 不安装自启动项。卸载不会自动删除用户自行下载的模型和设置；完全清理可在退出后删除上述目录。

## 验证命令

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m ruff check services tests scripts
.\.venv\Scripts\python.exe -m ruff format --check services tests scripts
.\.venv\Scripts\python.exe -m mypy services/voice/src
.\.venv\Scripts\python.exe -m pytest -q
npm run typecheck
npm run build
.\.venv\Scripts\python.exe -m siling_voice doctor
.\.venv\Scripts\python.exe -m siling_voice wav .\your-16bit-pcm.wav --output .evidence\wav.json
```

完整模型测试需设置 `SILING_TEST_MODELS=1`。默认词的合成音频测试额外需要
`SILING_TEST_FIXTURES` 指向 CI 的 `synthetic-test-inputs-<commit>` 解压目录。
未提供时测试会明确 SKIP，不能据此声称默认词声学测试通过。
样本为 Kokoro 合成音频，不是真人录音。真实 Windows 测试按
[本机验收步骤](docs/windows-acceptance.md) 执行。

## 常见故障

| 现象 | 处理 |
|---|---|
| 模型缺失或校验失败 | 运行 `models verify`；损坏时删除 `models/.downloads` 中相应归档后重新 `models download` |
| 403 / 下载失败 | 检查 GitHub 官方模型下载是否能访问；不要改为来历不明的镜像 |
| 无麦克风或无法打开 | Windows 设置 → 隐私和安全性 → 麦克风，允许桌面应用访问；在设置中选择输入设备 |
| 被其他软件独占 | 关闭其他软件的独占输入，重新点击开始监听 |
| 设备拔出 / 溢出 | 会尝试有限次数恢复；重连后选择设备并重新开始监听 |
| 没有提示音 | 检查默认播放设备；输出设备不可用时仍继续转写 |
| 偶发误唤醒 | 在安静环境测试；暂时静音；后续根据实测调整关键词阈值 |
| 第二实例启动失败 | 退出已有实例；不要同时启动桌面与独立语音服务 |
| Linux `AUDIO_UNAVAILABLE` | 安装发行版 `libportaudio2` 并连接真实音频设备；容器通常没有麦克风 |

## 项目结构

`apps/desktop`：React + Tauri；`services/voice`：Python 音频与 API；
`packages/contracts`：前后端契约；`tests`：假设备与真实模型测试；
`scripts`：启动、打包、录音样本生成；`docs`：架构、决策、路线与验收证据。

[架构](docs/architecture.md) · [路线](docs/roadmap.md) · [变更记录](CHANGELOG.md)
