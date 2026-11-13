import {useEffect, useRef, useState} from "react";
import {createRoot} from "react-dom/client";
import type {Device, Settings, Status, VoiceEvent} from "../../../packages/contracts";
import {api, connect, exitDesktop} from "./api";
import "./style.css";

const labels = {IDLE: "等待唤醒", WAKE_DETECTED: "已唤醒", LISTENING: "正在听你说", TRANSCRIBING: "正在本地转写", THINKING: "正在思考", ACTING: "等待工具处理", SPEAKING: "正在播报", MUTED: "麦克风已释放", ERROR: "需要处理", STOPPING: "正在停止"};
const errors: Record<string, string> = {
  MODELS_OR_KEYWORD_INVALID: "模型未安装、校验失败或唤醒词不受支持。请运行模型下载命令后重试。",
  MICROPHONE_OPEN_FAILED: "无法打开麦克风。请检查 Windows 麦克风权限、选择的设备及其他应用的独占设置。",
  AUDIO_UNAVAILABLE: "未找到可用音频系统；请在 Windows 本机运行。",
  AUDIO_OVERFLOW_OR_DISCONNECT: "音频缓冲溢出或设备已断开，正在尝试恢复。",
  DEVICE_DISCONNECTED: "麦克风已断开，正在尝试恢复。", DEVICE_STALLED: "麦克风未返回音频，正在尝试恢复。",
  NO_INPUT_DEVICE: "没有可用输入设备。", ASR_FAILED: "本地识别失败，请重试。",
  EMPTY_TRANSCRIPT: "没有识别到文字，请重新说一句。", SERVICE_STOPPING: "识别任务正在结束，请稍候重试。",
  ENGINE_INIT_OR_RUNTIME_FAILED: "语音引擎启动失败。请运行 doctor 检查模型与依赖。",
  NOT_LISTENING: "请先开始监听。", KEYWORD_UNSUPPORTED: "模型不支持此唤醒词，请尝试其他汉字。",
  PROVIDER_DISABLED: "请先在 AI 与播报设置中选择服务。", API_KEY_MISSING: "请先保存 API Key。",
  PROVIDER_TIMEOUT: "AI 请求超时，已恢复可用状态。", PROVIDER_NETWORK_OR_RESPONSE_FAILED: "AI 服务未连接或返回异常，请检查地址和模型。",
  DIALOGUE_OR_TTS_FAILED: "对话或播报失败，文字结果仍可查看，请检查 TTS 模型和输出设备。",
  DIALOGUE_BUSY: "当前对话尚未结束，可点击取消或按住说话打断。",
  SECURE_STORAGE_WINDOWS_ONLY: "此系统不支持 Windows 加密存储，请使用 SILING_API_KEY 环境变量。"
};

