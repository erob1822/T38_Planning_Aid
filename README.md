# T-38 Planning Aid

## BLUF

The T-38 PlanAid tool streamlines the flight planning process by highlighting airports that meet key requirements for cross country ops:

- 7000 ft Landing Distance Available (LDA)
- Contract Gas
- Jet Air Start Unit (JASU or "Air-Start Cart")

Two versions are available:

| | **User-Friendly (GUI)** | **Developer (CLI)** |
|---|---|---|
| **Location** | `GUI Files/` | Root directory |
| **Interface** | Dark-themed GUI with progress bars | Command-line / terminal output |
| **Console window** | No | Yes |

Download the app from the 'Releases' section, or build either version by running their respective "build_exe" python script.

## Overview

This is a flight planning tool (not intended for in-flight use) developed by RPL Military interns with CB's support. It gathers and organizes data from the FAA, Defense Logistics Agency (DLA), and NASA AOD APIs, then produces a KML file (`T38 Apts DD Mon YYYY EXPIRES DD Mon YYYY.kml`) and an interactive HTML map. The KML file includes color-coded airport pins based on the data, helping with flight planning in ForeFlight or other EFBs. The HTML map auto-opens in your browser after each run, providing a zoomable, clickable view of all eligible airports.

---

## User-Friendly Version (GUI)

The GUI version (`GUI Files/`) is the recommended way to run the Planning Aid. It provides a polished, windowed interface with no terminal interaction required.

### Features

- Real-time progress bars for each data source (Airport & Runway Data, Chart Supplement/JASU, Recent T-38 Flights, Contract Fuel, Crew Comments)
- Status indicators turn green on completion, red on error
- **Map Legend** popup explaining all pin colors and inclusion logic
- **Credits** popup with project attribution
- Interactive HTML map auto-opens in your browser on completion
- Detects locked files (`wb_list.xlsx`, `T38_masterdict.xlsx`) and offers a **Try Again** button instead of crashing
- No console window — runs as a windowed application

### Getting the GUI (Easiest Way)

> **Note:** Windows may block unsigned `.exe` files. If the download doesn't work, just run the build_exe python script included in the main folder.

