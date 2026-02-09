# T-38 PlanAid (Evans Edition)

## BLUF

The T-38 PlanAid tool streamlines the flight planning process by highlighting airports that meet key requirements for cross country ops:

- 7000 ft Landing Distance Available (LDA)
- Contract Gas
- Jet Air Start Unit (JASU or "Air-Start Cart")

## Overview

This is a flight planning tool (not intended for in flight use) developed by RPL Military interns with CB's support. It gathers and organizes data from the FAA, Defense Logistics Agency (DLA), and NASA AOD APIs, then produces a KML file (`T38 Apts DD Mon YYYY.kml`). The KML file includes color-coded airport pins based on the data, helping with flight planning in ForeFlight or other EFBs.

This is an updated version of the main T38 PlanAid with changes made to increase efficiency and modularity — uses only three scripts instead of five, with about half the lines of code. Also includes `build_exe.py` which automatically creates a distribution-ready `.exe`. Fully functional as of 1/27/2026.

## To Generate a .KML file for Cross Country Planning

Download this repository as a .zip file and extract the contents. 

Either double click `T38_PlanAid.exe` or open a command window and type:

```cmd
T38_PlanAid.exe
```

The generated `.kml` file will appear in the `KML_Output/` folder.

## For Distribution

To create a standalone `.exe` for distribution (after downloading and extracting the zip file), open a terminal prompt, navigate to the correct folder and type:

```cmd
python build_exe.py
```

Or, with python installed, just double clink on build_exe.py.

This creates the folder `T38 PlanAid Distribution/` containing:
- `T38_PlanAid.exe` - standalone executable
- `wb_list.xlsx` - airport lists (blacklist, whitelist, categories, comments)
- `Data` - A folder for cached FAA data from the last time the script ran.

KML output files are created in `KML_Output/` on first run, and can be opened in foreflight, google earth, or KMZViewer.com

Zip and distribute the `T38 PlanAid Distribution/` folder. Pilots just double-click the exe and get a .kml file output, which will be up to date with the current publications every time it runs.

## Quick Start (For Development)

```cmd
pip install -r requirements.txt
python T38_PlanAid.py
```

Output: `T38 Apts {date}.kml` - usable in foreflight.

## Files

| File | Purpose |
|------|---------|
| `T38_PlanAid.py` | Master script - run this. Contains all config (URLs, version, paths) |
| `Data_Acquisition.py` | Downloads data from AOD, FAA, DLA APIs |
| `KML_Generator.py` | Builds airport database and generates KML |
| `build_exe.py` | Builds standalone `.exe` and packages distribution folder |
| `wb_list.xlsx` | Blacklist, whitelist, categories, comments, recent landings |

## Quick modifications for other use cases

| To change... | Edit this |
|--------------|-----------|
| Version string on KML | `T38_PlanAid.py` → `AppConfig.version` |
| Minimum runway length | `KML_Generator.py` → search `# MODIFY: runway threshold` |
| Pin colors/logic | `KML_Generator.py` → search `# MODIFY: pin color` |
| Add/remove airports | `wb_list.xlsx` → BLACKLIST, WHITELIST, CAT_ONE/TWO/THREE columns |
| API URLs | `T38_PlanAid.py` → `AppConfig` class variables |

## Pin Colors

- **Blue**: JASU listed but no recent ops - otherwise good to go
- **Yellow**: No JASU listed - call FBO to verify cart
- **Green**: Recently landed by T-38 - known to work  
- **Red diamond**: Category 2/3 - extra planning required
- **Red circle**: Category 1 - T-38 ops prohibited

## Dependencies

See `requirements.txt`. Key packages: `pandas`, `simplekml`, `requests`, `requests-ntlm`, `openpyxl`, `PyMuPDF`, `colorlog`, `tqdm`

## Troubleshooting

- **File Issues**: Ensure `wb_list.xlsx` is present and correctly formatted in the same folder as the executable. Revert to a backup if needed.
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
