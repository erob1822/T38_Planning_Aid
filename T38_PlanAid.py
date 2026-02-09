"""
T38_PlanAid.py - Master Orchestrator for T-38 PlanAid Application

This script serves as the main entry point for the T-38 PlanAid workflow. It:
- Defines the AppConfig dataclass, which holds all configuration and URL endpoints for data acquisition and KML generation.
- Initializes all required folders and cleans up old data for a fresh run.
- Orchestrates the data acquisition (including online Google Sheet and API pulls) and KML generation steps.

All configuration (API endpoints, Google Sheet URLs, file paths) is centralized in AppConfig and passed to submodules.
"""

# Standard library imports
import shutil
import sys
import time
import warnings
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

# Local module imports
import Data_Acquisition
import KML_Generator


warnings.filterwarnings("ignore")

# --- Logging Setup (Alec style) ---
import colorlog
import logging

def setup_logging(output_folder):
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    log_filename = 'logfile.log'
    log_filepath = output_folder / log_filename
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)-18s - %(levelname)-8s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG':    'cyan',
            'INFO':     'green',
            'WARNING':  'yellow',
            'ERROR':    'red',
            'CRITICAL': 'bold_red,bg_white',
        }
    ))
    log_filepath.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_filepath)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)-18s - %(levelname)-8s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    root_logger.addHandler(handler)
    root_logger.addHandler(file_handler)
    return logging.getLogger(__name__)

# Get the directory where the exe/script is located (not the current working directory)
if getattr(sys, 'frozen', False):
    # Running as compiled exe
    APP_DIR = Path(sys.executable).parent
else:
    # Running as script
    APP_DIR = Path(__file__).parent


@dataclass
class AppConfig:
    """Configuration for T-38 PlanAid application. Passed to sub-scripts.
    
    Holds all URLs, API endpoints, and folder paths used by Data_Acquisition and KML_Generator.
    Includes Google Sheet URL for comments, NASA APIs, FAA data, and DLA fuel sources.
    """
    
    # MODIFY: version - update this for each release, shown on KML pin within the Gulf of America.
    version: ClassVar[str] = 'Version 3.0'

    # AOD sources
    aod_flights_api: ClassVar[str] = 'https://ndjsammweb.ndc.nasa.gov/Flightmetrics/api/cbdata/t38airports'
    aod_comments_url: ClassVar[str] = 'https://docs.google.com/spreadsheets/d/1AZypD2UHW65op0CSiMAlxwdjPq71B6LNIKk4n0crovI/export?format=csv&gid=0'
    years_included: ClassVar[int] = 4

    # FAA data - API endpoints to find current download URLs
    nasr_file_finder: ClassVar[str] = 'https://external-api.faa.gov/apra/nfdc/nasr/chart'
    dcs_file_finder: ClassVar[str] = 'https://external-api.faa.gov/apra/supplement/chart'

    # DLA Contract Fuel
    dla_fuel_check: ClassVar[str] = 'https://cis.energy.dla.mil/ipcis/Ipcis'
    dla_fuel_download: ClassVar[str] = 'https://cis.energy.dla.mil/ipcis/Download?searchValue=UNITED%20STATES&field=REGION&recordType=100'

    # Instance fields - paths (all output goes into 'T38 Planning Aid' subfolder)
    app_dir: Path = field(default_factory=lambda: APP_DIR)
    work_dir: Path = field(default_factory=lambda: APP_DIR / 'T38 Planning Aid')
    data_folder: Path = field(default_factory=lambda: APP_DIR / 'T38 Planning Aid' / 'DATA')
    output_folder: Path = field(default_factory=lambda: APP_DIR / 'T38 Planning Aid' / 'KML_Output')

    def __post_init__(self):
        """Compute derived paths."""
        self.apt_data_dir = self.data_folder / 'apt_data'


