"""
T38_PlanAid.py - Master Orchestrator for T-38 PlanAid Application

Mirrors Alec's architecture: AppConfig dataclass holds all configuration,
passed to sub-scripts for data acquisition and KML generation.
"""

import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Any
import time
import warnings

warnings.filterwarnings("ignore")


@dataclass
class AppConfig:
    """Configuration for T-38 PlanAid application. Passed to sub-scripts."""
    
    # Current version - shown on KML pin outside T-38 working area
    version: ClassVar[str] = 'Version 3.0 (Evans Edition)'

    # Excel config
    master_excel_fname: ClassVar[str] = 'wb_list.xlsx'
    sheet_name: ClassVar[str] = 'kml data'
    header_row: ClassVar[int] = 1

    # Column headers in wb_list.xlsx
    AC: ClassVar[str] = 'APT_COMM'
    AU: ClassVar[str] = 'API_URL'
    CD: ClassVar[str] = 'COMMENT_DATE'
    CC: ClassVar[str] = 'COMMENTS'
    DL: ClassVar[str] = 'DATE_LANDED'
    RL: ClassVar[str] = 'RECENTLY_LANDED'
    FS: ClassVar[str] = 'FRONT_SEAT'
    BS: ClassVar[str] = 'BACK_SEAT'
    YI: ClassVar[str] = 'YEARS_INCLUDED'

    # Data sources config
    force_download: ClassVar[bool] = False
    timestamp_format: ClassVar[str] = "%Y%m%d_%H%M%S"

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

    # Instance fields
    data_folder: Path = field(default_factory=lambda: Path('DATA'))
    output_folder: Path = field(default_factory=lambda: Path('KML_Output'))

    def __post_init__(self):
        """Compute derived paths and create directories."""
        self.run_timestamp = datetime.now().strftime(self.timestamp_format)
        self.apt_data_dir = self.data_folder / 'apt_data'
        self.master_excel_path = Path(self.master_excel_fname)
        
        # Create directories
        self.data_folder.mkdir(parents=True, exist_ok=True)
        self.apt_data_dir.mkdir(parents=True, exist_ok=True)
        self.output_folder.mkdir(parents=True, exist_ok=True)


def main():
    """Main entry point - orchestrates all T-38 PlanAid scripts."""
    
    # Step 0: Initialize configuration
    print("Initializing T-38 PlanAid configuration...")
    cfg = AppConfig()
    print(f"  Data folder: {cfg.data_folder}")
    print(f"  Output folder: {cfg.output_folder}")
    print(f"  Timestamp: {cfg.run_timestamp}")
    
    # Step 1: Run Data Acquisition
    print("\nRunning Data_Acquisition.py...")
    import Data_Acquisition
    Data_Acquisition.run(cfg)
    
    # Step 2: Run KML Generator
    print("\nRunning KML_Generator.py...")
    import KML_Generator
    KML_Generator.run(cfg)
    
    print("\nScripts executed successfully.")


def print_credits():
    print("\nRPL Military Intern Developers by Alphabetical Order:")
    print("Nick Bostock \nJacob Cates \nAlex Clark \nIgnatius Liberto \nAdrien Richez \nJames Zuzelski")
    print("\nCB & AOD POCs by Alphabetical Order:")
    print("Sean Brady \nDan Cochran \nLuke Delaney \nJonny Kim")


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
    print_credits()
    
    # Print ASCII art with delay
    lines = NASA.strip().split('\n')
    for line in lines:
        print(line)
        time.sleep(0.1)
    input()

