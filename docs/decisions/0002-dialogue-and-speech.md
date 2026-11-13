# ADR 0002 — R2 中文对话与播报

日期：2026-11-13。基于 R1 的本地唤醒/转写，不改变待机音频边界。

- 支持仅转写、明确标注的 mock、loopback Ollama、OpenAI 兼容 HTTPS Provider。
  云端发送的是转写文本和有限上下文，需要在设置中明确同意；音频不上传。
  Ollama 模式限制 loopback，云服务拒绝明文 HTTP、URL 内凭据、自动重定向。
- httpx 0.28.1 从开发依赖提升为运行时依赖，固定版本；不依赖云 SDK。
  请求总时限 2–120 秒，响应限制 1 MiB，取消时关闭异步 HTTP 请求。
- Windows 使用用户范围 DPAPI 加密保存 API Key，设置和状态接口不返回 Key；
  也支持用户显式设置 SILING_API_KEY。没有真实 Key，不能声称云端服务已实测。
- Kokoro v1.1-zh int8 使用前轮已核验的官方归档与 SHA-256，新增独立显式下载命令
  `siling-voice tts download`，约 147 MB。运行时不静默下载。
  模型失败在 Windows 尝试已安装的中文 System.Speech 语音；失败时保留文字并回到可用状态。
- 播报通过每次生成回调/播放分块检查取消，系统 TTS 使用固定可信 PowerShell 脚本，
  文字通过 UTF-8 stdin JSON 传入，不拼接到脚本中。
- 半双工：思考、工具处理和播报时释放麦克风。按住说话或停止按钮可打断；不声称
  扬声器播放期间的免按键语音打断或回声消除已实现、已通过硬件测试。
- 上下文默认仅内存，最长 12 轮；磁盘历史由用户选择，清空会删除已保存历史。
  按住说话支持鼠标/触摸和聚焦按钮后的空格键，松开后结束录音；仍受最长时限限制。

已验证：三轮真实 ASR → mock LLM → 原生 Kokoro 中文波形生成（输出适配器替换为测试 sink），
以及原生 TTS 生成回调取消。该结果不代表声卡播放和 Windows 11 麦克风实测。
Provider 协议、上下文、HTTP 错误、超时和取消有自动化测试；云端与真实 Ollama 模型均需用户
配置后另做实测。

官方依据：
- https://docs.ollama.com/api/openai-compatibility
- https://api-docs.deepseek.com/api/create-chat-completion/
- https://learn.microsoft.com/en-us/windows/win32/api/dpapi/nf-dpapi-cryptprotectdata
- https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/kokoro-multi-lang-v1_1.html
