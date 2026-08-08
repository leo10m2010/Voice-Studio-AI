# QA — stale tag / stale commit v0.6.11

El error reportado seguía mostrando este código:

```rust
let state = window.state::<EngineProcess>();
if let Ok(mut guard) = state.0.lock() {
```

Ese código **no existe** en la fuente corregida.

La fuente v0.6.11 contiene:

```rust
let state = window.state::<EngineProcess>();

if let Err(error) = terminate_engine(state.inner()) {
    eprintln!("No se pudo cerrar el motor local: {error}");
}
```

Por tanto, si GitHub muestra otra vez `if let Ok(mut guard)`, está compilando
un tag/commit anterior.

## Protección añadida

Ambos workflows ahora:

1. imprimen `git rev-parse HEAD`;
2. imprimen el último commit;
3. inspeccionan `src-tauri/src/lib.rs`;
4. buscan explícitamente el patrón viejo;
5. abortan inmediatamente si lo encuentran;
6. exigen `terminate_engine(state.inner())`;
7. luego ejecutan `cargo check`.

## Antes de taggear

Ejecuta:

```powershell
npm run release:pretag
```

Solo si pasa:

```powershell
git tag v0.6.11
git push origin v0.6.11
```

Nunca reutilices un tag antiguo para una nueva compilación.
