#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    io::{Read, Write},
    process::{Child, Command},
    sync::{atomic::{AtomicBool, Ordering}, Mutex},
    time::Duration,
};
use tauri::{image::Image, menu::{Menu, MenuItem}, tray::TrayIconBuilder, Emitter, Manager};

#[cfg(windows)]
mod platform {
    use std::{ffi::c_void, os::windows::io::AsRawHandle, process::Child};
    type Handle = *mut c_void;
    #[link(name="kernel32")]
    extern "system" {
        fn CreateMutexW(attributes: Handle, owner: i32, name: *const u16) -> Handle;
        fn GetLastError() -> u32;
        fn CloseHandle(handle: Handle) -> i32;
        fn CreateJobObjectW(attributes: Handle, name: *const u16) -> Handle;
        fn SetInformationJobObject(job: Handle, class: i32, data: Handle, size: u32) -> i32;
        fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
    }
    #[link(name="user32")]
    extern "system" {
        fn FindWindowW(class: *const u16, title: *const u16) -> Handle;
        fn ShowWindow(window: Handle, command: i32) -> i32;
        fn SetForegroundWindow(window: Handle) -> i32;
    }
    pub struct Instance(Handle);
    impl Drop for Instance { fn drop(&mut self) { unsafe { CloseHandle(self.0); } } }
    pub fn single_instance() -> Option<Instance> {
        let name: Vec<u16> = "Local\\SiLingDesktop-v1\0".encode_utf16().collect();
        let handle = unsafe { CreateMutexW(std::ptr::null_mut(), 0, name.as_ptr()) };
        if handle.is_null() { panic!("SiLing single-instance mutex failed"); }
        if unsafe { GetLastError() } == 183 {
            let title: Vec<u16> = "司聆 SiLing\0".encode_utf16().collect();
            unsafe {
                let window = FindWindowW(std::ptr::null(), title.as_ptr());
                if !window.is_null() { ShowWindow(window, 9); SetForegroundWindow(window); }
                CloseHandle(handle);
            }
            None
        } else { Some(Instance(handle)) }
    }
    #[repr(C)]
    struct BasicLimits { process_time: i64, job_time: i64, flags: u32, min_ws: usize,
        max_ws: usize, active: u32, affinity: usize, priority: u32, scheduling: u32 }
    #[repr(C)]
    struct Limits { basic: BasicLimits, io: [u64; 6], process_memory: usize,
        job_memory: usize, peak_process: usize, peak_job: usize }
    pub struct Job(Handle);
    // Kernel handles are thread-independent; ownership is protected by Runtime's mutex.
    unsafe impl Send for Job {}
    impl Job {
        pub fn assign(child: &Child) -> std::io::Result<Self> {
            unsafe {
                let job = CreateJobObjectW(std::ptr::null_mut(), std::ptr::null());
                if job.is_null() { return Err(std::io::Error::last_os_error()); }
                let mut limits: Limits = std::mem::zeroed();
                limits.basic.flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                if SetInformationJobObject(job, 9, &mut limits as *mut _ as Handle,
                    std::mem::size_of::<Limits>() as u32) == 0
                    || AssignProcessToJobObject(job, child.as_raw_handle()) == 0 {
                    CloseHandle(job); return Err(std::io::Error::last_os_error());
                }
                Ok(Self(job))
            }
        }
    }
    impl Drop for Job { fn drop(&mut self) { unsafe { CloseHandle(self.0); } } }
}

#[derive(Clone, Deserialize, Serialize)]
struct Connection { url: String, token: String, pid: u32 }
struct Runtime {
    child: Child,
    connection: Connection,
    _directory: tempfile::TempDir,
    #[cfg(windows)] _job: Option<platform::Job>,
}
struct VoiceService { runtime: Mutex<Runtime>, stopping: AtomicBool }

#[tauri::command]
fn service_info(service: tauri::State<VoiceService>) -> Result<Connection, String> {
    if service.stopping.load(Ordering::SeqCst) { return Err("SERVICE_STOPPING".into()); }
    Ok(service.runtime.lock().map_err(|_| "SERVICE_LOCK_FAILED")?.connection.clone())
}
#[tauri::command]
fn exit_app(app: tauri::AppHandle) { app.exit(0); }

