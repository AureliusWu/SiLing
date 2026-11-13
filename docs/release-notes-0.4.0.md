司聆 0.4.0 RC1：按 R2 → R3 → R4 顺序开发的 Windows x64 候选版。

- R2：Ollama / OpenAI 兼容接口、用户范围 DPAPI 密钥、本地 Kokoro 中文播报、系统 TTS 兜底、有限多轮上下文、超时取消与按住说话。
- R3：动态托盘、悬浮窗、可选自启动；预设应用/目录、音量与系统信息工具；参数校验、单次确认和脱敏执行记录。
- R4：冻结 EXE 真实模型验证、安装/卸载检查、异常 sidecar 重启、Job Object 退出清理、脱敏诊断包导出。

下载 `SiLing-0.4.0-windows-x64.zip`，解压后先运行 `Install-Voice-Models.cmd`，再运行 `SiLing.exe`。
中文神经网络播报需另运行 `Install-Chinese-TTS.cmd`，然后在设置中选择 Kokoro。模型只在显式安装时下载。
默认不开启云调用、播报或开机启动；工具默认需要逐次确认。云 AI 需自备服务和 API Key，可能计费。

这是未签名候选版。Windows 11 真实麦克风/扬声器、蓝牙、睡眠、长期资源与误唤醒验收仍为 NOT_VERIFIED。
Windows Server CI 的软件结果不能代替硬件验收；半双工，使用按钮/PTT 中断，不支持播报时免按键语音打断。
安装包不包含模型权重；中文 KWS 权重独立许可仍待确认。详见包内 README、QA 矩阵和第三方说明。

软件验收：[验证运行](https://github.com/AureliusWu/SiLing/actions/runs/43353517604)。
本地81通过/1 Windows DPAPI跳过；Windows常规72通过，真实模型独立10通过；
实际冻结版中文24kHz波形、NSIS安装卸载、自启清理、Tauri宿主/悬浮窗/诊断/崩溃恢复/退出无残留均通过。
运行时模型输出依然不能代替真人麦克风和扬声器测试。
