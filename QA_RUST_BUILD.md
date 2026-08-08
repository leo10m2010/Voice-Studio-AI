# QA — Rust/Tauri build v0.6.10

## Error corregido

```text
error[E0597]: `state` does not live long enough
src/lib.rs:121
```

La causa era un `MutexGuard` temporal creado dentro de `on_window_event`.
Rust podía mantener vivo el temporal del `Result<MutexGuard<...>>` hasta el
final del bloque, mientras el `State` local ya estaba siendo destruido.

## Cambio

Antes:

```rust
let state = window.state::<EngineProcess>();
if let Ok(mut guard) = state.0.lock() {
    if let Some(child) = guard.as_mut() {
        let _ = child.kill();
        let _ = child.wait();
    }
    *guard = None;
}
```

Ahora:

```rust
fn take_engine_child(state: &EngineProcess) -> Result<Option<Child>, String> {
    let mut guard = state.0.lock().map_err(...)?;
    Ok(guard.take())
}

fn terminate_engine(state: &EngineProcess) -> Result<(), String> {
    if let Some(mut child) = take_engine_child(state)? {
        let _ = child.kill();
        let _ = child.wait();
    }
    Ok(())
}
```

Y el evento llama:

```rust
let state = window.state::<EngineProcess>();
terminate_engine(state.inner())
```

Ventajas:
- el `MutexGuard` se destruye dentro de `take_engine_child`;
- el lock ya está liberado antes de `kill()` / `wait()`;
- no existe el temporal que provocaba E0597;
- `stop_engine` y el cierre de ventana usan la misma ruta.

## GitHub Actions

Ahora ambos workflows ejecutan:

```powershell
cargo check --manifest-path .\src-tauri\Cargo.toml
```

El workflow de Release lo ejecuta **antes** de instalar/empaquetar PyTorch,
para detectar errores Rust rápidamente.