def main():
    """
    Main entry point - orchestrates all T-38 PlanAid scripts.
    
    Steps:
    1. Initializes configuration and cleans/creates all required folders.
    2. Runs Data_Acquisition (downloads all required data, including Google Sheet comments).
    3. Runs KML_Generator (builds master dictionary and generates KML and summary outputs).
    """
    cfg = AppConfig()
    logger = setup_logging(cfg.output_folder)
    logger.info("=" * 60)
    logger.info("T-38 PlanAid - Main Execution")
    logger.info("=" * 60)

    # Auto-extract bundled wb_list.xlsx on first run (standalone exe support)
    wb_dest = cfg.work_dir / 'wb_list.xlsx'
    if not wb_dest.exists() and getattr(sys, 'frozen', False):
        cfg.work_dir.mkdir(parents=True, exist_ok=True)
        bundled = Path(sys._MEIPASS) / 'wb_list.xlsx'
        if bundled.exists():
            shutil.copy2(bundled, wb_dest)
            logger.info(f"Extracted bundled wb_list.xlsx to {wb_dest}")
        else:
            logger.warning("wb_list.xlsx not found in bundled data or alongside exe.")

    # Migrate old cache from DATA/ to T38 Planning Aid/DATA/ if needed
    old_data = cfg.app_dir / 'DATA'
    if old_data.exists() and old_data != cfg.data_folder:
        old_cache = old_data / 'Cache'
        old_json = old_data / 'data_download_cache.json'
        if old_cache.exists() and not (cfg.data_folder / 'Cache').exists():
            cfg.data_folder.mkdir(parents=True, exist_ok=True)
            shutil.copytree(old_cache, cfg.data_folder / 'Cache')
            logger.info("Migrated cache from old DATA/ folder.")
        if old_json.exists() and not (cfg.data_folder / 'data_download_cache.json').exists():
            cfg.data_folder.mkdir(parents=True, exist_ok=True)
            shutil.copy2(old_json, cfg.data_folder / 'data_download_cache.json')
            logger.info("Migrated cache JSON from old DATA/ folder.")
    # Also migrate wb_list.xlsx from old location
    old_wb = cfg.app_dir / 'wb_list.xlsx'
    wb_dest = cfg.work_dir / 'wb_list.xlsx'
    if old_wb.exists() and not wb_dest.exists():
        cfg.work_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_wb, wb_dest)
        logger.info("Migrated wb_list.xlsx from old location.")

    try:
        # Clean up working directories while preserving cache
        # Keep Cache folder and cache JSON to preserve Alec's cycle caching
        if cfg.data_folder.exists():
            cache_folder = cfg.data_folder / 'Cache'
            cache_json = cfg.data_folder / 'data_download_cache.json'
            # Delete non-cache items
            for item in cfg.data_folder.iterdir():
                if item != cache_folder and item != cache_json:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
        cfg.data_folder.mkdir(parents=True, exist_ok=True)
        cfg.apt_data_dir.mkdir(parents=True, exist_ok=True)
        cfg.output_folder.mkdir(parents=True, exist_ok=True)

        logger.info("[1/2] Running Data_Acquisition...")
        logger.info("-" * 60)
        Data_Acquisition.run(cfg)
        logger.info("-" * 60)

        logger.info("[2/2] Running KML_Generator...")
        logger.info("-" * 60)
        map_path = KML_Generator.run(cfg)
        logger.info("-" * 60)

        logger.info("=" * 60)
        logger.info("All scripts executed successfully!")
        logger.info("=" * 60)
    except Exception as e:
        logger.error("=" * 60)
        logger.error("AN ERROR OCCURRED DURING EXECUTION")
        logger.error("=" * 60)
        logger.exception("Execution failed")
        return 1, None
    return 0, map_path


NASA = """                                                                 
███████████████████       ██████████████████       ████                                      
  ███████████████████      ███████████████████     ████                                     
                 █████                    █████    ████                                    
                 █████                    ████     ████                                    
  ███████████████████      ██████████████████      ████                                   
  █████████████████        ███████████████         ████                                 
  ████         ██████      █████                   ███████████████████                    
  ████           ██████     ████                   ██████████████████                     

                                                                                                                               
    ███████╗██╗  ██╗   ██╗    ███╗   ██╗ █████╗ ███████╗ █████╗ ██╗
    ██╔════╝██║  ╚██╗ ██╔╝    ████╗  ██║██╔══██╗██╔════╝██╔══██╗██║
    █████╗  ██║   ╚████╔╝     ██╔██╗ ██║███████║███████╗███████║██║
    ██╔══╝  ██║    ╚██╔╝      ██║╚██╗██║██╔══██║╚════██║██╔══██║╚═╝
    ██║     ███████╗██║       ██║ ╚████║██║  ██║███████║██║  ██║██╗
    ╚═╝     ╚══════╝╚═╝       ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝

-The Navy Rowers ( Adrien & Nick ) ( & Evan )
-Alec

███████╗███████╗███╗   ███╗██████╗ ███████╗██████╗     ███████╗ ██╗
██╔════╝██╔════╝████╗ ████║██╔══██╗██╔════╝██╔══██╗    ██╔════╝ ╚═╝   
███████╗█████╗  ██╔████╔██║██████╔╝█████╗  ██████╔╝    █████╗   ██║
╚════██║██╔══╝  ██║╚██╔╝██║██╔═══╝ ██╔══╝  ██╔══██╝    ██╔══╝   ██║
███████║███████╗██║ ╚═╝ ██║██║     ███████╗██║  ██║    ██║      ██║
╚══════╝╚══════╝╚═╝     ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝    ╚═╝      ╚═╝

- The Marines.

(You can close this window)"""


if __name__ == "__main__":
    cfg = AppConfig()
    exit_code, map_path = main()
    # Print ASCII art with delay
    lines = NASA.strip().split('\n')
    for line in lines:
        print(line)
        time.sleep(0.1)

    # Show user where their KML file is (last thing they see)
    kml_files = list(cfg.output_folder.glob('*.kml'))
    if kml_files:
        latest_kml = max(kml_files, key=lambda f: f.stat().st_mtime)
        print(f"\n{'=' * 60}")
        print(f"KML output [can be opened in Google Earth/Foreflight/KMZview.com]: {latest_kml.resolve()}")
        print(f"{'=' * 60}")

    # Open interactive map in default browser
    if map_path and map_path.exists():
        print(f"\n{'=' * 60}")
        print("MAP PIN LEGEND:")
        print(f"{'-' * 60}")
        print("  BLUE   - JASU listed, no recent ops — good to go")
        print("  GREEN  - Recently landed by T-38 (or whitelisted)")
        print("  YELLOW - No JASU listed — call FBO to verify cart")
        print("  RED (warning) - Category 2/3 — extra planning req'd")
        print("  RED (ban)     - Category 1 — T-38 ops prohibited")
        print(f"{'=' * 60}")
        print(f"\nOpening interactive map in browser...")
        webbrowser.open(map_path.resolve().as_uri())

    input()

