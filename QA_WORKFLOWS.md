# QA GitHub Actions v0.6.12

Problema de v0.6.11:
- bloques PowerShell con lineas sin sangria dentro de `run: |`;
- `Comprobar referencia de ejecucion` quedo fuera de `jobs.*.steps`;
- GitHub no podia registrar correctamente los workflows.

Sintoma:
- Actions mostraba `.github/workflows/validate.yml` en vez del nombre;
- no aparecia el workflow de Release.

v0.6.12:
- validate.yml reescrito;
- release-windows.yml reescrito;
- sin here-string PowerShell multilinea;
- todos los steps tienen 6 espacios de sangria;
- ambos archivos pasan parsing YAML local;
- Release conserva `workflow_dispatch` y trigger por tag `v*`;
- tauri-action publica NSIS en GitHub Release;
- el Release se verifica al final con `gh release view`.
