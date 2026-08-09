# Voice Studio AI v0.7.0 — Engine Manager

## Arquitectura

El instalador de la aplicación ya no contiene Python, PyTorch ni qwen-tts.

`Setup.exe`
→ instala Tauri/WebView2
→ primer inicio
→ Engine Manager
→ detecta CPU/NVIDIA
→ descarga partes del motor
→ reanuda descargas parciales
→ SHA-256 por parte
→ extracción a staging
→ `qwen-engine.exe --self-test-packaging`
→ activación atómica del runtime
→ inicia API local en 127.0.0.1:8765

## Sin terminal

En Release, Rust ejecuta `nvidia-smi`, el self-test y `qwen-engine.exe`
con `CREATE_NO_WINDOW`. No se abre PowerShell/CMD al usuario.

## Ubicación del motor

Tauri usa su `app_local_data_dir` y crea:

`engine/runtime/`
`engine/downloads/<version>/<flavor>/`

El runtime es privado de Voice Studio AI.

Los datos históricos del motor Python siguen en la carpeta de datos de la
aplicación y NO se borran al reparar/desinstalar el engine.

## Catálogo remoto

La app consulta:

https://github.com/leo10m2010/Voice-Studio-AI/releases/download/engine-v1.0.2/engine-manifest.json

Puede sobrescribirse en desarrollo con:

`VOICE_STUDIO_ENGINE_MANIFEST=C:\ruta\engine-manifest.json`

## Publicar motores

### Opción GitHub Actions

Actions → `03 - Publicar motores CPU y NVIDIA`

Ese workflow:
1. crea/usa Release `engine-v1.0.2`;
2. construye CPU y NVIDIA por separado;
3. divide cada runtime en ZIPs pequeños;
4. sube las partes;
5. crea y sube `engine-manifest.json`.

### Opción local

NVIDIA:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-engine-release.ps1 -Flavor nvidia
```

CPU:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-engine-release.ps1 -Flavor cpu
```

Los assets quedan en `engine-release`.

## Instalador de la aplicación

```powershell
npm run build:windows
```

Ya no ejecuta PyInstaller. Solo compila frontend + Rust + NSIS.

## UX

Primer inicio:
- detección de hardware;
- recomendación automática (NVIDIA cuando hay VRAM suficiente; CPU cuando conviene evitar un runtime CUDA pesado);
- selección CPU/NVIDIA;
- tamaño de descarga;
- progreso real;
- bytes descargados;
- etapas Descargar → Verificar → Instalar → Comprobar;
- cancelar con descarga parcial conservada;
- reparar/actualizar;
- desinstalar motor sin borrar voces/modelos/historial.
