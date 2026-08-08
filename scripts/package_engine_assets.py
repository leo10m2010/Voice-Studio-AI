from __future__ import annotations
import argparse, hashlib, json, os, zipfile
from pathlib import Path
from datetime import datetime, timezone

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def groups(files, max_raw):
    current, size = [], 0
    for p, rel, n in files:
        if current and size + n > max_raw:
            yield current
            current, size = [], 0
        current.append((p, rel, n))
        size += n
    if current:
        yield current

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine-dir", required=True)
    ap.add_argument("--flavor", choices=["cpu", "nvidia"], required=True)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--max-raw-mb", type=int, default=700)
    args = ap.parse_args()

    engine = Path(args.engine_dir).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    exe = engine / "qwen-engine.exe"
    if not exe.exists():
        raise SystemExit(f"No existe {exe}")

    files = []
    total_installed = 0
    for p in engine.rglob("*"):
        if p.is_file():
            rel = p.relative_to(engine).as_posix()
            n = p.stat().st_size
            files.append((p, rel, n))
            total_installed += n

    # Largest files first avoids creating a final oversized archive by accident.
    files.sort(key=lambda x: x[2], reverse=True)
    max_raw = args.max_raw_mb * 1024 * 1024
    parts = []

    for index, group in enumerate(groups(files, max_raw), 1):
        name = f"voice-engine-{args.flavor}-v{args.version}-part{index:02d}.zip"
        path = out / name
        print(f"Creando {name}...")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
            for source, rel, _ in group:
                z.write(source, rel)
        size = path.stat().st_size
        parts.append({
            "name": name,
            "url": args.base_url.rstrip("/") + "/" + name,
            "sha256": sha256(path),
            "bytes": size
        })

    package = {
        "flavor": args.flavor,
        "label": "Motor NVIDIA" if args.flavor == "nvidia" else "Motor CPU",
        "version": args.version,
        "download_bytes": sum(x["bytes"] for x in parts),
        "installed_bytes": total_installed,
        "description": (
            "Aceleración CUDA para equipos con GPU NVIDIA compatible."
            if args.flavor == "nvidia"
            else "Máxima compatibilidad; funciona sin una GPU NVIDIA."
        ),
        "parts": parts
    }

    fragment = out / f"engine-{args.flavor}.json"
    fragment.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_path = out / "engine-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema": 1,
            "version": args.version,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "engines": []
        }
    manifest["version"] = args.version
    manifest["published_at"] = datetime.now(timezone.utc).isoformat()
    manifest["engines"] = [x for x in manifest.get("engines", []) if x.get("flavor") != args.flavor]
    manifest["engines"].append(package)
    manifest["engines"].sort(key=lambda x: x["flavor"])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("Paquete:", args.flavor)
    print("Partes:", len(parts))
    print("Descarga:", round(package["download_bytes"] / 1024**3, 2), "GB")
    print("Instalado:", round(total_installed / 1024**3, 2), "GB")
    print("Manifest:", manifest_path)

if __name__ == "__main__":
    main()
