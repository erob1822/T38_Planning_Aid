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

import os
import traceback
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import pandas

# Optional imports - graceful degradation if not available
try:
    from requests_ntlm import HttpNtlmAuth
    HAS_NTLM = True
except ImportError:
    HAS_NTLM = False

# Suppress SSL warnings
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class DataAcquisition:
    """
    Data acquisition using cfg object from T38_PlanAid.py.
    Mirrors Alec's architecture - all URLs come from cfg.
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
            print("  requests_ntlm not installed, skipping AOD flight data")
            return False
        
        try:
            api_url = self.cfg.aod_flights_api
            years_included = self.cfg.years_included
            
            print(f"  API URL: {api_url}")
            print("  Fetching flight data...")
            
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
            
            print(f"  ✓ Found {len(latest_flights)} unique airports with recent flights")
            
            # Save to CSV
            flights_path = self.data_dir / "flights_data.csv"
            with open(flights_path, 'w') as f:
                f.write("ICAO,DATE_LANDED,FRONT_SEAT,BACK_SEAT\n")
                for code, flight in sorted(latest_flights.items(), key=lambda x: x[1]['date'], reverse=True):
                    f.write(f"{code},{flight['date']},{flight['front_seat']},{flight['back_seat']}\n")
            
            print(f"  ✓ Saved to {flights_path}")
            return True
            
        except Exception as e:
            print(f"  ✗ Flight data download failed: {e}")
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
            print(f"  URL: {url}")
            print("  Fetching comments...")
            
            gs_df = pandas.read_csv(url, header=3)
            
            comments_path = self.data_dir / "comments_data.csv"
            gs_df.to_csv(comments_path, index=False)
            
            print(f"  ✓ Downloaded {len(gs_df)} comment entries")
            print(f"  ✓ Saved to {comments_path}")
            return True
            
        except Exception as e:
            print(f"  ✗ Comments download failed: {e}")
            return False
    
    # FAA NASR DATA - uses cfg.nasr_file_finder
    
    def download_nasr(self, force: bool = False) -> bool:
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
        
        if not force and all((self.apt_data_dir / f).exists() for f in required_files):
            print("  ✓ NASR data already exists (use force=True to re-download)")
            return True
        
        try:
            api_url = self.cfg.nasr_file_finder
            print(f"  API: {api_url}")
            print("  Fetching current NASR cycle info...")
            
            params = {"edition": "current"}
            headers = {"Accept": "application/json"}
            
            response = self.session.get(api_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            download_url = data["edition"][0]["product"]["url"]
            edition_date = data["edition"][0]["editionDate"]
            
            print(f"  Edition: {edition_date}")
            print(f"  Download URL: {download_url}")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = Path(tmpdir) / "nasr_data.zip"
                
                print("  Downloading NASR zip file...")
                response = self.session.get(download_url, stream=True, timeout=120)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            print(self._progress_bar(downloaded, total_size), end='', flush=True)
                print()
                
                print("  Extracting NASR data...")
                extract_dir = Path(tmpdir) / "extracted"
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(extract_dir)
                
                # NASR zip contains nested zip: CSV_Data/<date>_CSV.zip
                # Find and extract the inner CSV zip
                inner_zips = list(extract_dir.rglob("*_CSV.zip"))
                if inner_zips:
                    print(f"  Found inner CSV zip: {inner_zips[0].name}")
                    csv_extract_dir = extract_dir / "csv_data"
                    with zipfile.ZipFile(inner_zips[0], 'r') as inner_zf:
                        inner_zf.extractall(csv_extract_dir)
                    # Update search path to include inner extraction
                    search_dirs = [extract_dir, csv_extract_dir]
                else:
                    search_dirs = [extract_dir]
                
                for csv_file in required_files:
                    found = False
                    for search_dir in search_dirs:
                        matches = list(search_dir.rglob(csv_file))
                        if matches:
                            src = matches[0]
                            dst = self.apt_data_dir / csv_file
                            df = pandas.read_csv(src, low_memory=False)
                            df.to_csv(dst, index=False)
                            print(f"  ✓ Extracted: {csv_file} ({len(df)} records)")
                            found = True
                            break
                    if not found:
                        print(f"  ✗ Could not find {csv_file} in archive")
            
            print("  ✓ NASR download complete!")
            return True
            
        except Exception as e:
            print(f"  ✗ NASR download failed: {e}")
            return False
    
    # DLA CONTRACT FUEL - uses cfg.dla_fuel_check and cfg.dla_fuel_download
    
    def download_fuel(self, force: bool = False) -> bool:
        """
        Download contract fuel data from DLA.
        
        Uses: cfg.dla_fuel_check, cfg.dla_fuel_download
        
        Produces:
            - DATA/fuel_data.csv
        
        Returns:
            True if successful
        """
        fuel_path = self.data_dir / "fuel_data.csv"
        
        if not force and fuel_path.exists():
            print("  ✓ Fuel data already exists (use force=True to re-download)")
            return True
        
        try:
            check_url = self.cfg.dla_fuel_check
            download_url = self.cfg.dla_fuel_download
            
            print(f"  Check URL: {check_url}")
            response = self.session.get(check_url, verify=False, timeout=30)
            print("  ✓ DLA site accessible")
            
            print(f"  Download URL: {download_url}")
            print("  Downloading fuel data...")
            
            response = self.session.get(download_url, verify=False, timeout=60)
            response.raise_for_status()
            
            with open(fuel_path, 'wb') as f:
                f.write(response.content)
            
            print(f"  ✓ Fuel data saved to {fuel_path}")
            return True
            
        except Exception as e:
            print(f"  ✗ Fuel download failed: {e}")
            
            # Try backup
            backup = Path("Alecs Code") / "DATA" / "fuel_data.csv"
            if backup.exists():
                import shutil
                shutil.copy(backup, fuel_path)
                print(f"  ✓ Using backup fuel data from {backup}")
                return True
            
            return False
    
    # FAA DCS (Digital Chart Supplement) - uses cfg.dcs_file_finder
    
    def download_dcs(self, force: bool = False) -> bool:
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
        
        # Check if we already have PDFs
        if not force and afd_dir.exists() and any(afd_dir.glob("*.pdf")):
            print(f"  ✓ DCS/AFD data already exists ({len(list(afd_dir.glob('*.pdf')))} PDFs)")
            return True
        
        try:
            api_url = self.cfg.dcs_file_finder
            print(f"  API: {api_url}")
            print("  Fetching current DCS cycle info...")
            
            params = {"edition": "current"}
            headers = {"Accept": "application/json"}
            
            response = self.session.get(api_url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            download_url = data["edition"][0]["product"]["url"]
            edition_date = data["edition"][0]["editionDate"]
            
            print(f"  Edition: {edition_date}")
            print(f"  Download URL: {download_url}")
            
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = Path(tmpdir) / "dcs_data.zip"
                
                print("  Downloading DCS zip file (this is large, ~200MB)...")
                response = self.session.get(download_url, stream=True, timeout=300)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            print(self._progress_bar(downloaded, total_size), end='', flush=True)
                print()
                
                print("  Extracting DCS PDFs...")
                extract_dir = Path(tmpdir) / "extracted"
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    zf.extractall(extract_dir)
                
                # Create afd directory and copy PDFs
                afd_dir.mkdir(parents=True, exist_ok=True)
                
                # Find all PDFs in extracted content
                pdf_files = list(extract_dir.rglob("*.pdf"))
                print(f"  Found {len(pdf_files)} PDF files")
                
                for pdf in pdf_files:
                    dst = afd_dir / pdf.name
                    import shutil
                    shutil.copy(pdf, dst)
                
                print(f"  ✓ Copied {len(pdf_files)} PDFs to {afd_dir}")
            
            print("  ✓ DCS download complete!")
            return True
            
        except Exception as e:
            print(f"  ✗ DCS download failed: {e}")
            traceback.print_exc()
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
            print("  ✗ PyMuPDF not installed - cannot parse JASU data")
            print("    Run: pip install pymupdf")
            return False
        
        import re
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        afd_dir = self.data_dir / "afd"
        
        if not afd_dir.exists() or not any(afd_dir.glob("*.pdf")):
            print("  ✗ No AFD PDFs found - run DCS download first")
            return False
        
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
            
            print(f"  Scanning {len(pdf_files)} PDF files for JASU references...")
            
            jasu_airports = set()
            
            # Parallel processing for speed
            with ThreadPoolExecutor() as executor:
                futures = {executor.submit(process_pdf, pdf): pdf for pdf in pdf_files}
                completed = 0
                for future in as_completed(futures):
                    result = future.result()
                    jasu_airports.update(result)
                    completed += 1
                    
                    # Progress bar
                    pct = int(100 * completed / len(pdf_files))
                    bar_len = 50
                    filled = int(bar_len * completed / len(pdf_files))
                    print(f"\r  [{'=' * filled}{' ' * (bar_len - filled)}] {pct}%", end='', flush=True)
            
            print(f"\n  ✓ Found {len(jasu_airports)} airports with JASU")
            
            # Save to CSV
            jasu_path = self.data_dir / "jasu_data.csv"
            with open(jasu_path, 'w') as f:
                f.write("ICAO\n")
                for icao in sorted(jasu_airports):
                    f.write(f"{icao}\n")
            
            print(f"  ✓ Saved to {jasu_path}")
            return True
            
        except Exception as e:
            print(f"  ✗ JASU parsing failed: {e}")
            traceback.print_exc()
            return False
    
    # MAIN EXECUTION
    
    def run_all(self, force: bool = False) -> Dict[str, bool]:
        """Run all data acquisition tasks with parallel downloads where possible."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = {}
        
        # PHASE 1: Parallel downloads for small/fast API calls
        print("\n" + "="*60)
        print("PHASE 1: Parallel API downloads (flights, comments, fuel)")
        print("="*60)
        
        parallel_tasks = {
            'flights': self.download_flights,
            'comments': self.download_comments,
            'fuel': lambda: self.download_fuel(force=force),
        }
        
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {executor.submit(func): name for name, func in parallel_tasks.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                    status = "✓" if results[name] else "✗"
                    print(f"  {name}: {status}")
                except Exception as e:
                    results[name] = False
                    print(f"  {name}: ✗ Error - {e}")
        
        # PHASE 2: Large sequential downloads (need progress bars)
        print("\n" + "="*60)
        print("PHASE 2: FAA NASR data (airports/runways)")
        print("="*60)
        results['nasr'] = self.download_nasr(force=force)
        
        print("\n" + "="*60)
        print("PHASE 3: FAA DCS (Digital Chart Supplement)")
        print("="*60)
        results['dcs'] = self.download_dcs(force=force)
        
        # PHASE 3: Parse JASU (depends on DCS)
        print("\n" + "="*60)
        print("PHASE 4: Parse JASU data from DCS PDFs")
        print("="*60)
        results['jasu'] = self.parse_jasu()
        
        # Summary
        print("\n" + "="*60)
        print("DATA ACQUISITION SUMMARY")
        print("="*60)
        for source, success in results.items():
            status = "✓ Success" if success else "✗ Failed"
            print(f"  {source}: {status}")
        
        return results


# MODULE-LEVEL FUNCTION (called by master script)

def run(cfg) -> Dict[str, bool]:
    """
    Main entry point - called by T38_PlanAid.py master script.
    
    Args:
        cfg: AppConfig object containing all API URLs and paths
        
    Returns:
        Dict mapping source name to success status
    """
    print("\nUsing API URLs from cfg object:")
    print(f"  AOD Flights: {cfg.aod_flights_api}")
    print(f"  AOD Comments: {cfg.aod_comments_url}")
    print(f"  FAA NASR: {cfg.nasr_file_finder}")
    print(f"  FAA DCS: {cfg.dcs_file_finder}")
    print(f"  DLA Fuel: {cfg.dla_fuel_download}")
    
    da = DataAcquisition(cfg)
    results = da.run_all(force=cfg.force_download)
    
    print("\nData acquisition complete!")
    return results