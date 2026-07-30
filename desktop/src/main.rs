// Prevents an additional console window on Windows in release builds (harmless
// on Linux/macOS). The desktop app's backend sidecar writes its own stdout to
// the shell's stderr for debugging.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    health_manager_desktop_lib::run();
}
