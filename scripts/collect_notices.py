"""Preserve installed runtime license texts alongside distributable binaries."""

from __future__ import annotations

import importlib.metadata as metadata
import json
import re
import shutil
from pathlib import Path

destination = Path("dist/third-party-licenses")
destination.mkdir(parents=True, exist_ok=True)
items = []
for requirement in Path("requirements.lock").read_text("utf-8").splitlines():
    if "==" not in requirement or requirement.startswith("#"):
        continue
    name = requirement.split("==")[0]
    try:
        distribution = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        continue  # e.g. Windows-only dependencies on a Linux host
    slug = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    found = []
    for file in distribution.files or []:
        if any(word in file.name.upper() for word in ("LICENSE", "COPYING", "NOTICE")):
            source = Path(distribution.locate_file(file))
            if source.is_file():
                target = destination / slug / str(file).replace("..", "_")
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                found.append(str(file))
    items.append(
        {
            "name": name,
            "version": distribution.version,
            "license_files": found,
            "project_urls": distribution.metadata.get_all("Project-URL") or [],
        }
    )
(destination / "versions.json").write_text(json.dumps(items, indent=2), "utf-8")
shutil.copy2("THIRD_PARTY_NOTICES.md", destination / "THIRD_PARTY_NOTICES.md")
(destination / "rebuild.txt").write_text(
    "Source and build scripts: https://github.com/AureliusWu/SiLing\n"
    "python-soxr source: https://github.com/dofuuz/python-soxr\n"
    "libsoxr source: https://sourceforge.net/projects/soxr/\n"
    "The unmodified LGPL modules are dynamically loaded. To replace them, use the\n"
    "published SiLing source, install a compatible modified python-soxr wheel,\n"
    "and run scripts/package_windows.py followed by npm run tauri -- build.\n"
    "No application source changes are required to rebuild against a compatible\n"
    "replacement. LGPL rights, including reverse engineering for debugging such\n"
    "modifications, are not restricted by this project.\n",
    "utf-8",
)
