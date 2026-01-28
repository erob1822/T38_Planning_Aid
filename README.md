# T-38 PlanAid (Evans Edition)

Working parallel version of the T38_Planaid script designed to suggest efficiency improvements. Notably: uses only three scripts instead of five, with about half the lines of code. Also includes a 'build_exe.py' which automatically creates a distribution-ready .exe.

## For distribution/easiest .kml generation.

To create a standalone `.exe` for distribution:

```bash
python build_exe.py
```

This creates `T38 PlanAid Distribution/` containing:
- `T38_PlanAid.exe` - standalone executable
- `wb_list.xlsx` - airport lists (blacklist, whitelist, categories, comments)

KML output files are created in `KML_Output/` on first run.

Zip and distribute that folder. Pilots just double-click the exe and get a .kml file output.

## Quick Start (For Development)

```bash
pip install -r requirements.txt
python T38_PlanAid_E.py
```

Output: `T38 Apts {date}.kml` - usable in foreflight.

## Files

| File | Purpose |
|------|---------|
| `T38_PlanAid_E.py` | Master script - run this. Contains all config (URLs, version, paths) |
| `Data_Acquisition.py` | Downloads data from AOD, FAA, DLA APIs |
| `KML_Generator.py` | Builds airport database and generates KML |
| `wb_list.xlsx` | Blacklist, whitelist, categories, comments, recent landings |

## Quick modifications for other use cases

| To change... | Edit this |
|--------------|-----------|
| Version string on KML | `T38_PlanAid_E.py` → `AppConfig.version` |
| Minimum runway length | `KML_Generator.py` → search `# MODIFY: runway threshold` |
| Pin colors/logic | `KML_Generator.py` → search `# MODIFY: pin color` |
| Add/remove airports | `wb_list.xlsx` → BLACKLIST, WHITELIST, CAT_ONE/TWO/THREE columns |
| API URLs | `T38_PlanAid_E.py` → `AppConfig` class variables |

## Pin Colors

- **Blue**: JASU listed but no recent ops - otherwise good to go
- **Yellow**: No JASU listed - call FBO to verify cart
- **Green**: Recently landed by T-38 - known to work  
- **Red diamond**: Category 2/3 - extra planning required
- **Red circle**: Category 1 - T-38 ops prohibited

## Dependencies

See `requirements.txt`. Key packages: `pandas`, `simplekml`, `requests`, `PyMuPDF`
