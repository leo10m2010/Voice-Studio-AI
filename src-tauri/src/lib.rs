use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    time::Duration,
};

use reqwest::{
    blocking::Client,
    header::RANGE,
    StatusCode,
};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter, Manager, State};
use zip::ZipArchive;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

const ENGINE_MANIFEST_URL: &str = "https://github.com/leo10m2010/Voice-Studio-AI/releases/download/engine-v1.0.0/engine-manifest.json";
const ENGINE_PORT: &str = "8765";

struct EngineProcess(Mutex<Option<Child>>);

struct EngineInstallState {
    cancel: Arc<AtomicBool>,
    running: Mutex<bool>,
}

impl Default for EngineInstallState {
    fn default() -> Self {
        Self {
            cancel: Arc::new(AtomicBool::new(false)),
            running: Mutex::new(false),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EnginePart {
    name: String,
    url: String,
    sha256: String,
    bytes: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EnginePackage {
    flavor: String,
    label: String,
    version: String,
    download_bytes: u64,
    installed_bytes: u64,
    #[serde(default)]
    description: String,
    parts: Vec<EnginePart>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct EngineManifest {
    schema: u32,
    version: String,
    #[serde(default)]
    published_at: Option<String>,
    engines: Vec<EnginePackage>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct EngineInstallRecord {
    version: String,
    flavor: String,
    label: String,
    installed_bytes: u64,
}

#[derive(Debug, Clone, Serialize)]
struct EngineStatus {
    installed: bool,
    version: Option<String>,
    flavor: Option<String>,
    label: Option<String>,
    path: String,
    installed_bytes: u64,
    executable_exists: bool,
    running: bool,
}

#[derive(Debug, Clone, Serialize)]
struct HardwareInfo {
    nvidia_available: bool,
    gpu_name: Option<String>,
    vram_gb: Option<f64>,
    driver_version: Option<String>,
    recommended_flavor: String,
}

#[derive(Debug, Clone, Serialize)]
struct EngineCatalog {
    manifest: EngineManifest,
    hardware: HardwareInfo,
    status: EngineStatus,
    recommended_flavor: String,
}

#[derive(Debug, Clone, Serialize)]
struct EngineProgress {
    stage: String,
    message: String,
    percent: f64,
    downloaded_bytes: u64,
    total_bytes: u64,
    part_index: usize,
    part_count: usize,
    flavor: String,
}

fn debug_project_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri must have a parent")
        .to_path_buf()
}

fn app_engine_root(app: &AppHandle) -> Result<PathBuf, String> {
    app.path()
        .app_local_data_dir()
        .map(|path| path.join("engine"))
        .map_err(|error| error.to_string())
}

fn runtime_dir(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app_engine_root(app)?.join("runtime"))
}

fn runtime_executable(app: &AppHandle) -> Result<PathBuf, String> {
    let name = if cfg!(windows) {
        "qwen-engine.exe"
    } else {
        "qwen-engine"
    };
    Ok(runtime_dir(app)?.join(name))
}

fn install_record_path(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(runtime_dir(app)?.join("install.json"))
}

fn directory_size(path: &Path) -> u64 {
    if !path.exists() {
        return 0;
    }
    let mut total = 0u64;
    let Ok(entries) = fs::read_dir(path) else {
        return 0;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if let Ok(meta) = entry.metadata() {
            if meta.is_file() {
                total = total.saturating_add(meta.len());
            } else if meta.is_dir() {
                total = total.saturating_add(directory_size(&path));
            }
        }
    }
    total
}

fn read_install_record(app: &AppHandle) -> Option<EngineInstallRecord> {
    let path = install_record_path(app).ok()?;
    let content = fs::read_to_string(path).ok()?;
    serde_json::from_str(&content).ok()
}

fn engine_running(state: &EngineProcess) -> bool {
    let Ok(mut guard) = state.0.lock() else {
        return false;
    };
    if let Some(child) = guard.as_mut() {
        return matches!(child.try_wait(), Ok(None));
    }
    false
}

fn engine_status_value(app: &AppHandle, process: &EngineProcess) -> Result<EngineStatus, String> {
    #[cfg(debug_assertions)]
    {
        let root = debug_project_root();
        let exe = if cfg!(windows) {
            root.join(".venv").join("Scripts").join("python.exe")
        } else {
            root.join(".venv").join("bin").join("python")
        };
        return Ok(EngineStatus {
            installed: exe.exists(),
            version: Some("dev".into()),
            flavor: Some("development".into()),
            label: Some("Entorno de desarrollo".into()),
            path: exe.display().to_string(),
            installed_bytes: 0,
            executable_exists: exe.exists(),
            running: engine_running(process),
        });
    }

    #[cfg(not(debug_assertions))]
    {
        let runtime = runtime_dir(app)?;
        let executable = runtime_executable(app)?;
        let record = read_install_record(app);
        Ok(EngineStatus {
            installed: executable.exists(),
            version: record.as_ref().map(|x| x.version.clone()),
            flavor: record.as_ref().map(|x| x.flavor.clone()),
            label: record.as_ref().map(|x| x.label.clone()),
            path: runtime.display().to_string(),
            installed_bytes: if runtime.exists() { directory_size(&runtime) } else { 0 },
            executable_exists: executable.exists(),
            running: engine_running(process),
        })
    }
}

#[cfg(windows)]
fn hidden_command(program: impl AsRef<std::ffi::OsStr>) -> Command {
    let mut command = Command::new(program);
    command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    command
}

#[cfg(not(windows))]
fn hidden_command(program: impl AsRef<std::ffi::OsStr>) -> Command {
    Command::new(program)
}

fn detect_hardware_value() -> HardwareInfo {
    #[cfg(windows)]
    {
        let output = hidden_command("nvidia-smi")
            .args([
                "--query-gpu=name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ])
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .output();

        if let Ok(output) = output {
            if output.status.success() {
                let text = String::from_utf8_lossy(&output.stdout);
                if let Some(line) = text.lines().next() {
                    let fields: Vec<_> = line.split(',').map(|value| value.trim()).collect();
                    let gpu_name = fields.first().filter(|x| !x.is_empty()).map(|x| x.to_string());
                    let vram_mb = fields.get(1).and_then(|x| x.parse::<f64>().ok());
                    let driver = fields.get(2).filter(|x| !x.is_empty()).map(|x| x.to_string());
                    let vram_gb = vram_mb.map(|mb| mb / 1024.0);
                    let recommended_flavor = if vram_gb.unwrap_or(0.0) >= 5.5 {
                        "nvidia"
                    } else {
                        "cpu"
                    };
                    return HardwareInfo {
                        nvidia_available: true,
                        gpu_name,
                        vram_gb,
                        driver_version: driver,
                        recommended_flavor: recommended_flavor.into(),
                    };
                }
            }
        }
    }

    HardwareInfo {
        nvidia_available: false,
        gpu_name: None,
        vram_gb: None,
        driver_version: None,
        recommended_flavor: "cpu".into(),
    }
}

fn manifest_source() -> String {
    std::env::var("VOICE_STUDIO_ENGINE_MANIFEST")
        .unwrap_or_else(|_| ENGINE_MANIFEST_URL.to_string())
}

fn http_client() -> Result<Client, String> {
    Client::builder()
        .user_agent(concat!("Voice-Studio-AI/", env!("CARGO_PKG_VERSION")))
        .connect_timeout(Duration::from_secs(20))
        .timeout(Duration::from_secs(120))
        .build()
        .map_err(|error| error.to_string())
}

fn load_manifest() -> Result<EngineManifest, String> {
    let source = manifest_source();

    let text = if source.starts_with("https://") || source.starts_with("http://") {
        let response = http_client()?
            .get(&source)
            .send()
            .map_err(|error| format!("No se pudo consultar el catálogo del motor: {error}"))?;

        if !response.status().is_success() {
            return Err(format!(
                "El catálogo del motor respondió HTTP {}. Publica engine-manifest.json en {}.",
                response.status(),
                source
            ));
        }

        response
            .text()
            .map_err(|error| format!("No se pudo leer el catálogo del motor: {error}"))?
    } else {
        fs::read_to_string(&source)
            .map_err(|error| format!("No se pudo abrir el catálogo local {source}: {error}"))?
    };

    let manifest: EngineManifest = serde_json::from_str(&text)
        .map_err(|error| format!("engine-manifest.json no es válido: {error}"))?;

    if manifest.engines.is_empty() {
        return Err("El catálogo del motor no contiene paquetes.".into());
    }

    Ok(manifest)
}

fn emit_progress(app: &AppHandle, progress: EngineProgress) {
    let _ = app.emit("engine-install-progress", progress);
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = File::open(path).map_err(|error| error.to_string())?;
    let mut hasher = Sha256::new();
    let mut buffer = vec![0u8; 1024 * 1024];

    loop {
        let read = file.read(&mut buffer).map_err(|error| error.to_string())?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }

    Ok(hex::encode(hasher.finalize()))
}

fn download_part(
    app: &AppHandle,
    client: &Client,
    part: &EnginePart,
    destination: &Path,
    already_completed: u64,
    total_bytes: u64,
    part_index: usize,
    part_count: usize,
    flavor: &str,
    cancel: &AtomicBool,
) -> Result<u64, String> {
    if cancel.load(Ordering::Relaxed) {
        return Err("Instalación cancelada.".into());
    }

    if destination.exists() && !part.sha256.is_empty() {
        if let Ok(existing_hash) = sha256_file(destination) {
            if existing_hash.eq_ignore_ascii_case(&part.sha256) {
                let bytes = fs::metadata(destination).map(|m| m.len()).unwrap_or(part.bytes);
                emit_progress(
                    app,
                    EngineProgress {
                        stage: "downloading".into(),
                        message: format!("Parte {part_index} de {part_count} ya estaba descargada."),
                        percent: if total_bytes > 0 {
                            ((already_completed + bytes) as f64 / total_bytes as f64) * 82.0
                        } else { 0.0 },
                        downloaded_bytes: already_completed + bytes,
                        total_bytes,
                        part_index,
                        part_count,
                        flavor: flavor.into(),
                    },
                );
                return Ok(bytes);
            }
        }
    }

    if let Some(parent) = destination.parent() {
        fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }

    let existing = fs::metadata(destination).map(|m| m.len()).unwrap_or(0);
    let mut request = client.get(&part.url);
    if existing > 0 {
        request = request.header(RANGE, format!("bytes={existing}-"));
    }

    let mut response = request
        .send()
        .map_err(|error| format!("No se pudo descargar {}: {error}", part.name))?;

    let append = existing > 0 && response.status() == StatusCode::PARTIAL_CONTENT;
    if !response.status().is_success() {
        return Err(format!(
            "La descarga {} respondió HTTP {}.",
            part.name,
            response.status()
        ));
    }

    let mut file = if append {
        OpenOptions::new()
            .create(true)
            .append(true)
            .open(destination)
            .map_err(|error| error.to_string())?
    } else {
        File::create(destination).map_err(|error| error.to_string())?
    };

    let base = if append { existing } else { 0 };
    let mut downloaded = base;
    let mut buffer = vec![0u8; 1024 * 1024];

    loop {
        if cancel.load(Ordering::Relaxed) {
            return Err("Instalación cancelada. La descarga parcial se conservará para reanudarla.".into());
        }

        let read = response
            .read(&mut buffer)
            .map_err(|error| format!("La descarga se interrumpió: {error}"))?;
        if read == 0 {
            break;
        }

        file.write_all(&buffer[..read])
            .map_err(|error| format!("No se pudo guardar la descarga: {error}"))?;
        downloaded = downloaded.saturating_add(read as u64);

        let global_downloaded = already_completed.saturating_add(downloaded);
        let percent = if total_bytes > 0 {
            (global_downloaded as f64 / total_bytes as f64).min(1.0) * 82.0
        } else {
            0.0
        };

        emit_progress(
            app,
            EngineProgress {
                stage: "downloading".into(),
                message: format!("Descargando parte {part_index} de {part_count}…"),
                percent,
                downloaded_bytes: global_downloaded,
                total_bytes,
                part_index,
                part_count,
                flavor: flavor.into(),
            },
        );
    }

    file.flush().map_err(|error| error.to_string())?;
    Ok(downloaded)
}

fn extract_archive(archive_path: &Path, destination: &Path) -> Result<(), String> {
    let file = File::open(archive_path).map_err(|error| error.to_string())?;
    let mut archive = ZipArchive::new(file)
        .map_err(|error| format!("Archivo de motor inválido: {error}"))?;
    archive
        .extract(destination)
        .map_err(|error| format!("No se pudo extraer el motor: {error}"))
}

fn run_runtime_self_test(executable: &Path) -> Result<(), String> {
    let output = hidden_command(executable)
        .arg("--self-test-packaging")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .output()
        .map_err(|error| format!("No se pudo ejecutar la comprobación del motor: {error}"))?;

    if output.status.success() {
        return Ok(());
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    Err(format!(
        "El motor descargado no pasó la comprobación. {} {}",
        stdout.trim(),
        stderr.trim()
    ))
}

fn install_engine_blocking(
    app: AppHandle,
    flavor: String,
    cancel: Arc<AtomicBool>,
) -> Result<EngineStatus, String> {
    let manifest = load_manifest()?;
    let package = manifest
        .engines
        .iter()
        .find(|item| item.flavor.eq_ignore_ascii_case(&flavor))
        .cloned()
        .ok_or_else(|| format!("El catálogo no ofrece el motor '{flavor}'."))?;

    let root = app_engine_root(&app)?;
    let downloads = root.join("downloads").join(&package.version).join(&package.flavor);
    let staging = root.join(format!("staging-{}-{}", package.version, package.flavor));
    let runtime = root.join("runtime");

    fs::create_dir_all(&downloads).map_err(|error| error.to_string())?;
    if staging.exists() {
        fs::remove_dir_all(&staging).map_err(|error| error.to_string())?;
    }
    fs::create_dir_all(&staging).map_err(|error| error.to_string())?;

    let client = http_client()?;
    let total_bytes = if package.download_bytes > 0 {
        package.download_bytes
    } else {
        package.parts.iter().map(|part| part.bytes).sum()
    };

    emit_progress(
        &app,
        EngineProgress {
            stage: "preparing".into(),
            message: "Preparando descarga segura…".into(),
            percent: 1.0,
            downloaded_bytes: 0,
            total_bytes,
            part_index: 0,
            part_count: package.parts.len(),
            flavor: package.flavor.clone(),
        },
    );

    let mut completed = 0u64;
    for (index, part) in package.parts.iter().enumerate() {
        let path = downloads.join(&part.name);
        let actual = download_part(
            &app,
            &client,
            part,
            &path,
            completed,
            total_bytes,
            index + 1,
            package.parts.len(),
            &package.flavor,
            &cancel,
        )?;
        completed = completed.saturating_add(actual);

        emit_progress(
            &app,
            EngineProgress {
                stage: "verifying".into(),
                message: format!("Verificando parte {} de {}…", index + 1, package.parts.len()),
                percent: 82.0 + ((index + 1) as f64 / package.parts.len().max(1) as f64) * 7.0,
                downloaded_bytes: completed,
                total_bytes,
                part_index: index + 1,
                part_count: package.parts.len(),
                flavor: package.flavor.clone(),
            },
        );

        if !part.sha256.is_empty() {
            let actual_hash = sha256_file(&path)?;
            if !actual_hash.eq_ignore_ascii_case(&part.sha256) {
                let _ = fs::remove_file(&path);
                return Err(format!(
                    "La verificación SHA-256 falló para {}. Se eliminó esa parte para descargarla de nuevo.",
                    part.name
                ));
            }
        }

        if cancel.load(Ordering::Relaxed) {
            return Err("Instalación cancelada.".into());
        }

        emit_progress(
            &app,
            EngineProgress {
                stage: "installing".into(),
                message: format!("Instalando parte {} de {}…", index + 1, package.parts.len()),
                percent: 89.0 + ((index + 1) as f64 / package.parts.len().max(1) as f64) * 7.0,
                downloaded_bytes: completed,
                total_bytes,
                part_index: index + 1,
                part_count: package.parts.len(),
                flavor: package.flavor.clone(),
            },
        );

        extract_archive(&path, &staging)?;
    }

    let staged_executable = staging.join(if cfg!(windows) {
        "qwen-engine.exe"
    } else {
        "qwen-engine"
    });

    if !staged_executable.exists() {
        return Err(format!(
            "El paquete terminó de extraerse, pero falta {}.",
            staged_executable.display()
        ));
    }

    emit_progress(
        &app,
        EngineProgress {
            stage: "testing".into(),
            message: "Comprobando que el motor puede iniciar…".into(),
            percent: 97.0,
            downloaded_bytes: completed,
            total_bytes,
            part_index: package.parts.len(),
            part_count: package.parts.len(),
            flavor: package.flavor.clone(),
        },
    );

    run_runtime_self_test(&staged_executable)?;

    let backup = root.join("runtime-backup");
    if backup.exists() {
        let _ = fs::remove_dir_all(&backup);
    }
    if runtime.exists() {
        fs::rename(&runtime, &backup).map_err(|error| error.to_string())?;
    }

    if let Err(error) = fs::rename(&staging, &runtime) {
        if backup.exists() && !runtime.exists() {
            let _ = fs::rename(&backup, &runtime);
        }
        return Err(format!("No se pudo activar el motor nuevo: {error}"));
    }

    let record = EngineInstallRecord {
        version: package.version.clone(),
        flavor: package.flavor.clone(),
        label: package.label.clone(),
        installed_bytes: directory_size(&runtime),
    };
    fs::write(
        runtime.join("install.json"),
        serde_json::to_vec_pretty(&record).map_err(|error| error.to_string())?,
    )
    .map_err(|error| error.to_string())?;

    if backup.exists() {
        let _ = fs::remove_dir_all(&backup);
    }

    emit_progress(
        &app,
        EngineProgress {
            stage: "done".into(),
            message: "Motor instalado y verificado.".into(),
            percent: 100.0,
            downloaded_bytes: total_bytes,
            total_bytes,
            part_index: package.parts.len(),
            part_count: package.parts.len(),
            flavor: package.flavor.clone(),
        },
    );

    let dummy = EngineProcess(Mutex::new(None));
    engine_status_value(&app, &dummy)
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
                "No se encontró el entorno Python en {}. Ejecuta scripts/setup-windows.ps1.",
                python.display()
            ));
        }

        let mut command = Command::new(python);
        command
            .arg(script)
            .current_dir(&root)
            .env("QWEN_STUDIO_ROOT", &root)
            .env("QWEN_ENGINE_PORT", ENGINE_PORT)
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());

        return command.spawn().map_err(|error| error.to_string());
    }

    #[cfg(not(debug_assertions))]
    {
        let executable = runtime_executable(app)?;
        if !executable.exists() {
            return Err("ENGINE_NOT_INSTALLED".into());
        }

        let mut command = hidden_command(executable);
        command
            .env("QWEN_ENGINE_PORT", ENGINE_PORT)
            .stdout(Stdio::null())
            .stderr(Stdio::null());

        return command.spawn().map_err(|error| error.to_string());
    }
}

#[tauri::command]
fn detect_hardware() -> HardwareInfo {
    detect_hardware_value()
}

#[tauri::command]
fn engine_status(
    app: AppHandle,
    process: State<EngineProcess>,
) -> Result<EngineStatus, String> {
    engine_status_value(&app, process.inner())
}

#[tauri::command]
fn engine_catalog(
    app: AppHandle,
    process: State<EngineProcess>,
) -> Result<EngineCatalog, String> {
    let manifest = load_manifest()?;
    let hardware = detect_hardware_value();
    let status = engine_status_value(&app, process.inner())?;

    let preferred = if hardware.recommended_flavor == "nvidia"
        && manifest.engines.iter().any(|item| item.flavor == "nvidia")
    {
        "nvidia"
    } else if manifest.engines.iter().any(|item| item.flavor == "cpu") {
        "cpu"
    } else {
        manifest
            .engines
            .first()
            .map(|item| item.flavor.as_str())
            .unwrap_or("cpu")
    };

    Ok(EngineCatalog {
        manifest,
        hardware,
        status,
        recommended_flavor: preferred.into(),
    })
}

#[tauri::command]
async fn install_engine(
    app: AppHandle,
    flavor: String,
    install_state: State<'_, EngineInstallState>,
) -> Result<EngineStatus, String> {
    {
        let mut running = install_state
            .running
            .lock()
            .map_err(|_| "No se pudo bloquear el instalador del motor.".to_string())?;
        if *running {
            return Err("Ya hay una instalación del motor en curso.".into());
        }
        *running = true;
    }

    install_state.cancel.store(false, Ordering::Relaxed);
    let cancel = install_state.cancel.clone();
    let app_for_task = app.clone();

    let result = tauri::async_runtime::spawn_blocking(move || {
        install_engine_blocking(app_for_task, flavor, cancel)
    })
    .await
    .map_err(|error| format!("El instalador interno se interrumpió: {error}"))
    .and_then(|value| value);

    if let Ok(mut running) = install_state.running.lock() {
        *running = false;
    }

    result
}

#[tauri::command]
fn cancel_engine_install(install_state: State<EngineInstallState>) {
    install_state.cancel.store(true, Ordering::Relaxed);
}

#[tauri::command]
fn start_engine(
    app: AppHandle,
    state: State<EngineProcess>,
) -> Result<String, String> {
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "No se pudo bloquear el estado.".to_string())?;

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

fn take_engine_child(state: &EngineProcess) -> Result<Option<Child>, String> {
    let mut guard = state
        .0
        .lock()
        .map_err(|_| "No se pudo bloquear el estado del motor.".to_string())?;

    Ok(guard.take())
}

fn terminate_engine(state: &EngineProcess) -> Result<(), String> {
    if let Some(mut child) = take_engine_child(state)? {
        let _ = child.kill();
        let _ = child.wait();
    }
    Ok(())
}

#[tauri::command]
fn stop_engine(state: State<EngineProcess>) -> Result<(), String> {
    terminate_engine(state.inner())
}

#[tauri::command]
fn uninstall_engine(
    app: AppHandle,
    process: State<EngineProcess>,
) -> Result<(), String> {
    terminate_engine(process.inner())?;

    #[cfg(not(debug_assertions))]
    {
        let runtime = runtime_dir(&app)?;
        if runtime.exists() {
            fs::remove_dir_all(runtime).map_err(|error| error.to_string())?;
        }
    }

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(EngineProcess(Mutex::new(None)))
        .manage(EngineInstallState::default())
        .invoke_handler(tauri::generate_handler![
            detect_hardware,
            engine_status,
            engine_catalog,
            install_engine,
            cancel_engine_install,
            start_engine,
            stop_engine,
            uninstall_engine
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state = window.state::<EngineProcess>();

                if let Err(error) = terminate_engine(state.inner()) {
                    eprintln!("No se pudo cerrar el motor local: {error}");
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Voice Studio AI");
}
