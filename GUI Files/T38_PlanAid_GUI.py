"""
T38_PlanAid_GUI.py - GUI Version of T-38 PlanAid (Testing Only)

Replaces the command-window interface with a clean tkinter GUI showing
progress bars for each data-acquisition step. Designed for pilots —
only shows what they need to know.
"""

# Standard library imports
import shutil
import sys
import threading
import time
import warnings
import webbrowser
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import ClassVar
import tkinter as tk
from tkinter import ttk
import queue
import traceback

# Pillow is optional — used to render the RPL logo inside the window.
# The .ico file is always set as the window icon via tkinter natively.
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Local module imports
import Data_Acquisition
import KML_Generator


# ─────────────────────────────────────────────────────────────────────
#  tqdm shim — intercepts Data_Acquisition's tqdm calls so the GUI
#  can show real byte-level / iteration-level progress.
# ─────────────────────────────────────────────────────────────────────
_progress_callback = None        # set by the worker thread before each source
_progress_pct_base = 0.0         # where the download phase starts  (e.g. 0.20)
_progress_pct_span = 0.0         # how much of the bar the download fills (e.g. 0.55)

class _GUIProgressBar:
    """Drop-in replacement for tqdm that forwards progress to the GUI."""
    def __init__(self, iterable=None, *, total=None, **kwargs):
        self.iterable = iterable
        self.total = total or 0
        self.n = 0

    def update(self, n=1):
        self.n += n
        if _progress_callback and self.total:
            frac = min(self.n / self.total, 1.0)
            pct = _progress_pct_base + frac * _progress_pct_span
            _progress_callback(int(pct * 100))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def __iter__(self):
        if self.iterable is not None:
            for item in self.iterable:
                yield item
                self.update(1)

    # tqdm attributes that callers may touch
    def set_description(self, *a, **kw): pass
    def close(self): pass

# Monkey-patch tqdm inside Data_Acquisition
Data_Acquisition.tqdm = _GUIProgressBar

warnings.filterwarnings("ignore")

# --- Logging Setup (file-only, no console spam) ---
import logging

def setup_logging(output_folder):
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    log_filepath = output_folder / 'logfile.log'
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    log_filepath.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_filepath)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)-18s - %(levelname)-8s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    root_logger.addHandler(file_handler)
    return logging.getLogger(__name__)

# Get the directory where the exe/script is located
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
    BUNDLE_DIR = Path(sys._MEIPASS)          # PyInstaller temp extraction folder
else:
    APP_DIR = Path(__file__).parent
    BUNDLE_DIR = APP_DIR                      # Same folder when running from source


@dataclass
class AppConfig:
    """Configuration for T-38 PlanAid application."""
    version: ClassVar[str] = 'Version 3.0'
    aod_flights_api: ClassVar[str] = 'https://ndjsammweb.ndc.nasa.gov/Flightmetrics/api/cbdata/t38airports'
    aod_comments_url: ClassVar[str] = 'https://docs.google.com/spreadsheets/d/1AZypD2UHW65op0CSiMAlxwdjPq71B6LNIKk4n0crovI/export?format=csv&gid=0'
    years_included: ClassVar[int] = 4
    nasr_file_finder: ClassVar[str] = 'https://external-api.faa.gov/apra/nfdc/nasr/chart'
    dcs_file_finder: ClassVar[str] = 'https://external-api.faa.gov/apra/supplement/chart'
    dla_fuel_check: ClassVar[str] = 'https://cis.energy.dla.mil/ipcis/Ipcis'
    dla_fuel_download: ClassVar[str] = 'https://cis.energy.dla.mil/ipcis/Download?searchValue=UNITED%20STATES&field=REGION&recordType=100'
    app_dir: Path = field(default_factory=lambda: APP_DIR)
    work_dir: Path = field(default_factory=lambda: APP_DIR / 'T38 Planning Aid')
    data_folder: Path = field(default_factory=lambda: APP_DIR / 'T38 Planning Aid' / 'DATA')
    output_folder: Path = field(default_factory=lambda: APP_DIR / 'T38 Planning Aid' / 'KML_Output')

    def __post_init__(self):
        self.apt_data_dir = self.data_folder / 'apt_data'