1. Go to the [latest release](https://github.com/erob1822/T38_Planning_Aid/releases/latest) and download the ZIP for your operating system
2. Extract the ZIP to a folder of your choice
3. Run `T-38 Planning Aid GUI.exe` from inside the extracted folder

No install or Python required. On first run the app downloads all data automatically. Subsequent runs reuse cached data.

> **Windows:** May show a SmartScreen warning — right-click → Keep → Keep anyway.

### Running the GUI from source

```cmd
cd "GUI Files"
python -m pip install -r requirements.txt
python T38_PlanAid_GUI.py
```

### Building the GUI exe

```cmd
cd "GUI Files"
python build_GUI_exe.py
```

This creates `T38 PlanAid GUI Distribution/` containing:
- The windowed `.exe` (no console)
- Bundled images (`RPLLogo.ico`, `NASAT38s.png`)
- A pre-populated `T38 Planning Aid/DATA/` folder with cached data

The build script automatically installs all dependencies including PyInstaller and Pillow.

### GUI Project Structure

| File | Purpose |
|------|---------|
| `GUI Files/T38_PlanAid_GUI.py` | Main GUI application — tkinter interface, threaded data pipeline, progress bars |
| `GUI Files/Data_Acquisition.py` | Downloads data from AOD, FAA, DLA APIs with 28/56-day cycle caching |
| `GUI Files/KML_Generator.py` | Builds airport database, generates KML, and creates interactive HTML map |
| `GUI Files/build_GUI_exe.py` | Builds standalone windowed `.exe` and packages distribution folder |
| `GUI Files/requirements.txt` | Python dependencies (includes Pillow for header images) |

---

## Developer Version (CLI)

The CLI version (root directory) runs in the terminal and is suited for developers, scripting, and automation. It produces identical output to the GUI version.

### Getting the CLI (Easiest Way)

> **Note:** Windows may block unsigned `.exe` files. If the download doesn't work, just run the build_exe python script included in the main folder.

1. Go to the [latest release](https://github.com/erob1822/T38_Planning_Aid/releases/latest) and download the ZIP for your operating system:
   - **Windows**: [**T38-PlanAid-Windows.zip**](https://github.com/erob1822/T38_Planning_Aid/releases/latest/download/T38-PlanAid-Windows.zip)
   - **Mac**: [**T38-PlanAid-Mac.zip**](https://github.com/erob1822/T38_Planning_Aid/releases/latest/download/T38-PlanAid-Mac.zip)
2. Extract the ZIP to a folder of your choice
3. Run `T-38 Planning Aid.exe` (Windows) or `T-38 Planning Aid` (Mac) from inside the extracted folder

No install or Python required. On first run the app downloads all data automatically and creates a `T38 Planning Aid/` folder next to itself. Subsequent runs reuse cached data if the folder is kept alongside the executable.

> **Mac users:** You may see an "unidentified developer" warning. Right-click the app → **Open** → click **Open** again. This is a one-time step.

### Running the CLI from source

```cmd
git clone https://github.com/erob1822/T38_Planning_Aid.git
cd T38_Planning_Aid
python -m pip install -r requirements.txt
python T38_PlanAid.py
```

### Building the CLI exe

```cmd
python build_exe.py
```

This creates `T38 PlanAid Distribution/` containing the exe and a pre-populated `T38 Planning Aid/` folder with cached data.

### CLI Project Structure

| File | Purpose |
|------|---------|
| `T38_PlanAid.py` | Master script — orchestrates everything. Contains all config (URLs, version, paths) |
| `Data_Acquisition.py` | Downloads data from AOD, FAA, DLA APIs with 28/56-day cycle caching |
| `KML_Generator.py` | Builds airport database, generates KML, and creates interactive HTML map |
| `build_exe.py` | Builds standalone `.exe` and packages distribution folder |
| `requirements.txt` | Python dependencies |

---

## Output

Both versions produce identical output in a `T38 Planning Aid/` folder:

```
T38 Planning Aid/
├── KML_Output/
│   ├── T38 Apts DD Mon YYYY EXPIRES DD Mon YYYY.kml   ← open in ForeFlight / Google Earth
│   ├── T38 Map DD Mon YYYY EXPIRES DD Mon YYYY.html   ← interactive browser map (auto-opens)
│   ├── T38_Airports.txt
│   └── T38_masterdict.xlsx
├── DATA/                                               ← cached FAA / DLA data
└── wb_list.xlsx                                        ← editable airport lists
```

- Open the `.kml` in **ForeFlight**, **Google Earth**, or [KMZView.com](https://kmzview.com)
- The interactive `.html` map auto-opens in your browser after each run

## Interactive Map

After each run, an interactive HTML map auto-opens in your default browser. It displays all eligible airports on an OpenStreetMap base layer with the same color-coded markers as the KML file. Click any marker for a popup with LDA, fuel, JASU status, category restrictions, and comments. The map can be zoomed, panned, and shared as a standalone `.html` file.

## Pin Colors

- **Green**: Recently landed by T-38 — known to work
- **Blue**: JASU listed but no recent ops — otherwise good to go
- **Yellow**: No JASU listed — call FBO to verify cart
- **Red diamond**: Category 2/3 — extra planning required
- **Red circle**: Category 1 — T-38 ops prohibited

## Quick Modifications

| To change... | Edit this |
|--------------|-----------|
| Version string on KML | `AppConfig.version` in the main script (`T38_PlanAid.py` or `T38_PlanAid_GUI.py`) |
| Minimum runway length | `KML_Generator.py` → search `# MODIFY: runway threshold` |
| Pin colors/logic | `KML_Generator.py` → search `# MODIFY: pin color` |
| Add/remove airports | `wb_list.xlsx` → BLACKLIST, WHITELIST, CAT_ONE/TWO/THREE columns |
| API URLs | `AppConfig` class variables in the main script |

## Dependencies

Install via `python -m pip install -r requirements.txt`. Key packages: `pandas`, `simplekml`, `folium`, `requests`, `requests-ntlm`, `openpyxl`, `PyMuPDF`, `colorlog`, `tqdm`. The GUI version additionally requires `Pillow` for header images.

## Troubleshooting

- **File locked / "Try Again" prompt (GUI)**: Close `wb_list.xlsx` or `T38_masterdict.xlsx` in Excel, then click **Try Again**. The GUI detects locked files and lets you retry without restarting.
- **File Issues**: `wb_list.xlsx` is auto-extracted on first run. If it gets corrupted, delete it from `T38 Planning Aid/` and the app will regenerate it. Revert to a backup if you've made custom edits.
- **URL Changes**: If FAA or DLA URLs change, update the endpoints in the `AppConfig` class.
- **API Issues**: Contact AOD IT if API paths are down or outdated. Update the relevant URL in `AppConfig`.

## Automated Release Builds (GitHub Actions)

The repo includes a GitHub Actions workflow (`.github/workflows/build-release.yml`) that automatically builds standalone executables for **both Windows and Mac** whenever a new release is published.

### How it works

1. A developer pushes code to `main` and creates a new **Release** on GitHub (Releases → Draft a new release → choose a tag like `v3.0` → Publish)
2. GitHub Actions spins up a **Windows** runner and a **macOS** runner in the cloud
3. Each runner installs Python, all dependencies, and PyInstaller, then builds the executable for its OS
4. The executables are packaged into ZIP files (`T38-PlanAid-Windows.zip` and `T38-PlanAid-Mac.zip`) alongside `wb_list.xlsx` and the `DATA/` folder
5. Both ZIPs are automatically attached to the Release as downloadable assets

### For users

Go to [Releases](https://github.com/erob1822/T38_Planning_Aid/releases), download the executable for your OS, and run it. No Python required.

- **Windows**: May show a SmartScreen warning — right-click the download → Keep → Keep anyway
- **Mac**: May show an "unidentified developer" warning — right-click the app → Open → Open again (one-time step)

### Manual trigger

You can also trigger a build manually without creating a release: go to the repo's **Actions** tab → **Build Release** → **Run workflow**. This is useful for testing the build without publishing a release.
