"""
KML_Generator.py - T-38 Airport KML Generator

PURPOSE:
    Builds a master dictionary of CONUS airports with T-38 relevant data and generates
    a KML file with color-coded pins for use in Google Earth flight planning.
    
    This is an optimized version based on Evan's testbed improvements:
    - Uses pandas merge() for runway matching instead of O(n³) nested loops
    - Uses sets for O(1) membership lookups instead of lists
    - Uses dicts keyed by ICAO for crew/comment lookups instead of .index() searches
    - Compact style setup using dict comprehension

DATA SOURCES (from Data_Acquisition.py):
    - DATA/apt_data/APT_BASE.csv: Airport ICAO/IATA codes, coordinates, ownership type
    - DATA/apt_data/APT_RWY.csv: Runway IDs and lengths per airport
    - DATA/apt_data/APT_RWY_END.csv: Runway end declared distances (LDA)
    - DATA/fuel_data.csv: Airports with government contract fuel (header on row 3)
    - DATA/jasu_data.csv: Airports with JASU (air start cart) listed in A/FD
    - wb_list.xlsx: Recently landed, blacklist, whitelist, categories, comments, crew info

OUTPUT:
    - T38_masterdict.xlsx: Full airport database with all computed fields
    - T38 Apts {date}.kml: Color-coded airport pins for Google Earth
    - T38_Airports.txt: Tab-delimited summary for quick reference

PIN COLOR LOGIC (as a refresher):
    - Blue: JASU listed, no recent ops (or has issues) - good to go
    - Yellow: No JASU listed, no recent ops - call FBO to verify cart availability
    - Green: Recently landed by T-38 (and no issues flagged) - known to work
    - Red diamond: Category 2 or 3 airport - requires extra planning/approval
    - Red circle: Category 1 airport - T-38 operations prohibited

USAGE (from master script):
    import KML_Generator
    KML_Generator.run()
"""

import pandas as pd
import simplekml
from simplekml import Style
from pathlib import Path
from datetime import datetime
from typing import Dict, Set, Tuple, Any

# CONFIGURATION

DATA = Path("DATA")
VERSION = "Version 3.0"  # Update this when pushing changes

# Military ownership codes (these airports always have fuel)
MIL_CODES = {"CG", "MA", "MN", "MR"}

# Standard text blocks for pin descriptions
FOOTER = (
    "<br/><br/>To add/edit comments or note errors:"
    "<br/>Contact CB/AOD T38 rep"
    "<br/>or"
    "<br/>Fill out Google sheet:  https://tinyurl.com/NASAT38Comments"
    "<br/>(Copy/Paste Required)"
)

NOTE = (
    "<br/><br/>## NOTE: Aircrew shall confirm the accuracy of"
    "<br/>runway information in either the A/FD or IFR Supplement."
    "<br/>The \"Declared Distances\" section of the"
    "<br/>A/FD and IFR Supplement is omitted when"
    "<br/>declared distances equal the runway length."
    "<br/>Declared distances may also be reduced via NOTAM.##"
)


# HELPER FUNCTIONS

def get_date_string() -> str:
    """Extract date from AFD files or use current date for output naming."""
    afd_path = DATA / "afd"
    if afd_path.exists():
        pdfs = list(afd_path.glob("*.pdf"))
        if pdfs:
            # Parse date from filename like "SW_123_10AUG2023.pdf"
            try:
                name = pdfs[0].stem
                parts = name.split('_')
                if len(parts) >= 3:
                    date_str = parts[2]  # e.g., "10AUG2023"
                    dt = datetime.strptime(date_str, "%d%b%Y")
                    return dt.strftime("%d %b %Y")
            except (ValueError, IndexError):
                pass
    return datetime.now().strftime("%d %b %Y")


