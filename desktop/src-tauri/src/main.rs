#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod backend;

use backend::{Backend, Session};
use std::{path::PathBuf, sync::Mutex};
use tauri::Manager;

struct BackendState(Mutex<Result<Backend, String>>);

fn trusted_origin(url: &tauri::Url) -> bool {
    if cfg!(debug_assertions)
        && url.scheme() == "http"
        && url.host_str() == Some("127.0.0.1")
        && url.port() == Some(1420)
    {
        return true;
    }
    matches!(
        (url.scheme(), url.host_str(), url.port()),
        ("tauri", Some("localhost"), None) | ("http" | "https", Some("tauri.localhost"), None)
    )
}

#[tauri::command]
fn backend_session(
    window: tauri::WebviewWindow,
    state: tauri::State<'_, BackendState>,
) -> Result<Session, String> {
    if window.label() != "main" || !trusted_origin(&window.url().map_err(|_| "Invalid window.")?) {
        return Err("This window cannot access the desktop session.".into());
    }
    let mut state = state
        .0
        .lock()
        .map_err(|_| "Backend state is unavailable.")?;
    match state.as_mut() {
        Ok(backend) => backend.session(),
        Err(message) => Err(message.clone()),
    }
}

fn main() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![backend_session])
        .setup(|app| {
            // Source-checkout development layout. Packaging Python is a separate task.
            let directory = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../backend");
            app.manage(BackendState(Mutex::new(Backend::start(&directory))));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to run Nova");
    app.run(|handle, event| {
        if let tauri::RunEvent::Exit = event {
            // Replace the value under its lock; never remove Tauri state while borrowed.
            if let Ok(mut state) = handle.state::<BackendState>().0.lock() {
                *state = Err("Nova has closed.".into());
            }
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn session_origin_is_not_a_hostname_prefix_check() {
        for url in [
            "https://evil.example",
            "http://127.0.0.1:1421",
            "http://tauri.localhost.evil.example",
            "http://tauri.localhost:9999",
        ] {
            assert!(!trusted_origin(&url.parse().unwrap()));
        }
        assert!(trusted_origin(&"tauri://localhost".parse().unwrap()));
    }
}
