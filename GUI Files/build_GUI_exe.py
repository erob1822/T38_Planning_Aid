"""
build_GUI_exe.py - Build script for T38_PlanAid_GUI executable

This script automates the creation of a standalone Windows executable for the T-38 PlanAid GUI application using PyInstaller.

Features:
- Installs PyInstaller if not present.
- Cleans previous build artifacts and distribution folders.
- Builds a single-file executable from T38_PlanAid_GUI.py, including all required hidden imports.
- Copies wb_list.xlsx and the DATA folder to the distribution folder to ensure the executable is packaged with cached data.
- Bundles RPLLogo.ico inside the exe so the GUI logo renders at runtime.
- Uses --windowed flag so no console window appears behind the GUI.

Usage:
    python build_GUI_exe.py

Requirements:
    pip install pyinstaller Pillow
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
    else:
        print("Warning: requirements.txt not found. Skipping requirements installation.")

    # Ensure Pillow is installed (needed for GUI logo rendering)
    try:
        import PIL
    except ImportError:
        print("Installing Pillow (for GUI logo)...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])

    # Ensure PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Remove previous build and distribution folders for a clean build
    for folder in ['build', 'dist', 'T38 PlanAid GUI Distribution', '__pycache__']:
        folder_path = script_dir / folder
        if folder_path.exists():
            shutil.rmtree(folder_path)

    # Remove old spec file if present
    for spec_name in ['T38_PlanAid_GUI.spec', 'T-38 Planning Aid GUI.spec']:
        spec_file = script_dir / spec_name
        if spec_file.exists():
            spec_file.unlink()

    # Build the executable with all required hidden imports
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                            # Single .exe file
        "--windowed",                           # No console window behind the GUI
        "--name", "T-38 Planning Aid GUI",      # Output name
        "--icon", "RPLLogo.ico",                # Application icon
        "--distpath", "T38 PlanAid GUI Distribution",  # Output folder
        "--hidden-import=fitz",                 # PyMuPDF
        "--hidden-import=pandas",
        "--hidden-import=openpyxl",
        "--hidden-import=simplekml",
        "--hidden-import=folium",
        "--hidden-import=requests",
        "--hidden-import=requests_ntlm",
        "--hidden-import=spnego",
        "--hidden-import=sspilib",
        "--hidden-import=PIL",
        "--hidden-import=PIL._tkinter_finder",
        "--collect-all", "fitz",                # Collect all PyMuPDF files
        "--collect-all", "sspilib",             # Collect SSPI native bindings for NTLM auth
        "--add-data", "wb_list.xlsx;.",          # Bundle wb_list.xlsx inside exe
        "--add-data", "RPLLogo.ico;.",           # Bundle RPL logo inside exe for GUI display
        "--add-data", "NASAT38s.png;.",          # Bundle T-38 banner image inside exe
        "T38_PlanAid_GUI.py"                    # Entry point
    ]

    print("Building GUI executable...")
    print(f"Command: {' '.join(cmd)}")

    result = subprocess.run(cmd, cwd=Path(__file__).parent)

    if result.returncode == 0:
        # Always resolve paths relative to this script's directory
        script_dir = Path(__file__).resolve().parent
        distribution_folder = script_dir / "T38 PlanAid GUI Distribution"
        exe_path = distribution_folder / "T-38 Planning Aid GUI.exe"
        work_folder = distribution_folder / "T38 Planning Aid"
        work_folder.mkdir(parents=True, exist_ok=True)

        # Find wb_list.xlsx anywhere in the project (root or subfolders)
        wb_list_src = None
        for p in script_dir.rglob('wb_list.xlsx'):
            wb_list_src = p
            break
        wb_list_dst = work_folder / "wb_list.xlsx"
        if wb_list_src and wb_list_src.exists():
            shutil.copy2(wb_list_src, wb_list_dst)
            print(f"Copied wb_list.xlsx from {wb_list_src} to T38 Planning Aid folder")
        else:
            print(f"Warning: wb_list.xlsx not found in project directory tree.")

        # Copy RPLLogo.ico alongside the exe so the GUI can find it at runtime
        logo_src = script_dir / "RPLLogo.ico"
        logo_dst = distribution_folder / "RPLLogo.ico"
        if logo_src.exists():
            shutil.copy2(logo_src, logo_dst)
            print(f"Copied RPLLogo.ico to distribution folder")

        # Copy NASAT38s.png alongside the exe for the T-38 banner
        banner_src = script_dir / "NASAT38s.png"
        banner_dst = distribution_folder / "NASAT38s.png"
        if banner_src.exists():
            shutil.copy2(banner_src, banner_dst)
            print(f"Copied NASAT38s.png to distribution folder")

        # Copy the DATA folder to the work folder (cached data, apt_data, afd, etc.)
        data_src = script_dir / "DATA"
        data_dst = work_folder / "DATA"
        if data_src.exists() and data_src.is_dir():
            shutil.copytree(data_src, data_dst, dirs_exist_ok=True)
            print(f"Copied DATA folder to T38 Planning Aid folder")
        else:
            print(f"Warning: DATA folder not found in project directory.")

        # Copy exe to the project root so it's visible when unzipping
        exe_root_copy = script_dir / "T-38 Planning Aid GUI.exe"
        if exe_path.exists():
            shutil.copy2(exe_path, exe_root_copy)
            print(f"Copied GUI exe to project root: {exe_root_copy.absolute()}")

        print(f"\nBuild successful!")
        print(f"Executable: {exe_path.absolute()}")
        print(f"\nDistribution folder ready: {distribution_folder.absolute()}")
        print(f"Contents:")
        for item in sorted(distribution_folder.rglob('*')):
            rel = item.relative_to(distribution_folder)
            print(f"  - {rel}")
        print(f"  (KML_Output folder will be created on first run inside 'T38 Planning Aid')")
    else:
        print(f"\nBuild failed with code {result.returncode}")
        sys.exit(1)

if __name__ == "__main__":
    main()
