# Changelog

## 0.1.0 — 2026-11-13（R0/R1 candidate）

- 新建独立 monorepo，Python 3.12 语音服务、React/TypeScript 界面和 Tauri Windows 外壳。
- 本地默认「你好司聆」中文关键词唤醒，Silero VAD 端点和 SenseVoiceSmall int8 中文转写。
- 麦克风枚举/选择、输入电平、44.1/48 kHz 连续重采样、提示音、手动唤醒后备入口。
- 有界录音、无语音超时、去重冷却、取消、静音、设备失败有限恢复和本地单实例。
- 显式官方模型下载与大小/SHA-256 校验、离线安装、严格归档提取与逐文件校验。
- 假设备与真实模型测试，合成中文男女声正例和无唤醒词/噪声负例。
- Windows sidecar 与 NSIS 候选构建流程；硬件验收仍为 NOT_VERIFIED。