fn request_bytes(connection: &Connection, path: &str, body: Option<Value>) -> Result<Vec<u8>, String> {
    let port: u16 = connection.url.strip_prefix("http://127.0.0.1:")
        .ok_or("SERVICE_URL_INVALID")?.parse().map_err(|_| "SERVICE_URL_INVALID")?;
    let address = std::net::SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = std::net::TcpStream::connect_timeout(&address, Duration::from_millis(800))
        .map_err(|_| "SERVICE_UNAVAILABLE")?;
    stream.set_read_timeout(Some(Duration::from_secs(2))).map_err(|_| "SERVICE_UNAVAILABLE")?;
    stream.set_write_timeout(Some(Duration::from_secs(2))).map_err(|_| "SERVICE_UNAVAILABLE")?;
    let method = if body.is_some() { "POST" } else { "GET" };
    let data = body.map(|v| v.to_string()).unwrap_or_default();
    let header = format!("{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{data}", connection.token, data.len());
    stream.write_all(header.as_bytes()).map_err(|_| "SERVICE_UNAVAILABLE")?;
    let mut bytes = Vec::new();
    stream.take(2_097_152).read_to_end(&mut bytes).map_err(|_| "SERVICE_UNAVAILABLE")?;
    let end = bytes.windows(4).position(|x| x == b"\r\n\r\n").ok_or("SERVICE_RESPONSE_INVALID")?;
    if !bytes.starts_with(b"HTTP/1.1 200") { return Err("SERVICE_REQUEST_REJECTED".into()); }
    Ok(bytes[end + 4..].to_vec())
}

fn request(connection: &Connection, path: &str, body: Option<Value>) -> Result<Value, String> {
    serde_json::from_slice(&request_bytes(connection, path, body)?)
        .map_err(|_| "SERVICE_RESPONSE_INVALID".into())
}
#[tauri::command]
fn export_diagnostics(app: tauri::AppHandle, service: tauri::State<VoiceService>) -> Result<String, String> {
    let connection = service.runtime.lock().map_err(|_| "SERVICE_LOCK_FAILED")?.connection.clone();
    let data = request_bytes(&connection, "/api/diagnostics/download", None)?;
    let folder = app.path().download_dir().map_err(|_| "DOWNLOAD_DIRECTORY_UNAVAILABLE")?;
    std::fs::create_dir_all(&folder).map_err(|_| "DIAGNOSTIC_SAVE_FAILED")?;
    let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let path = folder.join(format!("SiLing-diagnostics-{stamp}.zip"));
    let mut output = std::fs::OpenOptions::new().create_new(true).write(true).open(&path)
        .map_err(|_| "DIAGNOSTIC_SAVE_FAILED")?;
    output.write_all(&data).map_err(|_| "DIAGNOSTIC_SAVE_FAILED")?;
    Ok(path.to_string_lossy().to_string())
}

fn start_service() -> Result<Runtime, Box<dyn std::error::Error>> {
    let directory = tempfile::Builder::new().prefix("siling-session-").tempdir()?;
    let ready = directory.path().join("ready.json");
    let exe = std::env::current_exe()?;
    let sibling = exe.parent().ok_or("missing executable directory")?.join("SiLing-Voice.exe");
    let mut command = if sibling.exists() { Command::new(sibling) }
    else if cfg!(debug_assertions) {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let mut python = Command::new(root.join(".venv/Scripts/python.exe"));
        python.arg("-m").arg("siling_voice").current_dir(root); python
    } else { return Err("missing packaged SiLing-Voice.exe".into()); };
    command.args(["serve", "--no-browser", "--port", "0", "--ready-file"]).arg(&ready);
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }
    let mut child = command.spawn()?;
    #[cfg(windows)]
    let job = match platform::Job::assign(&child) {
        Ok(job) => job,
        Err(error) => {let _ = child.kill(); let _ = child.wait(); return Err(error.into());}
    };
    for _ in 0..300 {
        if let Ok(contents) = std::fs::read_to_string(&ready) {
            if let Ok(connection) = serde_json::from_str::<Connection>(&contents) {
                return Ok(Runtime {child, connection, _directory: directory,
                    #[cfg(windows)] _job: Some(job)});
            }
        }
        if child.try_wait()?.is_some() { return Err("voice service exited before readiness".into()); }
        std::thread::sleep(Duration::from_millis(50));
    }
    let _ = child.kill(); let _ = child.wait();
    Err("voice service startup timeout".into())
}

fn icon(state: &str) -> Image<'static> {
    let rgb = match state {
        "LISTENING" | "WAKE_DETECTED" => [190, 65, 65],
        "THINKING" | "TRANSCRIBING" | "ACTING" => [65, 110, 190],
        "SPEAKING" => [135, 85, 175], "MUTED" => [125, 135, 130],
        "ERROR" => [195, 115, 40], _ => [42, 115, 87],
    };
    let mut pixels = vec![0u8; 32 * 32 * 4];
    for pixel in pixels.chunks_exact_mut(4) { pixel.copy_from_slice(&[rgb[0], rgb[1], rgb[2], 255]); }
    Image::new_owned(pixels, 32, 32)
}
fn state_label(state: &str) -> &str {
    match state {
        "IDLE" => "等待唤醒", "LISTENING" => "正在录音", "TRANSCRIBING" => "正在转写",
        "THINKING" => "正在思考", "ACTING" => "等待工具确认", "SPEAKING" => "正在播报",
        "MUTED" => "麦克风已释放", "ERROR" => "需要处理", _ => "准备中",
    }
}