# ─────────────────────────────────────────────────────────────────────
#  COLOR PALETTE & STYLING  (NASA / military feel)
# ─────────────────────────────────────────────────────────────────────
BG           = "#0B1426"     # deep navy background
BG_CARD      = "#111E36"     # slightly lighter card panels
FG           = "#E8ECF1"     # light grey text
FG_DIM       = "#7889A0"     # muted text
ACCENT       = "#2E86DE"     # blue accent (progress bar fill)
ACCENT_DONE  = "#27AE60"     # green when complete
ACCENT_ERR   = "#E74C3C"     # red on error
BORDER       = "#1C2D4A"     # subtle panel border
FONT_TITLE   = ("Segoe UI Semibold", 18)
FONT_STEP    = ("Segoe UI", 11)
FONT_STATUS  = ("Segoe UI", 10)
FONT_SMALL   = ("Segoe UI", 9)


# ─────────────────────────────────────────────────────────────────────
#  FRIENDLY STEP LABELS  (pilot-facing — no jargon)
# ─────────────────────────────────────────────────────────────────────
STEP_LABELS = {
    "nasr":     "Airport & Runway Data",
    "dcs":      "Chart Supplement / JASU",
    "flights":  "Recent T-38 Flights",
    "fuel":     "Contract Fuel Locations",
    "comments": "Crew Comments",
    "wb_list":  "Reference Data Update",
    "kml":      "Building KML File",
    "map":      "Building Interactive Map",
}

# Ordered sequence for the progress panel
STEP_ORDER = ["flights", "comments", "fuel", "nasr", "dcs", "wb_list", "kml", "map"]


