from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.request


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
    parser = argparse.ArgumentParser(description="Download the pinned Qwen GGUF and verify it")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "models" / config["filename"],
    )
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.exists():
        if output.stat().st_size == config["size_bytes"] and sha256(output) == config["sha256"]:
            print(f"Verified existing model: {output}")
            return
        raise SystemExit(f"Existing file does not match the pinned artifact: {output}")

    partial = output.with_suffix(output.suffix + ".part")
    downloaded = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "disease-diagnosis-learning-mvp/0.1"}
    if downloaded:
        headers["Range"] = f"bytes={downloaded}-"
    request = urllib.request.Request(config["download_url"], headers=headers)

    print(f"Downloading pinned {config['quantization']} artifact to {partial}")
    with urllib.request.urlopen(request, timeout=60) as response:
        append = downloaded > 0 and response.status == 206
        mode = "ab" if append else "wb"
        if not append:
            downloaded = 0
        with partial.open(mode) as stream:
            while block := response.read(8 * 1024 * 1024):
                stream.write(block)
                downloaded += len(block)
                percent = downloaded * 100 / config["size_bytes"]
                print(f"\r{downloaded / 1_000_000_000:.2f} GB ({percent:.1f}%)", end="", flush=True)
    print()

    if partial.stat().st_size != config["size_bytes"]:
        raise SystemExit(
            f"Size mismatch: got {partial.stat().st_size}, expected {config['size_bytes']}. "
            "The partial file was kept for resume."
        )
    actual_hash = sha256(partial)
    if actual_hash != config["sha256"]:
        raise SystemExit(
            f"SHA-256 mismatch: got {actual_hash}, expected {config['sha256']}. "
            "The untrusted partial file was not activated."
        )
    partial.replace(output)
    print(f"Verified model: {output}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDownload interrupted; the partial file can be resumed.", file=sys.stderr)
        raise SystemExit(130)

