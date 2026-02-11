
"""
T38_PlanAid_GUI.py - Graphical User Interface for T-38 PlanAid

This script provides a user-friendly GUI for the T-38 Planning Aid application.
It replaces the old command-line interface with a windowed application that guides users
through each step of the data acquisition and KML/map generation process. The GUI displays
progress bars, status messages, and provides interactive popups for map legends and credits.

Key features:
- Step-by-step progress tracking for all data sources (flights, comments, fuel, etc.)
- Visual feedback for each phase (downloading, extracting, deploying, etc.)
- Automatic handling of file locks and retry logic for Excel files
- Popups for map legend and project credits
- Designed for users who may not be familiar with the underlying code or command-line tools
"""

# Standard library imports
###############################################################
# These modules provide core functionality for threading, file
# operations, GUI creation, and more. Most are built into Python.
###############################################################
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
# If Pillow is installed, we use it to display images in the GUI (e.g., logos).
# If not, the GUI still works, but without image support.
# The .ico file is always set as the window icon via tkinter natively.
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Heavy modules (Data_Acquisition, KML_Generator) are lazy-loaded
# in the worker thread so the GUI window appears instantly.
# These modules do the heavy lifting for data download and KML/map generation.
# We import them only when needed, so the GUI appears quickly for the user.
Data_Acquisition = None
KML_Generator = None


# ─────────────────────────────────────────────────────────────────────
#  tqdm shim — intercepts Data_Acquisition's tqdm calls so the GUI
#  can show real byte-level / iteration-level progress.
# The following class and variables allow us to intercept progress updates
# from the data acquisition process and display them in the GUI, instead of
# the console.
# ─────────────────────────────────────────────────────────────────────
_progress_callback = None        # set by the worker thread before each source
_progress_pct_base = 0.0         # where the download phase starts  (e.g. 0.20)
_progress_pct_span = 0.0         # how much of the bar the download fills (e.g. 0.55)

class _GUIProgressBar:
    """
    Drop-in replacement for tqdm that forwards progress to the GUI.
    This class mimics the tqdm progress bar used in the console version,
    but instead, it sends progress updates to the GUI so users can see
    real-time feedback for downloads and processing steps.
    """
    def __init__(self, iterable=None, *, total=None, **kwargs):
        self.iterable = iterable
        self.total = total or 0
        self.n = 0
        self._last_pct = -1     # throttle: only fire when % changes

    def update(self, n=1):
        self.n += n
        if _progress_callback and self.total:
            frac = min(self.n / self.total, 1.0)
            pct = int((_progress_pct_base + frac * _progress_pct_span) * 100)
            if pct != self._last_pct:
                self._last_pct = pct
                _progress_callback(pct)

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

def _lazy_import_heavy_modules():
    """
    Import heavy third-party modules in the worker thread, not at startup.
    This ensures the GUI window appears almost instantly, even if the
    underlying modules (like pandas, fitz, folium, requests) take a long
    time to load. This is especially important for users running the
    application as a bundled executable.
    """
    global Data_Acquisition, KML_Generator
    import Data_Acquisition as _DA
    import KML_Generator as _KG
    Data_Acquisition = _DA
    KML_Generator = _KG
    # Apply the tqdm shim so download progress routes through the GUI
    Data_Acquisition.tqdm = _GUIProgressBar

warnings.filterwarnings("ignore")

# --- Logging Setup (file-only, no console spam) ---
# All log messages are written to a file in the output folder.
# This avoids cluttering the user's screen with technical details,
# but still provides a way to diagnose problems if needed.
import logging

def setup_logging(output_folder):
        # Set up logging to a file in the output folder. No console output.
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

# This logic ensures the application can find its resources whether
# it's running as a standalone executable or as a Python script.
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
    BUNDLE_DIR = Path(sys._MEIPASS)          # PyInstaller temp extraction folder
else:
    APP_DIR = Path(__file__).parent
    BUNDLE_DIR = APP_DIR                      # Same folder when running from source


