# R0–R4 验证矩阵

2026-11-13，0.4.0 RC。Windows 11 实机硬件验收 **NOT_VERIFIED**。
本地 Linux x86_64 / Python 3.12.14，Windows CI Server 2022；不混淆合成样本、协议 mock 和真人设备。

| 项目 | 状态 | 实际证据与边界 |
|---|---|---|
| R0/R1 基线 | PASS | [0.1.0 五项 CI](https://github.com/AureliusWu/SiLing/actions/runs/43343803939)，证据留在 docs/evidence |
| R3 全 CI | PASS | [7016027 五项 CI](https://github.com/AureliusWu/SiLing/actions/runs/43351256307)，两平台 Python、前端、真实模型、Windows 冻结与安装包构建 |
| 0.4.0 本地全量 | PASS | **81 passed / 1 skipped**，67.40 s；包含10个真实模型用例；skip 为 Windows DPAPI，Windows CI 单独执行 |
| 覆盖率 | PASS | 本地语句覆盖 **65.41%**；未把未覆盖硬件分支算通过 |
| ruff / mypy / TS / build | PASS | 17 个生产 Python 模块，前端 JS 210.44 kB / gzip 67.11 kB |
| 实际 HTTP 协议 | PASS | scripts/r2_smoke.py 运行独立 loopback mock 服务与实际 API，三轮中文、上下文、慢请求取消、后续恢复和退出 |
| KWS→VAD→ASR | PASS | Kokoro sid3/58 合成「你好司聆」→「打开记事本。」；无唤醒命令/噪声/静音负例；不是长期误唤醒率 |
| 真实 ASR→mock LLM→真实 TTS | PASS | 连续3轮，Kokoro 原生中文 PCM 输出到测试 sink；无实际智能服务或声卡替代声明 |
| TTS/HTTP 取消与失败 | PASS | 原生生成回调取消，分块播放取消，HTTP 错误/超时/响应限额、状态恢复 |
| PTT / 静音 / 历史 | PASS | 持按无静音截断、松开结束、有界时限、晚到结果抑制、默认不保存历史 |
| Key / 云端同意 | PASS | DPAPI Windows 用例；配置/错误不回显 SecretStr；HTTPS、云同意、loopback 与重定向边界 |
| 工具边界 | PASS | 拒绝任意命令/路径/解释器、严格音量参数、票据单次使用/拒绝/过期、执行前路径复核、只读免 LLM |
| 诊断隐私 | PASS | 敏感 Key/正文/路径/唤醒词注入不出现在诊断 ZIP，401 鉴权，仅 diagnostics.json |
| R3 UI 浏览器操作 | PASS | 桌面/390px、mock 唤醒、3轮对话、白名单确认拒绝、清空/退出；0 page errors |
| 0.4.0 Windows 验收 | PASS | [978c9a7 全 CI](https://github.com/AureliusWu/SiLing/actions/runs/43353517604)：冻结 TTS、诊断下载、真实原生宿主崩溃恢复、悬浮窗、退出无残留服务、NSIS 静默安装卸载/自启清理 |
| Windows / Linux 常规单测 | PASS | 72 passed / 10 model skipped；71 passed / 11 skipped（10 model + Windows DPAPI）；模型独立任务10/10通过，36.38 s |
| 冻结中文播报 | PASS | 真实 Kokoro 24 kHz、3.725 s PCM 波形；无声卡测试 |
| 包内文件与来源 | PASS | 对978c9a7产物逐项核验98文件SHA-256、两EXE x64 PE、Cargo.lock语义一致；构建元数据含准确源码SHA |

## 真实环境与发行遗留

| 项目 | 状态 | 下一步 |
|---|---|---|
| Windows 11 麦克风/扬声器 | NOT_VERIFIED | 默认词20次、中文识别与真正发声，执行 windows-acceptance.md |
| 蓝牙/睡眠/独占/拔插/回声 | NOT_VERIFIED | 真机验证；半双工已实现但不等于声学回声消除 |
| 长稳/CPU/内存/背景误唤醒 | NOT_VERIFIED | 待机30分钟以上，记录设备、场景、实际数值 |
| 真正 Ollama/云端模型 | NOT_VERIFIED | 无预装模型/私人Key；协议 mock 不算真实智能服务 |
| VS Code/项目目录/音量实机 | NOT_VERIFIED | CI 参数校验与拒绝不代表用户设备实际成功 |
| KWS 权重独立许可 | NOT_VERIFIED | 不捆绑权重，正式分发前确认 |
| 代码签名/稳定正式版 | NOT_VERIFIED | 当前未签名候选版；不虚构证书或硬件验收 |

曾修复 Windows 非中文代码页输出失败、表单可访问标签缺失、安装 EXE 命名与自启动不匹配、
冻结进程 bootloader 异常退出时潜在残留服务。0.4.0 安装/进程修复已由上述 CI 验证。候选发布会重新构建并通过同一套检查；具体下载包来源以其 build-info.json 为准。
Starlette TestClient 有一条上游弃用提示，不影响现有结果。