def load_runway_data() -> Dict[str, list]:
    """
    Load and merge runway data from NASR CSVs.
    
    Returns:
        Dict mapping IATA code to list of (runway_id, lda) tuples
    """
    apt = pd.read_csv(DATA / "apt_data/APT_BASE.csv", low_memory=False)
    rwy = pd.read_csv(DATA / "apt_data/APT_RWY.csv", low_memory=False)
    rwy_end = pd.read_csv(DATA / "apt_data/APT_RWY_END.csv", low_memory=False)
    
    # Merge runway and runway end data
    rwy_merged = rwy.merge(rwy_end, on=['ARPT_ID', 'RWY_ID'])
    
    # Use declared LDA if available, otherwise fall back to runway length
    rwy_merged['LDA'] = rwy_merged['LNDG_DIST_AVBL'].fillna(rwy_merged['RWY_LEN']).astype(int)
    
    # Build lookup dict: {IATA: [(rwy_id, lda), ...]} for O(1) access
    rwy_lookup = rwy_merged.groupby('ARPT_ID').apply(
        lambda g: list(zip(g['RWY_ID'], g['LDA'])), 
        include_groups=False
    ).to_dict()
    
    return apt, rwy_lookup


def load_reference_sets() -> Tuple[Set[str], Set[str]]:
    """
    Load fuel and JASU data as sets for O(1) membership checks.
    
    Returns:
        Tuple of (fuel_set, jasu_set)
    """
    fuel_set = set(pd.read_csv(DATA / "fuel_data.csv", header=1)['ICAO'].dropna())
    
    jasu_path = DATA / "jasu_data.csv"
    if jasu_path.exists():
        jasu_set = set(pd.read_csv(jasu_path)['ICAO'].dropna())
    else:
        jasu_set = set()
        print("WARNING: jasu_data.csv not found - JASU data will be empty")
    
    return fuel_set, jasu_set


def load_wb_list(wb_path: str = 'wb_list.xlsx') -> Dict[str, Any]:
    """
    Load wb_list.xlsx and build lookup dicts for O(1) access.
    
    Returns:
        Dict containing all wb_list data structures
    """
    wb = pd.read_excel(wb_path)
    
    # Parse dates
    wb['COMMENT_DATE'] = pd.to_datetime(wb['COMMENT_DATE'], errors='coerce').dt.strftime('%m/%d/%Y')
    wb['DATE_LANDED'] = pd.to_datetime(wb['DATE_LANDED'], errors='coerce').dt.strftime('%d %b %Y')
    
    # Build lookup dicts
    landed = {
        r['RECENTLY_LANDED']: (r['DATE_LANDED'], r['FRONT_SEAT'], r['BACK_SEAT']) 
        for _, r in wb.dropna(subset=['RECENTLY_LANDED']).iterrows()
    }
    
    comments = {
        r['APT_COMM']: (r['COMMENTS'], r['COMMENT_DATE']) 
        for _, r in wb.dropna(subset=['APT_COMM']).iterrows()
    }
    
    # Build change request text
    changerequest_values = wb["CHANGE_REQUEST"].dropna().tolist()
    changerequest_text = "<br/>".join(str(v) for v in changerequest_values)
    
    return {
        'landed': landed,
        'comments': comments,
        'black_set': set(wb['BLACKLIST'].dropna()),
        'white_set': set(wb['WHITELIST'].dropna()),
        'cat1': set(wb['CAT_ONE'].dropna()),
        'cat2': set(wb['CAT_TWO'].dropna()),
        'cat3': set(wb['CAT_THREE'].dropna()),
        'rec_issues': set(wb['ISSUES_WITH_RECENTLY_LANDED'].dropna()),
        'changerequest_text': changerequest_text,
    }