fn set_mini(app: &tauri::AppHandle, visible: bool) -> Result<(), String> {
    if let Some(window) = app.get_webview_window("mini") {
        if visible {window.show()} else {window.hide()}.map_err(|_| "MINI_WINDOW_FAILED")?;
    } else if visible {
        tauri::WebviewWindowBuilder::new(app, "mini", tauri::WebviewUrl::App("index.html?view=mini".into()))
            .title("司聆 · 悬浮窗").inner_size(320.0, 190.0).resizable(false)
            .decorations(false).always_on_top(true).skip_taskbar(true)
            .build().map_err(|_| "MINI_WINDOW_FAILED")?;
    }
    if let Ok(directory) = app.path().app_config_dir() {
        let _ = std::fs::create_dir_all(&directory);
        let _ = std::fs::write(directory.join("desktop.json"), json!({"mini":visible}).to_string());
    }
    Ok(())
}
#[tauri::command]
fn toggle_mini(app: tauri::AppHandle) -> Result<(), String> {
    let visible = app.get_webview_window("mini").and_then(|w| w.is_visible().ok()).unwrap_or(false);
    set_mini(&app, !visible)
}

fn main() {
    #[cfg(windows)] let Some(_instance) = platform::single_instance() else { return; };
    let application = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![service_info, exit_app, toggle_mini, export_diagnostics])
        .setup(|app| {
            app.manage(VoiceService {runtime: Mutex::new(start_service()?), stopping: AtomicBool::new(false)});
            let show = MenuItem::with_id(app, "show", "打开司聆", true, None::<&str>)?;
            let status = MenuItem::with_id(app, "status", "状态：准备中", false, None::<&str>)?;
            let mute = MenuItem::with_id(app, "mute", "开始监听", true, None::<&str>)?;
            let mini = MenuItem::with_id(app, "mini", "显示/隐藏悬浮窗", true, None::<&str>)?;
            let startup = MenuItem::with_id(app, "startup", "切换开机启动", true, None::<&str>)?;
            let exit = MenuItem::with_id(app, "exit", "退出并释放麦克风", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &status, &mute, &mini, &startup, &exit])?;
            let tray = TrayIconBuilder::new().icon(icon("MUTED")).tooltip("司聆 · 麦克风已释放")
                .menu(&menu).on_menu_event(|app, event| {
                    match event.id.as_ref() {
                        "show" => {if let Some(window) = app.get_webview_window("main") {let _ = window.show(); let _ = window.set_focus();}},
                        "mini" => {let _ = toggle_mini(app.clone());},
                        "mute" | "startup" => {
                            let service = app.state::<VoiceService>();
                            let connection = service.runtime.lock().unwrap().connection.clone();
                            if let Ok(current) = request(&connection, "/api/status", None) {
                                let result = if event.id.as_ref() == "mute" {
                                    let action = if current["running"].as_bool().unwrap_or(false) {"mute"} else {"start"};
                                    request(&connection, "/api/control", Some(json!({"action":action})))
                                } else {
                                    request(&connection, "/api/desktop/autostart", Some(json!({"enabled":!current["autostart"].as_bool().unwrap_or(false)})))
                                };
                                if result.is_err() {let _ = app.emit("desktop-error", "DESKTOP_CONTROL_FAILED");}
                            }
                        },
                        "exit" => app.exit(0), _ => {}
                    }
                }).build(app)?;
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                let mut restarts = 0;
                loop {
                    std::thread::sleep(Duration::from_millis(700));
                    let Some(service) = handle.try_state::<VoiceService>() else { break; };
                    if service.stopping.load(Ordering::SeqCst) {break;}
                    let status_code = service.runtime.lock().unwrap().child.try_wait();
                    if let Ok(Some(code)) = status_code {
                        if code.success() {handle.exit(0); break;}
                        // A one-file bootloader can die while its extracted server survives.
                        // Close the old job BEFORE starting a replacement that needs its lock.
                        #[cfg(windows)] {service.runtime.lock().unwrap()._job.take();}
                        if restarts >= 3 {service.stopping.store(true, Ordering::SeqCst); let _ = status.set_text("状态：服务异常，请退出后重试"); break;}
                        restarts += 1;
                        std::thread::sleep(Duration::from_millis(500 * restarts));
                        match start_service() {
                            Ok(runtime) => {
                                *service.runtime.lock().unwrap() = runtime;
                                let _ = handle.emit("service-restarted", json!({"attempt":restarts,"microphone":"muted"}));
                            },
                            Err(_) => {let _ = status.set_text("状态：服务恢复失败"); continue;}
                        }
                    }
                    let connection = service.runtime.lock().unwrap().connection.clone();
                    if let Ok(current) = request(&connection, "/api/status", None) {
                        let state = current["state"].as_str().unwrap_or("ERROR");
                        let label = state_label(state);
                        let _ = status.set_text(format!("状态：{label}"));
                        let _ = mute.set_text(if current["running"].as_bool().unwrap_or(false) {"静音并释放麦克风"} else {"开始监听"});
                        let _ = tray.set_tooltip(Some(format!("司聆 · {label}")));
                        let _ = tray.set_icon(Some(icon(state)));
                    }
                }
            });
            if std::env::args().any(|x| x == "--background") {
                if let Some(window) = app.get_webview_window("main") {let _ = window.hide();}
            }
            if let Ok(directory) = app.path().app_config_dir() {
                if let Ok(contents) = std::fs::read_to_string(directory.join("desktop.json")) {
                    if serde_json::from_str::<Value>(&contents).ok().and_then(|v| v["mini"].as_bool()).unwrap_or(false) {
                        let _ = set_mini(app.handle(), true);
                    }
                }
            }
            // Explicit CI mode: test the real host, job ownership and service restart.
            let args: Vec<String> = std::env::args().collect();
            if let Some(index) = args.iter().position(|x| x == "--smoke-report") {
                let report = args.get(index + 1).ok_or("missing smoke report path")?.clone();
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(Duration::from_secs(2));
                    let service = handle.state::<VoiceService>();
                    let original = service.runtime.lock().unwrap().connection.clone();
                    let initial = request(&original, "/api/status", None).ok();
                    let mini_ok = set_mini(&handle, true).is_ok()
                        && handle.get_webview_window("mini").is_some();
                    let _ = set_mini(&handle, false);
                    let diagnostic_ok = request_bytes(&original, "/api/diagnostics/download", None)
                        .map(|data| data.starts_with(b"PK") && data.len() > 100).unwrap_or(false);
                    let _ = service.runtime.lock().unwrap().child.kill();
                    let mut recovered = false;
                    let mut recovered_pid = 0;
                    for _ in 0..100 {
                        std::thread::sleep(Duration::from_millis(200));
                        let next = service.runtime.lock().unwrap().connection.clone();
                        if next.url != original.url && request(&next, "/api/status", None)
                            .map(|v| v["state"] == "MUTED").unwrap_or(false) {
                            recovered = true; recovered_pid = next.pid; break;
                        }
                    }
                    let value = json!({"native_start":initial.is_some(),"initial_muted":initial.map(|v| v["state"] == "MUTED").unwrap_or(false),"service_restart":recovered,"mini_window":mini_ok,"diagnostic_download":diagnostic_ok,"initial_service_pid":original.pid,"recovered_service_pid":recovered_pid,"hardware_acceptance":"NOT_VERIFIED"});
                    let _ = std::fs::write(report, value.to_string());
                    handle.exit(if recovered && mini_ok && diagnostic_ok {0} else {1});
                });
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested {api, ..} = event {
                api.prevent_close(); let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("司聆启动失败；请关闭其他实例或运行 SiLing-Voice.exe doctor");
    application.run(|app, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(service) = app.try_state::<VoiceService>() {
                service.stopping.store(true, Ordering::SeqCst);
                if let Ok(mut runtime) = service.runtime.lock() {
                    #[cfg(windows)] {runtime._job.take();}
                    let _ = runtime.child.kill(); let _ = runtime.child.wait();
                }
            }
        }
    });
}
