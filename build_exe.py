"""
build_exe.py - Build script for T38_PlanAid executable

This script automates the creation of a standalone Windows executable for the T-38 PlanAid application using PyInstaller.

Features:
- Installs PyInstaller if not present.
- Cleans previous build artifacts and distribution folders.
- Builds a single-file executable from T38_PlanAid.py, including all required hidden imports.
- Copies wb_list.xlsx and the DATA folder to the distribution folder to ensure the executable is packaged with cached data.

Usage:
    python build_exe.py

Requirements:
    pip install pyinstaller
    (All dependencies listed in requirements.txt should be installed in your environment.)
"""

import subprocess
import sys
import shutil
from pathlib import Path

def main():

    # Get the directory where this script is located
    script_dir = Path(__file__).parent.resolve()


    # Ensure all required packages are installed (requirements.txt and pip itself)
    requirements_file = script_dir / 'requirements.txt'
    print("Ensuring pip is up to date...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    if requirements_file.exists():
        print("Installing required packages from requirements.txt...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(requirements_file)])
    else:
        print("Warning: requirements.txt not found. Skipping requirements installation.")

    # Try to import each dependency and install if missing
    import importlib
    with open(requirements_file) as reqf:
        for line in reqf:
            pkg = line.strip()
            if not pkg or pkg.startswith('#'):
                continue
            mod = pkg.split('==')[0].replace('-', '_')
            try:
                importlib.import_module(mod)
            except ImportError:
                print(f"Installing missing dependency: {pkg}")
                subprocess.check_call([sys.executable, "-m", "pip", "install", pkg])

    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Remove previous build and distribution folders for a clean build
    for folder in ['build', 'dist', 'T38 PlanAid Distribution']:
        folder_path = script_dir / folder
        if folder_path.exists():
            shutil.rmtree(folder_path)

    # Remove old spec file if present
    spec_file = script_dir / 'T38_PlanAid.spec'
    if spec_file.exists():
        spec_file.unlink()

    # Build the executable with all required hidden imports
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                    # Single .exe file
        "--name", "T38_PlanAid",        # Output name
        "--distpath", "T38 PlanAid Distribution",  # Output folder
        "--hidden-import=fitz",         # PyMuPDF
        "--hidden-import=pandas",
        "--hidden-import=openpyxl",
        "--hidden-import=simplekml",
        "--hidden-import=requests",
        "--hidden-import=requests_ntlm",
        "--hidden-import=spnego",
        "--hidden-import=sspilib",
        "--collect-all", "fitz",        # Collect all PyMuPDF files
        "--collect-all", "sspilib",     # Collect SSPI native bindings for NTLM auth
        "T38_PlanAid.py"              # Entry point
    ]

    print("Building executable...")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=Path(__file__).parent)

    if result.returncode == 0:
        # Always resolve paths relative to this script's directory
        script_dir = Path(__file__).resolve().parent
        distribution_folder = script_dir / "T38 PlanAid Distribution"
        exe_path = distribution_folder / "T38_PlanAid.exe"

        # Find wb_list.xlsx anywhere in the project (root or subfolders)
        wb_list_src = None
        for p in script_dir.rglob('wb_list.xlsx'):
            wb_list_src = p
            break
        wb_list_dst = distribution_folder / "wb_list.xlsx"
        if wb_list_src and wb_list_src.exists():
            shutil.copy2(wb_list_src, wb_list_dst)
            print(f"Copied wb_list.xlsx from {wb_list_src} to distribution folder")
        else:
            print(f"Warning: wb_list.xlsx not found in project directory tree.")

        # Copy the DATA folder to the distribution folder (cached data, apt_data, afd, etc.)
        data_src = script_dir / "DATA"
        data_dst = distribution_folder / "DATA"
        if data_src.exists() and data_src.is_dir():
            shutil.copytree(data_src, data_dst, dirs_exist_ok=True)
            print(f"Copied DATA folder to distribution folder")
        else:
            print(f"Warning: DATA folder not found in project directory.")

        print(f"\nBuild successful!")
        print(f"Executable: {exe_path.absolute()}")
        print(f"\nDistribution folder ready: {distribution_folder.absolute()}")
        print(f"Contents:")
        for item in distribution_folder.iterdir():
            print(f"  - {item.name}")
        print(f"  (KML_Output folder will be created on first run)")
    else:
        print(f"\nBuild failed with code {result.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    main()