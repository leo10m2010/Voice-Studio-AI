# QA Rust ownership fix v0.7.1

## Error

`E0505: cannot move out of manifest because it is borrowed`

`preferred` era un `&str`. En el fallback podía provenir de:

```rust
manifest.engines.first().map(|item| item.flavor.as_str())
```

Eso dejaba `manifest.engines` prestado. Después se intentaba mover `manifest`
completo a `EngineCatalog`, mientras el borrow seguía vivo para
`preferred.into()`.

## Fix

Ahora se crea un `String` propio antes de mover `manifest`:

```rust
let recommended_flavor = if hardware.recommended_flavor == "nvidia"
    && manifest.engines.iter().any(|item| item.flavor == "nvidia")
{
    "nvidia".to_string()
} else if manifest.engines.iter().any(|item| item.flavor == "cpu") {
    "cpu".to_string()
} else {
    manifest
        .engines
        .first()
        .map(|item| item.flavor.clone())
        .unwrap_or_else(|| "cpu".to_string())
};
```

Y después:

```rust
Ok(EngineCatalog {
    manifest,
    hardware,
    status,
    recommended_flavor,
})
```

No queda ningún borrow activo de `manifest` al moverlo.

Los parámetros `app` que solo se usan en builds `release` se marcaron como
`_app` para evitar warnings durante `cargo check` de debug.
