# 路线与接续进度

2026-11-13，0.4.0 RC。按 R0/R1 → R2 → R3 → R4 顺序实施，独立仓库 AureliusWu/SiLing。

| 阶段 | 已实现 | 验收状态 |
|---|---|---|
| R0 | monorepo、官方技术核验、依赖锁、模型供应链、架构与启动 | 软件 PASS；KWS 独立权重许可 NOT_VERIFIED |
| R1 | 中文 KWS→VAD→ASR、电平、设备选择、PTT 后备、有界恢复 | 软件与冻结真实模型 PASS；Windows 11 麦克风 NOT_VERIFIED |
| R2 | 可切换 Provider、DPAPI、Kokoro/系统 TTS、多轮上下文、取消超时、PTT | 三轮真实 ASR→mock LLM→真实 TTS 波形 PASS；真实云/Ollama/扬声器 NOT_VERIFIED |
| R3 | 动态托盘、悬浮窗、自启动、四种工具、白名单、确认票据、审计 | 单测和前端 PASS；0.3.0 五项 CI PASS；实际用户设备操作 NOT_VERIFIED |
| R4 | NSIS/便携包、故障重启、Job 进程树清理、诊断导出、发布流水线 | 0.4.0 新增安装/原生恢复验收在 CI 执行；硬件长稳、签名 NOT_VERIFIED |

## 下一轮顺序

1. 完成 0.4.0 Windows CI，修复实际失败后发布带 SHA-256 与来源提交的候选包。
2. Windows 11 默认麦克风、蓝牙、睡眠、拔插、声卡、30 分钟背景误唤醒和资源占用；按 qa-matrix 记录真实数据。
3. 用户自备模型/Key 的 Ollama 与云端实测；不发明个人日历/待办或真实智能回复。
4. 依据硬件证据优化首字、延迟、回声和免按键语音打断；当前半双工不声称实现 AEC。
5. 确认 KWS 权重独立许可与签名途径后，再评估正式稳定版/模型捆绑。

断点恢复时先读取默认分支 CI、QA 与 build-info.json，对失败项复现，避免跨项目修改。
没有硬件证据前不标 PASS_ON_DEVICE，不预写准确率、CPU、内存或长期稳定性达标数据。