@dataclass
class AppConfig:
    """
    Configuration for T-38 PlanAid application.
    Holds all paths, URLs, and settings needed throughout the app.
    This makes it easy to update configuration in one place and
    ensures consistency across the codebase.
    """
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
#  COLOR PALETTE & STYLING 
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
# These labels are shown to the user for each step
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
    """
    Main GUI class for T-38 PlanAid.

    """

    def __init__(self):
        ###############################################################
        # GUI Initialization
        # This section sets up the main window, loads images, builds
        # the layout, and prepares the application for user interaction.
        ###############################################################
        # Create the main application window and set its properties
        self.root = tk.Tk()
        self.root.title("T-38 Planning Aid")
        self.root.configure(bg=BG)
        self.root.resizable(False, False)

        # Set the window icon if available
        ico_path = BUNDLE_DIR / "RPLLogo.ico"
        if ico_path.exists():
            self.root.iconbitmap(str(ico_path))


        # Center the window on the user's screen
        self.win_w, win_h = 740, 620
        sx = (self.root.winfo_screenwidth() - self.win_w) // 2
        sy = (self.root.winfo_screenheight() - win_h) // 2
        self.root.geometry(f"{self.win_w}x{win_h}+{sx}+{sy}")

        # Create a thread-safe queue for communication between worker threads and the GUI
        self.msg_queue: queue.Queue = queue.Queue()


        # Dictionaries to hold references to progress bars, labels, and status indicators for each step
        self.bars: dict[str, ttk.Progressbar] = {}
        self.labels: dict[str, tk.Label] = {}
        self.status_labels: dict[str, tk.Label] = {}
        self.pct_labels: dict[str, tk.Label] = {}

        # Internal state for retry logic and configuration
        self._cfg = None
        self._logger = None
        self._retry_btn_frame: tk.Frame | None = None

        # Pre-load images for popups to avoid disk I/O during user interaction
        self._popup_t38_img = None   # 40px T-38 banner for popups
        self._popup_logo_img = None  # 40px RPL logo for popups
        self._load_popup_images()

        # Build the visual style and layout of the GUI
        self._build_styles()
        self._build_ui()

        # Start the data processing pipeline after the GUI is ready
        self.root.after(300, self._start_work)
        # Begin polling the message queue for updates from worker threads
        self.root.after(50, self._poll_queue)

    # ── Theming ──────────────────────────────────────────────────────
    def _build_styles(self):
        """
        Set up the color scheme and style for all GUI widgets, including
        progress bars and buttons, to ensure a consistent and visually
        appealing user experience.
        """
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

    def _load_popup_images(self):
        """
        Load and resize images for use in popup dialogs (legend, credits).
        This is done once at startup to avoid delays when the user opens a popup.
        """

        if not HAS_PIL:
            return
        banner_path = BUNDLE_DIR / "NASAT38s.png"
        if banner_path.exists():
            try:
                t38 = Image.open(str(banner_path))
                ratio = 40 / t38.height
                t38 = t38.resize((int(t38.width * ratio), 40), Image.LANCZOS)
                self._popup_t38_img = ImageTk.PhotoImage(t38)
            except Exception:
                pass
        ico_path = BUNDLE_DIR / "RPLLogo.ico"
        if ico_path.exists():
            try:
                img = Image.open(str(ico_path))
                img = img.resize((40, 40), Image.LANCZOS)
                self._popup_logo_img = ImageTk.PhotoImage(img)
            except Exception:
                pass

    # ── Layout ───────────────────────────────────────────────────────
    def _build_ui(self):
        """
        Construct the main layout of the application window, including
        header, progress bars for each step, status area, and action buttons.
        Each section is carefully organized for clarity and ease of use.
        """
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

            # ── Dedicated parsing sub-row (hidden until DCS parsing begins) ──
            if step == "dcs":
                self.parse_row = tk.Frame(container, bg=BG)
                # Don't pack yet — shown dynamically via "parse_show" message

                self.parse_label = tk.Label(
                    self.parse_row, text="   ↳ Parsing Publications", font=FONT_SMALL,
                    fg=FG_DIM, bg=BG, width=24, anchor="w"
                )
                self.parse_label.pack(side="left")

                self.parse_bar = ttk.Progressbar(
                    self.parse_row, orient="horizontal", length=260,
                    mode="determinate", maximum=100, value=0,
                    style="NASA.Horizontal.TProgressbar",
                )
                self.parse_bar.pack(side="left", padx=(6, 10))

                self.parse_pct = tk.Label(
                    self.parse_row, text="", font=FONT_SMALL,
                    fg=FG_DIM, bg=BG, width=5, anchor="e"
                )
                self.parse_pct.pack(side="left")

                self.parse_status = tk.Label(
                    self.parse_row, text="", font=FONT_SMALL,
                    fg=FG_DIM, bg=BG, width=18, anchor="w"
                )
                self.parse_status.pack(side="left", padx=(4, 0))

                self._parse_row_visible = False

        # ── Bottom status area ──────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=24, pady=(6, 0))

        self.bottom_frame = tk.Frame(self.root, bg=BG)
        self.bottom_frame.pack(fill="x", padx=24, pady=(10, 16))

        self.overall_label = tk.Label(
            self.bottom_frame, text="", font=FONT_STATUS,
            fg=FG, bg=BG, anchor="w", wraplength=580, justify="left"
        )
        self.overall_label.pack(side="left", fill="x", expand=True)

        # Right-side button stack (Map Legend above Credits)
        btn_stack = tk.Frame(self.bottom_frame, bg=BG)
        btn_stack.pack(side="right")

        tk.Button(
            btn_stack, text="Map Legend", font=FONT_SMALL,
            fg=FG, bg="#3A4A6B", activebackground="#2C3B57",
            activeforeground=FG, bd=0, padx=12, pady=4,
            cursor="hand2", command=self._show_legend
        ).pack(pady=(0, 4))

        tk.Button(
            btn_stack, text="Credits", font=FONT_SMALL,
            fg=FG, bg="#3A4A6B", activebackground="#2C3B57",
            activeforeground=FG, bd=0, padx=12, pady=4,
            cursor="hand2", command=self._show_credits
        ).pack()

    # ── Thread-safe messaging ────────────────────────────────────────
    def _send(self, msg_type: str, **kwargs):
        """
        Place a message in the queue for the GUI thread to process.
        This allows background threads to safely update the GUI without
        causing thread-safety issues or crashes.
        """

        self.msg_queue.put((msg_type, kwargs))

    def _poll_queue(self):
        """
        Continuously check the message queue for updates from worker threads.
        Applies progress updates, error messages, and status changes to the GUI.
        This keeps the interface responsive and up-to-date for the user.
        """

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
                elif msg_type == "overall_msg":
                    self.overall_label.configure(text=kw.get("text", ""), fg=FG_DIM)
                elif msg_type == "parse_show":
                    self._on_parse_show()
                elif msg_type == "parse_progress":
                    self._on_parse_progress(kw["current"], kw["total"], kw.get("name", ""))
                elif msg_type == "parse_done":
                    self._on_parse_done()
                elif msg_type == "wb_locked":
                    self._on_wb_locked(kw.get("detail", ""))
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    # ── Step state callbacks ─────────────────────────────────────────
    def _on_step_progress(self, step, pct, phase=""):
        """
        Update the progress bar and status label for a given step.
        This provides real-time feedback to the user about what is happening.
        """
        bar = self.bars[step]
        bar.configure(value=min(pct, 99))   # 100 only on "done"
        self.pct_labels[step].configure(text=f"{pct}%", fg=ACCENT)
        if phase:
            self.status_labels[step].configure(text=phase, fg=ACCENT)

    def _on_step_done(self, step, skipped=False):
        """
        Mark a step as complete in the GUI, updating the bar and label.
        Indicates to the user that this phase has finished successfully.
        """
        bar = self.bars[step]
        bar.configure(style="Done.Horizontal.TProgressbar", value=100)
        txt = "Cached ✓" if skipped else "Complete ✓"
        self.pct_labels[step].configure(text="100%", fg=ACCENT_DONE)
        self.status_labels[step].configure(text=txt, fg=ACCENT_DONE)

    def _on_step_error(self, step, detail=""):
        """
        Mark a step as failed in the GUI, showing an error color and message.
        This helps the user quickly identify which part of the process needs attention.
        """
        bar = self.bars[step]
        bar.configure(style="Err.Horizontal.TProgressbar", value=100)
        self.pct_labels[step].configure(text="—", fg=ACCENT_ERR)
        self.status_labels[step].configure(text="Error ✗", fg=ACCENT_ERR)

    # ── Dedicated parsing sub-bar callbacks ──────────────────────────
    def _on_parse_show(self):
        """
        Display the parsing progress bar for the DCS step, which involves
        processing multiple PDF files. This gives the user detailed feedback
        during a complex phase.
        """

        if not self._parse_row_visible:
            # Insert right after the DCS row by packing in order
            # pack_after isn't available, but we stored dcs row ref.
            # We'll use pack() — it will appear after all currently packed rows,
            # so we re-pack remaining rows after it.  Simpler: just pack it
            # right now; since step rows are packed in STEP_ORDER the dcs row
            # already exists and the remaining rows haven't changed.
            # We need to insert it after the dcs row.  We'll use the Tk
            # pack 'after' option.
            dcs_frame = self.bars["dcs"].master  # the row Frame
            self.parse_row.pack(fill="x", pady=(0, 4), after=dcs_frame)
            self._parse_row_visible = True

    def _on_parse_progress(self, current, total, name=""):
        """
        Update the parsing sub-bar with the current progress through PDF files.
        Shows the user exactly which file is being processed and how many remain.
        """
        pct = int((current / total) * 100) if total else 0
        self.parse_bar.configure(value=min(pct, 99))
        self.parse_pct.configure(text=f"{pct}%", fg=ACCENT)
        self.parse_status.configure(text=f"{current}/{total}  {name}", fg=ACCENT)

    def _on_parse_done(self):
        """
        Mark the parsing sub-bar as complete, indicating all files have been processed.
        """
        self.parse_bar.configure(style="Done.Horizontal.TProgressbar", value=100)
        self.parse_pct.configure(text="100%", fg=ACCENT_DONE)
        self.parse_status.configure(text="Complete ✓", fg=ACCENT_DONE)

    def _on_all_done(self, kml_path=None, map_path=None):
        """
        Called when all steps are finished. Updates the status area, opens the
        generated map in the browser, and provides buttons for further actions.
        """
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
        """
        Display a fatal error message in the GUI, instructing the user to check the log file.
        """
        self.overall_label.configure(
            text=f"Error: {detail}  — check logfile.log for details.",
            fg=ACCENT_ERR,
        )

    def _on_wb_locked(self, detail=""):
        """
        Handle the case where the Excel workbook is open in another program.
        Prompts the user to close the file and try again, preventing data corruption.
        """

        # Mark wb_list and downstream steps as errored
        for step in ("wb_list", "kml", "map"):
            if self.bars[step].cget("value") < 100:
                self._on_step_error(step, "File locked")

        # Build a user-friendly message that names the locked file
        if "masterdict" in detail.lower():
            file_hint = "T38_masterdict.xlsx"
        else:
            file_hint = "wb_list.xlsx"
        self.overall_label.configure(
            text=f"{file_hint} is open in another program (Excel?). "
                 "Please close it and click Try Again.",
            fg=ACCENT_ERR,
        )

        # Remove any previous retry button frame
        if self._retry_btn_frame is not None:
            self._retry_btn_frame.destroy()

        self._retry_btn_frame = tk.Frame(self.root, bg=BG)
        self._retry_btn_frame.pack(fill="x", padx=24, pady=(4, 14))

        tk.Button(
            self._retry_btn_frame, text="Try Again", font=FONT_SMALL,
            fg=FG, bg=ACCENT, activebackground="#1A6DBF",
            activeforeground=FG, bd=0, padx=18, pady=5,
            cursor="hand2",
            command=self._retry_from_wb_list,
        ).pack(side="left")

    def _retry_from_wb_list(self):
        """
        Retry the wb_list update and KML/map generation after the user closes the locked file.
        Resets the relevant progress bars and restarts the worker thread for these steps.
        """
        # Clean up the retry button
        if self._retry_btn_frame is not None:
            self._retry_btn_frame.destroy()
            self._retry_btn_frame = None

        # Reset progress bars for the steps we're retrying
        for step in ("wb_list", "kml", "map"):
            self.bars[step].configure(
                style="NASA.Horizontal.TProgressbar", value=0
            )
            self.pct_labels[step].configure(text="", fg=FG_DIM)
            self.status_labels[step].configure(text="Retrying…", fg=ACCENT)

        self.overall_label.configure(text="Retrying…", fg=FG_DIM)

        t = threading.Thread(
            target=self._run_wb_and_kml, daemon=True
        )
        t.start()

    def _run_wb_and_kml(self):
        """
        Worker thread: re-run the wb_list update and KML/map build after a retry.
        This allows the user to recover from file lock errors without restarting the app.
        """

        cfg = self._cfg
        logger = self._logger
        if cfg is None or logger is None:
            self._send("fatal", detail="Internal error: missing config for retry.")
            return

        # ── wb_list update ──────────────────────────────────────────
        self._send("step_progress", step="wb_list", pct=10, phase="Updating…")
        try:
            Data_Acquisition.update_wb_list(cfg)
            self._send("step_done", step="wb_list")
        except PermissionError:
            logger.exception("wb_list.xlsx is still locked")
            self._send("wb_locked", detail="wb_list.xlsx is still open")
            return
        except Exception as exc:
            logger.exception("wb_list update failed on retry")
            self._send("step_error", step="wb_list", detail=str(exc))
            return  # Don't generate KML from stale/missing data

        # ── KML / Map ───────────────────────────────────────────────
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
        except PermissionError:
            logger.exception("KML generation failed — wb_list.xlsx still locked")
            self._send("wb_locked", detail="wb_list.xlsx is still open")
            return
        except Exception as e:
            logger.exception("KML/Map generation failed on retry")
            self._send("step_error", step="kml", detail=str(e))
            self._send("step_error", step="map", detail=str(e))

        self._send("all_done", kml_path=kml_path, map_path=map_path)

    # ── Map Legend popup ──────────────────────────────────────────────
    def _show_legend(self):
        """
        Open a popup window showing the map legend, including pin color meanings
        and airport inclusion criteria. Helps users interpret the generated map.
        """
        win = tk.Toplevel(self.root)
        win.title("Map Legend — T-38 Planning Aid")
        win.configure(bg=BG)
        win.resizable(False, False)

        cw, ch = 620, 700
        sx = self.root.winfo_x() + (self.win_w - cw) // 2
        sy = self.root.winfo_y() + 10
        win.geometry(f"{cw}x{ch}+{sx}+{sy}")

        ico_path = BUNDLE_DIR / "RPLLogo.ico"
        if ico_path.exists():
            try:
                win.iconbitmap(str(ico_path))
            except Exception:
                pass

        # ── Header row with T-38 photo + title + RPL logo ──
        leg_header = tk.Frame(win, bg=BG)
        leg_header.pack(fill="x", padx=24, pady=(18, 2))
        leg_header.columnconfigure(1, weight=1)

        # T-38 photo (left) — use cached image
        if self._popup_t38_img:
            tk.Label(
                leg_header, image=self._popup_t38_img, bg=BG
            ).grid(row=0, column=0, sticky="w")

        # Centered title
        leg_title = tk.Frame(leg_header, bg=BG)
        leg_title.grid(row=0, column=1)
        tk.Label(
            leg_title, text="Map Legend", font=FONT_TITLE,
            fg=FG, bg=BG
        ).pack()
        tk.Label(
            leg_title, text="Pin Color Reference", font=FONT_SMALL,
            fg=FG_DIM, bg=BG
        ).pack()

        # RPL logo (right) — use cached image
        if self._popup_logo_img:
            tk.Label(
                leg_header, image=self._popup_logo_img, bg=BG
            ).grid(row=0, column=2, sticky="e")

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(12, 10))

        # ── Inclusion criteria ──
        tk.Label(
            win, text="Airport Inclusion Criteria", font=("Segoe UI Semibold", 12),
            fg=ACCENT, bg=BG
        ).pack(anchor="w", padx=30)

        criteria = [
            "• Must be in CONUS with a valid ICAO identifier (K___)",
            "• Longest declared LDA must be ≥ 7,000 ft",
            "• Must have government contract fuel on file",
        ]
        for c in criteria:
            tk.Label(
                win, text=c, font=FONT_SMALL,
                fg=FG, bg=BG, anchor="w"
            ).pack(fill="x", padx=36, pady=1)

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(12, 10))

        # ── Pin color legend ──
        tk.Label(
            win, text="Pin Colors", font=("Segoe UI Semibold", 12),
            fg=ACCENT, bg=BG
        ).pack(anchor="w", padx=30)

        # (color_swatch, label, description)
        pins = [
            ("#27AE60", "Green Pushpin",
             "Recently landed by a T-38 crew (no issues flagged), "
             "OR airport is on the Whitelist. Known to work — call FBO to confirm."),
            ("#2E86DE", "Blue Pushpin",
             "JASU (air-start cart) is listed in the A/FD but no recent T-38 ops. "
             "Good to go — call FBO to verify cart availability."),
            ("#F1C40F", "Yellow Pushpin",
             "No JASU listed in the A/FD and no recent T-38 ops. "
             "Call FBO to verify start-cart availability before planning."),
            ("#E74C3C", "Red Diamond  (Category 2 / 3)",
             "Airport is categorized as Cat 2 or Cat 3. "
             "Requires extra planning and/or approval before use."),
            ("#C0392B", "Red Circle  (Category 1)",
             "Category 1 airport — T-38 operations are prohibited."),
            ("#922B21", "Red Pushpin  (Blacklisted)",
             "Blacklisted airport — T-38 operations not authorized."),
        ]

        for color_hex, title, desc in pins:
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", padx=30, pady=4)

            # Color swatch
            swatch = tk.Canvas(row, width=18, height=18, bg=BG,
                               highlightthickness=0)
            swatch.pack(side="left", padx=(0, 8), pady=2)
            swatch.create_oval(2, 2, 16, 16, fill=color_hex, outline=color_hex)

            # Text
            text_frame = tk.Frame(row, bg=BG)
            text_frame.pack(side="left", fill="x", expand=True)
            tk.Label(
                text_frame, text=title, font=("Segoe UI Semibold", 10),
                fg=FG, bg=BG, anchor="w"
            ).pack(anchor="w")
            tk.Label(
                text_frame, text=desc, font=FONT_SMALL,
                fg=FG_DIM, bg=BG, anchor="w", wraplength=480, justify="left"
            ).pack(anchor="w")

        tk.Frame(win, bg=BORDER, height=1).pack(fill="x", padx=30, pady=(12, 10))

        # ── Close button ──
        tk.Button(
            win, text="Close", font=FONT_SMALL,
            fg=FG, bg="#3A4A6B", activebackground="#2C3B57",
            activeforeground=FG, bd=0, padx=20, pady=4,
            cursor="hand2", command=win.destroy
        ).pack(pady=(12, 16))

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

        # ── Header row with T-38 photo + title + RPL logo ──
        cred_header = tk.Frame(win, bg=BG)
        cred_header.pack(fill="x", padx=24, pady=(18, 2))
        cred_header.columnconfigure(1, weight=1)

        # T-38 photo (left) — use cached image
        if self._popup_t38_img:
            tk.Label(
                cred_header, image=self._popup_t38_img, bg=BG
            ).grid(row=0, column=0, sticky="w")

        # Centered title + version
        cred_title = tk.Frame(cred_header, bg=BG)
        cred_title.grid(row=0, column=1)
        tk.Label(
            cred_title, text="T-38 Planning Aid", font=FONT_TITLE,
            fg=FG, bg=BG
        ).pack()
        tk.Label(
            cred_title, text=AppConfig.version, font=FONT_SMALL,
            fg=FG_DIM, bg=BG
        ).pack()

        # RPL logo (right) — use cached image
        if self._popup_logo_img:
            tk.Label(
                cred_header, image=self._popup_logo_img, bg=BG
            ).grid(row=0, column=2, sticky="e")

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
        """
        Start the background thread that runs the main data processing pipeline.
        This keeps the GUI responsive while heavy work is done in the background.
        """
        t = threading.Thread(target=self._run_pipeline, daemon=True)
        t.start()

    def _run_pipeline(self):
        """
        Main worker function that runs the entire data acquisition and KML/map generation pipeline.
        Handles all steps in order, updating the GUI as each phase progresses.
        Includes error handling and retry logic for a robust user experience.
        """
        # Lazy-load heavy modules (pandas, fitz, folium, etc.)
        # so the GUI window appears immediately on startup.
        self._send("overall_msg", text="Loading modules…")
        _lazy_import_heavy_modules()
        self._send("overall_msg", text="")

        cfg = AppConfig()
        logger = setup_logging(cfg.output_folder)
        self._cfg = cfg
        self._logger = logger

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

            # Run small/fast sources in parallel, then big FAA sources sequentially
            small_sources = ["flights", "comments", "fuel"]
            big_sources = ["nasr", "dcs"]

            def _run_one(name):
                source = cache_mgr.sources.get(name)
                if source is None:
                    return
                try:
                    self._run_source_with_progress(name, source, logger)
                except Exception as exc:
                    logger.exception(f"Source {name} failed")
                    self._send("step_error", step=name, detail=str(exc))

            with Data_Acquisition.ThreadPoolExecutor(max_workers=3) as pool:
                pool.map(_run_one, small_sources)

            for name in big_sources:
                _run_one(name)

            cache_mgr._save_cache()

            # wb_list update
            self._send("step_progress", step="wb_list", pct=10, phase="Updating…")
            try:
                Data_Acquisition.update_wb_list(cfg)
                self._send("step_done", step="wb_list")
            except PermissionError as exc:
                logger.exception("wb_list.xlsx is locked by another process")
                self._send("wb_locked", detail=str(exc))
                return  # Stop pipeline — user must close the file first
            except Exception as exc:
                logger.exception("wb_list update failed")
                self._send("step_error", step="wb_list", detail=str(exc))
                return  # Don't generate KML from stale/missing data

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
        except PermissionError as e:
            logger.exception("KML generation failed — wb_list.xlsx appears locked")
            self._send("wb_locked", detail=str(e))
            return
        except Exception as e:
            logger.exception("KML/Map generation failed")
            self._send("step_error", step="kml", detail=str(e))
            self._send("step_error", step="map", detail=str(e))

        # ── Finished ────────────────────────────────────────────────
        self._send("all_done", kml_path=kml_path, map_path=map_path)

    # ── Per-source progress orchestration ────────────────────────────
    def _run_source_with_progress(self, name, source, logger):
        """
        Run a single data source step (e.g., flights, comments, fuel, nasr, dcs),
        updating the GUI with progress for each phase (checking, downloading, deploying).
        Handles both cached and fresh downloads, and manages sub-progress for complex steps.
        """

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
                deploy_msg = "Parsing pubs..." if name == "dcs" else "Deploying…"
                self._send("step_progress", step=name, pct=60, phase=deploy_msg)
                # Wire dedicated parsing bar for DCS
                if name == "dcs":
                    self._send("parse_show")
                    source._parse_progress_cb = lambda i, t, pdf: self._send(
                        "parse_progress", current=i, total=t, name=pdf
                    )
                try:
                    source.deploy_method(source)
                except Exception as e:
                    logger.error(f"[{name}] Deployment failed: {e}")
                    logger.debug(traceback.format_exc())
                finally:
                    if hasattr(source, '_parse_progress_cb'):
                        del source._parse_progress_cb
                    if name == "dcs":
                        self._send("parse_done")
            self._send("step_done", step=name, skipped=True)
            return

        # Phase 3: Download (20 → 80%)  — tqdm hook provides byte-level updates
        self._send("step_progress", step=name, pct=20, phase="Downloading…")

        # Wire up the tqdm shim for sources that stream large zips (nasr, dcs)
        if name in ("nasr", "dcs"):
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
            deploy_msg = "Parsing pubs..." if name == "dcs" else "Deploying…"
            self._send("step_progress", step=name, pct=85, phase=deploy_msg)
            # For non-DCS steps, keep tqdm shim for deploy progress
            if name != "dcs":
                _progress_pct_base = 0.85
                _progress_pct_span = 0.12
                _progress_callback = lambda pct: self._send(
                    "step_progress", step=name, pct=pct, phase="Deploying…"
                )
            else:
                # DCS: use dedicated parsing sub-bar instead of tqdm shim
                self._send("parse_show")
                source._parse_progress_cb = lambda i, t, pdf: self._send(
                    "parse_progress", current=i, total=t, name=pdf
                )
            try:
                source.deploy_method(source)
            except Exception as e:
                logger.error(f"[{name}] Deployment failed: {e}")
                logger.debug(traceback.format_exc())
            finally:
                _progress_callback = None
                if hasattr(source, '_parse_progress_cb'):
                    del source._parse_progress_cb
                if name == "dcs":
                    self._send("parse_done")

        self._send("step_done", step=name)

    # ── KML / map progress orchestration ─────────────────────────────
    def _run_kml_with_progress(self, cfg, logger):
        """
        Run the KML and map generation steps, providing detailed progress updates to the GUI.
        Handles data loading, master dictionary creation, Excel export, and final file generation.
        """

        global DATA, OUTPUT

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
        try:
            pd.DataFrame.from_dict(master_dict, orient='index').to_excel(
                cfg.output_folder / 'T38_masterdict.xlsx'
            )
        except PermissionError:
            raise PermissionError("T38_masterdict.xlsx is open in another program")
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
        """
        Start the Tkinter main event loop, displaying the GUI and waiting for user interaction.
        """
        self.root.mainloop()


# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    ###############################################################
    # Application Entry Point
    # This section ensures the app runs correctly whether started
    # as a script or as a bundled executable. It creates the GUI
    # and starts the main event loop.
    ###############################################################
    import multiprocessing
    multiprocessing.freeze_support()   # required for PyInstaller
    app = PlanAidGUI()
    app.run()