def build_master_dict(apt: pd.DataFrame, rwy_lookup: Dict, fuel_set: Set, 
                      jasu_set: Set, wb: Dict) -> Dict[str, Dict]:
    """
    Build master dictionary with one entry per ICAO airport.
    
    Enriches airport data with runway, fuel, jasu, and wb_list info.
    """
    master_dict = {}
    
    for _, row in apt.dropna(subset=['ICAO_ID']).iterrows():
        icao, iata = row['ICAO_ID'], row['ARPT_ID']
        rwy_data = rwy_lookup.get(iata, [])
        
        if not rwy_data:
            continue  # Skip airports with no runway data
        
        lda_list = [lda for _, lda in rwy_data]
        max_lda = max(lda_list)
        
        # Build runway output string showing both ends for runways >= 7000 ft
        rwy_out = ""
        for i in range(0, len(rwy_data), 2):
            lda1 = rwy_data[i][1]
            lda2 = rwy_data[i+1][1] if i+1 < len(rwy_data) else 0
            if lda1 >= 7000 or lda2 >= 7000:
                rwy_out = f"<br/>{rwy_data[i][0]}: {lda1}/{lda2}" + rwy_out
        
        # Lookup crew info and comments using O(1) dict access
        rec_info = wb['landed'].get(icao, (None, None, None))
        comm_info = wb['comments'].get(icao, (None, None))
        
        comm_str = ""
        if pd.notna(comm_info[0]) and str(comm_info[0]) != 'nan':
            if pd.notna(comm_info[1]):
                comm_str = f"<br/>{comm_info[1]}: {comm_info[0]}"
            else:
                comm_str = f"<br/>{comm_info[0]}"
        
        # Determine category restriction text
        cat = ""
        if icao in wb['cat1']:
            cat = "<br/><br/>Category 1 Airport, T38 operations prohibited."
        elif icao in wb['cat2']:
            cat = "<br/><br/>Category 2 Airport, Form 740A Required."
        elif icao in wb['cat3']:
            cat = "<br/><br/>Category 3 Airport, particular caution and prior planning required."
        
        master_dict[icao] = {
            "ICAO Name": icao,
            "IATA Name": iata,
            "Runway Length": max_lda,
            "Runway Output": rwy_out,
            "Contract Gas": icao in fuel_set or row['OWNERSHIP_TYPE_CODE'] in MIL_CODES,
            "JASU": icao in jasu_set,
            "Recently Landed": icao in wb['landed'],
            "Date Landed": rec_info[0] or "",
            "Front Seat": rec_info[1] or "",
            "Back Seat": rec_info[2] or "",
            "Black List": icao in wb['black_set'],
            "White List": icao in wb['white_set'],
            "Latitude": row['LAT_DECIMAL'],
            "Longitude": row['LONG_DECIMAL'],
            "OCONUS": icao[0] != 'K',
            "Category": cat,
            "Comments": comm_str,
            "Issues with Recently Landed": icao in wb['rec_issues'],
        }
    
    return master_dict


def create_kml_styles() -> Dict[str, Style]:
    """Create KML pin styles using compact dict approach."""
    styles = {k: Style() for k in ['ver', 'go', 'nogo', 'cat', 'cat1', 'prev']}
    
    urls = {
        'ver': 'pushpin/wht-pushpin.png',
        'go': 'pushpin/blue-pushpin.png',
        'nogo': 'pushpin/ylw-pushpin.png',
        'cat': 'paddle/red-diamond.png',
        'cat1': 'paddle/red-circle.png',
        'prev': 'pushpin/grn-pushpin.png'
    }
    
    for k, s in styles.items():
        s.iconstyle.icon.href = f'http://maps.google.com/mapfiles/kml/{urls[k]}'
    
    styles['ver'].iconstyle.color = 'ff000000'
    
    return styles


