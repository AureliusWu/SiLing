from __future__ import annotations

import hashlib
import json
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


def manifest() -> dict[str, Any]:
    return json.loads(Path(__file__).with_name("models.lock.json").read_text("utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def paths(root: Path) -> dict[str, Path]:
    assets = manifest()["assets"]
    kws = root / assets["kws"]["directory"]
    asr = root / assets["asr"]["directory"]
    return {
        "encoder": kws / "encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
        "decoder": kws / "decoder-epoch-13-avg-2-chunk-16-left-64.onnx",
        "joiner": kws / "joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx",
        "kws_tokens": kws / "tokens.txt",
        "asr": asr / "model.int8.onnx",
        "asr_tokens": asr / "tokens.txt",
        "vad": root / "silero_vad.onnx",
    }


def safe_extract(archive: Path, target: Path, expected_root: str) -> None:
    """Extract only ordinary model files, never links, devices or escaping paths."""
    with tarfile.open(archive, "r:bz2") as bundle:
        members = bundle.getmembers()
        total = 0
        for member in members:
            relative = Path(member.name)
            if (
                relative.is_absolute()
                or ".." in relative.parts
                or "\\" in member.name
                or not relative.parts
                or relative.parts[0] != expected_root
            ):
                raise ValueError("unsafe archive path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("non-regular archive member")
            total += member.size
            if total > 1_500_000_000:
                raise ValueError("model archive expands beyond size limit")
        for member in members:
            destination = target / member.name
            if member.isdir():
                destination.mkdir(parents=True, exist_ok=True)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                source = bundle.extractfile(member)
                if source is None:
                    raise ValueError("missing archive member")
                with source, destination.open("wb") as output:
                    shutil.copyfileobj(source, output)


def check_asset(path: Path, asset: dict[str, Any]) -> None:
    if path.stat().st_size != asset["bytes"] or sha256(path) != asset["sha256"]:
        raise ValueError(f"checksum mismatch: {asset['filename']}")


def install(root: Path, source: Path | None = None) -> dict[str, Any]:
    """Explicit provisioning only. Audio/inference never calls this function."""
    root.mkdir(parents=True, exist_ok=True)
    assets = manifest()["assets"]
    cache = root / ".downloads"
    cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".install-", dir=root) as work:
        staging = Path(work)
        for asset in assets.values():
            archive = (source or cache) / asset["filename"]
            if source is None and not archive.exists():
                partial = archive.with_suffix(".part")
                try:
                    request = urllib.request.Request(
                        asset["url"], headers={"User-Agent": "SiLing/0.1"}
                    )
                    with (
                        urllib.request.urlopen(request, timeout=60) as response,
                        partial.open("wb") as out,
                    ):
                        downloaded = 0
                        while chunk := response.read(1024 * 1024):
                            downloaded += len(chunk)
                            if downloaded > asset["bytes"]:
                                raise ValueError("download exceeds pinned size")
                            out.write(chunk)
                    check_asset(partial, asset)
                    partial.replace(archive)
                finally:
                    partial.unlink(missing_ok=True)
            check_asset(archive, asset)
            if "directory" in asset:
                safe_extract(archive, staging, asset["directory"])
            else:
                shutil.copy2(archive, staging / asset["filename"])
        file_hashes = {str(p.relative_to(staging)): sha256(p) for p in paths(staging).values()}
        receipt = {
            "schema": 1,
            "assets": {k: v["sha256"] for k, v in assets.items()},
            "files": file_hashes,
        }
        # An interrupted install has no valid receipt and cannot start inference.
        (root / "installed.json").unlink(missing_ok=True)
        for child in staging.iterdir():
            destination = root / child.name
            if destination.is_dir():
                shutil.rmtree(destination)
            elif destination.exists():
                destination.unlink()
            shutil.move(str(child), destination)
        (root / "installed.json").write_text(json.dumps(receipt, indent=2), "utf-8")
    return receipt


def verify_installed(root: Path) -> None:
    try:
        receipt = json.loads((root / "installed.json").read_text("utf-8"))
        expected = {k: v["sha256"] for k, v in manifest()["assets"].items()}
        if receipt["assets"] != expected:
            raise ValueError("model receipt does not match pinned assets")
        for path in paths(root).values():
            if sha256(path) != receipt["files"][str(path.relative_to(root))]:
                raise ValueError("installed model checksum mismatch")
    except (OSError, KeyError, json.JSONDecodeError) as error:
        raise ValueError("MODELS_MISSING: run siling-voice models download") from error
