import os
import sys
import queue
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import Dict, List

try:
    import customtkinter as ctk
    HAS_CTK = True
except ImportError:
    HAS_CTK = False
    from tkinter import ttk

from downloader import extract_urls, DownloadTask, KuaishouBatchDownloader

try:
    from auto_updater import check_for_updates_async, create_desktop_shortcut
    HAS_UPDATER = True
except ImportError:
    HAS_UPDATER = False



# ==============================================================================
# PURE WHITE LUXURY STUDIO THEME PALETTE (V3.0 ULTRA-SONIC IDM EDITION)
# ==============================================================================
BG_MAIN = "#F4F7FB"          # Soft pearl-white canvas background
CARD_BG = "#FFFFFF"          # Pure crisp white card surface
CARD_SUB = "#F8FAFC"         # Subtle cool-white row surface
BORDER_CLR = "#E2E8F0"       # Soft slate border
BORDER_SUCCESS = "#6EE7B7"   # Mint border on completion
BORDER_FAIL = "#FCA5A5"      # Soft coral border on failure

TEXT_PRIMARY = "#0F172A"     # Deep slate-navy primary text
TEXT_SECONDARY = "#475569"   # Muted slate secondary text
TEXT_MUTED = "#64748B"       # Subtle caption text

ACCENT_INDIGO = "#4F46E5"    # Royal Indigo primary accent
ACCENT_INDIGO_HVR = "#4338CA"
ACCENT_EMERALD = "#10B981"   # Vibrant Emerald start/complete accent
ACCENT_EMERALD_HVR = "#059669"
ACCENT_BLUE = "#0284C7"      # Sky Blue utility accent
ACCENT_BLUE_HVR = "#0369A1"
ACCENT_CORAL = "#EF4444"     # Coral Red stop/error accent
ACCENT_CORAL_HVR = "#DC2626"
ACCENT_AMBER = "#F59E0B"     # Amber retry/warning accent


