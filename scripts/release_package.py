"""Prepare one traceable Windows candidate with installer, portable app and evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path

version = json.loads(Path("package.json").read_text("utf-8"))["version"]
root = Path("dist/candidate")
shutil.rmtree(root, ignore_errors=True)
root.mkdir(parents=True)
shutil.copy2("dist/SiLing-Voice.exe", root)
shutil.copy2("apps/desktop/src-tauri/target/release/SiLing.exe", root)
for name in ("README.md", "LICENSE", "THIRD_PARTY_NOTICES.md", "CHANGELOG.md"):
    shutil.copy2(name, root)
shutil.copytree("docs", root / "docs")
shutil.copytree("dist/third-party-licenses", root / "third-party-licenses")
(root / "installer").mkdir()
for file in Path("apps/desktop/src-tauri/target/release/bundle/nsis").glob("*-setup.exe"):
    shutil.copy2(file, root / "installer")
(root / "reports").mkdir()
for file in Path(".evidence").glob("*.json"):
    if file.name.startswith(("frozen-", "native-", "windows-")):
        shutil.copy2(file, root / "reports")
shutil.copy2("apps/desktop/src-tauri/Cargo.lock", root / "reports")
(root / "samples").mkdir()
for name in ("positive-3.wav", "positive-58.wav", "provenance.json"):
    shutil.copy2(Path("fixtures") / name, root / "samples")
for filename, operation in (
    ("Install-Voice-Models.cmd", "models"),
    ("Install-Chinese-TTS.cmd", "tts"),
):
    (root / filename).write_bytes(
        (
            '@echo off\r\n"%~dp0SiLing-Voice.exe" ' + operation + " download\r\n"
            "if errorlevel 1 (echo Download failed. & pause & exit /b 1)\r\necho Done.\r\npause\r\n"
        ).encode()
    )
(root / "build-info.json").write_text(
    json.dumps(
        {
            "version": version,
            "commit": os.environ["GITHUB_SHA"],
            "built_at_utc": datetime.now(UTC).isoformat(),
            "hardware_acceptance": "NOT_VERIFIED",
            "models_bundled": False,
            "signed": False,
        },
        indent=2,
    ),
    "utf-8",
)
checksums = []
for file in sorted(root.rglob("*")):
    if file.is_file():
        with file.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        checksums.append(f"{digest}  {file.relative_to(root).as_posix()}")
(root / "SHA256SUMS.txt").write_text("\n".join(checksums) + "\n", "utf-8")
output = Path(f"dist/SiLing-{version}-windows-x64.zip")
with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for file in sorted(root.rglob("*")):
        if file.is_file():
            archive.write(file, file.relative_to(root).as_posix())
asset_sums = []
for asset in [output, *sorted((root / "installer").glob("*-setup.exe"))]:
    with asset.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    asset_sums.append(f"{digest}  {asset.name}")
Path("dist/SHA256SUMS.txt").write_text("\n".join(asset_sums) + "\n", "utf-8")
print(f"Candidate prepared: {output.name}, {output.stat().st_size} bytes")
