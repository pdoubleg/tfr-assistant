"""Download local MiniLM ONNX artifacts for dataset clustering.

This intentionally avoids PyTorch, Transformers, sentence-transformers, and HF
pipelines. It uses stdlib HTTP downloads from Hugging Face's resolved file URLs
and records SHA256 checksums in the target directory. Later runs verify existing
checksums before accepting the model files.

Run from ``backend``:

    uv run python scripts/download_minilm_onnx.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from urllib.request import urlopen

REPO = "Xenova/all-MiniLM-L6-v2"
REVISION = "cb3d680149bf9a3209564e1b27ab3bb355b65707"
DEFAULT_TARGET = Path("data/models/all-MiniLM-L6-v2")
FILES = [
    "onnx/model_quantized.onnx",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "config.json",
    "vocab.txt",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--revision", default=REVISION)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    args.target.mkdir(parents=True, exist_ok=True)
    manifest_path = args.target / "checksums.sha256.json"
    manifest = _read_manifest(manifest_path)

    for relative_path in FILES:
        destination = args.target / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() and not args.force:
            digest = _sha256(destination)
            expected = manifest.get(relative_path)
            if expected and expected != digest:
                raise SystemExit(
                    f"Checksum mismatch for {destination}: expected {expected}, got {digest}"
                )
            if expected:
                print(f"verified {relative_path} {digest}")
                continue

        url = _resolve_url(relative_path, args.revision)
        print(f"downloading {url}")
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            with urlopen(url) as response:  # noqa: S310 - explicit developer download script
                while chunk := response.read(1024 * 1024):
                    tmp_file.write(chunk)
        digest = _sha256(tmp_path)
        tmp_path.replace(destination)
        manifest[relative_path] = digest
        print(f"saved {relative_path} {digest}")

    manifest["repo"] = REPO
    manifest["revision"] = args.revision
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(f"wrote {manifest_path}")
    return 0


def _resolve_url(relative_path: str, revision: str) -> str:
    return f"https://huggingface.co/{REPO}/resolve/{revision}/{relative_path}"


def _read_manifest(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {key: value for key, value in payload.items() if isinstance(value, str)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    sys.exit(main())