function App() {
  const [status, setStatus] = useState<Status>();
  const [settings, setSettings] = useState<Settings>();
  const [devices, setDevices] = useState<Device[]>([]);
  const [messages, setMessages] = useState<VoiceEvent[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [key, setKey] = useState("");
  const [ready, setReady] = useState(false);
  const cursor = useRef(0);
  const mounted = useRef(true);
  const changed = useRef(false);
  const pttStart = useRef<Promise<void>>(Promise.resolve());

  async function refreshDevices() {
    try {setDevices((await api<{devices: Device[]}>("devices")).devices);}
    catch (e) {setError(String(e instanceof Error ? e.message : e));}
  }
  useEffect(() => {
    mounted.current = true;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<Status>(`status?after=${cursor.current}`);
        if (!mounted.current) return;
        // A restarted service can reset the sequence number.
        if (next.event_id < cursor.current) cursor.current = 0;
        else cursor.current = next.event_id;
        setStatus(next);
        if (!changed.current) setSettings(next.settings);
        for (const event of next.events) {
          if (event.type === "transcript" || event.type === "assistant") setMessages(old => [...old, event].slice(-24));
          if (event.type === "error") setError(event.code || "识别异常");
          if (event.type === "endpoint" && event.reason === "no_speech") setError("未听到指令，已回到待机。");
        }
      } catch (e) {if (mounted.current) setError(e instanceof Error ? e.message : String(e));}
      if (mounted.current) timer = setTimeout(() => void poll(), 200);
    }
    connect().then(async () => {
      if (!mounted.current) return;
      setReady(true);
      await refreshDevices();
      await poll();
    }).catch(e => setError(String(e.message)));
    return () => {mounted.current = false; clearTimeout(timer);};
  }, []);

  async function control(action: string) {
    setBusy(true); setError("");
    try {
      await api("control", "POST", {action});
      if (action === "clear" || action === "mute") setMessages([]);
      if (action === "exit") {setReady(false); setError("司聆已退出，麦克风已释放。可以关闭本窗口。"); mounted.current = false; await exitDesktop();}
    } catch (e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(false);}
  }
  function edit(patch: Partial<Settings>) {
    changed.current = true; if (settings) setSettings({...settings, ...patch});
  }
  async function save() {
    setBusy(true); setError("");
    try {await api("settings", "PUT", settings); changed.current = false;}
    catch (e) {setError(e instanceof Error ? e.message : String(e));}
    finally {setBusy(false);}
  }
  async function send() {
    if (!text.trim()) return;
    setError("");
    try {await api("chat", "POST", {text: text.trim()}); setText("");}
    catch (e) {setError(e instanceof Error ? e.message : String(e));}
  }
  async function saveKey() {
    try {await api("credential", "POST", {key}); setKey(""); setError("");}
    catch (e) {setError(e instanceof Error ? e.message : String(e));}
  }
  const listening = status?.state === "IDLE" || status?.state === "LISTENING";
  return <main>
    <header><div><span className="eyebrow">SiLing · 0.2.0</span><h1>司聆</h1></div><span className="privacy">{status?.cloud ? "● 云端 AI · 本地语音" : "● 本地语音处理"}</span></header>
    <section className="voice" aria-label="语音状态">
      {status?.mode === "demo" && <p className="demo">模拟演示 · 不采集麦克风，不进行真实语音识别</p>}
      <div className={`orb ${listening ? "active" : ""}`} aria-hidden="true">聆</div>
      <h2 aria-live="polite">{status?.loading ? "正在加载本地模型…" : status ? labels[status.state] : "正在连接本机服务…"}</h2>
      <p>{status?.state === "LISTENING" ? "请说一句中文，停顿后自动完成转写" : `开始监听后，说「${status?.settings.wake_word || "你好司聆"}」`}</p>
      <div className="meter" role="meter" aria-label="麦克风输入音量" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round((status?.level || 0) * 100)}><i style={{width: `${(status?.level || 0) * 100}%`}}/></div>
      <div className="actions">
        <button className="primary" disabled={!ready || busy} onClick={() => void control(status?.running ? "mute" : "start")}>{status?.running ? "静音并释放麦克风" : "开始监听"}</button>
        <button disabled={!ready || busy || status?.state !== "IDLE"} onClick={() => void control("wake")}>手动唤醒</button>
        <button disabled={!ready || busy || !status?.running} onClick={() => void control("cancel")}>取消本次</button>
        <button disabled={!ready} onPointerDown={e => {e.currentTarget.setPointerCapture(e.pointerId); pttStart.current = control("ptt_start");}} onPointerUp={() => {void pttStart.current.then(() => control("ptt_stop"));}} onPointerCancel={() => {void pttStart.current.then(() => control("cancel"));}} onKeyDown={e => {if (e.code === "Space" && !e.repeat) {e.preventDefault(); pttStart.current = control("ptt_start");}}} onKeyUp={e => {if (e.code === "Space") {e.preventDefault(); void pttStart.current.then(() => control("ptt_stop"));}}}>按住说话 / 打断</button>
      </div>
    </section>
    {error && <div role="alert" className="error">{errors[error] || error}</div>}
    {!status?.models_installed && status?.mode !== "demo" && <aside>首次使用需显式下载约 197 MB 模型：<code>siling-voice models download</code><br/>便携包可运行 <code>SiLing-Voice.exe models download</code>，完成后点击开始监听。</aside>}
    <section className="transcripts"><div className="section-title"><h2>对话与转写</h2><button disabled={!ready || busy} onClick={() => void control("clear")}>清空</button></div>
      {messages.length ? messages.map(m => <article key={m.id} className={m.type === "assistant" ? "assistant" : ""}><small>{m.type === "assistant" ? "司聆" : "你"}</small><p>{m.text}</p>{m.asr_ms !== undefined && <small>本地 ASR · {m.asr_ms} ms</small>}</article>) : <p className="empty">唤醒后说一句话，识别结果会显示在这里。</p>}
      <form className="chat-input" onSubmit={e => {e.preventDefault(); void send();}}><input aria-label="文字消息" value={text} maxLength={2000} onChange={e => setText(e.target.value)} placeholder="也可以输入文字测试 AI 对话"/><button disabled={!ready || status?.dialogue_active}>发送</button><button type="button" disabled={!status?.dialogue_active} onClick={() => void control("cancel")}>停止回复</button></form>
    </section>
    {settings && <details><summary>AI 与播报设置</summary><div className="settings">
      <label>对话服务<select value={settings.provider} onChange={e => edit({provider: e.target.value as Settings["provider"]})}><option value="disabled">仅转写</option><option value="mock">模拟对话（无真实 AI）</option><option value="ollama">Ollama 本地</option><option value="compatible">云端 / OpenAI 兼容接口</option></select></label>
      <label>API 地址<input value={settings.api_base} onChange={e => edit({api_base:e.target.value})}/></label>
      <label>模型 ID<input value={settings.llm_model} onChange={e => edit({llm_model:e.target.value})}/></label>
      <label>中文播报<select value={settings.tts} onChange={e => edit({tts:e.target.value as Settings["tts"]})}><option value="off">关闭播报</option><option value="kokoro">Kokoro 本地中文（需下载）</option><option value="system">Windows 系统中文语音</option><option value="mock">模拟播报（无声音）</option></select></label>
      {settings.tts === "kokoro" && <p>首次执行 <code>SiLing-Voice.exe tts download</code> 获取约 147 MB 模型。</p>}
      <label className="check"><input type="checkbox" checked={settings.cloud_consent} onChange={e => edit({cloud_consent:e.target.checked})}/>允许向选定云服务发送文字与上下文，可能产生费用（音频仍留在本机）</label>
      <label className="check"><input type="checkbox" checked={settings.save_history} onChange={e => edit({save_history:e.target.checked})}/>在本机保留对话历史（默认关闭，可清空删除）</label>
      <button disabled={!ready || busy} onClick={() => void save()}>保存 AI 与播报设置</button>
      <label>API Key（{status?.api_key_configured ? "已配置" : "未配置"}）<input type="password" value={key} autoComplete="off" onChange={e => setKey(e.target.value)} placeholder="Windows 用户加密保存，不写入设置"/></label>
      <button disabled={!key} onClick={() => void saveKey()}>加密保存 Key</button><button onClick={() => {void api("credential/delete","POST").then(() => setKey(""));}}>删除保存的 Key</button>
    </div></details>}
    {settings && <details><summary>麦克风与唤醒设置</summary><div className="settings">
      <label>输入设备<select value={settings.device ?? ""} onChange={e => edit({device: e.target.value === "" ? null : Number(e.target.value)})}><option value="">系统默认麦克风</option>{devices.map(d => <option key={d.id} value={d.id}>{d.name} ({d.sample_rate} Hz)</option>)}</select></label>
      <button disabled={!ready || busy} onClick={() => void refreshDevices()}>刷新设备</button>
      <label>中文唤醒词<input value={settings.wake_word} maxLength={12} onChange={e => edit({wake_word: e.target.value})}/></label>
      <label>结束静音时间<select value={settings.silence_ms} onChange={e => edit({silence_ms: Number(e.target.value)})}>{[400,700,1000,1500].map(n => <option key={n} value={n}>{n} ms</option>)}</select></label>
      <label className="check"><input type="checkbox" checked={settings.chime} onChange={e => edit({chime: e.target.checked})}/>唤醒提示音</label>
      <button disabled={!ready || busy} onClick={() => void save()}>保存设置并停止监听</button>
    </div></details>}
    <footer><p>音频始终本地处理；历史默认不保存。思考和播报期间释放麦克风，使用「按住说话」或停止按钮打断。</p><button disabled={!ready || busy} onClick={() => void control("exit")}>完全退出司聆</button></footer>
  </main>;
}

createRoot(document.getElementById("root")!).render(<App/>);