def generate_kml(master_dict: Dict, wb: Dict, date_str: str, version: str = None) -> int:
    """
    Generate KML file with color-coded airport pins.
    
    Args:
        master_dict: Dictionary of airport data
        wb: Workbook data from load_wb_list()
        date_str: Date string for filename
        version: Version string from cfg (falls back to global VERSION if None)
    
    Returns:
        Number of airports included in KML
    """
    if version is None:
        version = VERSION
        
    styles = create_kml_styles()
    kml_out = simplekml.Kml()
    
    # Version pin outside working area
    pnt = kml_out.newpoint(
        name=version, 
        description="Current version of T-38 PlanAid", 
        coords=[(-95.62, 27.84)]
    )
    pnt.style = styles['ver']
    
    txt_lines = []
    
    for d in master_dict.values():
        icao = d['ICAO Name']
        
        # Apply exclusion filters
        if d['OCONUS'] or d['Black List']:
            continue
        if d['Runway Length'] < 7000 or not d['Contract Gas']:
            continue
        if not (isinstance(icao, str) and icao.startswith('K') and len(icao) == 4):
            continue
        
        # Determine pin color based on JASU availability and recent ops history
        has_issue = not d['Recently Landed'] or d['Issues with Recently Landed']
        
        if d['JASU'] and has_issue:
            pin, style = 'blue', styles['go']
        elif not d['JASU'] and has_issue:
            pin, style = 'yellow', styles['nogo']
        elif d['Recently Landed'] or d['White List']:
            pin, style = 'green', styles['prev']
        else:
            continue
        
        # Override style for category airports (red pins)
        if "Category 1" in d['Category']:
            style = styles['cat1']
        elif "Category" in d['Category']:
            style = styles['cat']
        
        # Build description text
        rwy_info = (
            f"<br/>Longest Landing Distance Available (LDA): {d['Runway Length']}"
            f"{d['Category']}"
            f"<br/><br/>Runways with Declared LDAs >7000:{d['Runway Output']}"
        )
        
        if pin == 'green':
            crew = str(d['Front Seat']) if d['Front Seat'] else "Not Listed"
            if d['Back Seat']:
                crew += f" / {d['Back Seat']}"
            desc = (
                f"{icao} <br/>Has supported T38s in the past, start cart may or may not "
                f"be listed on A/FD, Call FBO. <br/>Government Contract Gas Available."
                f"{rwy_info}"
                f"<br/><br/>Date Last Landed: {d['Date Landed']}"
                f"<br/>Crew: {crew}"
                f"{NOTE}"
                f"<br/><br/>Comments: {d['Comments']}"
                f"{FOOTER}"
            )
        else:
            cart = "Air start cart listed" if pin == 'blue' else "No start cart listed"
            desc = (
                f"{icao} <br/>{cart} on A/FD, Call FBO. "
                f"<br/>Government Contract Gas Available."
                f"{rwy_info}"
                f"{NOTE}"
                f"<br/><br/>Comments: {d['Comments']}"
                f"{FOOTER}"
            )
        
        # Add point to KML
        point = kml_out.newpoint(
            name=f"{icao} {d['Runway Length']}", 
            description=desc, 
            coords=[(d['Longitude'], d['Latitude'])]
        )
        point.style = style
        
        # Record for txt output
        txt_color = 'red-circle' if "Category 1" in d['Category'] else \
                    'red-diamond' if "Category" in d['Category'] else pin
        comment_clean = str(d['Comments']).replace('<br/>', ' ').replace('nan', '').strip()
        txt_lines.append(f"{icao}\t{txt_color}\t{d['Runway Length']}\t{comment_clean}")
    
    # Save KML
    kml_filename = f"T38 Apts {date_str}.kml"
    kml_out.save(kml_filename)
    
    # Save txt summary
    with open('T38_Airports.txt', 'w') as f:
        f.write('ICAO\tPinColor\tRunwayLength\tComments\n')
        for line in txt_lines:
            f.write(line + '\n')
    
    return len(txt_lines)


# MODULE-LEVEL RUN FUNCTION

def run(cfg=None) -> Dict[str, Dict]:
    """
    Main entry point - called by T38_PlanAid.py master script.
    
    Args:
        cfg: AppConfig object from master script (contains version, paths, etc.)
             If None, uses defaults for standalone execution.
        
    Returns:
        master_dict for potential further processing
    """
    print("Running KML_Generator.py...")
    
    # Extract config values or use defaults
    if cfg is not None:
        wb_path = str(cfg.master_excel_path) if hasattr(cfg, 'master_excel_path') else 'wb_list.xlsx'
        version = cfg.version if hasattr(cfg, 'version') else VERSION
        data_path = cfg.data_folder if hasattr(cfg, 'data_folder') else DATA
    else:
        wb_path = 'wb_list.xlsx'
        version = VERSION
        data_path = DATA
    
    # Load all data sources
    print("  Loading runway data...")
    apt, rwy_lookup = load_runway_data()
    
    print("  Loading fuel and JASU data...")
    fuel_set, jasu_set = load_reference_sets()
    
    print("  Loading wb_list.xlsx...")
    wb = load_wb_list(wb_path)
    
    # Build master dictionary
    print("  Building master dictionary...")
    master_dict = build_master_dict(apt, rwy_lookup, fuel_set, jasu_set, wb)
    
    # Save master dict to Excel
    pd.DataFrame.from_dict(master_dict, orient='index').to_excel('T38_masterdict.xlsx')
    
    # Generate KML
    print("  Generating KML...")
    date_str = get_date_string()
    num_airports = generate_kml(master_dict, wb, date_str, version)
    
    print(f"\nKML file generated!")
    print(f"  - T38 Apts {date_str}.kml ({num_airports} airports)")
    print(f"  - T38_Airports.txt")
    print(f"  - T38_masterdict.xlsx ({len(master_dict)} total airports)")
    
    return master_dict


# AUTO-RUN ON IMPORT (matches original pattern - comment out if not desired)

# Uncomment below to auto-run when imported:
# run()
