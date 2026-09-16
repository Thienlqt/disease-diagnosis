from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "model_runtime.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    defaults = config["server"]
    parser = argparse.ArgumentParser(description="Start the pinned Qwen model with llama.cpp")
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "models" / config["filename"],
    )
    parser.add_argument("--host", default=defaults["host"])
    parser.add_argument("--port", type=int, default=defaults["port"])
    parser.add_argument("--ctx-size", type=int, default=defaults["context_size"])
    args = parser.parse_args()

    binary = shutil.which("llama-server")
    if not binary:
        raise SystemExit("llama-server was not found on PATH. Install llama.cpp first.")
    model = args.model.resolve()
    if not model.exists():
        raise SystemExit(f"Model not found: {model}\nRun: python3 scripts/download_qwen.py")
    if model.stat().st_size != config["size_bytes"] or sha256(model) != config["sha256"]:
        raise SystemExit("The model file does not match the pinned size and SHA-256; refusing to load it.")

    key_file = ROOT / "models" / ".llama_api_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        key_file.chmod(0o600)
    api_key = key_file.read_text(encoding="utf-8").strip()

    command = [
        binary,
        "--model",
        str(model),
        "--alias",
        defaults["model_alias"],
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--ctx-size",
        str(args.ctx_size),
        "--parallel",
        str(defaults["parallel_slots"]),
        "--jinja",
        "--no-webui",
        "--metrics",
        "--api-key",
        api_key,
    ]
    print("Starting local llama.cpp server with the verified Qwen artifact...")
    os.execv(binary, command)


if __name__ == "__main__":
    main()
