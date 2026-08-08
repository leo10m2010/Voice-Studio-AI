use std::{
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
};

use tauri::{AppHandle, Manager, State};

struct EngineProcess(Mutex<Option<Child>>);

fn debug_project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri must have a parent")
        .to_path_buf()
}

fn spawn_engine(app: &AppHandle) -> Result<Child, String> {
    #[cfg(debug_assertions)]
    {
        let root = debug_project_root();
        let python = if cfg!(windows) {
            root.join(".venv").join("Scripts").join("python.exe")
        } else {
            root.join(".venv").join("bin").join("python")
        };
        let script = root.join("engine").join("server.py");

        if !python.exists() {
            return Err(format!(
                "No se encontro el entorno Python en {}. Ejecuta scripts/setup-windows.ps1.",
                python.display()
            ));
        }

        let mut command = Command::new(python);
        command
            .arg(script)
            .current_dir(&root)
            .env("QWEN_STUDIO_ROOT", &root)
            .env("QWEN_ENGINE_PORT", "8765")
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());

        return command.spawn().map_err(|error| error.to_string());
    }

    #[cfg(not(debug_assertions))]
    {
        let resource_dir = app
            .path()
            .resource_dir()
            .map_err(|error| error.to_string())?;

        let executable = if cfg!(windows) {
            resource_dir
                .join("engine-dist")
                .join("qwen-engine")
                .join("qwen-engine.exe")
        } else {
            resource_dir
                .join("engine-dist")
                .join("qwen-engine")
                .join("qwen-engine")
        };

        if !executable.exists() {
            return Err(format!(
                "No se encontro el motor empaquetado en {}.",
                executable.display()
            ));
        }

        let mut command = Command::new(executable);
        command
            .env("QWEN_ENGINE_PORT", "8765")
            .stdout(Stdio::null())
            .stderr(Stdio::null());

        return command.spawn().map_err(|error| error.to_string());
    }
}

#[tauri::command]
fn start_engine(app: AppHandle, state: State<EngineProcess>) -> Result<String, String> {
    let mut guard = state.0.lock().map_err(|_| "No se pudo bloquear el estado.")?;

    if let Some(child) = guard.as_mut() {
        match child.try_wait() {
            Ok(None) => return Ok("running".into()),
            Ok(Some(_)) | Err(_) => {
                *guard = None;
            }
        }
    }

    let child = spawn_engine(&app)?;
    *guard = Some(child);
    Ok("started".into())
}

#[tauri::command]
fn stop_engine(state: State<EngineProcess>) -> Result<(), String> {
    let mut guard = state.0.lock().map_err(|_| "No se pudo bloquear el estado.")?;
    if let Some(child) = guard.as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    *guard = None;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(EngineProcess(Mutex::new(None)))
        .invoke_handler(tauri::generate_handler![start_engine, stop_engine])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<EngineProcess>();
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(child) = guard.as_mut() {
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                    *guard = None;
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Qwen Voice Studio");
}
