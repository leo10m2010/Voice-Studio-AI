# GitHub Releases — Voice Studio AI

## Qué instala el setup.exe

El instalador final contiene:

- Voice Studio AI / Tauri;
- frontend;
- motor Python generado con PyInstaller;
- intérprete/runtime Python necesario por PyInstaller;
- qwen-tts;
- PyTorch;
- torchaudio;
- librosa;
- soundfile;
- FastAPI/Uvicorn;
- runtime CUDA incluido por la distribución CUDA de PyTorch;
- WebView2 bootstrapper de Tauri.

El usuario final NO necesita instalar:

- Python;
- pip;
- Node.js;
- npm;
- Rust;
- Cargo;
- Microsoft Build Tools;
- CUDA Toolkit;
- cuDNN por separado.

### Requisitos que siguen siendo externos

Para acelerar con NVIDIA:
- un driver NVIDIA suficientemente reciente/compatible.

Sin una GPU compatible, Voice Studio AI puede usar CPU.

Los pesos de los modelos NO se meten en el instalador.
Se descargan cuando el usuario elige por primera vez un modelo y quedan en caché.

## GitHub Actions

Hay dos workflows:

### `.github/workflows/validate.yml`

Se ejecuta en pushes y pull requests.

Comprueba:
- versiones;
- sintaxis JavaScript;
- sintaxis Python;
- build de Vite.

No instala PyTorch y por eso es relativamente rápido.

### `.github/workflows/release-windows.yml`

Se ejecuta al crear un tag `v*`, por ejemplo:

```powershell
git add .
git commit -m "Release v0.6.6"
git tag v0.6.6
git push origin main
git push origin v0.6.6
```

También se puede lanzar manualmente desde:
GitHub → Actions → Build and Release Windows → Run workflow.

El workflow:
1. instala Node/Python/Rust en el runner;
2. crea `.venv`;
3. instala PyTorch CUDA 12.6;
4. instala qwen-tts y dependencias;
5. empaqueta el motor con PyInstaller;
6. compila Tauri;
7. genera NSIS `setup.exe`;
8. crea/publica la GitHub Release;
9. sube el instalador como asset.

## Versiones

Antes de crear un tag, estas tres versiones tienen que coincidir:

- `package.json`
- `src-tauri/tauri.conf.json`
- `src-tauri/Cargo.toml`

Puedes comprobarlo localmente:

```powershell
npm run release:check
```

El workflow también lo verifica automáticamente.

## GitHub token

No necesitas crear manualmente un Personal Access Token para la release del mismo repositorio.

GitHub Actions proporciona `GITHUB_TOKEN` automáticamente.
El workflow solicita únicamente:

```yaml
permissions:
  contents: write
```

para poder crear la Release y subir assets.

## Límite importante

GitHub Releases exige que cada asset individual sea menor a 2 GiB.

Como el motor CUDA empaquetado puede ser grande, el workflow informa del tamaño del sidecar antes de compilar.

Si el setup final se acercara al límite, la siguiente optimización sería separar:
- runtime/engine;
- o usar un engine bootstrap instalado la primera vez.

Por ahora el diseño objetivo sigue siendo un único instalador + descarga posterior únicamente de modelos.
