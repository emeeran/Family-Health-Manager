//! Tauri shell for the Family Health Manager desktop app.
//!
//! Responsibilities:
//!   * ensure a per-user data directory (XDG app data dir)
//!   * pick a free 127.0.0.1 port
//!   * best-effort start a system Ollama (if installed) for local AI
//!   * spawn the PyInstaller-frozen backend sidecar with cwd = data dir
//!   * wait for the backend to answer /health/ready, then load it same-origin
//!     in the webview (cookie-based auth requires same-origin over plain HTTP)
//!   * force WebKit software rendering so the webview initialises even when the
//!     GPU is saturated (e.g. a local Ollama model resident in VRAM)
//!   * kill the sidecar when the app exits
//!
//! The window is created hidden (see tauri.conf.json) and only shown once the
//! backend URL is loaded, so the user never sees a blank/loading flash.

use std::sync::Mutex;

use tauri::{Manager, RunEvent};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// Holds the spawned backend sidecar so we can kill it on exit.
struct SidecarState(Mutex<Option<CommandChild>>);

/// Bind an ephemeral 127.0.0.1 port and return it (the listener is dropped,
/// opening a tiny race that is harmless for a single-user desktop app).
fn pick_free_port() -> Result<u16, Box<dyn std::error::Error>> {
    let listener = std::net::TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

/// Wait until the backend answers HTTP 200 on `/health/ready`.
///
/// uvicorn binds its listening socket *before* lifespan startup (DB migrations,
/// scheduler) completes, so a successful TCP connect is NOT proof the app is
/// serving — navigating the webview at that moment loads a blank / connection-
/// error page. Poll the readiness endpoint (which runs `SELECT 1`) instead.
fn wait_until_ready(port: u16, timeout_secs: u64) -> bool {
    let addr: std::net::SocketAddr = format!("127.0.0.1:{port}").parse().expect("valid addr");
    let start = std::time::Instant::now();
    while start.elapsed().as_secs() < timeout_secs {
        if http_get_ok(addr, "/health/ready") {
            return true;
        }
        std::thread::sleep(std::time::Duration::from_millis(400));
    }
    false
}

/// Minimal HTTP/1.0 GET; returns true if the server replies 200. Deliberately
/// dependency-free (a blocking HTTP client is awkward inside the Tauri runtime).
fn http_get_ok(addr: std::net::SocketAddr, path: &str) -> bool {
    use std::io::{Read, Write};
    use std::net::TcpStream;
    use std::time::Duration;
    let Ok(mut stream) = TcpStream::connect_timeout(&addr, Duration::from_secs(1)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let request = format!("GET {path} HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 32];
    let n = stream.read(&mut buf).unwrap_or(0);
    let head = std::str::from_utf8(&buf[..n]).unwrap_or("");
    head.starts_with("HTTP/1.0 200") || head.starts_with("HTTP/1.1 200")
}

/// Tear down a whole process tree rooted at `root_pid`.
///
/// A PyInstaller onefile sidecar is a bootloader process that spawns a separate
/// Python child. Killing only the bootloader (e.g. `CommandChild::kill`, which
/// is SIGKILL on the one process we spawned) orphans the Python child, which
/// keeps serving on its port forever. So on exit we SIGTERM the bootloader and
/// every descendant (read from /proc) for a graceful shutdown, then SIGKILL any
/// survivors.
#[cfg(unix)]
fn kill_process_tree(root_pid: u32) {
    use std::collections::HashMap;
    let root = root_pid as i32;

    // Build a pid -> ppid map by scanning /proc (Linux; the deb is Linux-only).
    let mut ppid_of: HashMap<i32, i32> = HashMap::new();
    if let Ok(entries) = std::fs::read_dir("/proc") {
        for entry in entries.flatten() {
            if let Some(name) = entry.file_name().to_str() {
                if let Ok(pid) = name.parse::<i32>() {
                    if let Ok(stat) = std::fs::read_to_string(format!("/proc/{pid}/stat")) {
                        // /proc/<pid>/stat = "pid (comm) state ppid ..." — comm can
                        // contain spaces/parens, so split after the LAST ')'.
                        if let Some(idx) = stat.rfind(')') {
                            let mut parts = stat[idx + 1..].split_whitespace();
                            parts.next(); // state
                            if let Some(ppid_str) = parts.next() {
                                if let Ok(ppid) = ppid_str.parse::<i32>() {
                                    ppid_of.insert(pid, ppid);
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    // Collect the root + all descendants.
    let mut tree = vec![root];
    let mut stack = vec![root];
    while let Some(p) = stack.pop() {
        for (&pid, &ppid) in &ppid_of {
            if ppid == p && !tree.contains(&pid) {
                tree.push(pid);
                stack.push(pid);
            }
        }
    }

    // Graceful first (lets uvicorn run lifespan shutdown / bootloader forward).
    for &pid in &tree {
        unsafe { libc::kill(pid, libc::SIGTERM) };
    }
    std::thread::sleep(std::time::Duration::from_millis(600));
    // Then force-kill anything still alive.
    for &pid in &tree {
        if unsafe { libc::kill(pid, 0) } == 0 {
            unsafe { libc::kill(pid, libc::SIGKILL) };
        }
    }
}

/// Best-effort: if Ollama is installed but not running, start `ollama serve` so
/// the app has local AI. Never fatal — the backend degrades to cloud/empty.
fn try_start_ollama() {
    use std::process::{Command, Stdio};
    let ollama_addr: std::net::SocketAddr = "127.0.0.1:11434".parse().expect("valid addr");
    if std::net::TcpStream::connect_timeout(&ollama_addr, std::time::Duration::from_millis(300)).is_ok() {
        return; // already up
    }
    let on_path = Command::new("sh")
        .args(["-c", "command -v ollama"])
        .output();
    if let Ok(out) = on_path {
        if out.status.success() {
            let _ = Command::new("ollama")
                .arg("serve")
                .stdout(Stdio::null())
                .stderr(Stdio::null())
                .spawn();
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    // WebKit2GTK (the Linux webview) needs a GPU/EGL context to initialise its
    // compositing surface. On a host whose GPU is saturated (common here: a local
    // Ollama model + another LLM runtime resident in VRAM), WebKit can fail to
    // allocate that surface and the window comes up blank / fails to start.
    // Force the software paint path so the webview never depends on GPU
    // availability. Must be set before the webview is created; honour an explicit
    // override (export WEBKIT_DISABLE_COMPOSITING_MODE yourself to change it).
    if std::env::var_os("WEBKIT_DISABLE_COMPOSITING_MODE").is_none() {
        std::env::set_var("WEBKIT_DISABLE_COMPOSITING_MODE", "1");
    }

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // A second launch just focuses the existing window.
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .manage(SidecarState(Mutex::new(None)))
        .setup(|app| {
            // 1. Per-user data dir (XDG: ~/.local/share/com.dawnstar.healthmanager).
            let data_dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(data_dir.join("data").join("attachments"))?;
            std::fs::create_dir_all(data_dir.join("data").join("backups"))?;

            // 2. Free port + best-effort Ollama.
            let port = pick_free_port()?;
            try_start_ollama();

            // 3. Spawn the frozen backend sidecar. cwd = data dir so all the
            //    backend's CWD-relative paths (./data/health.db, data/scheduler.db,
            //    ./data/attachments, data/backups) land in the user's data dir.
            eprintln!("[shell] starting backend sidecar on 127.0.0.1:{port} (data dir: {})", data_dir.display());
            let sidecar = app.shell().sidecar("health-manager-backend").map_err(|e| {
                Box::<dyn std::error::Error>::from(format!("failed to resolve backend sidecar: {e}"))
            })?;
            let (mut rx, child) = sidecar
                .args([format!("--port={port}")])
                .env("APP_ENV", "desktop")
                .env("HM_PORT", port.to_string())
                .env("LOG_LEVEL", "info")
                .current_dir(data_dir)
                .spawn()
                .map_err(|e| {
                    Box::<dyn std::error::Error>::from(format!("failed to spawn backend: {e}"))
                })?;

            // Mirror sidecar stdout/stderr onto our own stderr (debugging aid).
            std::thread::spawn(move || {
                while let Some(event) = rx.blocking_recv() {
                    match event {
                        CommandEvent::Stdout(bytes) | CommandEvent::Stderr(bytes) => {
                            eprintln!("[backend] {}", String::from_utf8_lossy(&bytes).trim_end());
                        }
                        CommandEvent::Terminated(_) => break,
                        _ => {}
                    }
                }
            });

            app.state::<SidecarState>().0.lock().unwrap().replace(child);

            // 4. Wait for the backend to be actually serving HTTP — a TCP-listen
            //    success is too early (uvicorn binds before lifespan finishes) and
            //    would load the webview to a blank/error page.
            if !wait_until_ready(port, 90) {
                eprintln!(
                    "Health Manager: backend did not answer /health/ready on port {port} within \
                     90s. See the [backend] log above. Common causes: missing system libraries \
                     (tesseract-ocr, ghostscript, libwebkit2gtk-4.1-0), a slow first-run DB \
                     migration, or another instance already running."
                );
                return Err("backend did not become ready".into());
            }

            eprintln!("[shell] backend ready on port {port}; loading app in webview");

            // 5. Load the app same-origin from the backend and reveal the window.
            let window = app.get_webview_window("main").ok_or_else(|| {
                Box::<dyn std::error::Error>::from("main window not found")
            })?;
            let url = tauri::Url::parse(&format!("http://127.0.0.1:{port}/"))
                .map_err(|e| Box::<dyn std::error::Error>::from(format!("invalid url: {e}")))?;
            window.navigate(url)?;
            window.show()?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            // Tear down the backend sidecar when the app is exiting. Kill the
            // whole process tree, not just the spawned bootloader — a PyInstaller
            // onefile sidecar runs a bootloader parent + a separate Python child,
            // and SIGKILL on only the bootloader orphans the child.
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(child) = app_handle.state::<SidecarState>().0.lock().unwrap().take() {
                    let pid = child.pid();
                    #[cfg(unix)]
                    kill_process_tree(pid);
                    let _ = child.kill();
                }
            }
        });
}
