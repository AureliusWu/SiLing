# ADR 0001 — R0/R1 本地语音基线

状态：采纳，2026-11-13。

## 已核验的选择

1. sherpa-onnx **2.0.1**：官方 PyPI 当前可获取，Linux cp312 原生 API 已实际加载；Windows
   wheel 由 CI 验证。使用官方 Python KeywordSpotter / VoiceActivityDetector /
   OfflineRecognizer.from_sense_voice，CPU provider、2 线程，无需 CUDA。
2. KWS 使用 **zipformer-zh-en-3M-2025-12-20**（归档 32,885,699 bytes），选 chunk-16 的
   int8 encoder/joiner、fp32 decoder。官方还提供 chunk-8；本轮优先稳定基线，未实测其准确率
   与延迟，暂不切换。默认词 ppinyin：`n ǐ h ǎo s ī l íng @你好司聆`，所有 token 已在词表核验。
   中文自定义词在临时 UTF-8 文件生成，初始化完成后清理；不依赖额外模型训练。
3. Silero **silero_vad.onnx**（643,854 bytes），通过 sherpa 统一运行时调用，避免额外引入
   PyTorch。端点规则由纯 Python 单一状态机掌管，可用固定 WAV 和假设备复现。
4. SenseVoiceSmall **int8-2024-07-17**（163,002,883 bytes）。官方也有较新导出，本轮选择明确
   下载摘要和稳定接口的既有基线，已实际加载验证。量化模型存在中文同音字误差，不等同于
   100% 转写准确；官方 zh.wav 实测将“开放”识别为“开饭”，如实记录。
5. sounddevice **0.5.6**：Windows/macOS pip 分发带 PortAudio；Linux 需系统库。工作线程
   独占模型与音频读取，PortAudio 回调只复制样本入有界队列。
6. UI 为 React + TypeScript，可通过 Python 启动器直接打开本地网页；Tauri 2 作为 Windows
   窗口及托盘外壳。Python 3.12 x64 为本轮唯一锁定基线，不宣称 Python 3.11 已通过。
7. PyInstaller onefile sidecar：先构建 Python EXE、验证冻结程序，再由 Tauri 打包 NSIS。
   解决用户不安装 Python 也能运行的最低交付；启动时临时解压，尚未优化冷启动或签名。

## 调整与取舍

- 增加 **libsoxr** 连续重采样，替代逐帧无状态 resample，防止回调边界不连续；其 LGPL 许可
  与分发要求单独列明。后续若分发要求不适配，可换成已验证的可替换适配层。
- R1 不接入任何 LLM/TTS 服务。Kokoro 仅在 CI 生成合成测试样本，不能据此声称完整 AI
  对话已完成。R2 候选本地中文 Kokoro / Windows 系统 TTS 兜底；自然度和 CPU 延迟待测。
- 本环境无真实声卡，不把容器 WAV 回放、CI 或 mock 标记为 PASS_ON_DEVICE。
- 默认启动静音、显式点击开始监听；避免安装或启动即采集用户音频。

## 官方依据

- [KWS 模型与 text2token](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html)
- [KWS Python 例子](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/keyword-spotter-from-microphone.py)
- [SenseVoice Python API](https://k2-fsa.github.io/sherpa/onnx/sense-voice/python-api.html)
- [Silero 模型说明](https://k2-fsa.github.io/sherpa/onnx/vad/silero-vad.html)
- [sounddevice 安装说明](https://python-sounddevice.readthedocs.io/en/latest/installation.html)
- [Tauri Windows 前置条件](https://v2.tauri.app/start/prerequisites/)
- [Kokoro 中文样本和 speaker 对应](https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/kokoro-multi-lang-v1_1.html)

模型授权的已确认和待确认部分见 THIRD_PARTY_NOTICES.md，不能用推理 API 可运行推导许可。
