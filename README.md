# T-38 PlanAid (Evans Edition)

## BLUF

The T-38 PlanAid tool streamlines the flight planning process by highlighting airports that meet key requirements for cross country ops:

- 7000 ft Landing Distance Available (LDA)
- Contract Gas
- Jet Air Start Unit (JASU or "Air-Start Cart")

Download the app from the 'Releases' section.

## Overview

This is a flight planning tool (not intended for in flight use) developed by RPL Military interns with CB's support. It gathers and organizes data from the FAA, Defense Logistics Agency (DLA), and NASA AOD APIs, then produces a KML file (`T38 Apts DD Mon YYYY EXPIRES DD Mon YYYY.kml`) and an interactive HTML map. The KML file includes color-coded airport pins based on the data, helping with flight planning in ForeFlight or other EFBs. The HTML map auto-opens in your browser after each run, providing a zoomable, clickable view of all eligible airports.

This is an updated version of the main T38 PlanAid with changes made to increase efficiency and modularity — uses only three scripts instead of five, with about half the lines of code. Also includes `build_exe.py` which automatically creates a distribution-ready `.exe`. Fully functional as of 1/27/2026.

## Getting the Planning Aid (Easiest Way)

1. Go to the [**Releases**](https://github.com/erob1822/T38PlanAid_EvansVersion/releases) page
2. Download `T-38 Planning Aid.exe` from the latest release
3. Double-click it — no install, no Python, no other files needed

On first run the exe downloads all data automatically and creates a `T38 Planning Aid/` folder next to itself. Subsequent runs reuse cached data if the folder is kept alongside the exe.

Note: Windows doesn't seem to want to trust that download. If you can't get the .exe to download and run, you'll have to download the whole repository and run the 'build_exe.py" file on a computer with python installed.

## Output

All output goes into a `T38 Planning Aid/` folder created next to the exe:

```
T-38 Planning Aid.exe
T38 Planning Aid/
├── KML_Output/
│   ├── T38 Apts DD Mon YYYY EXPIRES DD Mon YYYY.kml   ← open in ForeFlight / Google Earth
│   ├── T38 Map DD Mon YYYY EXPIRES DD Mon YYYY.html   ← interactive browser map (auto-opens)
│   ├── T38_Airports.txt
│   └── T38_masterdict.xlsx
├── DATA/                                               ← cached FAA / DLA data
└── wb_list.xlsx                                        ← editable airport lists
```

- Open the `.kml` in **ForeFlight**, **Google Earth**, or [KMZViewer.com](https://kmzviewer.com)
- The interactive `.html` map auto-opens in your browser after each run

## For Development

```cmd
git clone https://github.com/erob1822/T38PlanAid_EvansVersion.git
cd T38PlanAid_EvansVersion
pip install -r requirements.txt
python T38_PlanAid.py
```

Output: `T38 Planning Aid/KML_Output/T38 Apts {date} EXPIRES {expiration}.kml` — usable in ForeFlight.
An interactive HTML map also opens automatically in your browser.

## Building the Exe

To build a standalone `.exe` for distribution:

```cmd
python build_exe.py
```

This creates `T38 PlanAid Distribution/` containing the exe and a pre-populated `T38 Planning Aid/` folder with cached data. Upload the exe to a new GitHub Release for others to download.

## Project Structure

| File | Purpose |
|------|---------|
| `T38_PlanAid.py` | Master script — orchestrates everything. Contains all config (URLs, version, paths) |
| `Data_Acquisition.py` | Downloads data from AOD, FAA, DLA APIs with 28/56-day cycle caching |
| `KML_Generator.py` | Builds airport database, generates KML, and creates interactive HTML map |
| `build_exe.py` | Builds standalone `.exe` and packages distribution folder |
| `wb_list.xlsx` | Blacklist, whitelist, categories, comments, recent landings |
| `requirements.txt` | Python dependencies |

## Quick modifications for other use cases

| To change... | Edit this |
|--------------|-----------|
| Version string on KML | `T38_PlanAid.py` → `AppConfig.version` |
| Minimum runway length | `KML_Generator.py` → search `# MODIFY: runway threshold` |
| Pin colors/logic | `KML_Generator.py` → search `# MODIFY: pin color` |
| Add/remove airports | `wb_list.xlsx` → BLACKLIST, WHITELIST, CAT_ONE/TWO/THREE columns |
| API URLs | `T38_PlanAid.py` → `AppConfig` class variables |

## Interactive Map

After each run, an interactive HTML map auto-opens in your default browser. It displays all eligible airports on an OpenStreetMap base layer with the same color-coded markers as the KML file. Click any marker for a popup with LDA, fuel, JASU status, category restrictions, and comments. The map can be zoomed, panned, and shared as a standalone `.html` file.

## Pin Colors

- **Blue**: JASU listed but no recent ops - otherwise good to go
- **Yellow**: No JASU listed - call FBO to verify cart
- **Green**: Recently landed by T-38 - known to work  
- **Red diamond**: Category 2/3 - extra planning required
- **Red circle**: Category 1 - T-38 ops prohibited

## Dependencies

Install via `pip install -r requirements.txt`. Key packages: `pandas`, `simplekml`, `folium`, `requests`, `requests-ntlm`, `openpyxl`, `PyMuPDF`, `colorlog`, `tqdm`

## Troubleshooting

- **File Issues**: `wb_list.xlsx` is auto-extracted on first run. If it gets corrupted, delete it from `T38 Planning Aid/` and the exe will regenerate it. Revert to a backup if you've made custom edits.
- **URL Changes**: If FAA or DLA URLs change, update the endpoints in `T38_PlanAid.py` → `AppConfig` class variables.
- **API Issues**: Contact AOD IT if API paths are down or outdated. Update the relevant URL in `T38_PlanAid.py` → `AppConfig`.

## Contact Info and Attributions

### RPL Military Interns (Authors / Developers)

- Nicholas Bostock [API scraping and AOD integration]
- Jacob Cates [Scraping websites and downloading/packaging data]
- Alex Clark, +1(469) 406-8546 (POC AUG2024)
- Alec Engl, +1(727) 488-0507 aengl5337@gmail.com (POC NOV2025)
- Ignatius Liberto, 757-373-8787, ignatiusliberto@gmail.com (POC NOV2024) [AFD Scraping, data harvesting, LDA logic, KML Generation]
- Adrien Richez, +1(678) 788-4015, adrichez24@gmail.com (POC SEP2024) [API scraping and AOD integration]
- Evan Robertson +1 (410) 507-6109, erob1822@gmail.com (POC FEB2026) [.exe generation and v3.0 integration]
- James Zuzelski, +1(248) 930-3461, (POC JUN2024)

### CB / AOD POCs

- Sean Brady
- Dan Cochran
- Luke Delaney
- Jonny Kim
