# ADR 0004 — R4 可靠性和交付

2026-11-13。保持 sidecar 隔离，不依赖本机预装 Python。

- Tauri mainBinaryName 统一为 SiLing，确保安装/便携/自启动的实际路径一致。
- Windows Job Object 设置 KILL_ON_JOB_CLOSE，覆盖 PyInstaller bootloader 与提取的服务。
  sidecar 异常时先关闭旧 Job 再重启，默认保持静音，最多三次。
- Windows CI 在隔离 runner 静默安装、启用/验证 HKCU Run，再启动真实 Tauri 宿主，
  用显式 --smoke-report 断言初始静音、悬浮窗、诊断下载和崩溃恢复，退出后检查服务 PID 已结束。
  静默卸载确认程序和 Run 项清理。该软件验证不能替代干净 Windows11 硬件验收。
- NSIS POSTUNINSTALL 只清理本程序自启项；不默认删除用户模型/历史/密钥。
- 诊断只导出固定字段，不打包原日志/设置；代码白名单错误码，防止随意字符串进入报告。
- 发布任务仅在 release: 提交且所有前置任务成功后执行，最小 job 级 contents:write。
  创建 prerelease，不覆盖已有标签；无签名证书，硬件项保留 NOT_VERIFIED。

官方依据：
- https://v2.tauri.app/reference/config/#mainbinaryname
- https://v2.tauri.app/distribute/windows-installer/#nsis-installer-hooks
- https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
- https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information
