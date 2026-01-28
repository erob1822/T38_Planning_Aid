"""
Data_Acquisition.py - Unified Data Fetcher for T-38 PlanAid. Does everything--API pulls, airport data, fuel data, JASU etc, and writes to CSV

PURPOSE:
    Module to acquire all external data needed by the KML generator.
    Accepts cfg object
    
DATA SOURCES (URLs from cfg object):
    1. AOD Flight API - cfg.aod_flights_api
    2. AOD Comments - cfg.aod_comments_url  
    3. FAA NASR - cfg.nasr_file_finder (28-day cycle)
    4. DLA Fuel - cfg.dla_fuel_download

OUTPUT:
    - DATA/apt_data/APT_BASE.csv, APT_RWY.csv, APT_RWY_END.csv (from NASR)
    - DATA/fuel_data.csv (from DLA)
    - DATA/flights_data.csv, comments_data.csv

USAGE (from master script):
    import Data_Acquisition
    Data_Acquisition.run(cfg)
"""

# Standard library imports
import re
import shutil
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict

# Third-party imports
import pandas
import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
from tqdm import tqdm

# Optional NTLM auth - graceful degradation if not available
try:
    from requests_ntlm import HttpNtlmAuth
    HAS_NTLM = True
except ImportError:
    HAS_NTLM = False

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class DataAcquisition:
    """
    Data acquisition using cfg object from T38_PlanAid.py.
    """
    
    def __init__(self, cfg):
        """
        Initialize with configuration object.
        
        Args:
            cfg: AppConfig object from T38_PlanAid.py containing all URLs
        """
        self.cfg = cfg
        self.data_dir = cfg.data_folder
        self.apt_data_dir = cfg.apt_data_dir
        
        # Configure HTTP session with retries
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic."""
        retry_strategy = Retry(
            total=5,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session = requests.Session()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session
    
    def _progress_bar(self, current: int, total: int, width: int = 50) -> str:
        """Generate a progress bar string."""
        if total == 0:
            return f"[{'=' * width}] 100%"
        progress = int(width * current / total)
        percent = int(100 * current / total)
        return f"\r[{'=' * progress}{' ' * (width - progress)}] {percent}%"
    
    # AOD FLIGHT DATA - uses cfg.aod_flights_api
    
    def download_flights(self) -> bool:
        """
        Download recent flight data from AOD API.
        
        Uses: cfg.aod_flights_api
        
        Returns:
            True if successful
        """
        if not HAS_NTLM:
            return False
        
        try:
            api_url = self.cfg.aod_flights_api
            years_included = self.cfg.years_included
            
            response = self.session.get(
                api_url, 
                verify=False, 
                auth=HttpNtlmAuth('', ''),
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            
            # Calculate cutoff date
            cutoff_date = (datetime.now() - timedelta(days=years_included * 365)).strftime('%Y-%m-%d')
            
            # Process entries - keep only the most recent flight per airport
            latest_flights: Dict[str, Dict] = {}
            
            for entry in data:
                airport_code = entry.get('Airport', '').strip()
                flight_date = entry.get('FlightDate', '')[:10]
                
                if flight_date < cutoff_date:
                    continue
                
                # Parse crew info
                abvs = entry.get('ABVs', '')
                if isinstance(abvs, str):
                    crew = abvs.strip().split(',')
                    front_seat = crew[0].strip() if len(crew) > 0 else ''
                    back_seat = crew[1].strip() if len(crew) > 1 else ''
                else:
                    front_seat, back_seat = '', ''
                
                if airport_code not in latest_flights or flight_date > latest_flights[airport_code]['date']:
                    latest_flights[airport_code] = {
                        'icao': airport_code,
                        'date': flight_date,
                        'front_seat': front_seat,
                        'back_seat': back_seat
                    }
            
            # Save to CSV
            flights_path = self.data_dir / "flights_data.csv"
            with open(flights_path, 'w') as f:
                f.write("ICAO,DATE_LANDED,FRONT_SEAT,BACK_SEAT\n")
                for code, flight in sorted(latest_flights.items(), key=lambda x: x[1]['date'], reverse=True):
                    f.write(f"{code},{flight['date']},{flight['front_seat']},{flight['back_seat']}\n")
            
            return True
            
        except Exception:
            return False
    
    # AOD COMMENTS - uses cfg.aod_comments_url
    
    def download_comments(self) -> bool:
        """
        Download comments from Google Sheets.
        
        Uses: cfg.aod_comments_url
        
        Returns:
            True if successful
        """
        try:
            url = self.cfg.aod_comments_url
            gs_df = pandas.read_csv(url, header=3)
            
            comments_path = self.data_dir / "comments_data.csv"
            gs_df.to_csv(comments_path, index=False)
            return True
            
        except Exception:
            return False
    
    # FAA NASR DATA - uses cfg.nasr_file_finder
    
    def download_nasr(self) -> bool:
        """
        Download FAA NASR data (Airport, Runway, Runway End data).
        
        Uses: cfg.nasr_file_finder to get download URL
        
        Produces:
            - DATA/apt_data/APT_BASE.csv
            - DATA/apt_data/APT_RWY.csv  
            - DATA/apt_data/APT_RWY_END.csv
        
        Returns:
            True if successful
        """
        required_files = ['APT_BASE.csv', 'APT_RWY.csv', 'APT_RWY_END.csv']
        
        try:
            api_url = self.cfg.nasr_file_finder
            params = {"edition": "current"}
            headers = {"Accept": "application/json"}
            
            response = self.session.get(api_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            download_url = data["edition"][0]["product"]["url"]
            
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = Path(tmpdir) / "nasr_data.zip"
                
                nasr_desc = "Downloading FAA National Airspace System Resources (NASR) dataset"
                response = self.session.get(download_url, stream=True, timeout=120)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                chunk_size = 8192
                with open(zip_path, 'wb') as f, tqdm(
                    total=total_size if total_size > 0 else None,
                    unit='B', unit_scale=True, desc=nasr_desc
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        f.write(chunk)
                        pbar.update(len(chunk))
                
                extract_dir = Path(tmpdir) / "extracted"
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(extract_dir)
                
                # NASR zip contains nested zip: CSV_Data/<date>_CSV.zip
                inner_zips = list(extract_dir.rglob("*_CSV.zip"))
                if inner_zips:
                    csv_extract_dir = extract_dir / "csv_data"
                    with zipfile.ZipFile(inner_zips[0], 'r') as inner_zf:
                        inner_zf.extractall(csv_extract_dir)
                    search_dirs = [extract_dir, csv_extract_dir]
                else:
                    search_dirs = [extract_dir]
                
                for csv_file in required_files:
                    for search_dir in search_dirs:
                        matches = list(search_dir.rglob(csv_file))
                        if matches:
                            src = matches[0]
                            dst = self.apt_data_dir / csv_file
                            # Direct copy is faster than read_csv/to_csv
                            shutil.copy(src, dst)
                            break
            
            return True
            
        except Exception:
            return False
    
    # DLA CONTRACT FUEL - uses cfg.dla_fuel_check and cfg.dla_fuel_download
    
    def download_fuel(self) -> bool:
        """
        Download contract fuel data from DLA.
        
        Uses: cfg.dla_fuel_check, cfg.dla_fuel_download
        
        Produces:
            - DATA/fuel_data.csv
        
        Returns:
            True if successful
        """
        fuel_path = self.data_dir / "fuel_data.csv"
        
        try:
            check_url = self.cfg.dla_fuel_check
            download_url = self.cfg.dla_fuel_download
            
            self.session.get(check_url, verify=False, timeout=30)
            response = self.session.get(download_url, verify=False, timeout=60)
            response.raise_for_status()
            
            with open(fuel_path, 'wb') as f:
                f.write(response.content)
            
            return True
            
        except Exception:
            return False
    
    # FAA DCS (Digital Chart Supplement) - uses cfg.dcs_file_finder
    
    def download_dcs(self) -> bool:
        """
        Download FAA DCS (Digital Chart Supplement) PDFs.
        These contain A/FD airport info including JASU references.
        
        Uses: cfg.dcs_file_finder
        
        Produces:
            - DATA/afd/*.pdf (individual airport pages)
        
        Returns:
            True if successful
        """
        afd_dir = self.data_dir / "afd"
        
        try:
            api_url = self.cfg.dcs_file_finder
            params = {"edition": "current"}
            headers = {"Accept": "application/json"}
            
            response = self.session.get(api_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            download_url = data["edition"][0]["product"]["url"]
            
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = Path(tmpdir) / "dcs_data.zip"
                
                dcs_desc = "Downloading FAA Digital Chart Supplement (DCS) dataset (~200MB)"
                response = self.session.get(download_url, stream=True, timeout=300)
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                chunk_size = 8192
                with open(zip_path, 'wb') as f, tqdm(
                    total=total_size if total_size > 0 else None,
                    unit='B', unit_scale=True, desc=dcs_desc
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        f.write(chunk)
                        pbar.update(len(chunk))
                
                extract_dir = Path(tmpdir) / "extracted"
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(extract_dir)
                
                # Create afd directory and copy PDFs
                afd_dir.mkdir(parents=True, exist_ok=True)
                
                # Find all PDFs in extracted content
                pdf_files = list(extract_dir.rglob("*.pdf"))
                
                for pdf in pdf_files:
                    dst = afd_dir / pdf.name
                    shutil.copy(pdf, dst)
            
            return True
            
        except Exception:
            return False
    
    # JASU FINDER - parses DCS PDFs for JASU references
    
    def parse_jasu(self) -> bool:
        """
        Parse DCS/AFD PDF files for airports with JASU (air start carts).
        Uses Evan's optimized logic with PyMuPDF and parallel processing.
        
        Produces:
            - DATA/jasu_data.csv
        
        Returns:
            True if successful
        """
        try:
            import fitz  # PyMuPDF - faster than PyPDF2
        except ImportError:
            return False
        
        afd_dir = self.data_dir / "afd"
        
        def extract_icao_jasu_from_text(text: str) -> list:
            """
            Find ICAO codes linked to JASU equipment by proximity.
            Returns list of ICAO codes for airports with valid JASU equipment.
            """
            lines = text.splitlines()
            kval_list = []  # Line indices containing ICAO codes
            JASU_ref = None
            buzzkill = 1  # 1 = no valid equipment found
            
            for idx, line in enumerate(lines):
                # ICAO pattern: ( KXXX ) or ( PAXX ) with optional spaces
                match = re.search(r'\(\s*(K|PA)\s*(\w{3,4})\s*\)', line)
                if match:
                    kval_list.append(idx)
                
                # Check for JASU and valid equipment
                if 'JASU' in line:
                    JASU_ref = idx
                    # Valid equipment codes indicating a real JASU
                    for equipment in ['95', '60A', 'MSU', 'GTC', 'WELLS', 'NCPP', 'MA-']:
                        if equipment in line or (idx + 1 < len(lines) and equipment in lines[idx + 1]):
                            buzzkill = 0
                            break
            
            extracted = []
            if JASU_ref is not None and buzzkill == 0:
                # Find closest ICAO code before the JASU line
                prior_icaos = [i for i in kval_list if i < JASU_ref]
                if prior_icaos:
                    corr_port = prior_icaos[-1]
                    match = re.search(r'\(\s*(K|PA)\s*(\w{3,4})\s*\)', lines[corr_port])
                    if match:
                        airport_code = f"{match.group(1)}{match.group(2)}"
                        extracted.append(airport_code)
            return extracted
        
        def process_pdf(pdf_path: Path) -> list:
            """Process a single PDF and return list of ICAO codes with JASU."""
            icaos = []
            try:
                with fitz.open(str(pdf_path)) as doc:
                    for page in doc:
                        text = page.get_text()
                        page_icaos = extract_icao_jasu_from_text(text)
                        icaos.extend(page_icaos)
            except Exception:
                pass  # Skip problematic PDFs
            return icaos
        
        try:
            # Filter valid AFD PDFs (pattern: CS_XX_YYYYMMDD.pdf)
            pdf_files = [f for f in afd_dir.iterdir() 
                        if f.suffix.lower() == '.pdf' 
                        and re.match(r'^CS_[A-Z]{2}_\d{8}\.pdf$', f.name)]
            
            if not pdf_files:
                # Fall back to all PDFs if naming pattern doesn't match
                pdf_files = [f for f in afd_dir.iterdir() if f.suffix.lower() == '.pdf']
            
            from tqdm import tqdm
            print("  Downloading and parsing FAA Pubs for ICAOs with JASUs...")
            jasu_airports = set()
            # Parallel processing for speed
            with ThreadPoolExecutor() as executor:
                futures = {executor.submit(process_pdf, pdf): pdf for pdf in pdf_files}
                total = len(pdf_files)
                with tqdm(total=total, desc="JASU Parsing", unit="pdf") as pbar:
                    for future in as_completed(futures):
                        result = future.result()
                        jasu_airports.update(result)
                        pbar.update(1)
            
            # Save to CSV
            jasu_path = self.data_dir / "jasu_data.csv"
            with open(jasu_path, 'w') as f:
                f.write("ICAO\n")
                for icao in sorted(jasu_airports):
                    f.write(f"{icao}\n")
            
            return True
            
        except Exception:
            return False
    
    # MAIN EXECUTION
    
    def run_all(self):
        """Run all data acquisition tasks."""
        results = {}
        
        # PHASE 1: Parallel downloads for small/fast API calls
        print("Fetching flight data, comments, and fuel...")
        parallel_tasks = {
            'flights': self.download_flights,
            'comments': self.download_comments,
            'fuel': self.download_fuel,
        }
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(func): name for name, func in parallel_tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception:
                    results[name] = False
        
        # PHASE 2: Large sequential downloads
        print("Fetching FAA airport/runway data...")
        results['nasr'] = self.download_nasr()
        
        print("Fetching FAA Chart Supplement...")
        results['dcs'] = self.download_dcs()
        
        # PHASE 3: Parse JASU (depends on DCS)
        results['jasu'] = self.parse_jasu()
        
        return results


# MODULE-LEVEL FUNCTION (called by master script)

def run(cfg):
    """
    Main entry point - called by T38_PlanAid.py master script.
    
    Args:
        cfg: AppConfig object containing all API URLs and paths
    """
    da = DataAcquisition(cfg)
    da.run_all()
    
    print("Data acquisition complete!")