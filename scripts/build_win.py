"""
Build Windows .exe for DBVisualizer.

Usage:
    uv run python scripts/build_win.py

Output:
    dist/DBVisualizer/DBVisualizer.exe   (--onedir mode)
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "DBVisualizer"
ENTRY = ROOT / "dbvisualizer" / "__main__.py"
ICON = ROOT / "assets" / "icon.ico"  # optional, skipped if missing


def ensure_pyinstaller():
    """Add pyinstaller as dev dependency if not present."""
    result = subprocess.run(
        ["uv", "run", "python", "-c", "import PyInstaller"],
        cwd=str(ROOT), capture_output=True,
    )
    if result.returncode != 0:
        print("Installing pyinstaller as dev dependency...")
        subprocess.run(["uv", "add", "--dev", "pyinstaller"], cwd=str(ROOT), check=True)


def build():
    ensure_pyinstaller()

    cmd = [
        "uv", "run", "python", "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        # Gradio frontend assets
        "--collect-all", "gradio",
        "--collect-all", "gradio_client",
        "--collect-all", "safehttpx",
        "--collect-all", "groovy",
        # Matplotlib backends & data
        "--collect-all", "matplotlib",
        # Hidden imports that PyInstaller may miss
        "--hidden-import", "natsort",
        "--hidden-import", "seaborn",
        "--hidden-import", "dbvisualizer",
        "--hidden-import", "dbvisualizer.data",
        "--hidden-import", "dbvisualizer.plot",
        "--hidden-import", "dbvisualizer.ui",
        # Output settings
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
    ]

    if ICON.exists():
        cmd += ["--icon", str(ICON)]

    cmd.append(str(ENTRY))

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode == 0:
        exe = ROOT / "dist" / APP_NAME / f"{APP_NAME}.exe"
        print(f"\nBuild succeeded: {exe}")
        print(f"Run with:  .\\dist\\{APP_NAME}\\{APP_NAME}.exe [your.db]")
    else:
        print("\nBuild failed.", file=sys.stderr)
        sys.exit(result.returncode)


if __name__ == "__main__":
    build()
