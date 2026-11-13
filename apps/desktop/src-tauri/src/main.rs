#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::{process::{Child, Command}, sync::Mutex, time::Duration};
use tauri::{image::Image, menu::{Menu, MenuItem}, tray::TrayIconBuilder, Manager};

#[derive(Clone, Deserialize, Serialize)]
struct Connection { url: String, token: String }
struct VoiceService { child: Mutex<Child>, connection: Connection, _directory: tempfile::TempDir }

#[tauri::command]
fn service_info(service: tauri::State<VoiceService>) -> Connection {
    service.connection.clone()
}

#[tauri::command]
fn exit_app(app: tauri::AppHandle) {
    app.exit(0);
}

fn start_service() -> Result<VoiceService, Box<dyn std::error::Error>> {
    let directory = tempfile::Builder::new().prefix("siling-session-").tempdir()?;
    let ready = directory.path().join("ready.json");
    let exe = std::env::current_exe()?;
    let sibling = exe.parent().ok_or("missing executable directory")?.join("SiLing-Voice.exe");
    let mut command = if sibling.exists() {
        Command::new(sibling)
    } else if cfg!(debug_assertions) {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let mut python = Command::new(root.join(".venv/Scripts/python.exe"));
        python.arg("-m").arg("siling_voice").current_dir(root);
        python
    } else {
        return Err("missing packaged SiLing-Voice.exe".into());
    };
    command.args(["serve", "--no-browser", "--port", "0", "--ready-file"]);
    command.arg(&ready);
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    let mut child = command.spawn()?;
    for _ in 0..200 {
        if let Ok(contents) = std::fs::read_to_string(&ready) {
            if let Ok(connection) = serde_json::from_str::<Connection>(&contents) {
                return Ok(VoiceService {child: Mutex::new(child), connection, _directory: directory});
            }
        }
        if child.try_wait()?.is_some() {
            return Err("voice service exited; another SiLing instance may be running".into());
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    let _ = child.kill();
    let _ = child.wait();
    Err("voice service startup timeout".into())
}

fn main() {
    let application = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![service_info, exit_app])
        .setup(|app| {
            app.manage(start_service()?);
            let show = MenuItem::with_id(app, "show", "打开司聆", true, None::<&str>)?;
            let exit = MenuItem::with_id(app, "exit", "退出并释放麦克风", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &exit])?;
            let mut pixels = vec![0u8; 32 * 32 * 4];
            for pixel in pixels.chunks_exact_mut(4) { pixel.copy_from_slice(&[42, 115, 87, 255]); }
            TrayIconBuilder::new().icon(Image::new_owned(pixels, 32, 32))
                .tooltip("司聆 · 关闭窗口后仍可从托盘打开")
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {if let Some(window) = app.get_webview_window("main") {let _ = window.show(); let _ = window.set_focus();}},
                    "exit" => app.exit(0),
                    _ => {}
                }).build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested {api, ..} = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("司聆启动失败；请关闭其他实例或运行 SiLing-Voice.exe doctor");
    application.run(|app, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(service) = app.try_state::<VoiceService>() {
                if let Ok(mut child) = service.child.lock() {
                    // Process termination also closes every PortAudio device handle.
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    });
}
