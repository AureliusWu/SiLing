# 第三方组件、模型和来源

核验时间：2026-11-13。项目代码的 MIT 许可不替代依赖与模型自身条款。

| 组件 | 锁定版本/模型 | 来源与许可核验 |
|---|---|---|
| sherpa-onnx / core | 2.0.1 | [官方仓库](https://github.com/k2-fsa/sherpa-onnx)，Apache-2.0；ONNX Runtime 依照其 MIT notices |
| sounddevice | 0.5.6 | [官方](https://github.com/spatialaudio/python-sounddevice)，MIT；Windows pip wheel 附带 PortAudio，须保留其许可 |
| pypinyin | 0.55.0 | [官方](https://github.com/mozillazg/python-pinyin)，MIT |
| numpy / soxr | 2.5.4 / 1.1.0 | NumPy BSD-3-Clause；python-soxr LGPL-2.1-or-later，动态原生库与 wheel 保留原始 notices，最终再分发须核验相应义务 |
| FastAPI / uvicorn / Pydantic | 0.162.5 / 0.52.1 / 2.14.3 | 官方 PyPI 与项目仓库，MIT / BSD-3-Clause / MIT |
| React / Vite / TypeScript | 19.2.0 / 7.2.2 / 5.9.3 | 官方 npm，MIT / MIT / Apache-2.0；package-lock.json 固定依赖树与完整性 |
| Tauri | 2.12.5 / tauri-build 2.7.4，见 Cargo.lock | [官方](https://v2.tauri.app/)，MIT / Apache-2.0；CLI 固定 2.9.4，API 固定 2.9.0 |
| 中文 KWS | zipformer-zh-en-3M-2025-12-20 | [官方模型文档](https://k2-fsa.github.io/sherpa/onnx/kws/pretrained_models/index.html)、[官方发布](https://github.com/k2-fsa/sherpa-onnx/releases/tag/kws-models)。分发档案未发现独立权重 LICENSE，不能直接把代码 Apache-2.0 等同于权重许可；此项保持 NOT_VERIFIED，正式捆绑分发前需确认。候选安装包不捆绑权重 |
| Silero VAD | 官方 silero_vad.onnx，643,854 bytes | [官方模型文档](https://k2-fsa.github.io/sherpa/onnx/vad/silero-vad.html)、[Silero 上游](https://github.com/snakers4/silero-vad)，MIT |
| SenseVoiceSmall int8 | 2024-07-17 | [官方文档](https://k2-fsa.github.io/sherpa/onnx/sense-voice/pretrained.html)。权重采用 [FunASR MODEL_LICENSE 1.1](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE)，与代码 MIT 不同；保留原模型名、来源与作者。归档 LICENSE 指向上游条款。HF 官方模型卡同样指向此协议 |
| Kokoro 中文播报/合成样本 | v1.1-zh int8，speakers 3 / 58 | [官方模型](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh)，Apache-2.0；[sherpa 使用文档](https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/kokoro-multi-lang-v1_1.html)。R2 已集成本地 TTS，需用户显式 `tts download`；归档147,052,523 bytes，SHA-256 固定在 tts.py；安装包不含权重 |

完整 Python 运行时与开发锁分别见 requirements.lock、requirements-dev.lock。
所有模型下载 URL、字节数和 SHA-256 见 services/voice/src/siling_voice/models.lock.json；
来源为官方 GitHub Release API 的 digest，不使用本次下载后临时计算的值冒充上游签名。
归档 SHA-256 一致表示完整性相符，不表示发布者身份获得独立第三方签名验证。

模型归档只在用户执行显式 provisioning 命令时下载。离线电脑可在联网电脑获取三个官方归档，
命名为 `kws.tar.bz2`、`asr.tar.bz2`、`silero_vad.onnx`，然后运行
`siling-voice models install --from <directory>`；校验逻辑相同。

当前不对声学准确率、长期 CPU/内存或 TTS 自然度作生产承诺。源代码修改、模型更新与正式
再分发时需重新核验相关依赖和权重许可，不应仅沿用本表。
