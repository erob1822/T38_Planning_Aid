"""
Mission Brief Generator for T-38 Operations

Generates formatted mission briefing sheets by combining airport data with 
flight planning parameters. Creates printable briefs for cross-country training.

Author: Evans Edition Extension
Purpose: Automate mission brief creation for T-38 cross-country flights
"""

import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import textwrap


class BriefingSheet:
    """Constructs a formatted mission brief document"""
    
    def __init__(self, departure_icao, destination_icao, alternate_icao=None):
        self.dep = departure_icao.upper()
        self.dest = destination_icao.upper()
        self.alt = alternate_icao.upper() if alternate_icao else None
        self.brief_time = datetime.now()
        self.takeoff_time = None
        self.airport_db = {}
        self.whitelist_db = pd.DataFrame()
        
    def load_databases(self):
        """Pull airport information from generated files"""
        base_path = Path(__file__).parent
        
        # Check for master dictionary
        masterdict_path = base_path / 'KML_Output' / 'T38_masterdict.xlsx'
        if masterdict_path.exists():
            master_df = pd.read_excel(masterdict_path)
            for _, airport_row in master_df.iterrows():
                icao_code = str(airport_row.get('ICAO', '')).strip()
                if icao_code:
                    self.airport_db[icao_code] = airport_row
        
        # Load whitelist for additional notes
        whitelist_path = base_path / 'wb_list.xlsx'
        if whitelist_path.exists():
            self.whitelist_db = pd.read_excel(whitelist_path)
    
    def get_airfield_block(self, icao_identifier):
        """Format airfield information block"""
        if icao_identifier not in self.airport_db:
            return f"*** {icao_identifier} - DATA NOT AVAILABLE ***\n"
        
        apt_info = self.airport_db[icao_identifier]
        
        block_lines = []
        block_lines.append(f"\n{'='*70}")
        block_lines.append(f"AIRFIELD: {icao_identifier} - {apt_info.get('NAME', 'Unknown')}")
        block_lines.append(f"{'='*70}")
        
        # Coordinates
        latitude = apt_info.get('LAT', 'N/A')
        longitude = apt_info.get('LON', 'N/A')
        block_lines.append(f"COORDINATES: {latitude}, {longitude}")
        
        # Runway information
        max_length = apt_info.get('MAX_RWY_LENGTH', 'Unknown')
        block_lines.append(f"LONGEST RUNWAY: {max_length} ft")
        
        # JASU availability
        jasu_status = "AVAILABLE" if apt_info.get('JASU', False) else "NOT LISTED - COORDINATE WITH FBO"
        block_lines.append(f"AIR START CART (JASU): {jasu_status}")
        
        # Fuel contract
        fuel_status = "CONTRACT FUEL AVAILABLE" if apt_info.get('FUEL', False) else "Commercial Fuel"
        block_lines.append(f"FUEL: {fuel_status}")
        
        # Recent operations
        recent = apt_info.get('RECENT_OPS', '')
        if pd.notna(recent) and str(recent).strip():
            block_lines.append(f"RECENT T-38 OPS: {recent}")
        
        # Category restrictions
        category = str(apt_info.get('CATEGORY', '')).strip()
        if category in ['1', '2', '3']:
            warning_msg = {
                '1': '*** CATEGORY 1 - T-38 OPS PROHIBITED ***',
                '2': '*** CATEGORY 2 - EXTRA PLANNING REQUIRED ***',
                '3': '*** CATEGORY 3 - COORDINATION REQUIRED ***'
            }
            block_lines.append(f"\nWARNING: {warning_msg.get(category, '')}")
        
        # Comments from whitelist
        comments = apt_info.get('COMMENTS', '')
        if pd.notna(comments) and str(comments).strip():
            block_lines.append(f"\nNOTES:")
            wrapped = textwrap.fill(str(comments), width=68, 
                                   initial_indent='  ', subsequent_indent='  ')
            block_lines.append(wrapped)
        
        return '\n'.join(block_lines) + '\n'
    
    def calculate_flight_times(self, airspeed_kts=350, wind_component=0):
        """Estimate flight duration between waypoints"""
        if self.dep not in self.airport_db or self.dest not in self.airport_db:
            return "Time calculation unavailable - missing coordinates"
        
        # Simple great circle approximation
        dep_lat = float(self.airport_db[self.dep].get('LAT', 0))
        dep_lon = float(self.airport_db[self.dep].get('LON', 0))
        dest_lat = float(self.airport_db[self.dest].get('LAT', 0))
        dest_lon = float(self.airport_db[self.dest].get('LON', 0))
        
        # Rough distance calculation (not precise spherical)
        lat_diff = abs(dest_lat - dep_lat) * 60  # nautical miles
        lon_diff = abs(dest_lon - dep_lon) * 60 * 0.7  # rough cosine adjustment
        distance_nm = (lat_diff**2 + lon_diff**2)**0.5
        
        groundspeed = airspeed_kts + wind_component
        flight_minutes = (distance_nm / groundspeed) * 60 if groundspeed > 0 else 0
        
        hours = int(flight_minutes // 60)
        minutes = int(flight_minutes % 60)
        
        return (f"Estimated Distance: {distance_nm:.0f} NM\n"
                f"Estimated Flight Time: {hours}+{minutes:02d} "
                f"(assuming {airspeed_kts} kts TAS, {wind_component:+d} kt wind component)")
    
    def generate_complete_brief(self, pilot_name="", instructor_name="", 
                                 mission_number="", sortie_type="Cross-Country Training"):
        """Assemble the full mission briefing document"""
        
        self.load_databases()
        
        header = []
        header.append("\n" + "="*70)
        header.append("T-38 MISSION BRIEFING SHEET".center(70))
        header.append("="*70)
        header.append(f"Generated: {self.brief_time.strftime('%d %b %Y %H%M')}L")
        header.append(f"Mission Type: {sortie_type}")
        if mission_number:
            header.append(f"Mission #: {mission_number}")
        if pilot_name:
            header.append(f"Pilot: {pilot_name}")
        if instructor_name:
            header.append(f"Instructor: {instructor_name}")
        header.append("="*70)
        
        # Route summary
        route_section = ["\nFLIGHT ROUTE:"]
        route_section.append(f"  Departure: {self.dep}")
        route_section.append(f"  Destination: {self.dest}")
        if self.alt:
            route_section.append(f"  Alternate: {self.alt}")
        
        # Time/distance estimates
        route_section.append("\n" + self.calculate_flight_times())
        
        # Airfield blocks
        departure_block = self.get_airfield_block(self.dep)
        destination_block = self.get_airfield_block(self.dest)
        alternate_block = self.get_airfield_block(self.alt) if self.alt else ""
        
        # Assembly
        complete_document = '\n'.join(header)
        complete_document += '\n'.join(route_section)
        complete_document += departure_block
        complete_document += destination_block
        complete_document += alternate_block
        
        # Footer
        footer = ["\n" + "="*70]
        footer.append("BRIEFING COMPLETE - Verify all NOTAMs and weather prior to flight")
        footer.append("="*70 + "\n")
        
        complete_document += '\n'.join(footer)
        
        return complete_document
    
    def save_to_file(self, output_filename=None):
        """Write briefing to text file"""
        if not output_filename:
            timestamp = self.brief_time.strftime('%Y%m%d_%H%M')
            output_filename = f"MissionBrief_{self.dep}_{self.dest}_{timestamp}.txt"
        
        output_path = Path(__file__).parent / 'KML_Output' / output_filename
        output_path.parent.mkdir(exist_ok=True, parents=True)
        
        brief_content = self.generate_complete_brief()
        
        with open(output_path, 'w') as brief_file:
            brief_file.write(brief_content)
        
        return output_path


def interactive_mode():
    """Command-line interface for mission brief generation"""
    print("\n" + "="*70)
    print("T-38 MISSION BRIEFING GENERATOR".center(70))
    print("="*70 + "\n")
    
    departure = input("Enter Departure ICAO (e.g., KRND): ").strip()
    destination = input("Enter Destination ICAO (e.g., KPNS): ").strip()
    alternate = input("Enter Alternate ICAO (press Enter to skip): ").strip()
    
    print("\nOptional Information:")
    pilot = input("Pilot name (press Enter to skip): ").strip()
    instructor = input("Instructor name (press Enter to skip): ").strip()
    mission_num = input("Mission number (press Enter to skip): ").strip()
    
    alternate_final = alternate if alternate else None
    
    briefing = BriefingSheet(departure, destination, alternate_final)
    
    brief_text = briefing.generate_complete_brief(
        pilot_name=pilot,
        instructor_name=instructor,
        mission_number=mission_num
    )
    
    print(brief_text)
    
    save_choice = input("\nSave briefing to file? (y/n): ").strip().lower()
    if save_choice == 'y':
        saved_path = briefing.save_to_file()
        print(f"\nBriefing saved to: {saved_path}")
    
    print("\nThank you for using Mission Brief Generator!")


if __name__ == "__main__":
    interactive_mode()
