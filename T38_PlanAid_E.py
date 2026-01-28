"""
T38_PlanAid_E.py - Master Orchestrator for T-38 PlanAid Application

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar

# Local module imports
import Data_Acquisition
import KML_Generator

warnings.filterwarnings("ignore")

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
    version: ClassVar[str] = 'Version 3.0 (Evans Edition)'

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

    # Instance fields - paths (relative to APP_DIR so exe output lands next to exe)
    app_dir: Path = field(default_factory=lambda: APP_DIR)
    data_folder: Path = field(default_factory=lambda: APP_DIR / 'DATA')
    output_folder: Path = field(default_factory=lambda: APP_DIR / 'KML_Output')

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
    # Initialize configuration
    cfg = AppConfig()
    
    # Delete DATA folder to ensure fresh data every run (removes old CSVs and ensures new download)
    if cfg.data_folder.exists():
        shutil.rmtree(cfg.data_folder)
    cfg.data_folder.mkdir(parents=True, exist_ok=True)
    cfg.apt_data_dir.mkdir(parents=True, exist_ok=True)
    cfg.output_folder.mkdir(parents=True, exist_ok=True)
    
    # Run Data Acquisition (downloads all data, including Google Sheet comments, APIs, and external CSVs)
    Data_Acquisition.run(cfg)
    
    # Run KML Generator (builds master dict and generates KML/Excel/txt outputs)
    KML_Generator.run(cfg)


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

███████╗███████╗███╗   ███╗██████╗ ███████╗██████╗     ███████╗ ██╗
██╔════╝██╔════╝████╗ ████║██╔══██╗██╔════╝██╔══██╗    ██╔════╝ ╚═╝   
███████╗█████╗  ██╔████╔██║██████╔╝█████╗  ██████╔╝    █████╗   ██║
╚════██║██╔══╝  ██║╚██╔╝██║██╔═══╝ ██╔══╝  ██╔══██╝    ██╔══╝   ██║
███████║███████╗██║ ╚═╝ ██║██║     ███████╗██║  ██║    ██║      ██║
╚══════╝╚══════╝╚═╝     ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝    ╚═╝      ╚═╝

- The Marines.

(You can close this window)"""


if __name__ == "__main__":
    main()
    
    # Print ASCII art with delay
    lines = NASA.strip().split('\n')
    for line in lines:
        print(line)
        time.sleep(0.1)
    input()