class TaskRowWidget:
    """
    Sleek Pure-White Card Row for each Kuaishou Video Download Task.
    Displays index badge, video title, IDM engine badge, smooth progress bar,
    speed, file size, ETA, and an action button (Open File / Retry).
    """

    def __init__(self, parent, task: DownloadTask, use_ctk: bool, on_retry_single):
        self.task = task
        self.use_ctk = use_ctk
        self.on_retry_single = on_retry_single

        if use_ctk:
            self.frame = ctk.CTkFrame(
                parent,
                corner_radius=12,
                fg_color=CARD_BG,
                border_width=1,
                border_color=BORDER_CLR,
            )
            self.frame.pack(fill="x", padx=8, pady=5)

            top_row = ctk.CTkFrame(self.frame, fg_color="transparent")
            top_row.pack(fill="x", padx=14, pady=(10, 4))

            self.num_badge = ctk.CTkLabel(
                top_row,
                text=f"#{task.task_id:02d}",
                font=ctk.CTkFont(size=12, weight="bold"),
                fg_color="#EEF2FF",
                text_color=ACCENT_INDIGO,
                corner_radius=6,
                width=42,
                height=24,
            )
            self.num_badge.pack(side="left", padx=(0, 10))

            self.title_lbl = ctk.CTkLabel(
                top_row,
                text=task.title,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=TEXT_PRIMARY,
                anchor="w",
            )
            self.title_lbl.pack(side="left", fill="x", expand=True)

            self.engine_lbl = ctk.CTkLabel(
                top_row,
                text="IDM Turbo Ready",
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#EEF2FF",
                text_color=ACCENT_INDIGO,
                corner_radius=6,
                padx=8,
                height=22,
            )
            self.engine_lbl.pack(side="right", padx=(8, 0))

            self.status_lbl = ctk.CTkLabel(
                top_row,
                text=task.status,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=ACCENT_INDIGO,
                anchor="e",
            )
            self.status_lbl.pack(side="right", padx=(8, 4))

            mid_row = ctk.CTkFrame(self.frame, fg_color="transparent")
            mid_row.pack(fill="x", padx=14, pady=(2, 10))

            self.pbar = ctk.CTkProgressBar(
                mid_row,
                height=10,
                corner_radius=5,
                fg_color="#E2E8F0",
                progress_color=ACCENT_INDIGO,
            )
            self.pbar.set(0.0)
            self.pbar.pack(side="left", fill="x", expand=True, padx=(0, 14))

            self.action_btn = ctk.CTkButton(
                mid_row,
                text="🔄 Retry",
                width=76,
                height=24,
                corner_radius=6,
                font=ctk.CTkFont(size=11, weight="bold"),
                fg_color="#F1F5F9",
                text_color=TEXT_SECONDARY,
                hover_color="#E2E8F0",
                command=self._handle_action,
            )
            self.action_btn.pack(side="right", padx=(8, 0))

            self.meta_lbl = ctk.CTkLabel(
                mid_row,
                text="ទំហំ: -   |   ល្បឿន: -   |   ETA: -",
                font=ctk.CTkFont(size=11),
                text_color=TEXT_MUTED,
                width=260,
                anchor="e",
            )
            self.meta_lbl.pack(side="right")
        else:
            self.frame = tk.Frame(parent, bg=CARD_BG, bd=1, relief="solid")
            self.frame.pack(fill="x", padx=8, pady=4)

            top_row = tk.Frame(self.frame, bg=CARD_BG)
            top_row.pack(fill="x", padx=10, pady=(6, 2))

            self.title_lbl = tk.Label(
                top_row,
                text=f"#{task.task_id:02d}  {task.title}",
                fg=TEXT_PRIMARY,
                bg=CARD_BG,
                font=("Segoe UI", 10, "bold"),
                anchor="w",
            )
            self.title_lbl.pack(side="left", fill="x", expand=True)

            self.status_lbl = tk.Label(
                top_row,
                text=task.status,
                fg=ACCENT_INDIGO,
                bg=CARD_BG,
                font=("Segoe UI", 9, "bold"),
                anchor="e",
            )
            self.status_lbl.pack(side="right")

            mid_row = tk.Frame(self.frame, bg=CARD_BG)
            mid_row.pack(fill="x", padx=10, pady=(2, 8))

            self.pbar = ttk.Progressbar(mid_row, orient="horizontal", mode="determinate", maximum=100)
            self.pbar.pack(side="left", fill="x", expand=True, padx=(0, 10))

            self.meta_lbl = tk.Label(
                mid_row,
                text="Size: - | Speed: - | ETA: -",
                fg=TEXT_MUTED,
                bg=CARD_BG,
                font=("Segoe UI", 9),
                width=30,
                anchor="e",
            )
            self.meta_lbl.pack(side="right")

    def _handle_action(self):
        if self.task.filepath and os.path.exists(self.task.filepath):
            folder = os.path.dirname(self.task.filepath)
            if sys.platform.startswith("win"):
                os.startfile(folder)
            elif sys.platform == "darwin":
                os.system(f'open "{folder}"')
            else:
                webbrowser.open(f"file://{folder}")
        else:
            self.on_retry_single(self.task)

    def refresh(self):
        short_title = self.task.title if len(self.task.title) <= 68 else self.task.title[:65] + "..."
        if self.use_ctk:
            self.title_lbl.configure(text=short_title)
            self.status_lbl.configure(text=self.task.status)
            self.engine_lbl.configure(text=self.task.engine_used)
            self.pbar.set(self.task.progress)
            self.meta_lbl.configure(
                text=f"ទំហំ: {self.task.size_str}   |   ល្បឿន: {self.task.speed_str}   |   ETA: {self.task.eta_str}"
            )

            if "Completed" in self.task.status:
                self.frame.configure(border_color=BORDER_SUCCESS, fg_color="#F0FDF4")
                self.status_lbl.configure(text_color=ACCENT_EMERALD)
                self.pbar.configure(progress_color=ACCENT_EMERALD)
                self.num_badge.configure(fg_color="#DCFCE7", text_color=ACCENT_EMERALD)
                self.action_btn.configure(
                    text="📂 បើកមើល",
                    fg_color=ACCENT_EMERALD,
                    text_color="#FFFFFF",
                    hover_color=ACCENT_EMERALD_HVR,
                )
            elif "Failed" in self.task.status:
                self.frame.configure(border_color=BORDER_FAIL, fg_color="#FEF2F2")
                self.status_lbl.configure(text_color=ACCENT_CORAL)
                self.pbar.configure(progress_color=ACCENT_CORAL)
                self.num_badge.configure(fg_color="#FEE2E2", text_color=ACCENT_CORAL)
                self.action_btn.configure(
                    text="🔄 Retry",
                    fg_color=ACCENT_INDIGO,
                    text_color="#FFFFFF",
                    hover_color=ACCENT_INDIGO_HVR,
                )
            elif "Cancelled" in self.task.status:
                self.status_lbl.configure(text_color=ACCENT_AMBER)
                self.pbar.configure(progress_color=ACCENT_AMBER)
            else:
                self.frame.configure(border_color=BORDER_CLR, fg_color=CARD_BG)
                self.status_lbl.configure(text_color=ACCENT_INDIGO)
                self.pbar.configure(progress_color=ACCENT_INDIGO)
        else:
            self.title_lbl.config(text=f"#{self.task.task_id:02d}  {short_title}")
            self.status_lbl.config(text=self.task.status)
            self.pbar["value"] = int(self.task.progress * 100)
            self.meta_lbl.config(
                text=f"Size: {self.task.size_str} | Speed: {self.task.speed_str} | ETA: {self.task.eta_str}"
            )


