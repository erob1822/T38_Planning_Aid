"""
build_exe.py - Build T38_PlanAid executable

Run this script to create a standalone .exe file.
Requires: pip install pyinstaller
"""

import subprocess
import sys
import shutil
from pathlib import Path

def main():
    # Get the directory where this script is located
    script_dir = Path(__file__).parent.resolve()
    
    # Check if PyInstaller is installed
    try:
        import PyInstaller
    except ImportError:
        print("Installing PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    # Clean previous builds
    for folder in ['build', 'dist', 'T38 PlanAid Distribution']:
        folder_path = script_dir / folder
        if folder_path.exists():
            shutil.rmtree(folder_path)
    
    spec_file = script_dir / 'T38_PlanAid.spec'
    if spec_file.exists():
        spec_file.unlink()
    
    # Build command
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
        "--collect-all", "fitz",        # Collect all PyMuPDF files
        "T38_PlanAid_E.py"              # Entry point
    ]
    
    print("Building executable...")
    print(f"Command: {' '.join(cmd)}")
    
    result = subprocess.run(cmd, cwd=Path(__file__).parent)
    
    if result.returncode == 0:
        distribution_folder = Path("T38 PlanAid Distribution")
        exe_path = distribution_folder / "T38_PlanAid.exe"

        # Copy wb_list.xlsx to the distribution folder, so the exe is always accompanied by it.
        wb_list_src = Path("wb_list.xlsx")
        wb_list_dst = distribution_folder / "wb_list.xlsx"
        if wb_list_src.exists():
            shutil.copy2(wb_list_src, wb_list_dst)
            print(f"Copied wb_list.xlsx to distribution folder")
        else:
            print(f"Warning: wb_list.xlsx not found in source directory")
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
