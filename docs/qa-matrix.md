# R0/R1 验证矩阵

日期：2026-11-13（北京时间）。候选版本：0.1.0。

**Windows 11 麦克风硬件验收：NOT_VERIFIED。** 没有连接真实 Windows 麦克风，
任何 mock、合成 WAV、Linux 原生模型或 Windows Server CI 均不标为 PASS_ON_DEVICE。

## 软件证据

代码基线：`11cbd31af0b2be651304ebde0d8d21177c2c2772`。
[CI 运行](https://github.com/AureliusWu/SiLing/actions/runs/43343803939)。
本地环境 Linux x86_64 / glibc 2.41 / Python 3.12.14 / Node 24.22.1。
Windows CI 为 Windows Server 2022 / Python 3.12，具体小版本以运行日志为准。

| 项目 | 状态 | 实际证据 / 边界 |
|---|---|---|
| 独立仓库 | PASS | AureliusWu/SiLing；从空仓库初始化，无其他项目变更 |
| Python 安装与启动 | PASS | 本地离线安装可编辑包；CI 从锁文件全新安装 |
| lint / 格式 / mypy | PASS | ruff、ruff format、10 个生产模块 mypy；Windows 与 Linux CI 同样通过 |
| TypeScript / 前端构建 | PASS | `npm run typecheck` / `npm run build`；前端 JS 约 201 kB，gzip 约 64 kB |
| 全部本地测试 | PASS | **50 passed，0 skipped**，包含 8 个真实模型测试；约 24.34 s |
| 覆盖率 | PASS | 本地全测试语句覆盖率 65.02%，纯状态机 96.33%；没有把未覆盖硬件分支算作通过 |
| Windows/Linux 常规 CI 单测 | PASS | 42 passed / 8 skipped；真实模型用例在独立 real-models job 执行，skip 为明确配置边界 |
| 真实 ONNX 模型测试 | PASS | real-models job 8/8；本地同组 8/8，无 mock 替代 KWS/VAD/ASR |
| 默认唤醒词闭环 | PASS | Kokoro 合成女声 sid 3、男声 sid 58，均为「你好司聆」→「打开记事本。」→ IDLE |
| 本地 ASR 耗时 | PASS | 单次观测：女声样本 167.2 ms，男声 176.6 ms；只含 ASR，不是端到端或用户电脑的性能保证 |
| 负例 | PASS | 10 秒确定性白噪声、男女声只说命令没有唤醒词，均未唤醒；不外推长期误唤醒率 |
| 唤醒后无指令 | PASS | 合成唤醒词后静音，6 秒等待超时，未生成转写，恢复 IDLE |
| 官方中文录音 | PASS | 官方 zh_3（关键词“法国”）组合录音跑通；官方 ASR zh.wav 实测“开放”误识为“开饭”，未隐藏错字 |
| 默认词拼音和自定义词 | PASS | 「你好司聆」「小爱同学」「你好小聆」分词和词表校验成功；不代表每个词已完成真人声学测试 |
| 录音上限、取消、噪声、冷却 | PASS | 单测验证 15 s 有界、无语音不调用 ASR、取消不产出文本、重复唤醒去重 |
| 加载/ASR 中静音 | PASS | 假设备并发测试阻止加载结束后晚开麦克风，并抑制取消/静音后的晚到识别结果 |
| 44.1 / 48 kHz 重采样 | PASS | 连续切块重采样测试；硬件采样率协商仍待实机 |
| 队列溢出/设备断开 | PASS | 假设备/回调故障测试；真实拔插和独占未测 |
| loopback API 权限 | PASS | 无 token 401；外部 Host 拒绝；非白名单 Origin 无 CORS 许可 |
| 模型供应完整性 | PASS | 三个官方归档均与锁定 Release digest 和字节数一致；启动校验必需文件 |
| 不安全 tar / 被篡改文件 | PASS | 拒绝绝对路径、越界、软链接、错误摘要 |
| UI 操作与布局 | PASS | CI Playwright：桌面和 390px 视口无横向溢出，模拟转写/静音清理/设置/退出，0 page errors |
| Python wheel/sdist | PASS | 两平台 CI 实际构建；纯服务包与 Windows 完整候选包用途不同 |
| Windows 冻结程序 | PASS | 修复后的 EXE 通过 doctor、HTTP/UI 鉴权与模拟闭环、完全退出，以及男女声真实 KWS/VAD/ASR 推理；每次返回码和识别 JSON 均验证 |
| Tauri EXE / NSIS / 便携 ZIP | PASS | Windows CI 全部成功；实际输出桌面 EXE、43,319,944 bytes NSIS 安装程序和便携 ZIP；下载后核验 PE 与 SHA-256，交互/安装实机仍未测 |

## 构建产物

[Windows Artifact](https://github.com/AureliusWu/SiLing/actions/runs/43343803939/artifacts/13999789082)。
原始 Actions 归档 SHA-256：`cbd48877c46e8c25f7e6dfb0977a1c51c25b434f405cc09d63a1f3d91910c5cd`。
便携 ZIP SHA-256：`a3c60a2c4cf9acb514668cef5a98ca89d28ed2215a8b995c082b5c8d2905ebdc`。
安装程序 SHA-256：`9430100ce7781ee09b0792f9ffad6f72c9596ca0ce5ccf83265562ac4ded0650`。
Windows 冻结 ASR 单次观测：女声 80.8 ms，男声 81.2 ms，均识别为“打开记事本。”。
构建内 build-info.json 记录 commit，模型不在包内。Artifact 保留 30 天。
Rust 实际解析 tauri 2.12.5 / tauri-build 2.7.4，对应已构建图写入 Cargo.lock。

## 实机与发行遗留

| 项目 | 状态 | 下一步 |
|---|---|---|
| Windows 11 真麦克风默认唤醒与转写 | NOT_VERIFIED | docs/windows-acceptance.md；安静环境 20 次真实统计 |
| 蓝牙、独占权限、拔插、睡眠、回声 | NOT_VERIFIED | 对应实机用例，不用假设备结果代替 |
| 待机 CPU/内存、误唤醒频率、长稳 | NOT_VERIFIED | 记录设备/场景与实际计时数据 |
| Tauri 窗口/托盘真实交互、安装卸载 | NOT_VERIFIED | 安装到干净 Windows 11 验收；CI 编译不构成安装实测 |
| 中文 KWS 权重独立许可 | NOT_VERIFIED | 官方归档无独立权重 LICENSE，正式捆绑前确认；当前安装包不包含模型 |
| 代码签名 | NOT_VERIFIED | 仅候选构建，未购证书、未签名 |
| R2 LLM / 中文播报 / 3 轮对话 | NOT_VERIFIED | 本轮不包含此功能；进度见 roadmap.md |

## 曾发现并修复的问题

首次供应验证在不存在的模型 LICENSE URL 上失败；改查官方模型卡和实际归档，保留许可未确认项。
首次 Windows 冻结推理生成结果后，输出中文时因 cp1252/charmap 失败：
[失败运行](https://github.com/AureliusWu/SiLing/actions/runs/43341258245)。
修复为 CLI 显式 UTF-8 stdout/stderr，并增加 ASCII 重定向回归测试；冻结验证脚本逐次检查
进程返回码与实际 JSON，避免 PowerShell 只检查最后一条命令而漏报。

测试有一条 Starlette 关于 httpx TestClient 的上游弃用提示；不影响当前通过结果，后续升级
测试客户端时处理，不将其描述为生产故障。