# ─────────────────────────────────────────────────────────────────────
#  GUI APPLICATION
# ─────────────────────────────────────────────────────────────────────
class PlanAidGUI:
    """Classy, minimal GUI for T-38 PlanAid."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("T-38 Planning Aid")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        # Window icon
        ico_path = BUNDLE_DIR / "RPLLogo.ico"
        if ico_path.exists():
            self.root.iconbitmap(str(ico_path))

        # Center on screen
        self.win_w, win_h = 740, 620
        sx = (self.root.winfo_screenwidth() - self.win_w) // 2
        sy = (self.root.winfo_screenheight() - win_h) // 2
        self.root.geometry(f"{self.win_w}x{win_h}+{sx}+{sy}")

        # Message queue for thread-safe GUI updates
        self.msg_queue: queue.Queue = queue.Queue()

        # Track widgets for each step
        self.bars: dict[str, ttk.Progressbar] = {}
        self.labels: dict[str, tk.Label] = {}
        self.status_labels: dict[str, tk.Label] = {}
        self.pct_labels: dict[str, tk.Label] = {}

        self._build_styles()
        self._build_ui()

        # Start processing on the next event-loop tick
        self.root.after(300, self._start_work)
        # Poll the queue
        self.root.after(50, self._poll_queue)

    # ── Theming ──────────────────────────────────────────────────────
    def _build_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        # Progress bar – blue fill on dark trough
        style.configure(
            "NASA.Horizontal.TProgressbar",
            troughcolor=BG_CARD,
            background=ACCENT,
            thickness=14,
            borderwidth=0,
        )
        # Green-filled variant for completed bars
        style.configure(
            "Done.Horizontal.TProgressbar",
            troughcolor=BG_CARD,
            background=ACCENT_DONE,
            thickness=14,
            borderwidth=0,
        )
        # Error variant
        style.configure(
            "Err.Horizontal.TProgressbar",
            troughcolor=BG_CARD,
            background=ACCENT_ERR,
            thickness=14,
            borderwidth=0,
        )

    # ── Layout ───────────────────────────────────────────────────────
    def _build_ui(self):
        # ── Header row (T-38 left │ centered title │ RPL logo right) ─
        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", padx=24, pady=(20, 4))
        header.columnconfigure(1, weight=1)   # center column stretches

        # T-38 photo top-left
        self.t38_image = None
        banner_path = BUNDLE_DIR / "NASAT38s.png"
        if banner_path.exists() and HAS_PIL:
            try:
                t38 = Image.open(str(banner_path))
                ratio = 48 / t38.height
                t38 = t38.resize((int(t38.width * ratio), 48), Image.LANCZOS)
                self.t38_image = ImageTk.PhotoImage(t38)
                tk.Label(
                    header, image=self.t38_image, bg=BG
                ).grid(row=0, column=0, sticky="w")
            except Exception:
                pass

        # Centered title + version
        title_frame = tk.Frame(header, bg=BG)
        title_frame.grid(row=0, column=1)
        tk.Label(
            title_frame, text="T-38 Planning Aid", font=FONT_TITLE,
            fg=FG, bg=BG
        ).pack()
        tk.Label(
            title_frame, text=AppConfig.version, font=FONT_SMALL,
            fg=FG_DIM, bg=BG
        ).pack()

        # RPL logo top-right
        self.logo_image = None
        ico_path = BUNDLE_DIR / "RPLLogo.ico"
        if ico_path.exists() and HAS_PIL:
            try:
                img = Image.open(str(ico_path))
                img = img.resize((48, 48), Image.LANCZOS)
                self.logo_image = ImageTk.PhotoImage(img)
                tk.Label(
                    header, image=self.logo_image, bg=BG
                ).grid(row=0, column=2, sticky="e")
            except Exception:
                pass

        # ── Divider ─────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=24, pady=(8, 12))

        # ── Subtitle ────────────────────────────────────────────────
        tk.Label(
            self.root,
            text="Gathering data and building your flight-planning files…",
            font=FONT_STATUS, fg=FG_DIM, bg=BG, anchor="w"
        ).pack(fill="x", padx=28)

        # ── Step rows ───────────────────────────────────────────────
        container = tk.Frame(self.root, bg=BG)
        container.pack(fill="both", expand=True, padx=24, pady=(10, 6))

        for step in STEP_ORDER:
            row = tk.Frame(container, bg=BG)
            row.pack(fill="x", pady=6)

            lbl = tk.Label(
                row, text=STEP_LABELS[step], font=FONT_STEP,
                fg=FG, bg=BG, width=24, anchor="w"
            )
            lbl.pack(side="left")

            bar = ttk.Progressbar(
                row, orient="horizontal", length=260,
                mode="determinate", maximum=100, value=0,
                style="NASA.Horizontal.TProgressbar",
            )
            bar.pack(side="left", padx=(6, 10))

            pct_lbl = tk.Label(
                row, text="", font=FONT_SMALL,
                fg=FG_DIM, bg=BG, width=5, anchor="e"
            )
            pct_lbl.pack(side="left")

            stat = tk.Label(
                row, text="Waiting", font=FONT_SMALL,
                fg=FG_DIM, bg=BG, width=12, anchor="w"
            )
            stat.pack(side="left", padx=(4, 0))

            self.bars[step] = bar
            self.labels[step] = lbl
            self.status_labels[step] = stat
            self.pct_labels[step] = pct_lbl

        # ── Bottom status area ──────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=24, pady=(6, 0))

        self.bottom_frame = tk.Frame(self.root, bg=BG)
        self.bottom_frame.pack(fill="x", padx=24, pady=(10, 16))

        self.overall_label = tk.Label(
            self.bottom_frame, text="", font=FONT_STATUS,
            fg=FG, bg=BG, anchor="w", wraplength=580, justify="left"
        )
        self.overall_label.pack(side="left", fill="x", expand=True)

        tk.Button(
            self.bottom_frame, text="Credits", font=FONT_SMALL,
            fg=FG, bg="#3A4A6B", activebackground="#2C3B57",
            activeforeground=FG, bd=0, padx=12, pady=4,
            cursor="hand2", command=self._show_credits
        ).pack(side="right")

    # ── Thread-safe messaging ────────────────────────────────────────
    def _send(self, msg_type: str, **kwargs):
        """Put a message on the queue for the GUI thread to process."""
        self.msg_queue.put((msg_type, kwargs))

    def _poll_queue(self):
        """Drain the message queue and apply GUI updates."""
        try:
            while True:
                msg_type, kw = self.msg_queue.get_nowait()
                if msg_type == "step_progress":
                    self._on_step_progress(kw["step"], kw["pct"], kw.get("phase", ""))
                elif msg_type == "step_done":
                    self._on_step_done(kw["step"], kw.get("skipped", False))
                elif msg_type == "step_error":
                    self._on_step_error(kw["step"], kw.get("detail", ""))
                elif msg_type == "all_done":
                    self._on_all_done(kw.get("kml_path"), kw.get("map_path"))
                elif msg_type == "fatal":
                    self._on_fatal(kw.get("detail", ""))
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    # ── Step state callbacks ─────────────────────────────────────────
    def _on_step_progress(self, step, pct, phase=""):
        bar = self.bars[step]
        bar.configure(value=min(pct, 99))   # 100 only on "done"
        self.pct_labels[step].configure(text=f"{pct}%", fg=ACCENT)
        if phase:
            self.status_labels[step].configure(text=phase, fg=ACCENT)

    def _on_step_done(self, step, skipped=False):
        bar = self.bars[step]
        bar.configure(style="Done.Horizontal.TProgressbar", value=100)
        txt = "Cached ✓" if skipped else "Complete ✓"
        self.pct_labels[step].configure(text="100%", fg=ACCENT_DONE)
        self.status_labels[step].configure(text=txt, fg=ACCENT_DONE)

    def _on_step_error(self, step, detail=""):
        bar = self.bars[step]
        bar.configure(style="Err.Horizontal.TProgressbar", value=100)
        self.pct_labels[step].configure(text="—", fg=ACCENT_ERR)
        self.status_labels[step].configure(text="Error ✗", fg=ACCENT_ERR)

    def _on_all_done(self, kml_path=None, map_path=None):
        parts = ["All done!"]
        if kml_path:
            parts.append(f"KML → {Path(kml_path).name}")
        self.overall_label.configure(text="  ·  ".join(parts), fg=ACCENT_DONE)

        # Auto-open the interactive map in the default browser
        if map_path and Path(map_path).exists():
            webbrowser.open(Path(map_path).resolve().as_uri())

        # Add action buttons on a new row below the status text
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill="x", padx=24, pady=(4, 14))

        if map_path and Path(map_path).exists():
            tk.Button(
                btn_frame, text="Open Map Again", font=FONT_SMALL,
                fg=FG, bg=ACCENT, activebackground="#1A6DBF",
                activeforeground=FG, bd=0, padx=14, pady=4,
                cursor="hand2",
                command=lambda: webbrowser.open(Path(map_path).resolve().as_uri())
            ).pack(side="left", padx=(0, 10))

        if kml_path and Path(kml_path).exists():
            tk.Button(
                btn_frame, text="Open KML Folder", font=FONT_SMALL,
                fg=FG, bg="#3A4A6B", activebackground="#2C3B57",
                activeforeground=FG, bd=0, padx=14, pady=4,
                cursor="hand2",
                command=lambda: webbrowser.open(str(Path(kml_path).parent.resolve()))
            ).pack(side="left")

    def _on_fatal(self, detail):
        self.overall_label.configure(
            text=f"Error: {detail}  — check logfile.log for details.",
            fg=ACCENT_ERR,
        )

    # ── Credits popup ─────────────────────────────────────────────────
    def _show_credits(self):
        """Open a styled popup showing project credits."""
        win = tk.Toplevel(self.root)
        win.title("Credits — T-38 Planning Aid")
        win.configure(bg=BG)
        win.resizable(False, False)

        cw, ch = 560, 740
        sx = self.root.winfo_x() + (self.win_w - cw) // 2
        sy = self.root.winfo_y() + 20
        win.geometry(f"{cw}x{ch}+{sx}+{sy}")

        ico_path = BUNDLE_DIR / "RPLLogo.ico"
        if ico_path.exists():
            try:
                win.iconbitmap(str(ico_path))
            except Exception:
                pass

        tk.Label(
            win, text="T-38 Planning Aid", font=FONT_TITLE,
            fg=FG, bg=BG
        ).pack(pady=(18, 2))
        tk.Label(
            win, text=AppConfig.version, font=FONT_SMALL,
            fg=FG_DIM, bg=BG
        ).pack()

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(12, 10))

        # ── Developers ──
        tk.Label(
            win, text="RPL Military Interns", font=("Segoe UI Semibold", 12),
            fg=ACCENT, bg=BG
        ).pack(anchor="w", padx=30)

        devs = [
            "Nicholas Bostock",
            "Jacob Cates",
            "Alex Clark",
            "Alec Engl",
            "Ignatius Liberto",
            "Adrien Richez",
            "James Zuzelski",
            "Evan Robertson [Current Military Intern POC]",   
        ]
        for d in devs:
            tk.Label(
                win, text=f"  {d}", font=FONT_SMALL,
                fg=FG, bg=BG, anchor="w"
            ).pack(fill="x", padx=30, pady=1)

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(12, 10))

        # ── CB / AOD POCs ──
        tk.Label(
            win, text="CB / AOD POCs", font=("Segoe UI Semibold", 12),
            fg=ACCENT, bg=BG
        ).pack(anchor="w", padx=30)

        pocs = ["Sean Brady", "Dan Cochran", "Luke Delaney", "Jonny Kim"]
        for p in pocs:
            tk.Label(
                win, text=f"  {p}", font=FONT_SMALL,
                fg=FG, bg=BG, anchor="w"
            ).pack(fill="x", padx=30, pady=1)

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(12, 10))

        tk.Label(
            win, text="Built by the RPL at NASA Johnson Space Center. Go Navy, Beat Army!",
            font=FONT_SMALL, fg=FG_DIM, bg=BG
        ).pack(pady=(4, 6))

        # ── ASCII Art ──
        ascii_art = (
            "███████████████████       ██████████████████       ████\n"
            "  ███████████████████      ███████████████████     ████\n"
            "                 █████                    █████    ████\n"
            "                 █████                    ████     ████\n"
            "  ███████████████████      ██████████████████      ████\n"
            "  █████████████████        ███████████████         ████\n"
            "  ████         ██████      █████                   ███████████████████\n"
            "  ████           ██████     ████                   ██████████████████\n"
        )
        fly_nasa = (
            "███████╗██╗  ██╗   ██╗    ███╗   ██╗ █████╗ ███████╗ █████╗ ██╗\n"
            "██╔════╝██║  ╚██╗ ██╔╝    ████╗  ██║██╔══██╗██╔════╝██╔══██╗██║\n"
            "█████╗  ██║   ╚████╔╝     ██╔██╗ ██║███████║███████╗███████║██║\n"
            "██╔══╝  ██║    ╚██╔╝      ██║╚██╗██║██╔══██║╚════██║██╔══██║╚═╝\n"
            "██║     ███████╗██║       ██║ ╚████║██║  ██║███████║██║  ██║██╗\n"
            "╚═╝     ╚══════╝╚═╝       ╚═╝  ╚═══╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝\n"
        )

        ascii_frame = tk.Frame(win, bg=BG)
        ascii_frame.pack(pady=(6, 0))
        tk.Label(
            ascii_frame, text=ascii_art, font=("Consolas", 5),
            fg=ACCENT, bg=BG, justify="left"
        ).pack()
        tk.Label(
            ascii_frame, text=fly_nasa, font=("Consolas", 6),
            fg=FG, bg=BG, justify="left"
        ).pack(pady=(2, 0))

        tk.Button(
            win, text="Close", font=FONT_SMALL,
            fg=FG, bg="#3A4A6B", activebackground="#2C3B57",
            activeforeground=FG, bd=0, padx=20, pady=4,
            cursor="hand2", command=win.destroy
        ).pack(pady=(8, 16))

    # ── Background worker ────────────────────────────────────────────
    def _start_work(self):
        t = threading.Thread(target=self._run_pipeline, daemon=True)
        t.start()

    def _run_pipeline(self):
        cfg = AppConfig()
        logger = setup_logging(cfg.output_folder)

        # ── Pre-flight house-keeping (same as original main()) ──────
        try:
            wb_dest = cfg.work_dir / 'wb_list.xlsx'
            if not wb_dest.exists() and getattr(sys, 'frozen', False):
                cfg.work_dir.mkdir(parents=True, exist_ok=True)
                bundled = Path(sys._MEIPASS) / 'wb_list.xlsx'
                if bundled.exists():
                    shutil.copy2(bundled, wb_dest)

            # Migrate old cache
            old_data = cfg.app_dir / 'DATA'
            if old_data.exists() and old_data != cfg.data_folder:
                old_cache = old_data / 'Cache'
                old_json = old_data / 'data_download_cache.json'
                if old_cache.exists() and not (cfg.data_folder / 'Cache').exists():
                    cfg.data_folder.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(old_cache, cfg.data_folder / 'Cache')
                if old_json.exists() and not (cfg.data_folder / 'data_download_cache.json').exists():
                    cfg.data_folder.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(old_json, cfg.data_folder / 'data_download_cache.json')
            old_wb = cfg.app_dir / 'wb_list.xlsx'
            if old_wb.exists() and not wb_dest.exists():
                cfg.work_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(old_wb, wb_dest)

            # Clean working dirs (preserve cache)
            if cfg.data_folder.exists():
                cache_folder = cfg.data_folder / 'Cache'
                cache_json = cfg.data_folder / 'data_download_cache.json'
                for item in cfg.data_folder.iterdir():
                    if item != cache_folder and item != cache_json:
                        if item.is_dir():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
            cfg.data_folder.mkdir(parents=True, exist_ok=True)
            cfg.apt_data_dir.mkdir(parents=True, exist_ok=True)
            cfg.output_folder.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.exception("Pre-flight setup failed")
            self._send("fatal", detail=str(e))
            return

        # ── Data Acquisition (step-by-step with real progress) ──────
        try:
            cache_mgr = Data_Acquisition.CycleCache(cfg)

            for name in ["flights", "comments", "fuel", "nasr", "dcs"]:
                source = cache_mgr.sources.get(name)
                if source is None:
                    continue
                try:
                    self._run_source_with_progress(name, source, logger)
                except Exception as exc:
                    logger.exception(f"Source {name} failed")
                    self._send("step_error", step=name, detail=str(exc))

            cache_mgr._save_cache()

            # wb_list update
            self._send("step_progress", step="wb_list", pct=10, phase="Updating…")
            try:
                Data_Acquisition.update_wb_list(cfg)
                self._send("step_done", step="wb_list")
            except Exception as exc:
                logger.exception("wb_list update failed")
                self._send("step_error", step="wb_list", detail=str(exc))

        except Exception as e:
            logger.exception("Data acquisition failed")
            self._send("fatal", detail=str(e))
            return

        # ── KML Generation (with sub-phase progress) ────────────────
        kml_path = None
        map_path = None
        try:
            self._run_kml_with_progress(cfg, logger)
            kml_files = list(cfg.output_folder.glob("*.kml"))
            if kml_files:
                kml_path = str(max(kml_files, key=lambda f: f.stat().st_mtime))
            map_files = list(cfg.output_folder.glob("*.html"))
            if map_files:
                map_path = str(max(map_files, key=lambda f: f.stat().st_mtime))
        except Exception as e:
            logger.exception("KML/Map generation failed")
            self._send("step_error", step="kml", detail=str(e))
            self._send("step_error", step="map", detail=str(e))

        # ── Finished ────────────────────────────────────────────────
        self._send("all_done", kml_path=kml_path, map_path=map_path)

    # ── Per-source progress orchestration ────────────────────────────
    def _run_source_with_progress(self, name, source, logger):
        """Run a single DataSource with phased progress updates."""
        global _progress_callback, _progress_pct_base, _progress_pct_span

        # Phase 1: Check cycle (0 → 10%)
        self._send("step_progress", step=name, pct=5, phase="Checking…")
        source.check_cycle_status()
        self._send("step_progress", step=name, pct=10, phase="Checking…")

        # Phase 2: Check cache (10 → 20%)
        source.should_skip_download()
        self._send("step_progress", step=name, pct=20, phase="Cache check")

        if source.skip_download:
            # Still need to deploy cached data to the working directories
            if source.success and callable(source.deploy_method):
                deploy_msg = "Parsing FAA pubs. This may take a while…" if name == "dcs" else "Deploying…"
                self._send("step_progress", step=name, pct=60, phase=deploy_msg)
                try:
                    source.deploy_method(source)
                except Exception as e:
                    logger.error(f"[{name}] Deployment failed: {e}")
                    logger.debug(traceback.format_exc())
            self._send("step_done", step=name, skipped=True)
            return

        # Phase 3: Download (20 → 80%)  — tqdm hook provides byte-level updates
        self._send("step_progress", step=name, pct=20, phase="Downloading…")

        # Wire up the tqdm shim so it reports to this step
        _progress_pct_base = 0.20
        _progress_pct_span = 0.55
        _progress_callback = lambda pct: self._send(
            "step_progress", step=name, pct=pct, phase="Downloading…"
        )

        try:
            source.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            folder_name = source.current_cycle_date if source.current_cycle_date else source.timestamp
            source.download_subdir = source.source_cache_folder / folder_name
            source.download_subdir.mkdir(parents=True, exist_ok=True)
            source.download_method(source)
            source.success = True
            if source.current_cycle_date:
                source.downloaded_cycle_date = source.current_cycle_date
        except Exception as e:
            _progress_callback = None
            logger.error(f"[{name}] Download failed: {e}")
            logger.debug(traceback.format_exc())
            self._send("step_error", step=name, detail=str(e))
            return

        _progress_callback = None
        self._send("step_progress", step=name, pct=80, phase="Extracting…")

        # Phase 4: Deploy (80 → 100%)
        if source.success and callable(source.deploy_method):
            deploy_msg = "Parsing FAA pubs. This may take a while…" if name == "dcs" else "Deploying…"
            self._send("step_progress", step=name, pct=85, phase=deploy_msg)
            # Re-hook tqdm for JASU parsing (dcs step)
            _progress_pct_base = 0.85
            _progress_pct_span = 0.12
            _progress_callback = lambda pct: self._send(
                "step_progress", step=name, pct=pct, phase="Processing…"
            )
            try:
                source.deploy_method(source)
            except Exception as e:
                logger.error(f"[{name}] Deployment failed: {e}")
                logger.debug(traceback.format_exc())
            _progress_callback = None

        self._send("step_done", step=name)

    # ── KML / map progress orchestration ─────────────────────────────
    def _run_kml_with_progress(self, cfg, logger):
        """Run KML + map generation with progress reporting."""
        global DATA, OUTPUT, APP_DIR_KML

        # Point KML_Generator at the right folders
        KML_Generator.DATA = cfg.data_folder
        KML_Generator.OUTPUT = cfg.output_folder
        KML_Generator.APP_DIR = cfg.app_dir

        # Phase 1: Load data (0 → 30%)
        self._send("step_progress", step="kml", pct=5, phase="Loading data…")
        apt, rwy_lookup = KML_Generator.load_runway_data()
        self._send("step_progress", step="kml", pct=15, phase="Loading data…")
        fuel_set, jasu_set = KML_Generator.load_reference_sets()
        self._send("step_progress", step="kml", pct=20, phase="Loading data…")
        wb = KML_Generator.load_wb_list(cfg.work_dir / 'wb_list.xlsx')
        self._send("step_progress", step="kml", pct=30, phase="Loading data…")

        # Phase 2: Build master dict (30 → 50%)
        self._send("step_progress", step="kml", pct=35, phase="Building dict…")
        master_dict = KML_Generator.build_master_dict(apt, rwy_lookup, fuel_set, jasu_set, wb)
        self._send("step_progress", step="kml", pct=50, phase="Building dict…")

        # Save master dict
        import pandas as pd
        pd.DataFrame.from_dict(master_dict, orient='index').to_excel(
            cfg.output_folder / 'T38_masterdict.xlsx'
        )
        self._send("step_progress", step="kml", pct=55, phase="Saved Excel")

        # Phase 3: Generate KML (55 → 80%)
        self._send("step_progress", step="kml", pct=60, phase="Writing KML…")
        date_str = KML_Generator.get_date_string()
        exp_str = KML_Generator.get_expiration_string()
        num_airports = KML_Generator.generate_kml(master_dict, wb, date_str, cfg.version, exp_str)
        self._send("step_progress", step="kml", pct=85, phase=f"{num_airports} airports")
        self._send("step_done", step="kml")

        # Phase 4: Generate map (0 → 100%)
        self._send("step_progress", step="map", pct=10, phase="Rendering…")
        KML_Generator.generate_map(master_dict, date_str, exp_str)
        self._send("step_done", step="map")

    # ── Run ──────────────────────────────────────────────────────────
    def run(self):
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = PlanAidGUI()
    app.run()
