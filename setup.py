"""
setup.py -one-time workspace initialiser for S8-Assignment.

What it does:
  1. Creates workspace/ by copying S8SharedCode/code and S8SharedCode/gateway.
  2. Applies patches from patches/ (coder.md, table_extractor.md, agent_config.yaml).
  3. Copies .env to workspace/.env.
  4. Creates required empty directories (state/, sandbox/papers/).
  5. Installs Python dependencies via uv (if available) or pip.

Run once before start.bat.  Safe to re-run -skips steps already done.
"""
from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Force UTF-8 output on Windows to avoid cp1252 encode errors
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HERE = Path(__file__).parent.resolve()
# Locate S8SharedCode relative to this file
_CANDIDATES = [
    HERE.parent / "Session 8" / "S8SharedCode",
    HERE.parent / "S8SharedCode",
]
S8 = next((p for p in _CANDIDATES if p.exists()), None)

WORKSPACE = HERE / "workspace"
GATEWAY_DIR = WORKSPACE / "gateway"
CODE_DIR = WORKSPACE / "code"
PATCHES_DIR = HERE / "patches"
ENV_FILE = HERE / ".env"


def _info(msg: str) -> None:
    print(f"  [setup] {msg}")


def _check_s8():
    if S8 is None:
        print("ERROR: Cannot locate S8SharedCode.")
        print("  Looked in:")
        for c in _CANDIDATES:
            print(f"    {c}")
        print("  Set S8_ROOT env var to its path and re-run.")
        sys.exit(1)
    _info(f"S8SharedCode found at {S8}")


def _copy_dir(src: Path, dst: Path, label: str) -> None:
    if dst.exists():
        _info(f"{label}: already exists -skipping copy")
        return
    _info(f"Copying {src.name} ->{dst} ...")
    shutil.copytree(str(src), str(dst), dirs_exist_ok=False,
                    ignore=shutil.ignore_patterns(".DS_Store", "__pycache__", "*.pyc"))
    _info(f"{label}: done")


def _apply_patches() -> None:
    _info("Applying patches ...")
    for src in PATCHES_DIR.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(PATCHES_DIR)
        dst = CODE_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        _info(f"  patched: {rel}")


def _copy_env() -> None:
    dst = WORKSPACE / ".env"
    if dst.exists():
        _info(".env already in workspace -skipping")
        return
    if ENV_FILE.exists():
        shutil.copy2(str(ENV_FILE), str(dst))
        _info(f"Copied .env ->{dst}")
    else:
        _info("WARNING: .env not found -gateway will start without keys")


def _ensure_dirs() -> None:
    for d in [
        CODE_DIR / "state" / "sessions",
        CODE_DIR / "logs",
        WORKSPACE / "logs",
    ]:
        d.mkdir(parents=True, exist_ok=True)
    _info("Runtime directories ensured")


def _install_deps() -> None:
    for subdir in [GATEWAY_DIR, CODE_DIR]:
        pyproject = subdir / "pyproject.toml"
        if not pyproject.exists():
            continue
        _info(f"Installing deps in {subdir.name}/ ...")
        # Try uv first; fall back to pip
        uv = shutil.which("uv")
        if uv:
            r = subprocess.run([uv, "sync"], cwd=str(subdir), capture_output=False)
        else:
            req = subdir / "requirements.txt"
            if req.exists():
                r = subprocess.run(
                    [sys.executable, "-m", "pip", "install", "-r", str(req), "-q"],
                    cwd=str(subdir),
                )
            else:
                _info(f"  no requirements.txt; skipping pip install for {subdir.name}")
                continue
        if r.returncode != 0:
            _info(f"  WARNING: dep install exited {r.returncode} -check manually")
        else:
            _info(f"  {subdir.name}: deps installed")


def main() -> None:
    print("\n" + "=" * 60)
    print("  S8-Assignment  setup")
    print("=" * 60)
    _check_s8()
    WORKSPACE.mkdir(exist_ok=True)
    _copy_dir(S8 / "gateway", GATEWAY_DIR, "gateway")
    _copy_dir(S8 / "code", CODE_DIR, "code")
    _apply_patches()
    _copy_env()
    _ensure_dirs()
    _install_deps()
    print("\n" + "=" * 60)
    print("  Setup complete.  Run: start.bat")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