class KuaishouDownloaderApp:
    def __init__(self):
        if HAS_CTK:
            ctk.set_appearance_mode("Light")
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
            self.root.configure(fg_color=BG_MAIN)
        else:
            self.root = tk.Tk()
            self.root.configure(bg=BG_MAIN)

        self.root.title("Kuaishou Multi-Link Turbo Studio Pro V3.0 (IDM Ultra-Speed White Edition)")
        self.root.geometry("1080x780")
        self.root.minsize(940, 660)

        self.output_dir = os.path.join(os.path.expanduser("~"), "Downloads", "Kuaishou_Videos")
        self.update_queue: "queue.Queue[DownloadTask]" = queue.Queue()
        self.row_widgets: Dict[int, TaskRowWidget] = {}
        self.tasks: Dict[int, DownloadTask] = {}
        self.engine: KuaishouBatchDownloader = None

        self._build_ui()
        self._poll_queue()

        # ----------------------------------------------------------------------
        # AUTO SHORTCUT & VERSION UPDATE CHECK (ON CLIENT STARTUP)
        # ----------------------------------------------------------------------
        if HAS_UPDATER:
            # 1. ស្វ័យប្រវត្តបង្កើត Shortcut លើ Desktop ពេល Run លើកដំបូង
            create_desktop_shortcut("Kuaishou Multi Downloader Turbo")
            # 2. ពិនិត្យ Update ពី Server/GitHub ស្វ័យប្រវត្ត (1.5 វិនាទីក្រោយបើក Tool)
            self.root.after(1500, lambda: check_for_updates_async(self.root))


    def _build_ui(self):
        if HAS_CTK:
            self._build_ctk_ui()
        else:
            self._build_tk_ui()

    def _build_ctk_ui(self):
        # 1. TOP HERO STUDIO HEADER (PURE WHITE WITH KPI PILLS)
        header = ctk.CTkFrame(
            self.root,
            corner_radius=0,
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER_CLR,
        )
        header.pack(fill="x", padx=0, pady=0)

        header_inner = ctk.CTkFrame(header, fg_color="transparent")
        header_inner.pack(fill="x", padx=24, pady=14)

        brand_box = ctk.CTkFrame(header_inner, fg_color="transparent")
        brand_box.pack(side="left")

        badge_lbl = ctk.CTkLabel(
            brand_box,
            text="🚀 IDM TURBO V3.0 (16x SPEED)",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#EEF2FF",
            text_color=ACCENT_INDIGO,
            corner_radius=6,
            padx=10,
            pady=2,
        )
        badge_lbl.pack(side="left", padx=(0, 12))

        title_col = ctk.CTkFrame(brand_box, fg_color="transparent")
        title_col.pack(side="left")

        ctk.CTkLabel(
            title_col,
            text="KUAISHOU MULTI-LINK ULTRA-SONIC DOWNLOADER",
            font=ctk.CTkFont(size=19, weight="bold"),
            text_color=TEXT_PRIMARY,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_col,
            text="បំបែក Link ព្រមគ្នាក្នុង 0.5 វិនាទី (Parallel Race) + បច្ចេកវិទ្យា IDM Multi-Channel ទាញយកលឿនបំផុត",
            font=ctk.CTkFont(size=12),
            text_color=TEXT_SECONDARY,
            anchor="w",
        ).pack(anchor="w")

        kpi_box = ctk.CTkFrame(header_inner, fg_color="transparent")
        kpi_box.pack(side="right")

        self.kpi_total = self._make_kpi_pill(kpi_box, "សរុប (Total): 0", "#F1F5F9", TEXT_PRIMARY)
        self.kpi_active = self._make_kpi_pill(kpi_box, "កំពុងដើរ (Active): 0", "#EFF6FF", ACCENT_BLUE)
        self.kpi_done = self._make_kpi_pill(kpi_box, "ជោគជ័យ (Done): 0", "#ECFDF5", ACCENT_EMERALD)
        self.kpi_fail = self._make_kpi_pill(kpi_box, "បរាជ័យ (Failed): 0", "#FEF2F2", ACCENT_CORAL)

        # 2. SMART LINK INPUT CARD (WHITE STUDIO CARD)
        input_card = ctk.CTkFrame(
            self.root,
            corner_radius=14,
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER_CLR,
        )
        input_card.pack(fill="x", padx=22, pady=(14, 8))

        lbl_row = ctk.CTkFrame(input_card, fg_color="transparent")
        lbl_row.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            lbl_row,
            text="🔗 បញ្ចូល Links វីដេអូ Kuaishou (ដាក់បានច្រើន Link ឬ Paste អត្ថបទ Share ទាំងមូល):",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left")

        self.link_count_badge = ctk.CTkLabel(
            lbl_row,
            text="រកឃើញ 2 Links",
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#EEF2FF",
            text_color=ACCENT_INDIGO,
            corner_radius=6,
            padx=10,
            height=24,
        )
        self.link_count_badge.pack(side="left", padx=(10, 0))

        ctk.CTkButton(
            lbl_row,
            text="🧹 សម្អាត",
            width=86,
            height=28,
            corner_radius=8,
            fg_color="#F1F5F9",
            text_color=TEXT_SECONDARY,
            hover_color="#E2E8F0",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.clear_links,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            lbl_row,
            text="📂 នាំចូលពី .TXT",
            width=120,
            height=28,
            corner_radius=8,
            fg_color="#F1F5F9",
            text_color=TEXT_PRIMARY,
            hover_color="#E2E8F0",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.import_txt,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            lbl_row,
            text="📋 Paste ពី Clipboard",
            width=145,
            height=28,
            corner_radius=8,
            fg_color="#EEF2FF",
            text_color=ACCENT_INDIGO,
            hover_color="#E0E7FF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.paste_clipboard,
        ).pack(side="right")

        self.url_textbox = ctk.CTkTextbox(
            input_card,
            height=105,
            corner_radius=10,
            fg_color=CARD_SUB,
            text_color=TEXT_PRIMARY,
            border_width=1,
            border_color="#CBD5E1",
            font=ctk.CTkFont(family="Consolas", size=13),
        )
        self.url_textbox.pack(fill="x", padx=16, pady=(2, 12))
        self.url_textbox.insert(
            "1.0",
            "https://v.kuaishou.com/J3Q4vExT\nhttps://v.kuaishou.com/JXno21cF\n",
        )
        self.url_textbox.bind("<KeyRelease>", lambda e: self._update_link_count())

        # 3. SETTINGS & TURBO ACTION CONTROLS CARD (WHITE STUDIO CARD)
        ctrl_card = ctk.CTkFrame(
            self.root,
            corner_radius=14,
            fg_color=CARD_BG,
            border_width=1,
            border_color=BORDER_CLR,
        )
        ctrl_card.pack(fill="x", padx=22, pady=6)

        row1 = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=(12, 6))

        ctk.CTkLabel(
            row1,
            text="📁 ទីតាំងរក្សាទុក (Save Folder):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_PRIMARY,
        ).pack(side="left", padx=(0, 8))

        self.dir_entry = ctk.CTkEntry(
            row1,
            fg_color=CARD_SUB,
            text_color=TEXT_PRIMARY,
            border_color="#CBD5E1",
            corner_radius=8,
            height=32,
        )
        self.dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.dir_entry.insert(0, self.output_dir)

        ctk.CTkButton(
            row1,
            text="ជ្រើសរើស Folder",
            width=125,
            height=32,
            corner_radius=8,
            fg_color="#F1F5F9",
            text_color=TEXT_PRIMARY,
            hover_color="#E2E8F0",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.choose_folder,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            row1,
            text="📂 បើក Folder",
            width=110,
            height=32,
            corner_radius=8,
            fg_color=ACCENT_BLUE,
            text_color="#FFFFFF",
            hover_color=ACCENT_BLUE_HVR,
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.open_output_folder,
        ).pack(side="left")

        row2 = ctk.CTkFrame(ctrl_card, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=(6, 12))

        ctk.CTkLabel(
            row2,
            text="⚡ វីដេអូព្រមគ្នា (Batch):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 6))

        self.workers_var = ctk.StringVar(value="8")
        ctk.CTkOptionMenu(
            row2,
            values=["2", "4", "6", "8", "12", "16"],
            variable=self.workers_var,
            width=70,
            height=32,
            corner_radius=8,
            fg_color="#EEF2FF",
            button_color="#E0E7FF",
            button_hover_color="#C7D2FE",
            text_color=ACCENT_INDIGO,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            row2,
            text="🚀 ល្បឿន IDM ក្នុង ១ វីដេអូ (Channels):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SECONDARY,
        ).pack(side="left", padx=(0, 6))

        self.idm_var = ctk.StringVar(value="12")
        ctk.CTkOptionMenu(
            row2,
            values=["4", "8", "12", "16"],
            variable=self.idm_var,
            width=70,
            height=32,
            corner_radius=8,
            fg_color="#ECFDF5",
            button_color="#D1FAE5",
            button_hover_color="#A7F3D0",
            text_color=ACCENT_EMERALD_HVR,
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(0, 12))

        self.btn_stop = ctk.CTkButton(
            row2,
            text="⏹ បញ្ឈប់",
            width=95,
            height=36,
            corner_radius=9,
            fg_color=ACCENT_CORAL,
            hover_color=ACCENT_CORAL_HVR,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            state="disabled",
            command=self.stop_downloads,
        )
        self.btn_stop.pack(side="right", padx=(6, 0))

        self.btn_retry_failed = ctk.CTkButton(
            row2,
            text="🔄 Retry Failed",
            width=130,
            height=36,
            corner_radius=9,
            fg_color=ACCENT_INDIGO,
            hover_color=ACCENT_INDIGO_HVR,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=12, weight="bold"),
            command=self.retry_failed_tasks,
        )
        self.btn_retry_failed.pack(side="right", padx=(6, 0))

        self.btn_start = ctk.CTkButton(
            row2,
            text="🚀 ទាញយកល្បឿនលឿនបំផុត (Start Ultra-Turbo)",
            width=255,
            height=36,
            corner_radius=9,
            fg_color=ACCENT_EMERALD,
            hover_color=ACCENT_EMERALD_HVR,
            text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.start_downloads,
        )
        self.btn_start.pack(side="right")

        # 4. OVERALL PROGRESS BANNER
        overall_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        overall_frame.pack(fill="x", padx=24, pady=(4, 4))

        self.overall_lbl = ctk.CTkLabel(
            overall_frame,
            text="ស្ថានភាពប្រព័ន្ធ (System Status): រួចរាល់សម្រាប់ការទាញយកល្បឿនលឿនបំផុត (IDM 12x Turbo Ready)",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=TEXT_SECONDARY,
        )
        self.overall_lbl.pack(side="left")

        self.overall_bar = ctk.CTkProgressBar(
            overall_frame,
            width=300,
            height=10,
            corner_radius=5,
            fg_color="#E2E8F0",
            progress_color=ACCENT_EMERALD,
        )
        self.overall_bar.set(0.0)
        self.overall_bar.pack(side="right", pady=4)

        # 5. SCROLLABLE DOWNLOAD QUEUE (PURE WHITE SURFACE)
        self.scroll_area = ctk.CTkScrollableFrame(
            self.root,
            corner_radius=14,
            fg_color=CARD_SUB,
            border_width=1,
            border_color=BORDER_CLR,
            label_text="📋 បញ្ជីវីដេអូកំពុងដំណើរការព្រមគ្នា (Active Multi-Channel IDM Queue)",
            label_fg_color="#EEF2FF",
            label_text_color=ACCENT_INDIGO,
            label_font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.scroll_area.pack(fill="both", expand=True, padx=22, pady=(4, 18))

    def _make_kpi_pill(self, parent, text: str, bg_color: str, txt_color: str):
        lbl = ctk.CTkLabel(
            parent,
            text=text,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=bg_color,
            text_color=txt_color,
            corner_radius=8,
            padx=12,
            height=28,
        )
        lbl.pack(side="left", padx=(6, 0))
        return lbl

    def _build_tk_ui(self):
        top = tk.Frame(self.root, bg=CARD_BG)
        top.pack(fill="x", padx=16, pady=10)
        tk.Label(
            top,
            text="🚀 KUAISHOU MULTI-LINK ULTRA-SONIC DOWNLOADER V3.0",
            fg=ACCENT_INDIGO,
            bg=CARD_BG,
            font=("Segoe UI", 14, "bold"),
        ).pack(side="left")

        self.url_textbox = tk.Text(self.root, height=6, bg=CARD_BG, fg=TEXT_PRIMARY)
        self.url_textbox.pack(fill="x", padx=16, pady=6)

        ctrl = tk.Frame(self.root, bg=BG_MAIN)
        ctrl.pack(fill="x", padx=16, pady=6)
        self.dir_entry = tk.Entry(ctrl, width=45, bg=CARD_BG, fg=TEXT_PRIMARY)
        self.dir_entry.pack(side="left", padx=(0, 8))
        self.dir_entry.insert(0, self.output_dir)
        self.workers_var = tk.StringVar(value="8")
        self.idm_var = tk.StringVar(value="12")

        self.btn_start = tk.Button(
            ctrl, text="Start Ultra-Turbo", bg=ACCENT_EMERALD, fg="white", command=self.start_downloads
        )
        self.btn_start.pack(side="right", padx=4)
        self.btn_stop = tk.Button(
            ctrl, text="Stop", bg=ACCENT_CORAL, fg="white", state="disabled", command=self.stop_downloads
        )
        self.btn_stop.pack(side="right", padx=4)

        self.overall_lbl = tk.Label(self.root, text="Ready", fg=TEXT_SECONDARY, bg=BG_MAIN)
        self.overall_lbl.pack(fill="x", padx=16)

        self.scroll_area = tk.Frame(self.root, bg=CARD_BG)
        self.scroll_area.pack(fill="both", expand=True, padx=16, pady=8)

    def _update_link_count(self):
        if not HAS_CTK:
            return
        raw = self.url_textbox.get("1.0", "end")
        urls = extract_urls(raw)
        self.link_count_badge.configure(text=f"រកឃើញ {len(urls)} Links")

    def clear_links(self):
        self.url_textbox.delete("1.0", "end")
        self._update_link_count()

    def paste_clipboard(self):
        try:
            clip = self.root.clipboard_get()
            if clip:
                current = self.url_textbox.get("1.0", "end").strip()
                if current:
                    self.url_textbox.insert("end", "\n" + clip.strip() + "\n")
                else:
                    self.url_textbox.delete("1.0", "end")
                    self.url_textbox.insert("1.0", clip.strip() + "\n")
                self._update_link_count()
        except Exception:
            pass

    def import_txt(self):
        path = filedialog.askopenfilename(
            title="Select .txt file with Kuaishou links",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if path and os.path.isfile(path):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            self.url_textbox.delete("1.0", "end")
            self.url_textbox.insert("1.0", content)
            self._update_link_count()

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Select Download Folder")
        if folder:
            self.output_dir = folder
            self.dir_entry.delete(0, "end")
            self.dir_entry.insert(0, folder)

    def open_output_folder(self):
        target = self.dir_entry.get().strip() or self.output_dir
        os.makedirs(target, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(target)
        elif sys.platform == "darwin":
            os.system(f'open "{target}"')
        else:
            webbrowser.open(f"file://{target}")

    def start_downloads(self):
        raw_text = self.url_textbox.get("1.0", "end")
        urls = extract_urls(raw_text)

        if not urls:
            messagebox.showwarning(
                "មិនមាន Link (No Links Found)",
                "សូមបញ្ចូល Link វីដេអូ Kuaishou យ៉ាងហោចណាស់ ១ ជាមុនសិន!",
            )
            return

        for w in self.row_widgets.values():
            w.frame.destroy()
        self.row_widgets.clear()
        self.tasks.clear()

        task_list: List[DownloadTask] = []
        for idx, url in enumerate(urls, start=1):
            t = DownloadTask(task_id=idx, url=url)
            self.tasks[idx] = t
            row = TaskRowWidget(self.scroll_area, t, HAS_CTK, self.retry_single_task)
            self.row_widgets[idx] = row
            task_list.append(t)

        self._run_task_list(task_list)

    def retry_failed_tasks(self):
        failed_list = [
            t for t in self.tasks.values() if "Failed" in t.status or "Cancelled" in t.status
        ]
        if not failed_list:
            messagebox.showinfo("ព័ត៌មាន", "មិនមាន Link ដែលបរាជ័យត្រូវទាញយកម្ដងទៀតទេ!")
            return
        for t in failed_list:
            t.cancelled = False
            t.progress = 0.0
            t.status = "រង់ចាំ (Queued)"
            if t.task_id in self.row_widgets:
                self.row_widgets[t.task_id].refresh()
        self._run_task_list(failed_list)

    def retry_single_task(self, task: DownloadTask):
        task.cancelled = False
        task.progress = 0.0
        task.status = "រង់ចាំ (Queued)"
        if task.task_id in self.row_widgets:
            self.row_widgets[task.task_id].refresh()
        self._run_task_list([task])

    def _run_task_list(self, task_list: List[DownloadTask]):
        self.output_dir = self.dir_entry.get().strip() or self.output_dir
        max_workers = int(self.workers_var.get())
        idm_channels = int(self.idm_var.get())

        if HAS_CTK:
            self.btn_start.configure(state="disabled")
            self.btn_stop.configure(state="normal")
            self.overall_lbl.configure(
                text=f"🚀 កំពុងទាញយកល្បឿនលឿន {len(task_list)} វីដេអូព្រមគ្នា ({idm_channels}x IDM Channels)..."
            )
        else:
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")

        self.engine = KuaishouBatchDownloader(
            output_dir=self.output_dir,
            max_workers=max_workers,
            idm_channels=idm_channels,
            on_update=lambda task: self.update_queue.put(task),
            on_all_complete=self._on_batch_finished,
        )
        self.engine.start_batch(task_list)

    def stop_downloads(self):
        if self.engine:
            self.engine.stop_all()

    def _on_batch_finished(self):
        self.root.after(80, self._finalize_batch_ui)

    def _refresh_kpis(self):
        if not HAS_CTK:
            return
        total = len(self.tasks)
        done = sum(1 for t in self.tasks.values() if "Completed" in t.status)
        failed = sum(1 for t in self.tasks.values() if "Failed" in t.status)
        active = max(0, total - done - failed)

        self.kpi_total.configure(text=f"សរុប (Total): {total}")
        self.kpi_active.configure(text=f"កំពុងដើរ (Active): {active}")
        self.kpi_done.configure(text=f"ជោគជ័យ (Done): {done}")
        self.kpi_fail.configure(text=f"បរាជ័យ (Failed): {failed}")

    def _finalize_batch_ui(self):
        if HAS_CTK:
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
        else:
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="normal")

        self._refresh_kpis()
        total = len(self.tasks)
        done = sum(1 for t in self.tasks.values() if "Completed" in t.status)
        failed = sum(1 for t in self.tasks.values() if "Failed" in t.status)
        if HAS_CTK:
            self.overall_lbl.configure(
                text=f"✅ បានបញ្ចប់ (Finished): ជោគជ័យ {done}/{total} វីដេអូ   |   បរាជ័យ {failed}"
            )
            self.overall_bar.set(1.0 if total > 0 and done == total else (done / max(1, total)))

    def _poll_queue(self):
        try:
            while True:
                task = self.update_queue.get_nowait()
                widget = self.row_widgets.get(task.task_id)
                if widget:
                    widget.refresh()
                if HAS_CTK and self.tasks:
                    self._refresh_kpis()
                    total = len(self.tasks)
                    avg_prog = sum(t.progress for t in self.tasks.values()) / total
                    done = sum(1 for t in self.tasks.values() if "Completed" in t.status)
                    self.overall_bar.set(avg_prog)
                    self.overall_lbl.configure(
                        text=f"🚀 កំពុងទាញយកល្បឿនលឿន: រួចរាល់ {done}/{total} ({int(avg_prog * 100)}%)"
                    )
        except queue.Empty:
            pass
        self.root.after(50, self._poll_queue)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = KuaishouDownloaderApp()
    app.run()
