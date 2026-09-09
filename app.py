import csv
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from ctypes import windll
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageDraw, ImageFont, ImageTk


APP_NAME = "SCCM toolsBox"
DEFAULT_PROFILE = {"name": "Default", "server": "", "site_code": ""}

LIGHT_THEME = {
    "window": "#007348",
    "surface": "#FFFFFF",
    "surface_2": "#F5F8FC",
    "surface_3": "#EEF3FA",
    "text": "#1F2937",
    "muted_text": "#6B7280",
    "accent_blue": "#007348",
    "accent_green": "#007348",
    "border": "#D4DFEC",
    "sidebar_active": "#007348",
    "sidebar_active_line": "#007348",
    "output_bg": "#EFF5FB",
    "tabs_shell_bg": "#FFFFFF",
    "tabs_btn_bg": "#FFFFFF",
    "tabs_btn_hover": "#EEF3FA",
    "tabs_btn_active": "#007348",
    "tabs_btn_border": "#D4DFEC",
    "tabs_btn_text": "#1F2937",
    "tabs_btn_text_active": "#FFFFFF",
}

DARK_THEME = {
    "window": "#007348",
    "surface": "#152033",
    "surface_2": "#1B2A42",
    "surface_3": "#243553",
    "text": "#E5EDF8",
    "muted_text": "#AABBD4",
    "accent_blue": "#007348",
    "accent_green": "#007348",
    "border": "#30435E",
    "sidebar_active": "#007348",
    "sidebar_active_line": "#007348",
    "output_bg": "#1A2740",
    "tabs_shell_bg": "#152033",
    "tabs_btn_bg": "#152033",
    "tabs_btn_hover": "#243553",
    "tabs_btn_active": "#007348",
    "tabs_btn_border": "#30435E",
    "tabs_btn_text": "#E5EDF8",
    "tabs_btn_text_active": "#FFFFFF",
}

# Pre-compiled PowerShell syntax patterns — shared by all preview windows.
_PS1_HIGHLIGHT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("string",   re.compile(r'"[^\n"]*"|\'[^\n\']*\'')),
    ("variable", re.compile(r'\$[A-Za-z_][A-Za-z0-9_:]*')),
    ("operator", re.compile(r'-(?:eq|ne|gt|lt|ge|le|like|notlike|match|notmatch|contains|notcontains|in|notin)\b', re.IGNORECASE)),
    ("keyword",  re.compile(r'\b(?:if|else|elseif|function|param|return|foreach|for|while|do|switch|try|catch|finally|throw|trap|begin|process|end|in)\b', re.IGNORECASE)),
    ("cmdlet",   re.compile(r'\b[A-Za-z][A-Za-z0-9]*-[A-Za-z][A-Za-z0-9]*\b')),
    ("number",   re.compile(r'\b\d+\b')),
    ("comment",  re.compile(r'#.*$', re.MULTILINE)),
]


class SCCMToolboxApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x760")
        self.minsize(900, 580)

        self.base_dir = Path(__file__).resolve().parent
        self.profiles_path = self.base_dir / "profiles.json"
        self.settings_path = self.base_dir / "settings.json"
        self.ps1_dir = self.base_dir / "ps1"
        self.ps1_dir.mkdir(exist_ok=True)
        self.cmtrace_dev_dir = self.base_dir / "CMTraceDev"
        self.cmtrace_listen = "127.0.0.1:19847"
        self.ps1_search_root = self.ps1_dir
        self.ps1_recursive_search = True
        self.ps1_script_map = {}
        self.cmtrace_fallback_process = None
        self.cmtrace_start_mode = "unknown"
        self.cmtrace_webview_ready = threading.Event()
        self.cmtrace_webview_thread = None
        self.cmtrace_webview_form = None
        self.cmtrace_webview_control = None
        self.cmtrace_webview_handle = None
        self.cmtrace_webview_loaded_url = None
        self.cmtrace_webview_last_url = None
        self.cmtrace_webview_start_error = None
        self.cmtrace_webview_nav_error = None

        self.theme_name = "light"
        self.theme = LIGHT_THEME
        self.profiles_data = self.load_profiles()
        self.active_profile_name = self.load_active_profile_name()
        self.active_profile = self.get_active_profile()

        self.tab_buttons = {}
        self.current_tab = "Tools"
        self.tab_frames = {}
        self.top_tabs = [
            ("Tools", "Tools"),
            ("PS1", "Vanilla PS"),
            ("InfraTools", "Infra Tools"),
            ("CMTrace", "CMTrace"),
        ]
        self.tab_icons = {
            "Tools": "🛠️",
            "PS1": "💻",
            "InfraTools": "⚙️",
            "CMTrace": "📋",
        }
        self.vertical_menu_items = [
            ("Last10DPLM", "Last 10 DPLM"),
            ("CollMember", "CollMember"),
            ("CollVariable", "CollVariable"),
            ("CopyDeplmt", "Copy Deplmt"),
        ]
        self.vertical_menu_icons = {
            "Last10DPLM": "📊",
            "CollMember": "🧩",
            "CollVariable": "🏷️",
            "CopyDeplmt": "📋",
        }
        self.vertical_menu_selected = ""
        self.vertical_menu_buttons = []
        self.sccm_buttons = []
        self.tools_mode = "sccm"
        self.infra_menu_buttons = []
        self.infra_selected_tool_key = None
        self.infra_tools_map = {}
        self.is_closing = False
        self.icon_font_path = Path(r"C:\Windows\Fonts\seguiemj.ttf")
        self.icon_cache: dict[tuple[str, int, int | None, int | None], ImageTk.PhotoImage] = {}
        self.tab_icon_refs: dict[str, ImageTk.PhotoImage] = {}
        self.tools_layout_mode = "wide"
        self.infra_layout_mode = "wide"
        self.ps1_layout_mode = "wide"
        self.collvariable_actions_mode = ""

        self.init_styles()
        self.build_ui()
        self.bind("<Configure>", self._on_window_resize)
        self.after_idle(self._apply_responsive_layout)
        self.apply_theme()
        self.refresh_ps1_list()
        self.show_home(run_check=False)
        self.protocol("WM_DELETE_WINDOW", self.on_app_close)

    def load_profiles(self) -> dict:
        if not self.profiles_path.exists():
            data = {"profiles": [DEFAULT_PROFILE], "active_profile": DEFAULT_PROFILE["name"]}
            self.profiles_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return data
        try:
            with self.profiles_path.open("r", encoding="utf-8") as handle:
                loaded = json.load(handle)
        except (json.JSONDecodeError, OSError):
            return {"profiles": [DEFAULT_PROFILE], "active_profile": DEFAULT_PROFILE["name"]}
        profiles = loaded.get("profiles") or [DEFAULT_PROFILE]
        active_profile = loaded.get("active_profile") or profiles[0]["name"]
        return {"profiles": profiles, "active_profile": active_profile}

    def save_profiles(self) -> None:
        payload = {"profiles": self.profiles_data["profiles"], "active_profile": self.active_profile_name}
        self.profiles_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_active_profile_name(self) -> str:
        if self.settings_path.exists():
            try:
                with self.settings_path.open("r", encoding="utf-8") as handle:
                    settings = json.load(handle)
            except (json.JSONDecodeError, OSError):
                settings = {}
            theme = settings.get("theme", "light")
            if theme in ("light", "dark"):
                self.theme_name = theme
                self.theme = DARK_THEME if theme == "dark" else LIGHT_THEME
            saved_ps1_root = settings.get("ps1_search_root")
            if saved_ps1_root:
                self.ps1_search_root = Path(saved_ps1_root)
            active_profile = settings.get("active_profile")
            if active_profile:
                return active_profile
        return self.profiles_data.get("active_profile", DEFAULT_PROFILE["name"])

    def save_settings(self) -> None:
        payload = {
            "theme": self.theme_name,
            "active_profile": self.active_profile_name,
            "ps1_search_root": str(self.ps1_search_root) if self.ps1_search_root != self.ps1_dir else None,
        }
        self.settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def get_active_profile(self) -> dict:
        for profile in self.profiles_data["profiles"]:
            if profile["name"] == self.active_profile_name:
                return profile
        fallback = self.profiles_data["profiles"][0]
        self.active_profile_name = fallback["name"]
        return fallback

    def profile_status_text(self) -> str:
        profile = self.get_active_profile()
        server = profile.get("server", "").strip() or "Not set"
        site_code = profile.get("site_code", "").strip() or "Not set"
        return f"Connected to {server}  |  Site code: {site_code}"

    def _get_color_icon(
        self,
        glyph: str,
        size: int = 16,
        fixed_w: int | None = None,
        fixed_h: int | None = None,
    ) -> ImageTk.PhotoImage | None:
        key = (glyph, size, fixed_w, fixed_h)
        cached = self.icon_cache.get(key)
        if cached is not None:
            return cached
        if not self.icon_font_path.exists():
            return None
        try:
            font = ImageFont.truetype(str(self.icon_font_path), size=size)
            measure_image = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
            draw = ImageDraw.Draw(measure_image)
            bbox = draw.textbbox((0, 0), glyph, font=font, embedded_color=True)
            icon_w = bbox[2] - bbox[0]
            icon_h = bbox[3] - bbox[1]
            padding = 10
            canvas_w = fixed_w if fixed_w is not None else max(size + 16, icon_w + padding * 2)
            canvas_h = fixed_h if fixed_h is not None else max(size + 16, icon_h + padding * 2)
            image = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            x = (canvas_w - icon_w) // 2 - bbox[0]
            y = (canvas_h - icon_h) // 2 - bbox[1]
            draw.text((x, y), glyph, font=font, embedded_color=True)
            tk_icon = ImageTk.PhotoImage(image)
        except (OSError, ValueError, TypeError):
            return None
        self.icon_cache[key] = tk_icon
        return tk_icon

    def _set_widget_icon(
        self,
        widget: tk.Widget,
        glyph: str,
        text: str = "",
        size: int = 16,
        compound: str = "left",
    ) -> None:
        icon = self._get_color_icon(glyph, size=size)
        if icon is None:
            fallback = f"{glyph} {text}".strip()
            widget.configure(text=fallback)
            return
        widget.configure(text=text, image=icon, compound=compound)
        if isinstance(widget, tk.Button):
            if text:
                widget.configure(width=0)
                widget.configure(anchor="w")
                widget.configure(padx=10, pady=6)
            else:
                widget.configure(text="", width=0, padx=6, pady=4, anchor="center", justify="center", compound="center")
        setattr(widget, "_icon_ref", icon)

    def _set_fixed_button_icon(self, button: tk.Button, glyph: str, text: str, size: int = 14) -> None:
        icon = self._get_color_icon(glyph, size=size, fixed_w=24, fixed_h=24)
        if icon is None:
            fallback = f"{glyph} {text}".strip()
            button.configure(text=fallback)
            return
        button.configure(text=text, image=icon, compound="left")
        setattr(button, "_icon_ref", icon)

    def _apply_outlined_button_theme(
        self,
        button: tk.Button,
        theme: dict[str, str],
        accent_key: str = "accent_green",
        font: tuple[str, int] = ("Segoe UI", 9),
    ) -> None:
        button.configure(
            bg=theme["surface_2"],
            fg=theme["text"],
            activebackground=theme["sidebar_active"],
            activeforeground=theme["text"],
            relief="flat",
            bd=0,
            width=0,
            height=0,
            padx=8,
            pady=5,
            highlightthickness=1,
            highlightbackground=theme[accent_key],
            highlightcolor=theme[accent_key],
            cursor="hand2",
            font=font,
        )

    def init_styles(self) -> None:
        self.style = ttk.Style(self)
        self.style.theme_use("clam")

    def build_ui(self) -> None:
        self.root_frame = tk.Frame(self)
        self.root_frame.pack(fill="both", expand=True, padx=14, pady=14)

        self.main_card = tk.Frame(self.root_frame, padx=0, pady=0)
        self.main_card.pack(fill="both", expand=True)

        self.header = tk.Frame(self.main_card, height=88)
        self.header.pack(fill="x")
        self.header.pack_propagate(False)

        self.header_left = tk.Frame(self.header)
        self.header_left.pack(side="left", fill="y", padx=(16, 6), pady=10)

        self.home_button = tk.Button(self.header_left, text="Home", width=4, command=self.show_home)
        self.home_button.pack(side="left", padx=(0, 10))
        self._set_widget_icon(self.home_button, "🏠", "", size=18, compound="center")

        self.title_wrap = tk.Frame(self.header_left)
        self.title_wrap.pack(side="left", fill="y")
        self.title_label = tk.Label(self.title_wrap, text="SCCM Toolbox", font=("Segoe UI", 19, "bold"), anchor="w")
        self.title_label.pack(anchor="w")
        self.profile_status_label = tk.Label(self.title_wrap, font=("Segoe UI", 12), anchor="w")
        self.profile_status_label.pack(anchor="w", pady=(2, 0))

        self.header_right = tk.Frame(self.header)
        self.header_right.pack(side="right", fill="y", padx=(6, 16), pady=10)

        self.settings_button = tk.Button(self.header_right, text="Settings", width=30, command=self.open_settings)
        self.settings_button.pack(side="right", padx=(8, 0))
        self._set_widget_icon(self.settings_button, "⚙️", "", size=18, compound="center")
        self.theme_button = tk.Button(self.header_right, text="Theme", width=4, command=self.toggle_theme)
        self.theme_button.pack(side="right")
        self._set_widget_icon(self.theme_button, "🌙", "", size=18, compound="center")

        self.tab_bar_shell = tk.Frame(self.header_right)
        self.tab_bar_shell.pack(side="right", padx=(0, 10), pady=6)

        self.tab_canvas = tk.Canvas(self.tab_bar_shell, height=46, bd=0, highlightthickness=0)
        self.tab_canvas.pack(fill="x", expand=True)
        self.tab_bar = tk.Frame(self.tab_canvas, padx=6, pady=5)
        self.tab_bar_window = self.tab_canvas.create_window(10, 5, window=self.tab_bar, anchor="nw")
        self.tab_bar.bind("<Configure>", self.on_tab_bar_configure)
        self.tab_canvas.bind("<Configure>", self.on_tab_canvas_configure)
        total_tabs = len(self.top_tabs)
        for idx, (tab_name, tab_label) in enumerate(self.top_tabs):
            tab_width = self.get_tab_width(tab_label)
            tab_widget = tk.Canvas(
                self.tab_bar,
                height=36,
                width=tab_width,
                bd=0,
                highlightthickness=0,
                cursor="hand2",
            )
            tab_widget.pack(side="left", padx=0)
            left_radius = 12 if idx == 0 else 0
            right_radius = 12 if idx == total_tabs - 1 else 0
            shape_id = self.draw_canvas_segment(
                tab_widget,
                0,
                0,
                tab_width,
                36,
                left_radius,
                right_radius,
                "#FFFFFF",
            )
            icon_id = None
            tab_icon = self._get_color_icon(self.tab_icons.get(tab_name, ""), size=14)
            if tab_icon is not None:
                icon_id = tab_widget.create_image(14, 18, image=tab_icon, anchor="w")
                self.tab_icon_refs[tab_name] = tab_icon
            icon_text_offset = 18 if tab_name == "CMTrace" else 14
            text_x = tab_width // 2 + (icon_text_offset if icon_id is not None else 0)
            text_id = tab_widget.create_text(
                text_x,
                18,
                text=tab_label,
                font=("Segoe UI", 10, "bold"),
                fill="#000000",
            )
            separator_id = None
            if idx > 0:
                separator_id = tab_widget.create_line(0, 6, 0, 30, fill="#CCCCCC", width=1)
            tab_widget.bind("<Button-1>", lambda _event, name=tab_name: self.select_tab(name))
            tab_widget.bind("<Enter>", lambda _event, name=tab_name: self.on_tab_hover_enter(name))
            tab_widget.bind("<Leave>", lambda _event, name=tab_name: self.on_tab_hover_leave(name))
            tab_widget.tag_bind(shape_id, "<Button-1>", lambda _event, name=tab_name: self.select_tab(name))
            tab_widget.tag_bind(text_id, "<Button-1>", lambda _event, name=tab_name: self.select_tab(name))
            self.tab_buttons[tab_name] = {
                "canvas": tab_widget,
                "shape": shape_id,
                "text": text_id,
                "icon": icon_id,
                "separator": separator_id,
            }

        self.separator = tk.Frame(self.main_card, height=1)
        self.separator.pack(fill="x")

        self.content = tk.Frame(self.main_card)
        self.content.pack(fill="both", expand=True, padx=16, pady=14)

        self.build_tools_tab()
        self.build_ps1_tab()
        self.build_infra_tab()
        self.build_cmtrace_tab()

    def build_tools_tab(self) -> None:
        frame = tk.Frame(self.content)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.tab_frames["Tools"] = frame

        self.tools_layout = tk.Frame(frame, padx=14, pady=0)
        self.tools_layout.pack(fill="both", expand=True)

        self.left_panel = tk.Frame(self.tools_layout, width=210)
        self.left_panel.pack(side="left", fill="y", padx=(0, 14))
        self.left_panel.pack_propagate(False)

        self.sccm_menu_button = tk.Button(
            self.left_panel,
            text="SCCM",
            anchor="w",
            padx=14,
            pady=10,
            command=self.open_sccm_from_menu,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=("Segoe UI", 10, "bold"),
        )
        self.sccm_menu_button.pack(fill="x", pady=(0, 8))
        self._set_widget_icon(self.sccm_menu_button, "🏠", "SCCM", size=14)
        self.sccm_buttons.append(self.sccm_menu_button)

        self.vertical_menu = tk.Frame(self.left_panel, padx=10, pady=10)
        self.vertical_menu.pack(fill="both", expand=True)

        for item_key, item_label in self.vertical_menu_items:
            button = tk.Button(
                self.vertical_menu,
                text=item_label,
                anchor="w",
                padx=12,
                pady=10,
                command=lambda name=item_key: self.select_vertical_menu(name),
                relief="flat",
                bd=0,
                highlightthickness=0,
                font=("Segoe UI", 12, "bold"),
            )
            button.pack(fill="x", pady=4)
            # Fixed 32×32 icon so all text labels start at the same x position
            icon = self._get_color_icon(
                self.vertical_menu_icons.get(item_key, "📁"),
                size=14,
                fixed_w=32,
                fixed_h=32,
            )
            if icon is not None:
                button.configure(image=icon, compound="left", text=item_label)
                setattr(button, "_icon_ref", icon)
            else:
                glyph = self.vertical_menu_icons.get(item_key, "📁")
                button.configure(text=f"{glyph}  {item_label}")
            self.vertical_menu_buttons.append((item_key, button))

        self.tools_area_card = tk.Frame(self.tools_layout, padx=0, pady=0)
        self.tools_area_card.pack(side="left", fill="both", expand=True)

        self.connection_head = tk.Label(self.tools_area_card, font=("Segoe UI", 14), anchor="w", padx=18, pady=14)
        self.connection_head.pack(fill="x")

        self.inner_separator_1 = tk.Frame(self.tools_area_card, height=1)
        self.inner_separator_1.pack(fill="x")

        self.check_card = tk.Frame(self.tools_area_card, padx=22, pady=20)
        self.check_card.pack(fill="x", padx=14, pady=(14, 10))

        self.check_title = tk.Label(self.check_card, text="Check SCCM connection", font=("Segoe UI", 21, "bold"))
        self.check_title.pack(anchor="w")
        self._set_widget_icon(self.check_title, "✅", "Check SCCM connection", size=200)

        self.check_description = tk.Label(
            self.check_card,
            text="Test access to the SCCM server and display site information.",
            font=("Segoe UI", 13),
        )
        self.check_description.pack(anchor="w", pady=(8, 20))

        self.tools_actions = tk.Frame(self.check_card)
        self.tools_actions.pack()
        self.run_check_button = tk.Button(self.tools_actions, text="Run Check", command=self.check_sccm_connection)
        self.run_check_button.pack(side="left")
        self._set_widget_icon(self.run_check_button, "▶️", "Run Check", size=16)

        self.collmember_collections: list[str] = []
        self.collmember_machine_names: list[str] = []
        self.collmember_selected_collection_name = ""
        self.collmember_selected_collection_id = ""
        self.collmember_selected_collection_type = "Inconnu"
        self.collmember_selected_collection_type_code = 0
        self.collmember_filter_var = tk.StringVar(value="")
        self.collmember_machine_filter_var = tk.StringVar(value="")
        self.collmember_panel = tk.Frame(self.check_card)
        self.collmember_filter_label = tk.Label(
            self.collmember_panel,
            text="Collection",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.collmember_filter_label.pack(anchor="w")
        self.collmember_filter_row = tk.Frame(self.collmember_panel)
        self.collmember_filter_row.pack(fill="x", pady=(4, 10))
        self.collmember_filter_entry = tk.Entry(
            self.collmember_filter_row,
            textvariable=self.collmember_filter_var,
            font=("Segoe UI", 10),
        )
        self.collmember_filter_entry.pack(side="left", fill="x", expand=True)
        self.collmember_search_button = tk.Button(
            self.collmember_filter_row,
            text="Search",
            command=self.load_collmember_collections,
            font=("Segoe UI", 9),
        )
        self.collmember_search_button.pack(side="left", padx=(8, 0))
        self._set_widget_icon(self.collmember_search_button, "🔍", "", size=16, compound="center")
        self.collmember_search_button.configure(width=0, height=0, padx=8, pady=5)
        setattr(self.collmember_search_button, "_outlined_button", True)
        self.collmember_filter_entry.bind("<KeyRelease>", self._filter_collmember_collections)
        self.collmember_combo_label = tk.Label(
            self.collmember_panel,
            text="Collection",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.collmember_combo_label.pack(anchor="w")
        self.collmember_combo = ttk.Combobox(
            self.collmember_panel,
            values=[],
            state="readonly",
            style="CollMember.TCombobox",
        )
        self.collmember_combo.pack(fill="x", pady=(4, 0))
        self.collmember_combo.bind("<<ComboboxSelected>>", self.on_collmember_collection_selected)
        for widget in (
            self.check_card,
            self.check_title,
            self.check_description,
            self.collmember_panel,
            self.collmember_filter_label,
            self.collmember_filter_row,
            self.collmember_filter_entry,
            self.collmember_search_button,
            self.collmember_combo_label,
            self.collmember_combo,
        ):
            widget.bind("<MouseWheel>", self._on_collmember_output_mousewheel)

        self.collvariable_collections: list[str] = []
        self.collvariable_selected_collection_names: list[str] = []
        self.collvariable_filter_var = tk.StringVar(value="")
        self.collvariable_panel = tk.Frame(self.check_card)
        self.collvariable_filter_label = tk.Label(
            self.collvariable_panel,
            text="Collection Name filter",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.collvariable_filter_label.pack(anchor="w")
        self.collvariable_filter_row = tk.Frame(self.collvariable_panel)
        self.collvariable_filter_row.pack(fill="x", pady=(4, 10))
        self.collvariable_filter_entry = tk.Entry(
            self.collvariable_filter_row,
            textvariable=self.collvariable_filter_var,
            font=("Segoe UI", 10),
        )
        self.collvariable_filter_entry.pack(side="left", fill="x", expand=True)
        self.collvariable_search_button = tk.Button(
            self.collvariable_filter_row,
            text="Search",
            command=self.load_collvariable_collections,
            font=("Segoe UI", 9),
        )
        self.collvariable_search_button.pack(side="left", padx=(8, 0))
        self._set_widget_icon(self.collvariable_search_button, "🔍", "", size=16, compound="center")
        self.collvariable_search_button.configure(width=0, height=0, padx=8, pady=5)
        setattr(self.collvariable_search_button, "_outlined_button", True)
        self.collvariable_filter_entry.bind("<KeyRelease>", self._filter_collvariable_collections)
        self.collvariable_name_filters_frame = tk.Frame(self.collvariable_panel)
        self.collvariable_name_filters_frame.pack(fill="x", pady=(0, 8))
        self.collvariable_name_filter_vars = {
            "INF": tk.BooleanVar(value=True),
            "Patching": tk.BooleanVar(value=True),
            "Deployment": tk.BooleanVar(value=True),
            "Build": tk.BooleanVar(value=True),
        }
        self.collvariable_name_filter_checks: list[tk.Checkbutton] = []
        name_filters = ("INF", "Patching", "Deployment", "Build")
        for idx, name_filter in enumerate(name_filters):
            chk = tk.Checkbutton(
                self.collvariable_name_filters_frame,
                text=name_filter,
                variable=self.collvariable_name_filter_vars[name_filter],
                command=self._apply_collvariable_name_filters,
                anchor="w",
                padx=4,
            )
            chk.pack(side="left", padx=(0, 10) if idx < len(name_filters) - 1 else 0)
            self.collvariable_name_filter_checks.append(chk)
        self.collvariable_combo_label = tk.Label(
            self.collvariable_panel,
            text="Collections",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.collvariable_combo_label.pack(anchor="w")
        self.collvariable_list_frame = tk.Frame(self.collvariable_panel)
        self.collvariable_list_frame.pack(fill="both", expand=False, pady=(4, 0))
        self.collvariable_listbox = tk.Listbox(
            self.collvariable_list_frame,
            selectmode="extended",
            height=6,
            exportselection=False,
            activestyle="none",
            font=("Segoe UI", 10),
        )
        self.collvariable_listbox.pack(side="left", fill="both", expand=True)
        self.collvariable_listbox.bind("<<ListboxSelect>>", self.on_collvariable_collections_selected)
        self.collvariable_list_scrollbar = ttk.Scrollbar(
            self.collvariable_list_frame,
            orient="vertical",
            command=self.collvariable_listbox.yview,
        )
        self.collvariable_list_scrollbar.pack(side="right", fill="y")
        self.collvariable_listbox.configure(yscrollcommand=self.collvariable_list_scrollbar.set)
        for widget in (
            self.collvariable_panel,
            self.collvariable_filter_label,
            self.collvariable_filter_row,
            self.collvariable_filter_entry,
            self.collvariable_search_button,
            self.collvariable_name_filters_frame,
            self.collvariable_combo_label,
            self.collvariable_list_frame,
            self.collvariable_listbox,
        ):
            widget.bind("<MouseWheel>", self._on_collmember_output_mousewheel)

        # ── Copy Deplmt panel ────────────────────────────────────────────────
        self.copydeplmt_panel = tk.Frame(self.check_card)
        self.copydeplmt_title = tk.Label(
            self.copydeplmt_panel,
            text="Copy deployments",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        )
        self.copydeplmt_title.pack(anchor="w")

        # Source type selection
        self.copydeplmt_source_frame = tk.Frame(self.copydeplmt_panel)
        self.copydeplmt_source_frame.pack(fill="x", pady=(4, 6))
        self.copydeplmt_source_label = tk.Label(
            self.copydeplmt_source_frame,
            text="Source types",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.copydeplmt_source_label.pack(anchor="w")
        self.copydeplmt_source_types_frame = tk.Frame(self.copydeplmt_source_frame)
        self.copydeplmt_source_types_frame.pack(anchor="w", pady=(4, 0))
        self.copydeplmt_source_type_vars: dict[str, tk.BooleanVar] = {}
        self.copydeplmt_source_type_map = {
            "TS": "Task Sequence",
            "SUG": "Software Update Group",
            "App": "Application",
            "Program": "Program",
            "Baseline": "Baseline",
        }
        self.copydeplmt_source_type_checks: list[tk.Checkbutton] = []
        for key in ("TS", "SUG", "App", "Program", "Baseline"):
            var = tk.BooleanVar(value=(key == "TS"))
            self.copydeplmt_source_type_vars[key] = var
            checkbutton = tk.Checkbutton(
                self.copydeplmt_source_types_frame,
                text=key,
                variable=var,
                font=("Segoe UI", 9),
                anchor="w",
                padx=4,
                pady=2,
            )
            checkbutton.pack(side="left", padx=(0, 6))
            self.copydeplmt_source_type_checks.append(checkbutton)

        # Source collection lookup
        self.copydeplmt_collections_frame = tk.Frame(self.copydeplmt_panel)
        self.copydeplmt_collections_frame.pack(fill="x", pady=(6, 8))
        self.copydeplmt_source_collection_frame = tk.Frame(self.copydeplmt_collections_frame)
        self.copydeplmt_source_collection_frame.pack(fill="x")
        self.copydeplmt_source_collection_label = tk.Label(
            self.copydeplmt_source_collection_frame,
            text="Source collection filter",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.copydeplmt_source_collection_label.pack(anchor="w")
        self.copydeplmt_source_collection_row = tk.Frame(self.copydeplmt_source_collection_frame)
        self.copydeplmt_source_collection_row.pack(fill="x", pady=(4, 0))
        self.copydeplmt_source_collection_filter_var = tk.StringVar()
        self.copydeplmt_source_collection_var = tk.StringVar()
        self.copydeplmt_collections: list[str] = []
        self.copydeplmt_source_collection_entry = tk.Entry(
            self.copydeplmt_source_collection_row,
            textvariable=self.copydeplmt_source_collection_filter_var,
            font=("Segoe UI", 10),
        )
        self.copydeplmt_source_collection_entry.pack(side="left", fill="x", expand=True)
        self.copydeplmt_collection_search_button = tk.Button(
            self.copydeplmt_source_collection_row,
            text="Search",
            command=self.load_copydeplmt_collections,
            font=("Segoe UI", 9),
            padx=8,
            pady=5,
        )
        self.copydeplmt_collection_search_button.pack(side="left", padx=(8, 0))
        self._set_widget_icon(self.copydeplmt_collection_search_button, "🔍", "", size=16, compound="center")
        setattr(self.copydeplmt_collection_search_button, "_outlined_button", True)
        self.copydeplmt_source_collection_entry.bind("<KeyRelease>", self._filter_copydeplmt_collections)

        self.copydeplmt_collection_combo_label = tk.Label(
            self.copydeplmt_source_collection_frame,
            text="Source collection",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.copydeplmt_collection_combo_label.pack(anchor="w", pady=(8, 0))
        self.copydeplmt_source_collection_combo = ttk.Combobox(
            self.copydeplmt_source_collection_frame,
            values=[],
            state="readonly",
            style="CollMember.TCombobox",
            textvariable=self.copydeplmt_source_collection_var,
        )
        self.copydeplmt_source_collection_combo.pack(fill="x", pady=(4, 0))
        self.copydeplmt_source_collection_combo.bind("<<ComboboxSelected>>", self._on_copydeplmt_collection_selected)

        # Deployment list and selection
        self.copydeplmt_filter_row = tk.Frame(self.copydeplmt_panel)
        self.copydeplmt_filter_row.pack(fill="x", pady=(0, 8))
        self.copydeplmt_filter_label = tk.Label(
            self.copydeplmt_filter_row,
            text="Deployments",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.copydeplmt_filter_label.pack(side="left")
        self.copydeplmt_filter_button = tk.Button(
            self.copydeplmt_filter_row,
            text="Load",
            command=self.filter_copy_deployment_candidates,
            font=("Segoe UI", 9),
            padx=8,
            pady=5,
        )
        self.copydeplmt_filter_button.pack(side="left", padx=(8, 0))
        self._set_widget_icon(self.copydeplmt_filter_button, "🔍", "", size=16, compound="center")
        setattr(self.copydeplmt_filter_button, "_outlined_button", True)

        self.copydeplmt_candidates_frame = tk.Frame(self.copydeplmt_panel)
        self.copydeplmt_candidates_frame.pack(fill="both", expand=False, pady=(0, 8))
        self.copydeplmt_candidates_tree = ttk.Treeview(
            self.copydeplmt_candidates_frame,
            columns=("checked", "name", "type", "start", "collection"),
            show="headings",
            height=8,
            style="DPLM.Treeview",
        )
        self.copydeplmt_candidates_tree.heading("checked", text="Select")
        self.copydeplmt_candidates_tree.heading("name", text="Deployment")
        self.copydeplmt_candidates_tree.heading("type", text="Type")
        self.copydeplmt_candidates_tree.heading("start", text="Start")
        self.copydeplmt_candidates_tree.heading("collection", text="Collection")
        self.copydeplmt_candidates_tree.column("checked", width=52, minwidth=52, anchor="center", stretch=False)
        self.copydeplmt_candidates_tree.column("name", width=300, minwidth=220, anchor="w", stretch=True)
        self.copydeplmt_candidates_tree.column("type", width=160, minwidth=130, anchor="w", stretch=False)
        self.copydeplmt_candidates_tree.column("start", width=150, minwidth=130, anchor="center", stretch=False)
        self.copydeplmt_candidates_tree.column("collection", width=220, minwidth=150, anchor="w", stretch=True)
        self.copydeplmt_candidates_tree.pack(side="left", fill="both", expand=True)
        self.copydeplmt_candidates_tree.bind("<Button-1>", self._on_copydeplmt_candidates_tree_click)
        self.copydeplmt_candidates_tree.bind("<<TreeviewSelect>>", self._on_copydeplmt_candidate_selected)
        self.copydeplmt_candidates_scrollbar = ttk.Scrollbar(
            self.copydeplmt_candidates_frame,
            orient="vertical",
            command=self.copydeplmt_candidates_tree.yview,
        )
        self.copydeplmt_candidates_scrollbar.pack(side="right", fill="y")
        self.copydeplmt_candidates_tree.configure(yscrollcommand=self.copydeplmt_candidates_scrollbar.set)
        self.copydeplmt_all_candidates: list[dict[str, str]] = []
        self.copydeplmt_filtered_candidates: list[dict[str, str]] = []
        self.copydeplmt_checked_candidates: set[str] = set()
        self.copydeplmt_candidate_details_by_key: dict[str, dict[str, str]] = {}

        # Selected deployment details
        self.copydeplmt_details_frame = tk.Frame(self.copydeplmt_panel)
        self.copydeplmt_details_frame.pack(fill="both", expand=False, pady=(0, 8))
        self.copydeplmt_details_label = tk.Label(
            self.copydeplmt_details_frame,
            text="Deployment details",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.copydeplmt_details_label.pack(anchor="w")
        self.copydeplmt_details_tree = ttk.Treeview(
            self.copydeplmt_details_frame,
            columns=("property", "value"),
            show="headings",
            height=9,
            style="DPLM.Treeview",
        )
        self.copydeplmt_details_tree.heading("property", text="Property")
        self.copydeplmt_details_tree.heading("value", text="Value")
        self.copydeplmt_details_tree.column("property", width=300, minwidth=220, anchor="w", stretch=False)
        self.copydeplmt_details_tree.column("value", width=560, minwidth=320, anchor="w", stretch=True)
        self.copydeplmt_details_tree.pack(side="left", fill="both", expand=True)
        self.copydeplmt_details_scrollbar = ttk.Scrollbar(
            self.copydeplmt_details_frame,
            orient="vertical",
            command=self.copydeplmt_details_tree.yview,
        )
        self.copydeplmt_details_scrollbar.pack(side="right", fill="y")
        self.copydeplmt_details_tree.configure(yscrollcommand=self.copydeplmt_details_scrollbar.set)
        self.copydeplmt_details_tree.insert("", "end", values=("Info", "Select a deployment to view details."))

        # Destination collection and action
        self.copydeplmt_destination_collection_frame = tk.Frame(self.copydeplmt_panel)
        self.copydeplmt_destination_collection_frame.pack(fill="x", pady=(0, 8))
        self.copydeplmt_destination_collection_label = tk.Label(
            self.copydeplmt_destination_collection_frame,
            text="Destination collection",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.copydeplmt_destination_collection_label.pack(anchor="w")
        self.copydeplmt_destination_collection_var = tk.StringVar()
        self.copydeplmt_destination_collection_entry = tk.Entry(
            self.copydeplmt_destination_collection_frame,
            textvariable=self.copydeplmt_destination_collection_var,
            font=("Segoe UI", 10),
        )
        self.copydeplmt_destination_collection_entry.pack(fill="x", pady=(4, 0))

        self.copydeplmt_row = tk.Frame(self.copydeplmt_panel)
        self.copydeplmt_row.pack(fill="x", pady=(0, 8))
        self.copydeplmt_button = tk.Button(
            self.copydeplmt_row,
            text="Copy",
            command=self.copy_deployment_value,
            font=("Segoe UI", 9),
        )
        self.copydeplmt_button.pack(side="left", padx=(8, 0))
        self._set_widget_icon(self.copydeplmt_button, "📋", "", size=16, compound="center")
        self.copydeplmt_button.configure(width=0, height=0, padx=8, pady=5)
        setattr(self.copydeplmt_button, "_outlined_button", True)
        self.copydeplmt_hint = tk.Label(
            self.copydeplmt_panel,
            text="Use the source collection + loupe to load deployments, then select one or more entries.",
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.copydeplmt_hint.pack(anchor="w")

        # ── Last 10 DPLM panel ───────────────────────────────────────────────
        self.last10_card = tk.Frame(self.tools_area_card, padx=22, pady=20)

        dplm_header = tk.Frame(self.last10_card)
        dplm_header.pack(fill="x")
        self.dplm_title_label = tk.Label(dplm_header, text="Last 10 Deployments", font=("Segoe UI", 21, "bold"))
        self.dplm_title_label.pack(side="left", anchor="w")
        self._set_widget_icon(self.dplm_title_label, "📋", "Last 10 Deployments", size=20)
        self.dplm_refresh_button = tk.Button(dplm_header, text="Refresh", command=self.run_last10_dplm)
        self.dplm_refresh_button.pack(side="right", anchor="e")
        self._set_widget_icon(self.dplm_refresh_button, "🔄", "Refresh", size=16)

        tk.Label(
            self.last10_card,
            text="The last 10 active deployments sorted by start date.",
            font=("Segoe UI", 13),
        ).pack(anchor="w", pady=(4, 14))

        dplm_tree_frame = tk.Frame(self.last10_card)
        dplm_tree_frame.pack(fill="both", expand=True)

        dplm_cols = ("name", "collection", "start", "targeted", "inprogress", "success", "errors")
        self.dplm_tree = ttk.Treeview(
            dplm_tree_frame,
            columns=dplm_cols,
            show="headings",
            style="DPLM.Treeview",
            height=10,
        )
        col_defs = [
            ("name",       "Deployment name",      280, "w",      True),
            ("collection", "Collection",            160, "w",      True),
            ("start",      "Start",                 138, "center", False),
            ("targeted",   "Assets",                 82, "center", False),
            ("inprogress", "In progress",            82, "center", False),
            ("success",    "Success",                82, "center", False),
            ("errors",     "Errors",                 82, "center", False),
        ]
        for col_id, heading, width, anchor, stretch in col_defs:
            self.dplm_tree.heading(col_id, text=heading, anchor=anchor)
            self.dplm_tree.column(col_id, width=width, minwidth=width, anchor=anchor, stretch=stretch)

        dplm_vsb = ttk.Scrollbar(dplm_tree_frame, orient="vertical", command=self.dplm_tree.yview)
        dplm_hsb = ttk.Scrollbar(dplm_tree_frame, orient="horizontal", command=self.dplm_tree.xview)
        self.dplm_tree.configure(yscrollcommand=dplm_vsb.set, xscrollcommand=dplm_hsb.set)

        dplm_hsb.pack(side="bottom", fill="x")
        dplm_vsb.pack(side="right", fill="y")
        self.dplm_tree.pack(side="left", fill="both", expand=True)

        self.output_card = tk.Frame(self.tools_area_card, padx=0, pady=0)
        self.output_card.pack(fill="both", expand=True, padx=14, pady=(8, 14))

        self.output_title = tk.Label(self.output_card, text="Tool Output", font=("Segoe UI", 14, "bold"), anchor="w", padx=14, pady=8)
        self.output_title.pack(fill="x")

        self.inner_separator_2 = tk.Frame(self.output_card, height=1)
        self.inner_separator_2.pack(fill="x")

        self.output_text = tk.Text(self.output_card, font=("Consolas", 13), wrap="word", relief="flat", padx=14, pady=14)
        self.output_text.pack(fill="both", expand=True, padx=8, pady=8)
        self.output_text.insert("end", "Waiting for output...\n")
        self._make_text_output_readonly(self.output_text)

        self.collmember_scroll_container = tk.Frame(self.output_card)
        self.collmember_output_canvas = tk.Canvas(self.collmember_scroll_container, bd=0, highlightthickness=0)
        self.collmember_output_canvas.pack(side="left", fill="both", expand=True)
        self.collmember_output_scrollbar = ttk.Scrollbar(
            self.collmember_scroll_container,
            orient="vertical",
            command=self.collmember_output_canvas.yview,
        )
        self.collmember_output_scrollbar.pack(side="right", fill="y")
        self.collmember_output_canvas.configure(yscrollcommand=self.collmember_output_scrollbar.set)
        self.collmember_output_split = tk.Frame(self.collmember_output_canvas)
        self.collmember_output_window = self.collmember_output_canvas.create_window(
            (0, 0),
            window=self.collmember_output_split,
            anchor="nw",
        )
        self.collmember_output_split.bind("<Configure>", self._on_collmember_output_frame_configure)
        self.collmember_output_canvas.bind("<Configure>", self._on_collmember_output_canvas_configure)

        self.collmember_types_frame = tk.Frame(self.collmember_output_split)
        self.collmember_types_title = tk.Label(
            self.collmember_types_frame,
            text="TAB 1 - Membership Type",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=8,
            pady=6,
        )
        self.collmember_types_title.pack(fill="x")
        collmember_types_grid = tk.Frame(self.collmember_types_frame)
        collmember_types_grid.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.collmember_types_tree = ttk.Treeview(
            collmember_types_grid,
            columns=("type", "present"),
            show="headings",
            style="CollMemberType.Treeview",
            height=5,
        )
        self.collmember_types_tree.heading("type", text="Type")
        self.collmember_types_tree.heading("present", text="Present")
        self.collmember_types_tree.column("type", width=280, minwidth=220, anchor="w", stretch=True)
        self.collmember_types_tree.column("present", width=100, minwidth=90, anchor="center", stretch=False)
        self.collmember_types_tree.pack(side="left", fill="both", expand=True)

        self.collmember_queries_frame = tk.Frame(self.collmember_output_split)
        self.collmember_queries_title = tk.Label(
            self.collmember_queries_frame,
            text="TAB 2 - Query details",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=8,
            pady=6,
        )
        self.collmember_queries_title.pack(fill="x")
        self.collmember_queries_actions = tk.Frame(self.collmember_queries_frame)
        self.collmember_queries_actions.pack(fill="x", padx=8, pady=(0, 6))
        self.collmember_query_copy_button = tk.Button(
            self.collmember_queries_actions,
            text="Copy query",
            command=self.copy_selected_collmember_query,
            font=("Segoe UI", 9),
        )
        self.collmember_query_copy_button.pack(side="left", padx=(0, 8))
        self._set_widget_icon(self.collmember_query_copy_button, "📋", "Copy query", size=14)
        self.collmember_query_edit_button = tk.Button(
            self.collmember_queries_actions,
            text="Edit query",
            command=self.edit_selected_collmember_query,
            font=("Segoe UI", 9),
        )
        self.collmember_query_edit_button.pack(side="left")
        self._set_widget_icon(self.collmember_query_edit_button, "✏️", "Edit query", size=14)
        self.collmember_query_new_button = tk.Button(
            self.collmember_queries_actions,
            text="New query",
            command=self.create_collmember_query,
            font=("Segoe UI", 9),
        )
        self.collmember_query_new_button.pack(side="left", padx=(8, 0))
        self._set_widget_icon(self.collmember_query_new_button, "➕", "New query", size=14)
        self.collmember_query_device_list_button = tk.Button(
            self.collmember_queries_actions,
            text="Device list query",
            command=self.create_collmember_device_list_query,
            font=("Segoe UI", 9),
        )
        self.collmember_query_device_list_button.pack(side="left", padx=(8, 0))
        self._set_widget_icon(self.collmember_query_device_list_button, "🖥", "Device list query", size=14)
        for button in (
            self.collmember_query_copy_button,
            self.collmember_query_edit_button,
            self.collmember_query_new_button,
            self.collmember_query_device_list_button,
        ):
            button.configure(width=0, height=0, padx=8, pady=5)
            setattr(button, "_outlined_button", True)
        collmember_queries_grid = tk.Frame(self.collmember_queries_frame)
        collmember_queries_grid.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.collmember_queries_tree = ttk.Treeview(
            collmember_queries_grid,
            columns=("rulename", "query"),
            show="headings",
            style="CollMemberQuery.Treeview",
            height=8,
        )
        self.collmember_queries_tree.heading("rulename", text="RuleName")
        self.collmember_queries_tree.heading("query", text="Query")
        self.collmember_queries_tree.column("rulename", width=220, minwidth=160, anchor="w", stretch=False)
        self.collmember_queries_tree.column("query", width=800, minwidth=300, anchor="w", stretch=True)
        self.collmember_queries_tree.pack(side="left", fill="both", expand=True)

        self.collmember_machines_frame = tk.Frame(self.collmember_output_split)
        self.collmember_machines_title = tk.Label(
            self.collmember_machines_frame,
            text="TAB 3 - Devices/Users",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=8,
            pady=6,
        )
        self.collmember_machines_title.pack(fill="x")
        self.collmember_machines_filter_row = tk.Frame(self.collmember_machines_frame)
        self.collmember_machines_filter_row.pack(fill="x", padx=8, pady=(0, 6))
        self.collmember_machines_filter_label = tk.Label(
            self.collmember_machines_filter_row,
            text="Machine filter",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        )
        self.collmember_machines_filter_label.pack(side="left")
        self.collmember_machines_filter_entry = tk.Entry(
            self.collmember_machines_filter_row,
            textvariable=self.collmember_machine_filter_var,
            font=("Segoe UI", 9),
        )
        self.collmember_machines_filter_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.collmember_machines_filter_entry.bind("<KeyRelease>", self._filter_collmember_machines)
        collmember_machines_grid = tk.Frame(self.collmember_machines_frame)
        collmember_machines_grid.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.collmember_machines_tree = ttk.Treeview(
            collmember_machines_grid,
            columns=("machine",),
            show="headings",
            style="CollMemberMachine.Treeview",
            height=8,
        )
        self.collmember_machines_tree.heading("machine", text="Machine")
        self.collmember_machines_tree.column("machine", width=420, minwidth=260, anchor="w", stretch=True)
        self.collmember_machines_tree.pack(side="left", fill="both", expand=True)

        self.collmember_types_frame.pack(fill="both", expand=True)
        self.collmember_queries_frame.pack(fill="both", expand=True, pady=(8, 0))
        self.collmember_machines_frame.pack(fill="both", expand=True, pady=(8, 0))
        for widget in (
            self.collmember_output_canvas,
            self.collmember_output_split,
            self.collmember_types_frame,
            self.collmember_types_title,
            collmember_types_grid,
            self.collmember_types_tree,
            self.collmember_queries_frame,
            self.collmember_queries_title,
            self.collmember_queries_actions,
            self.collmember_query_copy_button,
            self.collmember_query_edit_button,
            self.collmember_query_new_button,
            self.collmember_query_device_list_button,
            collmember_queries_grid,
            self.collmember_queries_tree,
            self.collmember_machines_frame,
            self.collmember_machines_title,
            self.collmember_machines_filter_row,
            self.collmember_machines_filter_label,
            self.collmember_machines_filter_entry,
            collmember_machines_grid,
            self.collmember_machines_tree,
        ):
            widget.bind("<MouseWheel>", self._on_collmember_output_mousewheel)

        self.collvariable_output_split = tk.Frame(self.output_card)
        self.collvariable_names_values: list[tuple[str, str]] = []
        self.collvariable_groups: list[str] = []
        self.collvariable_actions = tk.Frame(self.collvariable_output_split)
        self.collvariable_actions.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=(8, 4))
        self.collvariable_add_button = tk.Button(
            self.collvariable_actions,
            text="ADD",
            command=self.add_collvariable_variable,
            font=("Segoe UI", 9),
        )
        self._set_fixed_button_icon(self.collvariable_add_button, "➕", "ADD", size=14)
        self.collvariable_new_button = tk.Button(
            self.collvariable_actions,
            text="NEW",
            command=self.new_collvariable_variable,
            font=("Segoe UI", 9),
        )
        self._set_fixed_button_icon(self.collvariable_new_button, "🆕", "NEW", size=14)
        self.collvariable_remove_button = tk.Button(
            self.collvariable_actions,
            text="REMOVE",
            command=self.remove_collvariable_variable,
            font=("Segoe UI", 9),
        )
        self._set_fixed_button_icon(self.collvariable_remove_button, "🗑", "REMOVE", size=14)
        self.collvariable_replace_button = tk.Button(
            self.collvariable_actions,
            text="REPLACE",
            command=self.replace_collvariable_variable,
            font=("Segoe UI", 9),
        )
        self._set_fixed_button_icon(self.collvariable_replace_button, "♻️", "REPLACE", size=14)
        self.collvariable_renumber_button = tk.Button(
            self.collvariable_actions,
            text="RE-NUMBER",
            command=self.renumber_collvariable_variables,
            font=("Segoe UI", 9),
        )
        self._set_fixed_button_icon(self.collvariable_renumber_button, "🔢", "RE-NUMBER", size=14)
        self.collvariable_action_buttons = (
            self.collvariable_new_button,
            self.collvariable_add_button,
            self.collvariable_remove_button,
            self.collvariable_replace_button,
            self.collvariable_renumber_button,
        )
        for button in self.collvariable_action_buttons:
            button.configure(width=0, height=0, padx=8, pady=5)
            setattr(button, "_outlined_button", True)
        self._layout_collvariable_action_buttons(compact=False)

        self.collvariable_tab1_frame = tk.Frame(self.collvariable_output_split)
        self.collvariable_tab1_title = tk.Label(
            self.collvariable_tab1_frame,
            text="TAB 1 - Name / Value",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=8,
            pady=6,
        )
        self.collvariable_tab1_title.pack(fill="x")
        collvariable_tab1_grid = tk.Frame(self.collvariable_tab1_frame)
        collvariable_tab1_grid.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.collvariable_tab1_tree = ttk.Treeview(
            collvariable_tab1_grid,
            columns=("name", "value"),
            show="headings",
            style="CollVariableNameValue.Treeview",
            height=8,
        )
        self.collvariable_tab1_tree.heading("name", text="Name")
        self.collvariable_tab1_tree.heading("value", text="Value")
        self.collvariable_tab1_tree.column("name", width=320, minwidth=220, anchor="w", stretch=True)
        self.collvariable_tab1_tree.column("value", width=620, minwidth=240, anchor="w", stretch=True)
        self.collvariable_tab1_tree.pack(side="left", fill="both", expand=True)

        self.collvariable_tab2_frame = tk.Frame(self.collvariable_output_split)
        self.collvariable_tab2_title = tk.Label(
            self.collvariable_tab2_frame,
            text="TAB 2 - Name filter by type",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            padx=8,
            pady=6,
        )
        self.collvariable_tab2_title.pack(fill="x")
        collvariable_tab2_grid = tk.Frame(self.collvariable_tab2_frame)
        collvariable_tab2_grid.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self.collvariable_tab2_tree = ttk.Treeview(
            collvariable_tab2_grid,
            columns=("name",),
            show="headings",
            style="CollVariableFilter.Treeview",
            height=7,
        )
        self.collvariable_tab2_tree.heading("name", text="Name")
        self.collvariable_tab2_tree.column("name", width=420, minwidth=260, anchor="w", stretch=True)
        self.collvariable_tab2_tree.pack(side="left", fill="both", expand=True)
        self.collvariable_tab2_tree.bind("<<TreeviewSelect>>", self._on_collvariable_group_selected)

        self.collvariable_output_split.columnconfigure(0, weight=2)
        self.collvariable_output_split.columnconfigure(1, weight=3)
        self.collvariable_output_split.rowconfigure(1, weight=1)
        self.collvariable_tab1_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 4))
        self.collvariable_tab2_frame.grid(row=1, column=1, sticky="nsew", padx=(4, 0))

    def build_ps1_tab(self) -> None:
        frame = tk.Frame(self.content, padx=18, pady=18)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.tab_frames["PS1"] = frame

        self.sccm_ps1_button = tk.Button(frame, text="SCCM", command=self.open_sccm_from_menu)
        self.sccm_ps1_button.pack(anchor="w", pady=(0, 10))
        self._set_widget_icon(self.sccm_ps1_button, "🏠", "SCCM", size=14)
        self.sccm_buttons.append(self.sccm_ps1_button)

        tk.Label(frame, text="PowerShell Scripts", font=("Segoe UI", 21, "bold")).pack(anchor="w")
        self.ps1_folder_label = tk.Label(frame, text="", font=("Segoe UI", 11), anchor="w")
        self.ps1_folder_label.pack(anchor="w", pady=(2, 12))

        actions = tk.Frame(frame)
        actions.pack(fill="x", pady=(0, 10))
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)

        actions_left = tk.Frame(actions)
        actions_left.grid(row=0, column=0, sticky="w")
        actions_right = tk.Frame(actions)
        actions_right.grid(row=0, column=1, sticky="e")

        left_actions = [
            ("📂", "Parcourir dossier", self.browse_ps1_folder),
            ("🗑", "Clear selection", self.clear_saved_ps1_folder),
        ]
        right_actions = [
            ("▶️", "Run Script", self.run_selected_ps1),
            ("👁", "Preview", self.open_selected_ps1_preview),
            ("🖥", "Edit", self.open_selected_ps1_in_ise),
            ("🧹", "Clear", self.clear_ps1_output),
            ("🔄", "Refresh", self.refresh_ps1_list),
        ]

        def make_toolbar_buttons(container: tk.Frame, items: list[tuple[str, str, object]]) -> None:
            for idx, (glyph, label, handler) in enumerate(items):
                btn = tk.Button(container, text=label, command=handler, font=("Segoe UI", 9))
                btn.pack(side="left", padx=(0, 8) if idx < len(items) - 1 else 0)
                self._set_widget_icon(btn, glyph, label, size=16)
                btn.configure(width=0, height=0, padx=8, pady=5)
                setattr(btn, "_outlined_button", True)

        make_toolbar_buttons(actions_left, left_actions)
        make_toolbar_buttons(actions_right, right_actions)

        self.ps1_body_pane = tk.PanedWindow(frame, orient="horizontal", sashrelief="flat", bd=0)
        self.ps1_body_pane.pack(fill="both", expand=True)

        self.ps1_tree_panel = tk.Frame(self.ps1_body_pane)
        self.ps1_output_panel = tk.Frame(self.ps1_body_pane)
        self.ps1_body_pane.add(self.ps1_tree_panel, minsize=220)
        self.ps1_body_pane.add(self.ps1_output_panel, minsize=260)

        self.ps1_tree = ttk.Treeview(self.ps1_tree_panel, show="tree", selectmode="browse")
        self.ps1_tree.pack(side="left", fill="both", expand=True, padx=(0, 10))
        ps1_scroll = ttk.Scrollbar(self.ps1_tree_panel, orient="vertical", command=self.ps1_tree.yview)
        ps1_scroll.pack(side="left", fill="y")
        self.ps1_tree.configure(yscrollcommand=ps1_scroll.set)

        self.ps1_output = tk.Text(self.ps1_output_panel, font=("Consolas", 11), wrap="word", relief="flat")
        self.ps1_output.pack(fill="both", expand=True)
        self._make_text_output_readonly(self.ps1_output)

    def build_infra_tab(self) -> None:
        frame = tk.Frame(self.content, padx=18, pady=18)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.tab_frames["InfraTools"] = frame

        self.sccm_infra_button = tk.Button(frame, text="SCCM", command=self.open_sccm_from_menu)
        self.sccm_infra_button.pack(anchor="w", pady=(0, 10))
        self._set_widget_icon(self.sccm_infra_button, "🏠", "SCCM", size=14)
        self.sccm_buttons.append(self.sccm_infra_button)

        self.infra_layout = tk.Frame(frame)
        self.infra_layout.pack(fill="both", expand=True)

        # ── Left panel ──────────────────────────────────────────────────────
        self.infra_left_panel = tk.Frame(self.infra_layout, width=210)
        self.infra_left_panel.pack(side="left", fill="y", padx=(0, 14))
        self.infra_left_panel.pack_propagate(False)

        self.infra_menu_canvas = tk.Canvas(self.infra_left_panel, bd=0, highlightthickness=0)
        self.infra_menu_canvas.pack(side="left", fill="both", expand=True)
        self.infra_menu_scrollbar = ttk.Scrollbar(
            self.infra_left_panel,
            orient="vertical",
            command=self.infra_menu_canvas.yview,
        )
        self.infra_menu_scrollbar.pack(side="right", fill="y")
        self.infra_menu_canvas.configure(yscrollcommand=self.infra_menu_scrollbar.set)

        self.infra_menu_frame = tk.Frame(self.infra_menu_canvas, padx=6, pady=6)
        self.infra_menu_window = self.infra_menu_canvas.create_window((0, 0), window=self.infra_menu_frame, anchor="nw")
        self.infra_menu_frame.bind("<Configure>", self._on_infra_menu_frame_configure)
        self.infra_menu_canvas.bind("<Configure>", self._on_infra_menu_canvas_configure)
        self.infra_menu_canvas.bind("<MouseWheel>", self._on_infra_menu_mousewheel)

        # ── Right panel ─────────────────────────────────────────────────────
        self.infra_right_panel = tk.Frame(self.infra_layout)
        self.infra_right_panel.pack(side="left", fill="both", expand=True)

        self.infra_tool_title = tk.Label(
            self.infra_right_panel,
            text="Select a tool",
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        )
        self.infra_tool_title.pack(fill="x", pady=(0, 8))

        self.infra_launch_button = tk.Button(
            self.infra_right_panel,
            text="Launch",
            command=self.launch_infra_tool,
        )
        self.infra_launch_button.pack(anchor="w", pady=(0, 10))
        self._set_widget_icon(self.infra_launch_button, "▶️", "Launch", size=14)

        self.infra_output = tk.Text(self.infra_right_panel, font=("Consolas", 11), wrap="word", relief="flat")
        self.infra_output.pack(fill="both", expand=True)
        self._make_text_output_readonly(self.infra_output)

        # ── Tool groups ──────────────────────────────────────────────────────
        infra_dir = self.base_dir / "Infra TOOLS"
        groups = [
            ("Built-in", [
                ("ping_sccm", "Ping serveur SCCM", "builtin", None),
            ]),
            ("Client Tools", [
                ("CliSpy",                    "CliSpy",                    "exe", infra_dir / "ClientTools" / "CliSpy.exe"),
                ("DeploymentMonitoringTool",  "DeploymentMonitoringTool",  "exe", infra_dir / "ClientTools" / "DeploymentMonitoringTool.exe"),
                ("PolicySpy",                "PolicySpy",                 "exe", infra_dir / "ClientTools" / "PolicySpy.exe"),
                ("PowerVwr",                 "PowerVwr",                  "exe", infra_dir / "ClientTools" / "PowerVwr.exe"),
            ]),
            ("Server Tools", [
                ("ContentLibraryExplorer",   "ContentLibraryExplorer",    "exe", infra_dir / "ServerTools" / "ContentLibraryExplorer.exe"),
                ("ContentOwnershipTool",     "ContentOwnershipTool",      "exe", infra_dir / "ServerTools" / "ContentOwnershipTool.exe"),
                ("DPJobMgr",                 "DPJobMgr",                  "exe", infra_dir / "ServerTools" / "DPJobMgr.exe"),
            ]),
            ("Service Connection", [
                ("ServiceConnectionTool",    "ServiceConnectionTool",     "exe", infra_dir / "ServiceConnectionTool" / "ServiceConnectionTool.exe"),
                ("setupdl",                  "setupdl",                   "exe", infra_dir / "ServiceConnectionTool" / "setupdl.exe"),
            ]),
            ("Port Config", [
                ("Portswitch",               "Portswitch",                "vbs", infra_dir / "PortConfiguration" / "Portswitch.vbs"),
            ]),
        ]

        for group_label, tools in groups:
            group_icon_map = {
                "Built-in": "🏓",
                "Client Tools": "👤",
                "Server Tools": "🖥",
                "Service Connection": "🔗",
                "Port Config": "🔌",
            }
            label_widget = tk.Label(
                self.infra_menu_frame,
                text=group_label,
                font=("Segoe UI", 9, "bold"),
                anchor="w",
                padx=4,
            )
            label_widget.pack(fill="x", pady=(8, 2))
            label_widget.bind("<MouseWheel>", self._on_infra_menu_mousewheel)
            self._set_widget_icon(label_widget, group_icon_map.get(group_label, "📁"), group_label, size=13)
            for key, label, tool_type, path in tools:
                self.infra_tools_map[key] = (path, tool_type, label)
                btn = tk.Button(
                    self.infra_menu_frame,
                    text=label,
                    anchor="w",
                    padx=14,
                    pady=8,
                    command=lambda k=key: self.select_infra_tool(k),
                    relief="flat",
                    bd=0,
                    highlightthickness=0,
                    font=("Segoe UI", 10),
                )
                btn.pack(fill="x", pady=2)
                btn.bind("<MouseWheel>", self._on_infra_menu_mousewheel)
                if key == "ping_sccm":
                    self._set_widget_icon(btn, "📡", label, size=13)
                self.infra_menu_buttons.append((key, btn))

    def build_cmtrace_tab(self) -> None:
        frame = tk.Frame(self.content, padx=0, pady=0)
        frame.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.tab_frames["CMTrace"] = frame

        # Status label kept for state updates but not displayed (webview fills the tab)
        self.cmtrace_status_label = tk.Label(frame, text="Initializing CMTraceDev...", font=("Segoe UI", 10, "bold"), anchor="w")

        # Dedicated host frame used to embed the external WinForms WebView window.
        self.cmtrace_web_host = tk.Frame(frame, height=520, bd=0, highlightthickness=0)
        self.cmtrace_web_host.pack(fill="both", expand=True)
        self.cmtrace_web_host.pack_propagate(False)
        self.cmtrace_web_host.bind("<Configure>", self._on_cmtrace_host_resize)

        self.cmtrace_embed_placeholder = tk.Label(
            self.cmtrace_web_host,
            text="Preparing CMTrace WebView...",
            anchor="center",
            justify="center",
            padx=10,
            pady=10,
        )
        self.cmtrace_embed_placeholder.pack(fill="both", expand=True)
        self.cmtrace_output = tk.Text(frame, font=("Consolas", 10), wrap="word", relief="flat", height=4)
        self.cmtrace_output.pack(fill="x", expand=False, pady=(8, 0))
        self._make_text_output_readonly(self.cmtrace_output)

    def apply_theme(self) -> None:
        t = DARK_THEME if self.theme_name == "dark" else LIGHT_THEME
        self.theme = t
        self.configure(bg=t["window"])

        self.root_frame.configure(bg=t["window"])
        self.main_card.configure(bg=t["surface"], highlightthickness=1, highlightbackground=t["border"])
        self.header.configure(bg=t["surface"])
        self.header_left.configure(bg=t["surface"])
        self.title_wrap.configure(bg=t["surface"])
        self.header_right.configure(bg=t["surface"])
        self.tab_bar_shell.configure(bg=t["surface"])
        self.tab_canvas.configure(bg=t["surface"])
        self.tab_bar.configure(bg=t["tabs_shell_bg"], bd=0)
        self.separator.configure(bg=t["border"])
        self.content.configure(bg=t["surface"])

        self.title_label.configure(bg=t["surface"], fg=t["text"])
        self.profile_status_label.configure(bg=t["surface"], fg=t["muted_text"])
        self.connection_head.configure(bg=t["surface"], fg=t["text"])
        self.check_title.configure(bg=t["surface"], fg=t["text"])
        self.check_description.configure(bg=t["surface"], fg=t["muted_text"])
        self.output_title.configure(bg=t["surface"], fg=t["text"])
        if hasattr(self, "cmtrace_status_label"):
            self.cmtrace_status_label.configure(bg=t["surface"], fg=t["muted_text"])
        if hasattr(self, "collmember_panel"):
            self.collmember_panel.configure(bg=t["surface"])
            self.collmember_filter_row.configure(bg=t["surface"])
            self.collmember_filter_label.configure(bg=t["surface"], fg=t["text"])
            self.collmember_combo_label.configure(bg=t["surface"], fg=t["text"])
            self.collmember_filter_entry.configure(
                bg=t["surface_2"],
                fg=t["text"],
                insertbackground=t["text"],
                relief="flat",
                highlightthickness=1,
                highlightbackground=t["border"],
                highlightcolor=t["accent_blue"],
            )
            self.style.configure(
                "CollMember.TCombobox",
                fieldbackground=t["surface_2"],
                background=t["surface_2"],
                foreground=t["text"],
                bordercolor=t["border"],
                arrowcolor=t["text"],
            )
            self.style.map(
                "CollMember.TCombobox",
                fieldbackground=[("readonly", t["surface_2"])],
                foreground=[("readonly", t["text"])],
                selectbackground=[("readonly", t["surface_3"])],
                selectforeground=[("readonly", t["text"])],
            )
        if hasattr(self, "collvariable_panel"):
            self.collvariable_panel.configure(bg=t["surface"])
            self.collvariable_filter_row.configure(bg=t["surface"])
            self.collvariable_filter_label.configure(bg=t["surface"], fg=t["text"])
            self.collvariable_combo_label.configure(bg=t["surface"], fg=t["text"])
            self.collvariable_name_filters_frame.configure(bg=t["surface"])
            for checkbox in self.collvariable_name_filter_checks:
                checkbox.configure(
                    bg=t["surface"],
                    fg=t["text"],
                    activebackground=t["surface"],
                    activeforeground=t["text"],
                    selectcolor=t["surface_2"],
                    highlightthickness=0,
                    cursor="hand2",
                )
            self.collvariable_list_frame.configure(bg=t["surface"])
            self.collvariable_listbox.configure(
                bg=t["surface_2"],
                fg=t["text"],
                selectbackground=t["accent_blue"],
                selectforeground="#FFFFFF",
                highlightthickness=1,
                highlightbackground=t["border"],
                highlightcolor=t["accent_blue"],
                relief="flat",
                bd=0,
            )
            self.collvariable_filter_entry.configure(
                bg=t["surface_2"],
                fg=t["text"],
                insertbackground=t["text"],
                relief="flat",
                highlightthickness=1,
                highlightbackground=t["border"],
                highlightcolor=t["accent_blue"],
            )
            self._apply_outlined_button_theme(self.collvariable_search_button, t)
        if hasattr(self, "copydeplmt_panel"):
            self.copydeplmt_panel.configure(bg=t["surface"])
            self.copydeplmt_title.configure(bg=t["surface"], fg=t["text"])
            self.copydeplmt_source_frame.configure(bg=t["surface"])
            self.copydeplmt_source_label.configure(bg=t["surface"], fg=t["text"])
            self.copydeplmt_collections_frame.configure(bg=t["surface"])
            self.copydeplmt_source_collection_frame.configure(bg=t["surface"])
            self.copydeplmt_source_collection_row.configure(bg=t["surface"])
            self.copydeplmt_destination_collection_frame.configure(bg=t["surface"])
            self.copydeplmt_source_types_frame.configure(bg=t["surface"])
            self.copydeplmt_filter_row.configure(bg=t["surface"])
            self.copydeplmt_filter_label.configure(bg=t["surface"], fg=t["text"])
            self.copydeplmt_candidates_frame.configure(bg=t["surface"])
            self.copydeplmt_details_frame.configure(bg=t["surface"])
            self.copydeplmt_details_label.configure(bg=t["surface"], fg=t["text"])
            self.copydeplmt_source_collection_label.configure(bg=t["surface"], fg=t["text"])
            self.copydeplmt_collection_combo_label.configure(bg=t["surface"], fg=t["text"])
            self.copydeplmt_destination_collection_label.configure(bg=t["surface"], fg=t["text"])
            for checkbutton in self.copydeplmt_source_type_checks:
                checkbutton.configure(
                    bg=t["surface"],
                    fg=t["text"],
                    activebackground=t["surface"],
                    activeforeground=t["text"],
                    selectcolor=t["surface_2"],
                    highlightthickness=0,
                    bd=0,
                )
            self.copydeplmt_hint.configure(bg=t["surface"], fg=t["muted_text"])
            for entry_widget in (
                self.copydeplmt_source_collection_entry,
                self.copydeplmt_destination_collection_entry,
            ):
                entry_widget.configure(
                    bg=t["surface_2"],
                    fg=t["text"],
                    insertbackground=t["text"],
                    relief="flat",
                    highlightthickness=1,
                    highlightbackground=t["border"],
                    highlightcolor=t["accent_blue"],
                )
            self._apply_outlined_button_theme(self.copydeplmt_button, t)
            self._apply_outlined_button_theme(self.copydeplmt_filter_button, t, accent_key="accent_blue")
            self._apply_outlined_button_theme(self.copydeplmt_collection_search_button, t, accent_key="accent_blue")
        if hasattr(self, "collmember_output_split"):
            self.collmember_scroll_container.configure(bg=t["surface"])
            self.collmember_output_canvas.configure(
                bg=t["surface"],
                highlightbackground=t["border"],
                highlightcolor=t["border"],
            )
        if hasattr(self, "collvariable_output_split"):
            self.collvariable_output_split.configure(bg=t["surface"])
            self.collvariable_actions.configure(bg=t["surface"])
            self.collvariable_tab1_frame.configure(bg=t["surface"])
            self.collvariable_tab2_frame.configure(bg=t["surface"])
            self.collvariable_tab1_title.configure(bg=t["surface"], fg=t["text"])
            self.collvariable_tab2_title.configure(bg=t["surface"], fg=t["text"])
            for button in (
                self.collvariable_add_button,
                self.collvariable_new_button,
                self.collvariable_remove_button,
                self.collvariable_replace_button,
                self.collvariable_renumber_button,
            ):
                self._apply_outlined_button_theme(button, t)
            self.collmember_output_split.configure(bg=t["surface"])
            self.collmember_types_frame.configure(bg=t["surface"])
            self.collmember_queries_frame.configure(bg=t["surface"])
            self.collmember_machines_frame.configure(bg=t["surface"])
            self.collmember_types_title.configure(bg=t["surface"], fg=t["text"])
            self.collmember_queries_title.configure(bg=t["surface"], fg=t["text"])
            self.collmember_machines_title.configure(bg=t["surface"], fg=t["text"])
            self.collmember_queries_actions.configure(bg=t["surface"])
            self.collmember_machines_filter_row.configure(bg=t["surface"])
            self.collmember_machines_filter_label.configure(bg=t["surface"], fg=t["text"])
            self.collmember_machines_filter_entry.configure(
                bg=t["surface_2"],
                fg=t["text"],
                insertbackground=t["text"],
                relief="flat",
                highlightthickness=1,
                highlightbackground=t["border"],
                highlightcolor=t["accent_blue"],
            )
            for button in (
                self.collmember_search_button,
                self.collmember_query_copy_button,
                self.collmember_query_edit_button,
                self.collmember_query_new_button,
                self.collmember_query_device_list_button,
            ):
                self._apply_outlined_button_theme(button, t)

        self.tools_layout.configure(bg=t["surface"])
        self.left_panel.configure(bg=t["surface"])
        self.vertical_menu.configure(bg=t["surface"], highlightthickness=0, bd=0)
        for item, button in self.vertical_menu_buttons:
            active = item == self.vertical_menu_selected
            button.configure(
                bg=t["sidebar_active"] if active else t["surface"],
                fg="#FFFFFF" if active else t["text"],
                activebackground=t["surface_3"],
                activeforeground=t["text"],
                cursor="hand2",
            )

        icon_button_style = {
            "bg": t["surface_2"],
            "fg": t["text"],
            "activebackground": t["surface_3"],
            "activeforeground": t["text"],
            "relief": "flat",
            "bd": 0,
            "highlightthickness": 0,
            "cursor": "hand2",
            "font": ("Segoe UI", 12, "bold"),
        }
        for button in (self.home_button, self.settings_button, self.theme_button):
            button.configure(**icon_button_style)
        self.home_button.configure(bg=t["surface"], activebackground=t["surface_2"])
        for sccm_button in self.sccm_buttons:
            sccm_button.configure(
                bg=t["accent_blue"],
                fg="#FFFFFF",
                activebackground=t["accent_blue"],
                activeforeground="#FFFFFF",
                relief="flat",
                bd=0,
                highlightthickness=0,
                cursor="hand2",
                font=("Segoe UI", 10, "bold"),
                padx=12,
                pady=6,
                anchor="w",
            )

        if self.theme_name == "dark":
            self._set_widget_icon(self.theme_button, "☀️", "", size=18, compound="center")
        else:
            self._set_widget_icon(self.theme_button, "🌙", "", size=18, compound="center")

        for name, tab_data in self.tab_buttons.items():
            is_active = name == self.current_tab
            fill = t["tabs_btn_active"] if is_active else t["tabs_btn_bg"]
            text_color = t["tabs_btn_text_active"] if is_active else t["tabs_btn_text"]
            tab_data["canvas"].configure(bg=t["tabs_shell_bg"])
            tab_data["canvas"].itemconfigure(tab_data["shape"], fill=fill)
            tab_data["canvas"].itemconfigure(tab_data["text"], fill=text_color)
            if tab_data.get("separator") is not None:
                tab_data["canvas"].itemconfigure(tab_data["separator"], fill=t["tabs_btn_border"])

        self.tools_area_card.configure(bg=t["surface"], highlightthickness=1, highlightbackground=t["border"])
        self.inner_separator_1.configure(bg=t["border"])
        self.check_card.configure(bg=t["surface"], highlightthickness=1, highlightbackground=t["border"])
        self.run_check_button.configure(
            bg=t["accent_blue"],
            fg="#FFFFFF",
            activebackground=t["accent_blue"],
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            font=("Segoe UI", 15, "bold"),
            pady=8,
        )
        self.tools_actions.configure(bg=t["surface"])
        self.output_card.configure(bg=t["surface"], highlightthickness=1, highlightbackground=t["border"])
        self.inner_separator_2.configure(bg=t["border"])

        text_widgets = [self.output_text, self.ps1_output, self.infra_output]
        for widget in text_widgets:
            widget.configure(bg=t["output_bg"], fg=t["text"], insertbackground=t["text"])
        error_color = "#F87171" if self.theme_name == "dark" else "#DC2626"
        self.ps1_output.tag_configure("error", foreground=error_color)
        self.output_text.tag_configure("error", foreground=error_color)

        self._configure_treeview_style("PS1.Treeview",  row_height=24, t=t, widget=self.ps1_tree)
        self._configure_treeview_style("DPLM.Treeview", row_height=26, t=t, widget=self.dplm_tree, heading=True)
        self._configure_treeview_style("CollMemberType.Treeview", row_height=24, t=t, widget=self.collmember_types_tree, heading=True)
        self._configure_treeview_style("CollMemberQuery.Treeview", row_height=24, t=t, widget=self.collmember_queries_tree, heading=True)
        self._configure_treeview_style("CollMemberMachine.Treeview", row_height=24, t=t, widget=self.collmember_machines_tree, heading=True)
        self._configure_treeview_style("CollVariableNameValue.Treeview", row_height=24, t=t, widget=self.collvariable_tab1_tree, heading=True)
        self._configure_treeview_style("CollVariableFilter.Treeview", row_height=24, t=t, widget=self.collvariable_tab2_tree, heading=True)
        self._apply_recursive_theme(self.last10_card, t)

        for tab_name, frame in self.tab_frames.items():
            frame.configure(bg=t["surface"])
            if tab_name != "Tools":
                for child in frame.winfo_children():
                    self._apply_recursive_theme(child, t)

        self.apply_infra_menu_theme()
        self._apply_global_button_size()
        self.update_profile_labels()
        self.draw_tab_capsule()
        # Lift the visible tab frame without triggering CMTrace reload or output reset.
        if self.current_tab in self.tab_frames:
            self.tab_frames[self.current_tab].lift()

    def _apply_global_button_size(self) -> None:
        for widget in self.winfo_children():
            self._apply_button_size_recursive(widget)

    def _apply_button_size_recursive(self, widget: tk.Widget) -> None:
        if isinstance(widget, tk.Button):
            text_value = str(widget.cget("text")).strip()
            if text_value:
                widget.configure(font=("Segoe UI", 10, "bold"))
            widget.configure(padx=10, pady=6)
        for child in widget.winfo_children():
            self._apply_button_size_recursive(child)

    def _apply_recursive_theme(self, widget: tk.Widget, theme: dict, depth: int = 0) -> None:
        if depth > 40:
            return
        if widget.__class__.__module__.startswith("tkinterweb"):
            return
        if isinstance(widget, tk.Label):
            bg = theme["surface"]
            fg = theme["text"] if "bold" in str(widget.cget("font")) else theme["muted_text"]
            widget.configure(bg=bg, fg=fg)
        elif isinstance(widget, tk.Frame):
            widget.configure(bg=theme["surface"])
        elif isinstance(widget, tk.Button):
            if getattr(widget, "_outlined_button", False):
                self._apply_outlined_button_theme(widget, theme)
            else:
                widget.configure(
                    bg=theme["surface_2"],
                    fg=theme["text"],
                    activebackground=theme["surface_3"],
                    activeforeground=theme["text"],
                    relief="flat",
                    bd=0,
                    width=0,
                    height=0,
                    highlightthickness=0,
                    cursor="hand2",
                )

        for child in widget.winfo_children():
            self._apply_recursive_theme(child, theme, depth + 1)

    def update_profile_labels(self) -> None:
        status = self.profile_status_text()
        self.profile_status_label.configure(text=status)
        self.connection_head.configure(text=status)

    def reset_tools_output(self) -> None:
        self.output_text.delete("1.0", "end")
        self.output_text.insert("end", "Waiting for output...\n")

    def _animate_nav_tab(self, tab_name: str) -> None:
        """Bounce animation applied to a nav tab canvas."""
        import numpy as np
        tab_data = self.tab_buttons.get(tab_name)
        if not tab_data:
            return
        canvas: tk.Canvas = tab_data["canvas"]
        if getattr(canvas, "_nav_anim_running", False):
            return
        canvas._nav_anim_running = True

        def ease(t: float) -> float:
            return t * t * (3 - 2 * t)

        total = 26
        current_y = [0]

        def step(i: int) -> None:
            if i >= total:
                delta = -current_y[0]
                items = [tab_data["shape"], tab_data["text"]]
                if tab_data.get("icon"):
                    items.append(tab_data["icon"])
                for item in items:
                    canvas.move(item, 0, delta)
                current_y[0] = 0
                canvas._nav_anim_running = False
                return

            t = i / total
            if t < 0.35:
                new_y = int(-9 * ease(t / 0.35))
            elif t < 0.70:
                new_y = int(-9 * (1 - ease((t - 0.35) / 0.35)))
            elif t < 0.85:
                new_y = int(-4 * ease((t - 0.70) / 0.15))
            else:
                new_y = int(-4 * (1 - ease((t - 0.85) / 0.15)))

            delta = new_y - current_y[0]
            current_y[0] = new_y
            items = [tab_data["shape"], tab_data["text"]]
            if tab_data.get("icon"):
                items.append(tab_data["icon"])
            for item in items:
                canvas.move(item, 0, delta)
            self.after(30, lambda: step(i + 1))

        step(0)

    def select_tab(self, tab_name: str) -> None:
        previous_tab = self.current_tab
        tab_changed = tab_name != previous_tab
        if tab_changed:
            self.reset_tools_output()
        self.current_tab = tab_name
        for name, frame in self.tab_frames.items():
            if name == tab_name:
                frame.lift()
        self.apply_theme_tabs_only()
        self._animate_nav_tab(tab_name)
        if tab_name == "CMTrace":
            try:
                self.load_cmtrace_local_in_app()
            except Exception as err:
                self.cmtrace_status_label.configure(text="Error opening CMTrace.")
                self.cmtrace_embed_placeholder.configure(text=f"CMTrace error:\n{err}")
                self.cmtrace_output.delete("1.0", "end")
                self.append_output(self.cmtrace_output, f"CMTrace error: {err}")

    def load_cmtrace_local_in_app(self) -> None:
        source_dir = self.cmtrace_dev_dir / "src"
        app_html = source_dir / "app.html"
        self.cmtrace_output.delete("1.0", "end")
        if not source_dir.exists():
            self.cmtrace_status_label.configure(text=f"Folder not found: {source_dir}")
            self.cmtrace_embed_placeholder.configure(text=f"Folder not found:\n{source_dir}")
            return

        if not app_html.exists():
            self.cmtrace_status_label.configure(text=f"No app.html found in {source_dir}")
            self.cmtrace_embed_placeholder.configure(text=f"No app.html found:\n{source_dir}")
            return

        # The virtual host keeps the embedded app on a stable HTTPS origin for WebView2.
        url = "https://cmtrace.local/app.html"
        self.cmtrace_status_label.configure(text="Initializing embedded WebView...")

        if not self._ensure_cmtrace_embedded_webview():
            err = self.cmtrace_webview_start_error or "WebView2 initialization failed."
            self.cmtrace_status_label.configure(text="WebView2 unavailable.")
            self.cmtrace_embed_placeholder.configure(text=f"WebView2 error:\n{err}")
            self.append_output(self.cmtrace_output, f"WebView2 error: {err}")
            self.append_output(self.cmtrace_output, "CMTrace switched to safe mode (no app crash).")
            return

        self.cmtrace_webview_loaded_url = url
        self.after(50, self._embed_cmtrace_webview_window)
        self.cmtrace_status_label.configure(text="")
        self.append_output(self.cmtrace_output, "CMTraceDev loaded in WebView2 (virtual host: cmtrace.local -> CMTraceDev\\src)")
        self.append_output(self.cmtrace_output, f"URL: {url}")

    def _ensure_cmtrace_embedded_webview(self) -> bool:
        if self.cmtrace_webview_handle and windll.user32.IsWindow(self.cmtrace_webview_handle):
            return True

        if self.cmtrace_webview_thread is None or not self.cmtrace_webview_thread.is_alive():
            self.cmtrace_webview_ready.clear()
            self.cmtrace_webview_start_error = None
            self.cmtrace_webview_thread = threading.Thread(
            target=self._run_cmtrace_webview_thread,
            name="CMTraceWebViewThread",
            daemon=True,
            )
            self.cmtrace_webview_thread.start()

        # Wait until the WinForms thread has either created the control or reported an error.
        if not self.cmtrace_webview_ready.wait(timeout=4):
            self.cmtrace_webview_start_error = self.cmtrace_webview_start_error or "WebView2 initialization timeout."
            return False

        self._embed_cmtrace_webview_window()
        return True

    def _run_cmtrace_webview_thread(self) -> None:
        try:
            import clr  # type: ignore
        except ImportError:
            self.cmtrace_webview_start_error = "pythonnet not installed. Install with: pip install pythonnet"
            self.cmtrace_webview_ready.set()
            return

        try:
            webview_lib = Path(sys.executable).resolve().parent / "Lib" / "site-packages" / "webview" / "lib"
            core_dll = webview_lib / "Microsoft.Web.WebView2.Core.dll"
            winforms_dll = webview_lib / "Microsoft.Web.WebView2.WinForms.dll"
            if not core_dll.exists() or not winforms_dll.exists():
                self.cmtrace_webview_start_error = f"WebView2 DLL not found in {webview_lib}"
                self.cmtrace_webview_ready.set()
                return

            clr.AddReference("System.Windows.Forms")
            clr.AddReference("System.Drawing")
            clr.AddReference(str(core_dll))
            clr.AddReference(str(winforms_dll))

            from System import Uri  # type: ignore
            from System.Threading import ApartmentState  # type: ignore
            from System.Windows.Forms import Application, DockStyle, Form, FormBorderStyle, FormStartPosition, Timer, UnhandledExceptionMode  # type: ignore
            from Microsoft.Web.WebView2.Core import CoreWebView2HostResourceAccessKind  # type: ignore
            from Microsoft.Web.WebView2.WinForms import WebView2  # type: ignore

            if Application.OleRequired() != ApartmentState.STA:
                self.cmtrace_webview_start_error = "WebView2 requires an STA thread."
                self.cmtrace_webview_ready.set()
                return

            def on_thread_exception(_sender, event_args) -> None:
                self.cmtrace_webview_start_error = f"WinForms exception: {event_args.Exception}"

            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException)
            Application.ThreadException += on_thread_exception

            form = Form()
            form.Text = "SCCM CMTrace Embedded WebView"
            form.FormBorderStyle = getattr(FormBorderStyle, "None")
            form.ShowInTaskbar = False
            form.StartPosition = FormStartPosition.Manual
            form.Left = -32000
            form.Top = -32000
            form.Width = 900
            form.Height = 700

            webview_control = WebView2()
            webview_control.Dock = DockStyle.Fill
            form.Controls.Add(webview_control)

            self.cmtrace_webview_form = form
            self.cmtrace_webview_control = webview_control
            mapped_folder = str((self.cmtrace_dev_dir / "src").resolve())

            def on_webview_initialized(_sender, event_args) -> None:
                try:
                    if not event_args.IsSuccess:
                        self.cmtrace_webview_start_error = f"WebView2 init error: {event_args.InitializationException}"
                        return
                    webview_control.CoreWebView2.SetVirtualHostNameToFolderMapping(
                        "cmtrace.local",
                        mapped_folder,
                        CoreWebView2HostResourceAccessKind.Allow,
                    )
                    self.cmtrace_webview_start_error = None
                except Exception as err:
                    self.cmtrace_webview_start_error = f"WebView2 mapping error: {err}"

            def on_shown(_sender, _event) -> None:
                self.cmtrace_webview_handle = int(form.Handle.ToInt64())
                self.cmtrace_webview_ready.set()
                try:
                    webview_control.CoreWebView2InitializationCompleted += on_webview_initialized
                    webview_control.EnsureCoreWebView2Async()
                except Exception as err:
                    self.cmtrace_webview_start_error = f"WebView2 init start error: {err}"
                    self.cmtrace_webview_ready.set()

            def on_tick(_sender, _event) -> None:
                pending_url = self.cmtrace_webview_loaded_url
                if not pending_url or pending_url == self.cmtrace_webview_last_url:
                    return
                if webview_control.CoreWebView2 is None:
                    return
                try:
                    webview_control.Source = Uri(pending_url)
                    self.cmtrace_webview_last_url = pending_url
                    self.cmtrace_webview_nav_error = None
                except Exception as err:
                    self.cmtrace_webview_nav_error = str(err)

            nav_timer = Timer()
            nav_timer.Interval = 300
            nav_timer.Tick += on_tick

            form.Shown += on_shown
            nav_timer.Start()
            Application.Run(form)
        except Exception as err:
            self.cmtrace_webview_start_error = str(err)
            self.cmtrace_webview_ready.set()

    def _embed_cmtrace_webview_window(self) -> None:
        child_hwnd = self.cmtrace_webview_handle
        if not child_hwnd or not windll.user32.IsWindow(child_hwnd):
            return

        parent_hwnd = self.cmtrace_web_host.winfo_id()
        style = windll.user32.GetWindowLongW(child_hwnd, -16)
        style = (style | 0x40000000) & ~0x00C00000
        windll.user32.SetWindowLongW(child_hwnd, -16, style)
        windll.user32.SetParent(child_hwnd, parent_hwnd)
        width = max(self.cmtrace_web_host.winfo_width(), 200)
        height = max(self.cmtrace_web_host.winfo_height(), 200)
        windll.user32.MoveWindow(child_hwnd, 0, 0, width, height, True)
        windll.user32.ShowWindow(child_hwnd, 5)
        if self.cmtrace_embed_placeholder.winfo_ismapped():
            self.cmtrace_embed_placeholder.pack_forget()

    def _on_cmtrace_host_resize(self, event: tk.Event) -> None:
        child_hwnd = self.cmtrace_webview_handle
        if not child_hwnd or not windll.user32.IsWindow(child_hwnd):
            return
        width = max(event.width, 200)
        height = max(event.height, 200)
        windll.user32.MoveWindow(child_hwnd, 0, 0, width, height, True)

    def apply_theme_tabs_only(self) -> None:
        t = self.theme
        for name, tab_data in self.tab_buttons.items():
            active = name == self.current_tab
            fill = t["tabs_btn_active"] if active else t["tabs_btn_bg"]
            text_color = t["tabs_btn_text_active"] if active else t["tabs_btn_text"]
            tab_data["canvas"].itemconfigure(tab_data["shape"], fill=fill)
            tab_data["canvas"].itemconfigure(tab_data["text"], fill=text_color)

    def on_tab_bar_configure(self, _event: tk.Event) -> None:
        req_w = self.tab_bar.winfo_reqwidth() + 20
        req_h = max(self.tab_bar.winfo_reqheight() + 10, 42)
        self.tab_canvas.configure(width=req_w, height=req_h)
        self.tab_canvas.coords(self.tab_bar_window, 10, 5)
        self.draw_tab_capsule()

    def on_tab_canvas_configure(self, _event: tk.Event) -> None:
        self.draw_tab_capsule()

    def _on_window_resize(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        self._apply_responsive_layout(width=event.width)

    def _apply_responsive_layout(self, width: int | None = None) -> None:
        current_width = width if width is not None else self.winfo_width()
        compact = current_width < 1040
        self._apply_tools_responsive_layout(compact)
        self._apply_infra_responsive_layout(compact)
        self._apply_ps1_responsive_layout(compact)
        self._layout_collvariable_action_buttons(compact)

    def _layout_collvariable_action_buttons(self, compact: bool) -> None:
        if not hasattr(self, "collvariable_actions") or not hasattr(self, "collvariable_action_buttons"):
            return
        desired_mode = "compact" if compact else "wide"
        if self.collvariable_actions_mode == desired_mode:
            return
        button_count = len(self.collvariable_action_buttons)
        for idx in range(button_count):
            self.collvariable_actions.grid_columnconfigure(idx, weight=0, uniform="")
        for button in self.collvariable_action_buttons:
            button.grid_forget()
        if compact:
            self.collvariable_actions.grid_columnconfigure(0, weight=1, uniform="collvar-actions")
            self.collvariable_actions.grid_columnconfigure(1, weight=1, uniform="collvar-actions")
            for idx, button in enumerate(self.collvariable_action_buttons):
                row = idx // 2
                column = idx % 2
                button.grid(row=row, column=column, sticky="ew", padx=4, pady=4)
        else:
            for idx in range(button_count):
                self.collvariable_actions.grid_columnconfigure(idx, weight=1, uniform="collvar-actions")
            for idx, button in enumerate(self.collvariable_action_buttons):
                button.grid(row=0, column=idx, sticky="ew", padx=4, pady=4)
        self.collvariable_actions_mode = desired_mode

    def _apply_tools_responsive_layout(self, compact: bool) -> None:
        if not hasattr(self, "left_panel") or not hasattr(self, "tools_area_card"):
            return
        desired_mode = "compact" if compact else "wide"
        if self.tools_layout_mode == desired_mode:
            return
        self.left_panel.pack_forget()
        self.tools_area_card.pack_forget()
        if compact:
            self.left_panel.configure(width=1)
            self.left_panel.pack_propagate(True)
            self.left_panel.pack(side="top", fill="x", padx=(0, 0), pady=(0, 10))
            self.vertical_menu.pack_configure(fill="x", expand=False)
            self.tools_area_card.pack(side="top", fill="both", expand=True)
        else:
            self.left_panel.configure(width=210)
            self.left_panel.pack_propagate(False)
            self.left_panel.pack(side="left", fill="y", padx=(0, 14))
            self.vertical_menu.pack_configure(fill="both", expand=True)
            self.tools_area_card.pack(side="left", fill="both", expand=True)
        self.tools_layout_mode = desired_mode

    def _apply_infra_responsive_layout(self, compact: bool) -> None:
        if not hasattr(self, "infra_left_panel") or not hasattr(self, "infra_right_panel"):
            return
        desired_mode = "compact" if compact else "wide"
        if self.infra_layout_mode == desired_mode:
            return
        self.infra_left_panel.pack_forget()
        self.infra_right_panel.pack_forget()
        if compact:
            self.infra_left_panel.configure(width=1)
            self.infra_left_panel.pack_propagate(True)
            self.infra_left_panel.pack(side="top", fill="x", padx=(0, 0), pady=(0, 10))
            self.infra_right_panel.pack(side="top", fill="both", expand=True)
        else:
            self.infra_left_panel.configure(width=210)
            self.infra_left_panel.pack_propagate(False)
            self.infra_left_panel.pack(side="left", fill="y", padx=(0, 14))
            self.infra_right_panel.pack(side="left", fill="both", expand=True)
        self.infra_layout_mode = desired_mode

    def _apply_ps1_responsive_layout(self, compact: bool) -> None:
        if not hasattr(self, "ps1_body_pane"):
            return
        desired_mode = "compact" if compact else "wide"
        if self.ps1_layout_mode == desired_mode:
            return
        orient = "vertical" if compact else "horizontal"
        self.ps1_body_pane.configure(orient=orient)
        self.after_idle(lambda: self._position_ps1_body_sash(compact))
        self.ps1_layout_mode = desired_mode

    def _position_ps1_body_sash(self, compact: bool) -> None:
        if not hasattr(self, "ps1_body_pane"):
            return
        if compact:
            total_height = max(self.ps1_body_pane.winfo_height(), 1)
            sash_y = max(int(total_height * 0.45), 180)
            self.ps1_body_pane.sash_place(0, 0, sash_y)
        else:
            total_width = max(self.ps1_body_pane.winfo_width(), 1)
            sash_x = max(int(total_width * 0.42), 300)
            self.ps1_body_pane.sash_place(0, sash_x, 0)

    def draw_tab_capsule(self) -> None:
        if not hasattr(self, "tab_canvas"):
            return
        t = self.theme
        canvas = self.tab_canvas
        canvas.delete("capsule")

        width = max(canvas.winfo_width(), self.tab_bar.winfo_reqwidth() + 20)
        height = max(canvas.winfo_height(), 42)
        radius = 18
        x1, y1, x2, y2 = 2, 2, width - 2, height - 2

        points = [
            x1 + radius, y1,
            x2 - radius, y1,
            x2, y1,
            x2, y1 + radius,
            x2, y2 - radius,
            x2, y2,
            x2 - radius, y2,
            x1 + radius, y2,
            x1, y2,
            x1, y2 - radius,
            x1, y1 + radius,
            x1, y1,
        ]
        canvas.create_polygon(
            points,
            smooth=True,
            splinesteps=36,
            fill=t["tabs_shell_bg"],
            outline=t["tabs_btn_border"],
            width=1,
            tags="capsule",
        )
        canvas.tag_lower("capsule")

    def draw_canvas_segment(
        self,
        canvas: tk.Canvas,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        left_radius: int,
        right_radius: int,
        fill: str,
    ) -> int:
        points = [
            x1 + left_radius, y1,
            x2 - right_radius, y1,
            x2, y1,
            x2, y1 + right_radius,
            x2, y2 - right_radius,
            x2, y2,
            x2 - right_radius, y2,
            x1 + left_radius, y2,
            x1, y2,
            x1, y2 - left_radius,
            x1, y1 + left_radius,
            x1, y1,
        ]
        return canvas.create_polygon(points, smooth=True, splinesteps=24, fill=fill, outline="", width=0)

    def get_tab_width(self, text: str) -> int:
        return max(88, int(len(text) * 8.4) + 34)

    def toggle_theme(self) -> None:
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        self.apply_theme()
        self.save_settings()

    def show_home(self, run_check: bool = True) -> None:
        self.open_sccm_from_menu(run_check=run_check)

    def select_vertical_menu(self, item_name: str) -> None:
        self.vertical_menu_selected = item_name
        if item_name == "Last10DPLM":
            self.tools_mode = "Last10DPLM"
        elif item_name == "CollMember":
            self.tools_mode = "CollMember"
        elif item_name == "CollVariable":
            self.tools_mode = "CollVariable"
        elif item_name == "CopyDeplmt":
            self.tools_mode = "CopyDeplmt"
        else:
            self.tools_mode = "sccm"
        self.configure_tools_mode()
        self._apply_vertical_menu_theme()

    def open_sccm_from_menu(self, run_check: bool = True) -> None:
        self.select_tab("Tools")
        self.tools_mode = "sccm"
        self.vertical_menu_selected = ""
        self.configure_tools_mode()
        self._apply_vertical_menu_theme()
        if run_check:
            self.check_sccm_connection()

    def configure_tools_mode(self) -> None:
        # hide all mode cards + output_card, then show the active ones
        for card in (self.check_card, self.last10_card):
            card.pack_forget()
        self.output_card.pack_forget()
        self.collmember_panel.pack_forget()
        self.collvariable_panel.pack_forget()
        self.copydeplmt_panel.pack_forget()
        self.tools_actions.pack_forget()
        self._set_collmember_output_split_visible(False)
        self._set_collvariable_output_split_visible(False)

        if self.tools_mode == "Last10DPLM":
            self.last10_card.pack(fill="both", expand=True, padx=14, pady=(14, 10))
        else:
            self.check_card.pack(fill="x", padx=14, pady=(14, 10))
            self.output_card.pack(fill="both", expand=True, padx=14, pady=(8, 14))

        if self.tools_mode == "sccm":
            self._set_widget_icon(self.check_title, "✅", "Check SCCM connection", size=20)
            self.check_description.configure(
                text="Test access to the SCCM server and display site information."
            )
            self.tools_actions.pack()
            self.run_check_button.configure(command=self.check_sccm_connection)
            self._set_widget_icon(self.run_check_button, "▶️", "Run Check", size=16)
        elif self.tools_mode == "CollMember":
            self._set_widget_icon(self.check_title, "🧩", "CollMember", size=20)
            self.check_description.configure(
                text="Filter then select an SCCM collection."
            )
            self.collmember_panel.pack(fill="x", pady=(4, 0))
            self._set_collmember_output_split_visible(True)
        elif self.tools_mode == "CollVariable":
            self._set_widget_icon(self.check_title, "🏷️", "CollVariable", size=20)
            self.check_description.configure(
                text="Filter by collection name and select a collection."
            )
            self.collvariable_panel.pack(fill="x", pady=(4, 0))
            self._set_collvariable_output_split_visible(True)
        elif self.tools_mode == "CopyDeplmt":
            self._set_widget_icon(self.check_title, "📋", "Copy Deplmt", size=20)
            self.check_description.configure(
                text="Copy deployment names from one or more TS, SUG, App, Program, or Baseline entries."
            )
            self.copydeplmt_panel.pack(fill="x", pady=(4, 0))

    def _set_collmember_output_split_visible(self, visible: bool) -> None:
        if visible:
            if self.output_text.winfo_manager():
                self.output_text.pack_forget()
            if self.collvariable_output_split.winfo_manager():
                self.collvariable_output_split.pack_forget()
            if not self.collmember_scroll_container.winfo_manager():
                self.collmember_scroll_container.pack(fill="both", expand=True, padx=8, pady=8)
            self.after_idle(self._on_collmember_output_frame_configure)
            return
        if self.collmember_scroll_container.winfo_manager():
            self.collmember_scroll_container.pack_forget()
        if not self.output_text.winfo_manager() and not self.collvariable_output_split.winfo_manager():
            self.output_text.pack(fill="both", expand=True, padx=8, pady=8)

    def _set_collvariable_output_split_visible(self, visible: bool) -> None:
        if visible:
            if self.output_text.winfo_manager():
                self.output_text.pack_forget()
            if self.collmember_scroll_container.winfo_manager():
                self.collmember_scroll_container.pack_forget()
            if not self.collvariable_output_split.winfo_manager():
                self.collvariable_output_split.pack(fill="both", expand=True, padx=8, pady=8)
            return
        if self.collvariable_output_split.winfo_manager():
            self.collvariable_output_split.pack_forget()
        if not self.output_text.winfo_manager() and not self.collmember_scroll_container.winfo_manager():
            self.output_text.pack(fill="both", expand=True, padx=8, pady=8)

    def _on_collmember_output_frame_configure(self, _event: tk.Event | None = None) -> None:
        bbox = self.collmember_output_canvas.bbox("all")
        if bbox:
            self.collmember_output_canvas.configure(scrollregion=bbox)

    def _on_collmember_output_canvas_configure(self, event: tk.Event) -> None:
        self.collmember_output_canvas.itemconfigure(self.collmember_output_window, width=event.width)

    def _clear_collmember_output_tables(self) -> None:
        for row in self.collmember_types_tree.get_children():
            self.collmember_types_tree.delete(row)
        for row in self.collmember_queries_tree.get_children():
            self.collmember_queries_tree.delete(row)
        for row in self.collmember_machines_tree.get_children():
            self.collmember_machines_tree.delete(row)
        self.collmember_machine_names = []

    def _set_collmember_output_error(self, message: str) -> None:
        self._clear_collmember_output_tables()
        self.collmember_types_tree.insert("", "end", values=("Error", "-"))
        self.collmember_queries_tree.insert("", "end", values=("Error", message))
        self.collmember_machines_tree.insert("", "end", values=(message,))

    def _update_collmember_member_buttons(self) -> None:
        if not hasattr(self, "collmember_member_add_button") or not hasattr(self, "collmember_member_remove_button"):
            return
        kind = self.collmember_selected_collection_type
        if kind == "Device":
            add_text = "Add Device"
            remove_text = "Remove Device"
        elif kind == "User":
            add_text = "Add User"
            remove_text = "Remove User"
        else:
            add_text = "Add member"
            remove_text = "Remove selected"
        self._set_widget_icon(self.collmember_member_add_button, "➕", add_text, size=14)
        self._set_widget_icon(self.collmember_member_remove_button, "🗑", remove_text, size=14)

    def _build_collmember_connection_script(self, server: str, site_code: str) -> str:
        return f"""
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$SiteCode = "{site_code}"
$ProviderMachineName = "{server}"
if ((Get-Module ConfigurationManager) -eq $null) {{
    Import-Module "$($ENV:SMS_ADMIN_UI_PATH)\\..\\ConfigurationManager.psd1" -ErrorAction Stop
}}
$existingDrive = Get-PSDrive -Name $SiteCode -PSProvider CMSite -ErrorAction SilentlyContinue
if ($existingDrive -and $existingDrive.Root -and $existingDrive.Root.Trim().ToLowerInvariant() -ne $ProviderMachineName.Trim().ToLowerInvariant()) {{
    Remove-PSDrive -Name $SiteCode -PSProvider CMSite -Force -ErrorAction Stop
    $existingDrive = $null
}}
if ($existingDrive -eq $null) {{
    New-PSDrive -Name $SiteCode -PSProvider CMSite -Root $ProviderMachineName -ErrorAction Stop | Out-Null
}}
Set-Location "$($SiteCode):\\"
"""

    def _parse_member_names(self, raw_text: str) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for line in raw_text.splitlines():
            for chunk in re.split(r"[,\t;]", line):
                name = chunk.strip().strip('"').strip("'")
                if not name:
                    continue
                lowered = name.lower()
                if lowered in {"name", "device", "devices", "computer", "hostname", "user", "users"}:
                    continue
                if lowered in seen:
                    continue
                seen.add(lowered)
                names.append(name)
        return names

    def _get_selected_copy_deployment_types(self) -> list[str]:
        selected_types: list[str] = []
        for short_name, long_name in self.copydeplmt_source_type_map.items():
            if self.copydeplmt_source_type_vars[short_name].get():
                selected_types.append(long_name)
        return selected_types

    def _copydeplmt_detail_fields_by_type(self) -> dict[str, list[str]]:
        return {
            "Task Sequence": [
                "Purpose",
                "MakeAvailableTo",
                "AllowIndependentExecution",
                "HighPerformance",
                "DisableOnTargets",
                "AssignmentSchedule",
                "Deadline",
                "TimeZone",
                "RerunBehavior",
                "UserNotifications",
                "ShowProgress",
                "AllowRestart",
                "SuppressNotifications",
                "CommitOnDeadlineOrMW",
                "AlertOnSuccess",
                "AlertOnFailure",
                "AlertOnCreation",
                "DownloadAllContentBeforeStart",
                "RunFromDP",
                "AllowFallbackUnprotectedDP",
                "AllowFallbackNeighborDP",
                "PreCacheContent",
                "SecurityScopes",
            ],
            "Software Update Group": [
                "Type",
                "DetailLevel",
                "Deadline",
                "TimeZone",
                "RerunBehavior",
                "UserNotifications",
                "RestartBehavior",
                "GracePeriod",
                "MaintenanceWindowCompliance",
                "AllowRestartOutsideMW",
                "AlertOnSuccess",
                "AlertOnFailure",
                "DownloadFromMUIfDPUnavailable",
                "AllowFallbackUnprotectedDP",
                "PeerSharing",
                "DeploymentPackage",
                "DownloadLocation",
                "Languages",
                "ExpressUpdates",
            ],
            "Application": [
                "Action",
                "Purpose",
                "AllowRepair",
                "AllowUserRestart",
                "Deadline",
                "TimeZone",
                "RerunBehavior",
                "UserNotifications",
                "CommitOnDeadlineOrMW",
                "AllowRestart",
                "PreCacheContent",
                "Requirements",
                "GlobalConditions",
                "DeviceType",
                "OSVersion",
                "MemoryRequirement",
                "CPURequirement",
                "DiskRequirement",
                "UserRequirement",
                "Dependencies",
                "RequiredApps",
                "OptionalApps",
                "Supersedence",
                "DPFallback",
                "RunFromDP",
                "DownloadFirst",
                "PeerCache",
                "AlertOnSuccess",
                "AlertOnFailure",
            ],
            "Program": [
                "Program",
                "Purpose",
                "RunMode",
                "RunWhenUserLoggedOff",
                "AllowUserInteraction",
                "AssignmentSchedule",
                "Deadline",
                "RerunBehavior",
                "UserNotifications",
                "RestartBehavior",
                "EstimatedRunTime",
                "MaxRunTime",
                "PlatformRequirements",
                "OSRequirements",
                "RunFromDP",
                "DownloadFirst",
                "AllowFallback",
                "SharedContent",
                "AlertOnSuccess",
                "AlertOnFailure",
            ],
            "Baseline": [
                "Purpose",
                "RemediationEnabled",
                "AllowRemediationOutsideMW",
                "EvaluationSchedule",
                "RerunBehavior",
                "UserNotifications",
                "ComplianceMessages",
                "NonComplianceAlerts",
                "AlertOnNonCompliance",
                "AlertOnRemediationFailure",
                "DownloadRequiredCIs",
                "DPFallback",
            ],
        }

    def _copydeplmt_detail_cmdlet_by_type(self) -> dict[str, str]:
        return {
            "Task Sequence": "Get-CMTaskSequenceDeployment",
            "Software Update Group": "Get-CMSoftwareUpdateDeployment",
            "Application": "Get-CMApplicationDeployment",
            "Program": "Get-CMPackageDeployment",
            "Baseline": "Get-CMBaselineDeployment",
        }

    def _build_ordered_copydeplmt_details(self, source_type: str, raw_details: dict[str, str]) -> dict[str, str]:
        ordered_details: dict[str, str] = {}
        type_name = str(raw_details.get("Type", source_type)).strip() or source_type
        ordered_details["Type"] = type_name
        detail_cmdlet = str(raw_details.get("DetailCmdlet", "")).strip()
        if detail_cmdlet:
            ordered_details["DetailCmdlet"] = detail_cmdlet
        field_order = self._copydeplmt_detail_fields_by_type().get(type_name, [])
        for field_name in field_order:
            value = raw_details.get(field_name, "-")
            value_text = str(value).strip()
            ordered_details[field_name] = value_text if value_text else "-"
        for key, value in raw_details.items():
            if key in ordered_details:
                continue
            value_text = str(value).strip()
            ordered_details[key] = value_text if value_text else "-"
        return ordered_details

    def _build_copy_deployment_candidates_script(self, source_collection_name: str, source_types: list[str]) -> str:
        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        if server and site_code:
            bootstrap = self._build_collmember_connection_script(server, site_code)
        else:
            bootstrap = """
$module = Get-Module -ListAvailable -Name ConfigurationManager | Select-Object -First 1
if (-not $module) { throw 'ConfigurationManager module not found.' }
Import-Module $module.Path -ErrorAction Stop
"""
        escaped_collection = source_collection_name.replace("'", "''")
        escaped_types = [source_type.replace("'", "''") for source_type in source_types]
        selected_types_literal = ", ".join(f"'{value}'" for value in escaped_types)
        detail_fields_literal = json.dumps(self._copydeplmt_detail_fields_by_type())
        detail_cmdlets_literal = json.dumps(self._copydeplmt_detail_cmdlet_by_type())
        return (
            f"""{bootstrap}
$sourceCollectionName = '{escaped_collection}'
$selectedTypes = @({selected_types_literal})
$detailFieldsByType = ConvertFrom-Json @'
{detail_fields_literal}
'@
$detailCmdletsByType = ConvertFrom-Json @'
{detail_cmdlets_literal}
'@
$typeMap = @{{
    1 = 'Application'
    2 = 'Program'
    5 = 'Software Update Group'
    7 = 'Task Sequence'
    8 = 'Baseline'
}}
$aliasMap = @{{
    AssignmentSchedule = @('AssignmentSchedule', 'AvailableTime', 'StartTime')
    Deadline = @('Deadline', 'EnforcementDeadline', 'DeploymentTime')
    TimeZone = @('TimeZone', 'UseUtc')
    RerunBehavior = @('RerunBehavior', 'ReRunBehavior')
    UserNotifications = @('UserNotifications', 'UserNotification')
    AllowRestart = @('AllowRestart', 'Restart', 'AllowSystemRestart')
    AlertOnSuccess = @('AlertOnSuccess', 'GenerateSuccessAlert')
    AlertOnFailure = @('AlertOnFailure', 'GenerateFailureAlert')
    AlertOnCreation = @('AlertOnCreation', 'GenerateCreationAlert')
    RunFromDP = @('RunFromDP', 'RunFromDistributionPoint')
    DPFallback = @('DPFallback', 'AllowFallback')
}}
function Get-FirstDeploymentPropertyValue {{
    param(
        [object[]]$Sources,
        [string[]]$PropertyNames
    )

    foreach ($source in @($Sources)) {{
        if (-not $source) {{
            continue
        }}
        foreach ($propertyName in @($PropertyNames)) {{
            if (-not $source.PSObject.Properties[$propertyName]) {{
                continue
            }}
            $candidateValue = $source.$propertyName
            if ($null -eq $candidateValue) {{
                continue
            }}
            if ($candidateValue -is [string]) {{
                if (-not [string]::IsNullOrWhiteSpace($candidateValue)) {{
                    return $candidateValue
                }}
            }} else {{
                return $candidateValue
            }}
        }}
    }}
    return $null
}}
function Convert-ApplicationDeploymentAction {{
    param($Value)

    if ($null -eq $Value) {{
        return $null
    }}
    switch ([int]$Value) {{
        0 {{ return 'Install' }}
        2 {{ return 'Uninstall' }}
        default {{ return [string]$Value }}
    }}
}}
function Convert-ApplicationDeploymentPurpose {{
    param($Value)

    if ($null -eq $Value) {{
        return $null
    }}
    switch ([int]$Value) {{
        1 {{ return 'Required' }}
        2 {{ return 'Available' }}
        default {{ return [string]$Value }}
    }}
}}
function Convert-BoolToText {{
    param($Value)

    if ($null -eq $Value) {{
        return $null
    }}
    if ($Value -is [bool]) {{
        return if ($Value) {{ 'Yes' }} else {{ 'No' }}
    }}
    try {{
        return if ([bool]$Value) {{ 'Yes' }} else {{ 'No' }}
    }} catch {{
        return [string]$Value
    }}
}}
function Convert-TaskSequenceDeploymentPurpose {{
    param($Value)

    if ($null -eq $Value) {{
        return $null
    }}
    switch ([int]$Value) {{
        0 {{ return 'Available' }}
        1 {{ return 'Required' }}
        default {{ return [string]$Value }}
    }}
}}
function Convert-BaselineDeploymentPurpose {{
    param($Value)

    if ($null -eq $Value) {{
        return $null
    }}
    switch ([int]$Value) {{
        0 {{ return 'Available' }}
        1 {{ return 'Required' }}
        default {{ return [string]$Value }}
    }}
}}
function Convert-DeploymentTypeName {{
    param([object]$Value)

    if ($null -eq $Value) {{
        return $null
    }}
    $text = [string]$Value
    if ([string]::IsNullOrWhiteSpace($text)) {{
        return $null
    }}
    $normalized = $text.Trim().ToLowerInvariant()
    switch ($normalized) {{
        'application' {{ return 'Application' }}
        'app' {{ return 'Application' }}
        'program' {{ return 'Program' }}
        'package' {{ return 'Program' }}
        'software update group' {{ return 'Software Update Group' }}
        'softwareupdategroup' {{ return 'Software Update Group' }}
        'sug' {{ return 'Software Update Group' }}
        'task sequence' {{ return 'Task Sequence' }}
        'tasksequence' {{ return 'Task Sequence' }}
        'tasksequences' {{ return 'Task Sequence' }}
        'baseline' {{ return 'Baseline' }}
        default {{ return $null }}
    }}
}}
function Resolve-DeploymentType {{
    param(
        $DeploymentObject,
        [string]$DeploymentName
    )

    $typeMap = @{{
        1 = 'Application'
        2 = 'Program'
        5 = 'Software Update Group'
        7 = 'Task Sequence'
        8 = 'Baseline'
    }}
    $propertyNames = @(
        'FeatureType',
        'FeatureTypeID',
        'ObjectType',
        'DeploymentType',
        'DeploymentObjectType',
        'Type',
        'TypeName',
        'ObjectTypeName',
        'DeploymentTypeName',
        'FeatureTypeName'
    )

    foreach ($propertyName in $propertyNames) {{
        if (-not $DeploymentObject -or -not $DeploymentObject.PSObject.Properties[$propertyName]) {{
            continue
        }}
        $propertyValue = $DeploymentObject.$propertyName
        if ($null -eq $propertyValue) {{
            continue
        }}
        if ($propertyValue -is [int] -or $propertyValue -is [long] -or $propertyValue -is [short] -or $propertyValue -is [byte]) {{
            $numericValue = [int]$propertyValue
            if ($typeMap.ContainsKey($numericValue)) {{
                return $typeMap[$numericValue]
            }}
            continue
        }}
        $normalized = Convert-DeploymentTypeName $propertyValue
        if ($normalized) {{
            return $normalized
        }}
        try {{
            $numericValue = [int]$propertyValue
            if ($typeMap.ContainsKey($numericValue)) {{
                return $typeMap[$numericValue]
            }}
        }} catch {{}}
    }}

    if ($DeploymentObject -and $DeploymentObject.PSObject.Properties['TaskSequenceName'] -and $DeploymentObject.TaskSequenceName) {{
        return 'Task Sequence'
    }}
    if ($DeploymentObject -and $DeploymentObject.PSObject.Properties['BaselineName'] -and $DeploymentObject.BaselineName) {{
        return 'Baseline'
    }}
    if ($DeploymentObject -and $DeploymentObject.PSObject.Properties['ApplicationName'] -and $DeploymentObject.ApplicationName) {{
        return 'Application'
    }}
    if ($DeploymentObject -and $DeploymentObject.PSObject.Properties['PackageName'] -and $DeploymentObject.PackageName) {{
        return 'Program'
    }}
    if ($DeploymentObject -and $DeploymentObject.PSObject.Properties['ProgramName'] -and $DeploymentObject.ProgramName) {{
        return 'Program'
    }}
    if ($DeploymentObject -and $DeploymentObject.PSObject.Properties['UpdateGroupName'] -and $DeploymentObject.UpdateGroupName) {{
        return 'Software Update Group'
    }}
    if ($DeploymentObject -and $DeploymentObject.PSObject.Properties['SoftwareUpdateGroupName'] -and $DeploymentObject.SoftwareUpdateGroupName) {{
        return 'Software Update Group'
    }}
    if ($DeploymentObject -and $DeploymentObject.PSObject.Properties['SoftwareUpdateGroup'] -and $DeploymentObject.SoftwareUpdateGroup) {{
        return 'Software Update Group'
    }}
    if ($DeploymentName) {{
        $nameText = $DeploymentName.Trim().ToLowerInvariant()
        if ($nameText -match 'task sequence|tasksequence|ts') {{ return 'Task Sequence' }}
        if ($nameText -match 'baseline|baseline deployment') {{ return 'Baseline' }}
        if ($nameText -match 'software update|sug|update group') {{ return 'Software Update Group' }}
    }}
    return 'Software Update Group'
}}
function Get-DeploymentDetailSource {{
    param(
        [string]$ResolvedType,
        [string]$DeploymentName,
        [string]$CollectionName,
        $DeploymentObject
    )

    switch ($ResolvedType) {{
        'Task Sequence' {{
            return Get-CMTaskSequenceDeployment -Name $DeploymentName -CollectionName $CollectionName -Fast -ErrorAction SilentlyContinue | Select-Object -First 1
        }}
        'Baseline' {{
            return Get-CMBaselineDeployment -Name $DeploymentName -CollectionName $CollectionName -Fast -ErrorAction SilentlyContinue | Select-Object -First 1
        }}
        'Software Update Group' {{
            return Get-CMSoftwareUpdateDeployment -Name $DeploymentName -CollectionName $CollectionName -ErrorAction SilentlyContinue | Select-Object -First 1
        }}
        'Application' {{
            return Get-CMApplicationDeployment -Name $DeploymentName -CollectionName $CollectionName -ErrorAction SilentlyContinue | Select-Object -First 1
        }}
        'Program' {{
            $programName = $null
            if ($DeploymentObject -and $DeploymentObject.PSObject.Properties['ProgramName'] -and $DeploymentObject.ProgramName) {{
                $programName = [string]$DeploymentObject.ProgramName
            }}
            if ($programName) {{
                $packageDeployment = Get-CMPackageDeployment -Name $DeploymentName -ProgramName $programName -CollectionName $CollectionName -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($packageDeployment) {{
                    return $packageDeployment
                }}
            }}
            return Get-CMPackageDeployment -Name $DeploymentName -CollectionName $CollectionName -ErrorAction SilentlyContinue | Select-Object -First 1
        }}
        default {{
            return $DeploymentObject
        }}
    }}
}}
function Get-DeploymentConfigSource {{
    param(
        [string]$ResolvedType,
        [string]$DeploymentName,
        [string]$ProgramName
    )

    switch ($ResolvedType) {{
        'Task Sequence' {{
            return Get-CMTaskSequence -Name $DeploymentName -Fast -ErrorAction SilentlyContinue | Select-Object -First 1
        }}
        'Baseline' {{
            return Get-CMBaseline -Name $DeploymentName -Fast -ErrorAction SilentlyContinue | Select-Object -First 1
        }}
        'Application' {{
            return Get-CMApplication -Name $DeploymentName -Fast -ErrorAction SilentlyContinue | Select-Object -First 1
        }}
        'Program' {{
            $packageObject = Get-CMPackage -Name $DeploymentName -Fast -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($packageObject) {{
                return $packageObject
            }}
            if ($ProgramName) {{
                return Get-CMProgram -PackageName $DeploymentName -ProgramName $ProgramName -ErrorAction SilentlyContinue | Select-Object -First 1
            }}
            return Get-CMProgram -PackageName $DeploymentName -ErrorAction SilentlyContinue | Select-Object -First 1
        }}
        default {{
            return $null
        }}
    }}
}}
function Convert-DetailValueToText {{
    param($Value)

    if ($null -eq $Value) {{
        return $null
    }}
    if ($Value -is [string]) {{
        if ([string]::IsNullOrWhiteSpace($Value)) {{
            return $null
        }}
        return $Value.Trim()
    }}
    if ($Value -is [System.Collections.IEnumerable] -and -not ($Value -is [string])) {{
        $items = @($Value | ForEach-Object {{ [string]$_ }} | Where-Object {{ $_ -and $_.Trim().Length -gt 0 }})
        if ($items.Count -eq 0) {{
            return $null
        }}
        return ($items -join ', ')
    }}
    return [string]$Value
}}
function Add-DetailProperties {{
    param(
        [hashtable]$DetailMap,
        $Source
    )

    if (-not $Source) {{
        return
    }}

    foreach ($property in $Source.PSObject.Properties) {{
        if (-not $property.IsGettable) {{
            continue
        }}
        $propertyName = [string]$property.Name
        if (-not $propertyName) {{
            continue
        }}
        if ($propertyName -like 'PS*' -or $propertyName -like '__*') {{
            continue
        }}
        if ($DetailMap.Contains($propertyName)) {{
            continue
        }}
        $valueText = Convert-DetailValueToText $property.Value
        if ($null -eq $valueText) {{
            continue
        }}
        $DetailMap[$propertyName] = $valueText
    }}
}}
$results = [System.Collections.Generic.List[object]]::new()
$deployments = Get-CMDeployment -CollectionName $sourceCollectionName -ErrorAction Stop
foreach ($deployment in @($deployments)) {{
    $name = $null
    if ($deployment.PSObject.Properties['TaskSequenceName'] -and $deployment.TaskSequenceName) {{
        $name = [string]$deployment.TaskSequenceName
    }} elseif ($deployment.PSObject.Properties['BaselineName'] -and $deployment.BaselineName) {{
        $name = [string]$deployment.BaselineName
    }} elseif ($deployment.ApplicationName) {{
        $name = [string]$deployment.ApplicationName
    }} elseif ($deployment.PackageName) {{
        $name = [string]$deployment.PackageName
    }} elseif ($deployment.AssignmentName) {{
        $name = [string]$deployment.AssignmentName
    }}
    if (-not $name) {{ continue }}
    $resolvedType = Resolve-DeploymentType -DeploymentObject $deployment -DeploymentName $name
    if (-not $resolvedType) {{
        $resolvedType = 'Software Update Group'
    }}
    if ($selectedTypes.Count -gt 0 -and -not ($selectedTypes -contains $resolvedType)) {{
        continue
    }}
    $startValue = '-'
    if ($deployment.PSObject.Properties['DeploymentTime'] -and $deployment.DeploymentTime) {{
        $startValue = $deployment.DeploymentTime.ToString("yyyy-MM-dd HH:mm")
    }}
    $detailSource = Get-DeploymentDetailSource -ResolvedType $resolvedType -DeploymentName $name -CollectionName $sourceCollectionName -DeploymentObject $deployment
    if (-not $detailSource) {{
        $detailSource = $deployment
    }}
    $programName = $null
    if ($detailSource -and $detailSource.PSObject.Properties['ProgramName'] -and $detailSource.ProgramName) {{
        $programName = [string]$detailSource.ProgramName
    }} elseif ($deployment.PSObject.Properties['ProgramName'] -and $deployment.ProgramName) {{
        $programName = [string]$deployment.ProgramName
    }}
    $configSource = Get-DeploymentConfigSource -ResolvedType $resolvedType -DeploymentName $name -ProgramName $programName
    $detail = [ordered]@{{}}
    $detail['Type'] = $resolvedType
    if ($detailCmdletsByType.PSObject.Properties[$resolvedType]) {{
        $detail['DetailCmdlet'] = [string]$detailCmdletsByType.PSObject.Properties[$resolvedType].Value
    }}
    if ($resolvedType -eq 'Application') {{
        $actionValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('Action', 'DeployAction', 'OfferTypeID', 'AssignmentAction')
        if ($null -ne $actionValue) {{
            $detail['Action'] = Convert-ApplicationDeploymentAction $actionValue
        }}
        $purposeValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('Purpose', 'DeployPurpose', 'DesiredConfigType')
        if ($null -ne $purposeValue) {{
            $detail['Purpose'] = Convert-ApplicationDeploymentPurpose $purposeValue
        }}
        $assignmentScheduleValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('AssignmentSchedule', 'StartTime', 'DeploymentTime')
        if ($null -ne $assignmentScheduleValue) {{
            $detail['AssignmentSchedule'] = [string]$assignmentScheduleValue
        }}
        $timeZoneValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('TimeZone', 'UseGMTTimes')
        if ($null -ne $timeZoneValue) {{
            if ($timeZoneValue -is [bool]) {{
                $detail['TimeZone'] = if ($timeZoneValue) {{ 'UTC' }} else {{ 'Local' }}
            }} else {{
                $detail['TimeZone'] = [string]$timeZoneValue
            }}
        }}
        $userNotificationsValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('UserNotifications', 'UserNotification', 'NotifyUser', 'UserUIExperience')
        if ($null -ne $userNotificationsValue) {{
            $detail['UserNotifications'] = Convert-BoolToText $userNotificationsValue
        }}
        $allowRestartValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('AllowRestart', 'RebootOutsideOfServiceWindows', 'SuppressReboot')
        if ($null -ne $allowRestartValue) {{
            $detail['AllowRestart'] = Convert-BoolToText $allowRestartValue
        }}
    }}
    if ($resolvedType -eq 'Task Sequence') {{
        $purposeValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('Purpose', 'DeployPurpose', 'DesiredConfigType')
        if ($null -ne $purposeValue) {{
            $detail['Purpose'] = Convert-TaskSequenceDeploymentPurpose $purposeValue
        }}
        $userNotificationsValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('UserNotifications', 'UserNotification', 'NotifyUser')
        if ($null -ne $userNotificationsValue) {{
            $detail['UserNotifications'] = Convert-BoolToText $userNotificationsValue
        }}
        $allowRestartValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('AllowRestart', 'AllowSystemRestart', 'RebootRequired')
        if ($null -ne $allowRestartValue) {{
            $detail['AllowRestart'] = Convert-BoolToText $allowRestartValue
        }}
    }}
    if ($resolvedType -eq 'Baseline') {{
        $purposeValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('Purpose', 'DeployPurpose', 'DesiredConfigType')
        if ($null -ne $purposeValue) {{
            $detail['Purpose'] = Convert-BaselineDeploymentPurpose $purposeValue
        }}
        $userNotificationsValue = Get-FirstDeploymentPropertyValue -Sources @($detailSource, $deployment, $configSource) -PropertyNames @('UserNotifications', 'UserNotification', 'NotifyUser')
        if ($null -ne $userNotificationsValue) {{
            $detail['UserNotifications'] = Convert-BoolToText $userNotificationsValue
        }}
    }}
    if ($detailFieldsByType.PSObject.Properties[$resolvedType]) {{
        $properties = @($detailFieldsByType.$resolvedType)
    }}
    foreach ($propertyName in $properties) {{
        if ($detail.Contains($propertyName)) {{
            $existingText = [string]$detail[$propertyName]
            if (-not [string]::IsNullOrWhiteSpace($existingText) -and $existingText -ne '-') {{
                continue
            }}
        }}
        $value = $null
        foreach ($source in @($detailSource, $deployment)) {{
            if (-not $source) {{
                continue
            }}
            if ($source.PSObject.Properties[$propertyName]) {{
                $candidateValue = $source.$propertyName
                if ($null -ne $candidateValue) {{
                    if ($candidateValue -is [string]) {{
                        if (-not [string]::IsNullOrWhiteSpace($candidateValue)) {{
                            $value = $candidateValue
                            break
                        }}
                    }} else {{
                        $value = $candidateValue
                        break
                    }}
                }}
            }}
            if ($aliasMap.ContainsKey($propertyName)) {{
                foreach ($aliasName in @($aliasMap[$propertyName])) {{
                    if ($source.PSObject.Properties[$aliasName]) {{
                        $candidateValue = $source.$aliasName
                        if ($null -ne $candidateValue) {{
                            if ($candidateValue -is [string]) {{
                                if (-not [string]::IsNullOrWhiteSpace($candidateValue)) {{
                                    $value = $candidateValue
                                    break
                                }}
                            }} else {{
                                $value = $candidateValue
                                break
                            }}
                        }}
                    }}
                }}
                if ($null -ne $value) {{
                    break
                }}
            }}
        }}
        if ($null -eq $value) {{
            $detail[$propertyName] = '-'
            continue
        }}
        if ($value -is [System.Collections.IEnumerable] -and -not ($value -is [string])) {{
            $items = @($value | ForEach-Object {{ [string]$_ }} | Where-Object {{ $_ -and $_.Trim().Length -gt 0 }})
            if ($items.Count -eq 0) {{
                $detail[$propertyName] = '-'
            }} else {{
                $detail[$propertyName] = ($items -join ', ')
            }}
            continue
        }}
        $valueText = [string]$value
        if ([string]::IsNullOrWhiteSpace($valueText)) {{
            $detail[$propertyName] = '-'
        }} else {{
            $detail[$propertyName] = $valueText
        }}
    }}
    Add-DetailProperties -DetailMap $detail -Source $detailSource
    Add-DetailProperties -DetailMap $detail -Source $deployment
    Add-DetailProperties -DetailMap $detail -Source $configSource
    $results.Add([PSCustomObject]@{{
        Name = $name
        Type = $resolvedType
        Start = $startValue
        Collection = $sourceCollectionName
        Details = [PSCustomObject]$detail
    }})
}}
$results | Sort-Object Name, Type -Unique | ConvertTo-Json -Compress -Depth 8
"""
        )

    def _build_copydeplmt_collections_script(self) -> str:
        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        if not server or not site_code:
            return ""
        bootstrap = self._build_collmember_connection_script(server, site_code)
        return (
            f"""{bootstrap}
Get-CMCollection -ErrorAction Stop |
    Select-Object -ExpandProperty Name |
    Sort-Object -Unique |
    ConvertTo-Json -Compress
"""
        )

    def load_copydeplmt_collections(self) -> None:
        filter_text = self.copydeplmt_source_collection_filter_var.get().strip()
        if not filter_text:
            self.copydeplmt_collections = []
            self.copydeplmt_source_collection_combo.configure(values=())
            self.copydeplmt_source_collection_var.set("")
            messagebox.showwarning("Copy Deplmt", "Collection filter cannot be empty.")
            self.copydeplmt_source_collection_entry.focus_set()
            return
        script = self._build_copydeplmt_collections_script()
        if not script:
            messagebox.showwarning("Copy Deplmt", "SCCM profile is incomplete.")
            return
        self.copydeplmt_collection_search_button.configure(state="disabled")
        self.copydeplmt_source_collection_combo.configure(state="disabled")
        self._set_widget_icon(self.copydeplmt_collection_search_button, "⏳", "", size=16, compound="center")

        def _done(stdout: str, stderr: str) -> None:
            self.copydeplmt_collection_search_button.configure(state="normal")
            self.copydeplmt_source_collection_combo.configure(state="readonly")
            self._set_widget_icon(self.copydeplmt_collection_search_button, "🔍", "", size=16, compound="center")
            if stderr and not stdout:
                self.copydeplmt_collections = []
                self.copydeplmt_source_collection_combo.configure(values=())
                self.copydeplmt_source_collection_var.set("")
                self.append_output(self.output_text, stderr, tag="error")
                return
            if not stdout:
                self.copydeplmt_collections = []
                self.copydeplmt_source_collection_combo.configure(values=())
                self.copydeplmt_source_collection_var.set("")
                return
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                self.copydeplmt_collections = []
                self.copydeplmt_source_collection_combo.configure(values=())
                self.copydeplmt_source_collection_var.set("")
                self.append_output(self.output_text, "Unable to parse collection list.", tag="error")
                return
            if isinstance(data, str):
                values = [data]
            elif isinstance(data, list):
                values = [str(item).strip() for item in data if str(item).strip()]
            else:
                values = []
            self.copydeplmt_collections = sorted(set(values), key=str.lower)
            self._filter_copydeplmt_collections()
            self.append_output(self.output_text, f"Loaded {len(self.copydeplmt_collections)} collection(s) for Copy Deplmt.")

        self._run_ps_async(script, _done)

    def _filter_copydeplmt_collections(self, _event: tk.Event | None = None) -> None:
        needle = self.copydeplmt_source_collection_filter_var.get().strip().lower()
        if not needle:
            self.copydeplmt_source_collection_combo.configure(values=())
            self.copydeplmt_source_collection_var.set("")
            return
        filtered = [name for name in self.copydeplmt_collections if needle in name.lower()]
        current = self.copydeplmt_source_collection_var.get().strip()
        self.copydeplmt_source_collection_combo.configure(values=filtered)
        if current in filtered:
            self.copydeplmt_source_collection_var.set(current)
        elif filtered:
            self.copydeplmt_source_collection_var.set(filtered[0])
        else:
            self.copydeplmt_source_collection_var.set("")

    def _on_copydeplmt_collection_selected(self, _event: tk.Event | None = None) -> None:
        if self.copydeplmt_source_collection_var.get().strip():
            # Switching collection invalidates the previously loaded deployment cache.
            self.copydeplmt_all_candidates = []
            self.copydeplmt_filtered_candidates = []
            self.copydeplmt_checked_candidates = set()
            self.copydeplmt_candidate_details_by_key = {}
            self._refresh_copy_deployment_candidates_tree()

    def _candidate_key(self, candidate: dict[str, str]) -> str:
        # Stable key used to keep checkbox state across tree refreshes.
        return "|".join(
            [
                candidate.get("Name", "").strip().lower(),
                candidate.get("Type", "").strip().lower(),
                candidate.get("Collection", "").strip().lower(),
                candidate.get("Start", "").strip().lower(),
            ]
        )

    def _get_checked_copy_deployment_names(self) -> list[str]:
        selected: list[str] = []
        seen: set[str] = set()
        for candidate in self.copydeplmt_all_candidates:
            candidate_name = candidate.get("Name", "").strip()
            if not candidate_name:
                continue
            key = self._candidate_key(candidate)
            if key not in self.copydeplmt_checked_candidates:
                continue
            lowered = candidate_name.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            selected.append(candidate_name)
        return selected

    def _refresh_copy_deployment_candidates_tree(self) -> None:
        for row_id in self.copydeplmt_candidates_tree.get_children():
            self.copydeplmt_candidates_tree.delete(row_id)
        for candidate in self.copydeplmt_filtered_candidates:
            key = self._candidate_key(candidate)
            checked = "☑" if key in self.copydeplmt_checked_candidates else "☐"
            self.copydeplmt_candidates_tree.insert(
                "",
                "end",
                values=(
                    checked,
                    candidate.get("Name", ""),
                    candidate.get("Type", ""),
                    candidate.get("Start", "-"),
                    candidate.get("Collection", ""),
                ),
                tags=(key,),
            )
        # Reset the details pane so it never shows stale data after a list rebuild.
        self._show_copydeplmt_candidate_details({})

    def _show_copydeplmt_candidate_details(self, details: dict[str, str]) -> None:
        for row_id in self.copydeplmt_details_tree.get_children():
            self.copydeplmt_details_tree.delete(row_id)
        if not details:
            self.copydeplmt_details_tree.insert("", "end", values=("Info", "Select a deployment to view details."))
            return
        for key, value in details.items():
            self.copydeplmt_details_tree.insert("", "end", values=(key, value if value else "-"))

    def _on_copydeplmt_candidate_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.copydeplmt_candidates_tree.selection()
        if not selection:
            self._show_copydeplmt_candidate_details({})
            return
        row_id = selection[0]
        tags = self.copydeplmt_candidates_tree.item(row_id, "tags")
        if not tags:
            self._show_copydeplmt_candidate_details({})
            return
        detail_key = str(tags[0])
        details = self.copydeplmt_candidate_details_by_key.get(detail_key, {})
        self._show_copydeplmt_candidate_details(details)

    def _on_copydeplmt_candidates_tree_click(self, event: tk.Event) -> None:
        region = self.copydeplmt_candidates_tree.identify("region", event.x, event.y)
        if region != "cell":
            return
        column = self.copydeplmt_candidates_tree.identify_column(event.x)
        if column != "#1":
            return
        row_id = self.copydeplmt_candidates_tree.identify_row(event.y)
        if not row_id:
            return
        tags = self.copydeplmt_candidates_tree.item(row_id, "tags")
        if not tags:
            return
        key = str(tags[0])
        if key in self.copydeplmt_checked_candidates:
            self.copydeplmt_checked_candidates.remove(key)
        else:
            self.copydeplmt_checked_candidates.add(key)
        self._refresh_copy_deployment_candidates_tree()
        return "break"

    def filter_copy_deployment_candidates(self) -> None:
        source_collection_name = self.copydeplmt_source_collection_var.get().strip()
        source_types = self._get_selected_copy_deployment_types()
        if not source_collection_name:
            messagebox.showwarning("Copy Deplmt", "Select a source collection first.")
            return
        if not source_types:
            messagebox.showwarning("Copy Deplmt", "Select at least one source type.")
            return
        self.copydeplmt_filter_button.configure(state="disabled")
        self._set_widget_icon(self.copydeplmt_filter_button, "⏳", "", size=16, compound="center")

        def _done(stdout: str, stderr: str) -> None:
            if self.is_closing:
                return
            self.copydeplmt_filter_button.configure(state="normal")
            self._set_widget_icon(self.copydeplmt_filter_button, "🔍", "", size=16, compound="center")
            if stderr and not stdout:
                self.copydeplmt_all_candidates = []
                self.copydeplmt_filtered_candidates = []
                self.copydeplmt_checked_candidates = set()
                self.copydeplmt_candidate_details_by_key = {}
                self._refresh_copy_deployment_candidates_tree()
                self.append_output(self.output_text, stderr, tag="error")
                return
            if not stdout:
                self.copydeplmt_all_candidates = []
                self.copydeplmt_filtered_candidates = []
                self.copydeplmt_checked_candidates = set()
                self.copydeplmt_candidate_details_by_key = {}
                self._refresh_copy_deployment_candidates_tree()
                return
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                self.append_output(self.output_text, "Unable to parse deployment list.", tag="error")
                return
            if isinstance(data, dict):
                records = [data]
            elif isinstance(data, list):
                records = [item for item in data if isinstance(item, dict)]
            else:
                records = []

            # Normalize the PowerShell payload before binding it to the treeview.
            collected = []
            details_by_key: dict[str, dict[str, str]] = {}
            for record in records:
                deployment_name = str(record.get("Name", "")).strip()
                if not deployment_name:
                    continue
                normalized_record = {
                    "Name": deployment_name,
                    "Type": str(record.get("Type", "")).strip(),
                    "Start": str(record.get("Start", "-")).strip() or "-",
                    "Collection": str(record.get("Collection", source_collection_name)).strip() or source_collection_name,
                }
                collected.append(normalized_record)
                raw_details = record.get("Details")
                details = raw_details if isinstance(raw_details, dict) else {}
                ordered_details = self._build_ordered_copydeplmt_details(
                    normalized_record["Type"],
                    {str(key): str(value) for key, value in details.items()},
                )
                details_by_key[self._candidate_key(normalized_record)] = ordered_details
            self.copydeplmt_all_candidates = collected
            self.copydeplmt_filtered_candidates = list(collected)
            self.copydeplmt_checked_candidates = set()
            self.copydeplmt_candidate_details_by_key = details_by_key
            self._refresh_copy_deployment_candidates_tree()
            self.append_output(
                self.output_text,
                f"Loaded {len(collected)} deployment(s) from '{source_collection_name}'.",
            )

        script = self._build_copy_deployment_candidates_script(source_collection_name, source_types)
        self._run_ps_async(script, _done)

    def copy_deployment_value(self) -> None:
        source_types = self._get_selected_copy_deployment_types()
        source_collection_name = self.copydeplmt_source_collection_var.get().strip()
        destination_collection_name = self.copydeplmt_destination_collection_var.get().strip()
        selected_candidates = self._get_checked_copy_deployment_names()
        if not selected_candidates:
            messagebox.showwarning("Copy Deplmt", "Select at least one deployment first.")
            return
        if not source_types:
            messagebox.showwarning("Copy Deplmt", "Select at least one source type.")
            return
        if not source_collection_name or not destination_collection_name:
            messagebox.showwarning("Copy Deplmt", "Enter both the source collection and destination collection.")
            return
        try:
            # Keep clipboard output grouped by the current selection for quick reuse.
            discovered_names = selected_candidates
            clipboard_text = "\n".join(discovered_names)
            self.clipboard_clear()
            self.clipboard_append(clipboard_text)
            self.append_output(
                self.output_text,
                f"Copied {len(discovered_names)} deployment name(s) from '{source_collection_name}' to '{destination_collection_name}' for {', '.join(source_types).lower()} entries.",
            )
        except Exception as exc:
            messagebox.showerror("Copy Deplmt", f"Unable to copy to clipboard:\n{exc}")

    def add_collmember_members(self) -> None:
        if not self.collmember_selected_collection_name or not self.collmember_selected_collection_id:
            messagebox.showwarning("CollMember", "Please select a collection first.")
            return
        if self.collmember_selected_collection_type not in {"Device", "User"}:
            messagebox.showwarning("CollMember", "Unsupported collection type.")
            return

        t = self.theme
        member_kind = "devices" if self.collmember_selected_collection_type == "Device" else "users"
        dialog = tk.Toplevel(self)
        dialog.title(f"Add {member_kind}")
        dialog.geometry("840x520")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=t["surface"])
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        tk.Label(
            dialog,
            text=f"Collection: {self.collmember_selected_collection_name} ({self.collmember_selected_collection_type})",
            bg=t["surface"],
            fg=t["text"],
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))

        editor = tk.Text(dialog, wrap="word", font=("Consolas", 11), bg=t["surface_2"], fg=t["text"], insertbackground=t["text"])
        editor.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 10))

        actions_top = tk.Frame(dialog, bg=t["surface"])
        actions_top.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 6))

        def import_csv_members() -> None:
            csv_path = filedialog.askopenfilename(
                title="Import member CSV",
                filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")],
            )
            if not csv_path:
                return
            try:
                csv_text = Path(csv_path).read_text(encoding="utf-8-sig")
            except OSError:
                messagebox.showerror("CollMember", f"Unable to read file:\n{csv_path}")
                return
            imported = self._parse_member_names("\n".join(",".join(row) for row in csv.reader(csv_text.splitlines())))
            if not imported:
                messagebox.showwarning("CollMember", "No member found in CSV.")
                return
            existing = self._parse_member_names(editor.get("1.0", "end"))
            merged = existing + [name for name in imported if name.lower() not in {x.lower() for x in existing}]
            editor.delete("1.0", "end")
            editor.insert("1.0", "\n".join(merged))

        import_button = tk.Button(actions_top, text="Importer CSV", command=import_csv_members, font=("Segoe UI", 9))
        import_button.pack(side="left")
        self._set_widget_icon(import_button, "📥", "Importer CSV", size=14)

        actions_bottom = tk.Frame(dialog, bg=t["surface"])
        actions_bottom.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))

        def submit_add_members() -> None:
            names = self._parse_member_names(editor.get("1.0", "end"))
            if not names:
                messagebox.showerror("CollMember", "No member detected.")
                return
            if not messagebox.askyesno("Confirm", f"Add {len(names)} member(s)?", parent=dialog):
                return

            profile = self.get_active_profile()
            server = profile.get("server", "").strip()
            site_code = profile.get("site_code", "").strip()
            if not server or not site_code:
                messagebox.showerror("CollMember", "Incomplete SCCM profile (server/site_code).")
                return

            escaped_names = [name.replace("'", "''") for name in names]
            member_lines = "\n".join(f"$memberNames += '{name}'" for name in escaped_names)
            collection_id = self.collmember_selected_collection_id.replace("'", "''")
            submit_button.configure(state="disabled")
            script = self._build_collmember_connection_script(server, site_code) + f"""
$collectionId = '{collection_id}'
$memberNames = @()
{member_lines}
$added = @()
$errors = @()
foreach ($memberName in $memberNames) {{
    if ('{self.collmember_selected_collection_type}' -eq 'Device') {{
        $target = Get-CMDevice -Name $memberName -Fast -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $target) {{
            $errors += "Device not found: $memberName"
            continue
        }}
        try {{
            Add-CMDeviceCollectionDirectMembershipRule -CollectionId $collectionId -ResourceId $target.ResourceID -ErrorAction Stop | Out-Null
            $added += $memberName
        }}
        catch {{
            $errors += "Add Device $memberName: $($_.Exception.Message)"
        }}
    }}
    elseif ('{self.collmember_selected_collection_type}' -eq 'User') {{
        $target = Get-CMUser -Name $memberName -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $target) {{
            $errors += "User not found: $memberName"
            continue
        }}
        try {{
            Add-CMUserCollectionDirectMembershipRule -CollectionId $collectionId -ResourceId $target.ResourceID -ErrorAction Stop | Out-Null
            $added += $memberName
        }}
        catch {{
            $errors += "Add User $memberName: $($_.Exception.Message)"
        }}
    }}
}}
[ordered]@{{ Added = $added; Errors = $errors }} | ConvertTo-Json -Compress
"""

            def _done(stdout: str, stderr: str) -> None:
                submit_button.configure(state="normal")
                if stderr and not stdout:
                    messagebox.showerror("CollMember", f"Error:\n{stderr}")
                    return
                added_count = 0
                errors: list[str] = []
                if stdout:
                    try:
                        payload = json.loads(stdout)
                        added_count = len(payload.get("Added", [])) if isinstance(payload, dict) else 0
                        errors = payload.get("Errors", []) if isinstance(payload, dict) else []
                    except json.JSONDecodeError:
                        pass
                if errors:
                    messagebox.showwarning(
                        "CollMember",
                        f"{added_count} member(s) added.\nErrors:\n" + "\n".join(str(err) for err in errors[:8]),
                    )
                else:
                    messagebox.showinfo("CollMember", f"{added_count} member(s) added.")
                dialog.destroy()
                self.load_collmember_collection_details(self.collmember_selected_collection_name)

            self._run_ps_async(script, _done)

        tk.Button(actions_bottom, text="Cancel", command=dialog.destroy, font=("Segoe UI", 9)).pack(side="left")
        submit_button = tk.Button(actions_bottom, text="Submit", command=submit_add_members, font=("Segoe UI", 9, "bold"))
        submit_button.pack(side="right")

    def remove_selected_collmember_members(self) -> None:
        if not self.collmember_selected_collection_name or not self.collmember_selected_collection_id:
            messagebox.showwarning("CollMember", "Please select a collection first.")
            return
        if self.collmember_selected_collection_type not in {"Device", "User"}:
            messagebox.showwarning("CollMember", "Unsupported collection type.")
            return
        selection = self.collmember_machines_tree.selection()
        if not selection:
            messagebox.showwarning("CollMember", "Select at least one member in TAB 3.")
            return
        names: list[str] = []
        for item_id in selection:
            values = self.collmember_machines_tree.item(item_id, "values")
            if not values:
                continue
            name = str(values[0]).strip()
            if not name or name.startswith("No ") or name.startswith("Select"):
                continue
            names.append(name)
        names = sorted(set(names), key=str.lower)
        if not names:
            messagebox.showwarning("CollMember", "No valid member selected.")
            return
        if not messagebox.askyesno("Confirm", f"Remove {len(names)} selected member(s)?", parent=self):
            return

        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        if not server or not site_code:
            messagebox.showerror("CollMember", "Incomplete SCCM profile (server/site_code).")
            return

        escaped_names = [name.replace("'", "''") for name in names]
        member_lines = "\n".join(f"$memberNames += '{name}'" for name in escaped_names)
        collection_id = self.collmember_selected_collection_id.replace("'", "''")
        script = self._build_collmember_connection_script(server, site_code) + f"""
$collectionId = '{collection_id}'
$memberNames = @()
{member_lines}
$removed = @()
$errors = @()
foreach ($memberName in $memberNames) {{
    if ('{self.collmember_selected_collection_type}' -eq 'Device') {{
        $rule = Get-CMDeviceCollectionDirectMembershipRule -CollectionId $collectionId -ErrorAction SilentlyContinue |
            Where-Object {{ $_.RuleName -eq $memberName }} |
            Select-Object -First 1
        if (-not $rule) {{
            $errors += "Direct Device rule not found: $memberName"
            continue
        }}
        try {{
            Remove-CMDeviceCollectionDirectMembershipRule -CollectionId $collectionId -ResourceId $rule.ResourceID -Force -ErrorAction Stop
            $removed += $memberName
        }}
        catch {{
            $errors += "Remove Device $memberName: $($_.Exception.Message)"
        }}
    }}
    elseif ('{self.collmember_selected_collection_type}' -eq 'User') {{
        $rule = Get-CMUserCollectionDirectMembershipRule -CollectionId $collectionId -ErrorAction SilentlyContinue |
            Where-Object {{ $_.RuleName -eq $memberName }} |
            Select-Object -First 1
        if (-not $rule) {{
            $errors += "Direct User rule not found: $memberName"
            continue
        }}
        try {{
            Remove-CMUserCollectionDirectMembershipRule -CollectionId $collectionId -ResourceId $rule.ResourceID -Force -ErrorAction Stop
            $removed += $memberName
        }}
        catch {{
            $errors += "Remove User $memberName: $($_.Exception.Message)"
        }}
    }}
}}
[ordered]@{{ Removed = $removed; Errors = $errors }} | ConvertTo-Json -Compress
"""

        def _done(stdout: str, stderr: str) -> None:
            if stderr and not stdout:
                messagebox.showerror("CollMember", f"Error:\n{stderr}")
                return
            removed_count = 0
            errors: list[str] = []
            if stdout:
                try:
                    payload = json.loads(stdout)
                    removed_count = len(payload.get("Removed", [])) if isinstance(payload, dict) else 0
                    errors = payload.get("Errors", []) if isinstance(payload, dict) else []
                except json.JSONDecodeError:
                    pass
            if errors:
                messagebox.showwarning(
                    "CollMember",
                    f"{removed_count} member(s) removed.\nErrors:\n" + "\n".join(str(err) for err in errors[:8]),
                )
            else:
                messagebox.showinfo("CollMember", f"{removed_count} member(s) removed.")
            self.load_collmember_collection_details(self.collmember_selected_collection_name)

        self._run_ps_async(script, _done)

    def _get_selected_collmember_query(self) -> tuple[str, str] | None:
        selection = self.collmember_queries_tree.selection()
        if not selection:
            messagebox.showwarning("CollMember", "Select a query in TAB 2.")
            return None
        values = self.collmember_queries_tree.item(selection[0], "values")
        if len(values) < 2:
            messagebox.showwarning("CollMember", "Invalid query.")
            return None
        rule_name = str(values[0]).strip()
        query_text = str(values[1]).strip()
        if not rule_name or rule_name == "-" or query_text in {"", "-", "No query"}:
            messagebox.showwarning("CollMember", "No editable query selected.")
            return None
        return rule_name, query_text

    def copy_selected_collmember_query(self) -> None:
        selected = self._get_selected_collmember_query()
        if selected is None:
            return
        _, query_text = selected
        self.clipboard_clear()
        self.clipboard_append(query_text)
        messagebox.showinfo("CollMember", "Query copied to clipboard.")

    def edit_selected_collmember_query(self) -> None:
        selected = self._get_selected_collmember_query()
        if selected is None:
            return
        collection_name = self.collmember_combo.get().strip()
        if not collection_name:
            messagebox.showwarning("CollMember", "Select a collection.")
            return
        rule_name, query_text = selected

        dialog = tk.Toplevel(self)
        dialog.title("Edit Query")
        dialog.geometry("900x520")
        dialog.transient(self)
        dialog.grab_set()
        t = self.theme
        dialog.configure(bg=t["surface"])

        tk.Label(
            dialog,
            text=f"Collection: {collection_name} | Rule: {rule_name}",
            bg=t["surface"],
            fg=t["text"],
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).pack(fill="x", padx=12, pady=(12, 8))

        editor = tk.Text(dialog, wrap="word", font=("Consolas", 11), bg=t["surface_2"], fg=t["text"], insertbackground=t["text"])
        editor.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        editor.insert("1.0", query_text)

        actions = tk.Frame(dialog, bg=t["surface"])
        actions.pack(fill="x", padx=12, pady=(0, 12))

        def save_query() -> None:
            new_query = editor.get("1.0", "end").strip()
            if not new_query:
                messagebox.showerror("CollMember", "Query cannot be empty.")
                return
            profile = self.get_active_profile()
            server = profile.get("server", "").strip()
            site_code = profile.get("site_code", "").strip()
            if not server or not site_code:
                messagebox.showerror("CollMember", "Incomplete SCCM profile (server/site_code).")
                return
            confirm = messagebox.askyesno(
                "Confirm update",
                f"Confirm query update '{rule_name}'?",
                parent=dialog,
            )
            if not confirm:
                return
            escaped_collection = collection_name.replace("'", "''")
            escaped_rule = rule_name.replace("'", "''")
            escaped_query = new_query.replace("'", "''")
            save_button.configure(state="disabled")

            script = f"""
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$SiteCode = "{site_code}"
$ProviderMachineName = "{server}"
if ((Get-Module ConfigurationManager) -eq $null) {{
    Import-Module "$($ENV:SMS_ADMIN_UI_PATH)\\..\\ConfigurationManager.psd1" -ErrorAction Stop
}}
$existingDrive = Get-PSDrive -Name $SiteCode -PSProvider CMSite -ErrorAction SilentlyContinue
if ($existingDrive -and $existingDrive.Root -and $existingDrive.Root.Trim().ToLowerInvariant() -ne $ProviderMachineName.Trim().ToLowerInvariant()) {{
    Remove-PSDrive -Name $SiteCode -PSProvider CMSite -Force -ErrorAction Stop
    $existingDrive = $null
}}
if ($existingDrive -eq $null) {{
    New-PSDrive -Name $SiteCode -PSProvider CMSite -Root $ProviderMachineName -ErrorAction Stop | Out-Null
}}
Set-Location "$($SiteCode):\\"
$collection = Get-CMCollection -Name '{escaped_collection}' -ErrorAction Stop | Select-Object -First 1
$collectionType = [int]$collection.CollectionType
$siteNamespace = "root\\SMS\\site_$SiteCode"

try {{
    Get-CimInstance -Namespace $siteNamespace -Query '{escaped_query}' -ErrorAction Stop | Select-Object -First 1 | Out-Null
}}
catch {{
    throw "Invalid query. No changes were applied. Details: $($_.Exception.Message)"
}}

if ($collectionType -eq 2) {{
    $rule = Get-CMDeviceCollectionQueryMembershipRule -CollectionId $collection.CollectionID -ErrorAction Stop |
        Where-Object {{ $_.RuleName -eq '{escaped_rule}' }} |
        Select-Object -First 1
    if (-not $rule) {{
        throw "Rule not found: {escaped_rule}"
    }}
    Remove-CMDeviceCollectionQueryMembershipRule -CollectionId $collection.CollectionID -RuleName '{escaped_rule}' -Force -ErrorAction Stop
    Add-CMDeviceCollectionQueryMembershipRule -CollectionId $collection.CollectionID -RuleName '{escaped_rule}' -QueryExpression '{escaped_query}' -ErrorAction Stop | Out-Null
}}
elseif ($collectionType -eq 1) {{
    $rule = Get-CMUserCollectionQueryMembershipRule -CollectionId $collection.CollectionID -ErrorAction Stop |
        Where-Object {{ $_.RuleName -eq '{escaped_rule}' }} |
        Select-Object -First 1
    if (-not $rule) {{
        throw "Rule not found: {escaped_rule}"
    }}
    Remove-CMUserCollectionQueryMembershipRule -CollectionId $collection.CollectionID -RuleName '{escaped_rule}' -Force -ErrorAction Stop
    Add-CMUserCollectionQueryMembershipRule -CollectionId $collection.CollectionID -RuleName '{escaped_rule}' -QueryExpression '{escaped_query}' -ErrorAction Stop | Out-Null
}}
else {{
    throw "Unsupported collection type: $collectionType"
}}
Write-Output "OK"
"""

            def _done(stdout: str, stderr: str) -> None:
                save_button.configure(state="normal")
                if stderr and not stdout:
                    messagebox.showerror("CollMember", f"Query update error:\n{stderr}")
                    return
                messagebox.showinfo("CollMember", "Query updated.")
                dialog.destroy()
                self.load_collmember_collection_details(collection_name)

            self._run_ps_async(script, _done)

        save_button = tk.Button(actions, text="Save", command=save_query, font=("Segoe UI", 9, "bold"))
        save_button.pack(side="right")

    def create_collmember_query(self) -> None:
        collection_name = self.collmember_combo.get().strip()
        if not collection_name:
            messagebox.showwarning("CollMember", "Select a collection.")
            return

        t = self.theme
        dialog = tk.Toplevel(self)
        dialog.title("New Query")
        dialog_width = 900
        dialog_height = 580
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        pos_x = max((screen_width - dialog_width) // 2, 0)
        pos_y = max((screen_height - dialog_height) // 2, 0)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{pos_x}+{pos_y}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=t["surface"])
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(3, weight=1)

        header_label = tk.Label(
            dialog,
            text=f"Collection: {collection_name}",
            bg=t["surface"],
            fg=t["text"],
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        )
        header_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))

        form = tk.Frame(dialog, bg=t["surface"])
        form.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        tk.Label(form, text="Rule Name", bg=t["surface"], fg=t["text"], anchor="w", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        rule_name_var = tk.StringVar(value="")
        rule_name_entry = tk.Entry(form, textvariable=rule_name_var, font=("Segoe UI", 10))
        rule_name_entry.pack(fill="x", pady=(4, 0))

        query_label = tk.Label(
            dialog,
            text="Query",
            bg=t["surface"],
            fg=t["text"],
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        )
        query_label.grid(row=2, column=0, sticky="ew", padx=12, pady=(4, 4))
        editor = tk.Text(dialog, wrap="word", font=("Consolas", 11), bg=t["surface_2"], fg=t["text"], insertbackground=t["text"])
        editor.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 10))

        actions = tk.Frame(dialog, bg=t["surface"])
        actions.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))

        def save_new_query() -> None:
            rule_name = rule_name_var.get().strip()
            new_query = editor.get("1.0", "end").strip()
            if not rule_name:
                messagebox.showerror("CollMember", "Rule Name is required.")
                return
            if not new_query:
                messagebox.showerror("CollMember", "Query cannot be empty.")
                return
            profile = self.get_active_profile()
            server = profile.get("server", "").strip()
            site_code = profile.get("site_code", "").strip()
            if not server or not site_code:
                messagebox.showerror("CollMember", "Incomplete SCCM profile (server/site_code).")
                return
            confirm = messagebox.askyesno(
                "Confirm creation",
                f"Confirm query creation '{rule_name}'?",
                parent=dialog,
            )
            if not confirm:
                return

            escaped_collection = collection_name.replace("'", "''")
            escaped_rule_name = rule_name.replace("'", "''")
            escaped_query = new_query.replace("'", "''")
            submit_button.configure(state="disabled")

            script = f"""
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$SiteCode = "{site_code}"
$ProviderMachineName = "{server}"
if ((Get-Module ConfigurationManager) -eq $null) {{
    Import-Module "$($ENV:SMS_ADMIN_UI_PATH)\\..\\ConfigurationManager.psd1" -ErrorAction Stop
}}
$existingDrive = Get-PSDrive -Name $SiteCode -PSProvider CMSite -ErrorAction SilentlyContinue
if ($existingDrive -and $existingDrive.Root -and $existingDrive.Root.Trim().ToLowerInvariant() -ne $ProviderMachineName.Trim().ToLowerInvariant()) {{
    Remove-PSDrive -Name $SiteCode -PSProvider CMSite -Force -ErrorAction Stop
    $existingDrive = $null
}}
if ($existingDrive -eq $null) {{
    New-PSDrive -Name $SiteCode -PSProvider CMSite -Root $ProviderMachineName -ErrorAction Stop | Out-Null
}}
Set-Location "$($SiteCode):\\"
$collection = Get-CMCollection -Name '{escaped_collection}' -ErrorAction Stop | Select-Object -First 1
$collectionType = [int]$collection.CollectionType
$siteNamespace = "root\\SMS\\site_$SiteCode"

try {{
    Get-CimInstance -Namespace $siteNamespace -Query '{escaped_query}' -ErrorAction Stop | Select-Object -First 1 | Out-Null
}}
catch {{
    throw "Invalid query. Query was not created. Details: $($_.Exception.Message)"
}}

if ($collectionType -eq 2) {{
    Add-CMDeviceCollectionQueryMembershipRule -CollectionId $collection.CollectionID -RuleName '{escaped_rule_name}' -QueryExpression '{escaped_query}' -ErrorAction Stop | Out-Null
}}
elseif ($collectionType -eq 1) {{
    Add-CMUserCollectionQueryMembershipRule -CollectionId $collection.CollectionID -RuleName '{escaped_rule_name}' -QueryExpression '{escaped_query}' -ErrorAction Stop | Out-Null
}}
else {{
    throw "Unsupported collection type: $collectionType"
}}
Write-Output "OK"
"""

            def _done(stdout: str, stderr: str) -> None:
                submit_button.configure(state="normal")
                if stderr and not stdout:
                    messagebox.showerror("CollMember", f"Query creation error:\n{stderr}")
                    return
                messagebox.showinfo("CollMember", "Query created.")
                dialog.destroy()
                self.load_collmember_collection_details(collection_name)

            self._run_ps_async(script, _done)

        cancel_button = tk.Button(actions, text="Cancel", command=dialog.destroy, font=("Segoe UI", 9))
        cancel_button.pack(side="left")
        submit_button = tk.Button(
            actions,
            text="Submit query",
            command=save_new_query,
            font=("Segoe UI", 10, "bold"),
            bg=t["accent_blue"],
            fg="#FFFFFF",
            activebackground=t["accent_blue"],
            activeforeground="#FFFFFF",
            relief="flat",
            padx=12,
            pady=6,
        )
        submit_button.pack(side="right")

    def create_collmember_device_list_query(self) -> None:
        collection_name = self.collmember_combo.get().strip()
        if not collection_name:
            messagebox.showwarning("CollMember", "Select a collection.")
            return

        t = self.theme
        dialog = tk.Toplevel(self)
        dialog.title("Device list query")
        dialog_width = 920
        dialog_height = 620
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        pos_x = max((screen_width - dialog_width) // 2, 0)
        pos_y = max((screen_height - dialog_height) // 2, 0)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{pos_x}+{pos_y}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=t["surface"])
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(4, weight=1)

        tk.Label(
            dialog,
            text=f"Collection: {collection_name}",
            bg=t["surface"],
            fg=t["text"],
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))

        form = tk.Frame(dialog, bg=t["surface"])
        form.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
        tk.Label(form, text="Rule Name", bg=t["surface"], fg=t["text"], anchor="w", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        rule_name_var = tk.StringVar(value="Device List Query")
        rule_name_entry = tk.Entry(form, textvariable=rule_name_var, font=("Segoe UI", 10))
        rule_name_entry.pack(fill="x", pady=(4, 0))

        helper = tk.Label(
            dialog,
            text="Paste a device list (1 per line or separated by commas/;), or import a CSV.",
            bg=t["surface"],
            fg=t["muted_text"],
            anchor="w",
            font=("Segoe UI", 9),
        )
        helper.grid(row=2, column=0, sticky="ew", padx=12, pady=(2, 6))

        top_actions = tk.Frame(dialog, bg=t["surface"])
        top_actions.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 6))
        devices_editor = tk.Text(
            dialog,
            wrap="word",
            font=("Consolas", 11),
            bg=t["surface_2"],
            fg=t["text"],
            insertbackground=t["text"],
        )
        devices_editor.grid(row=4, column=0, sticky="nsew", padx=12, pady=(0, 10))

        def parse_device_names(raw_text: str) -> list[str]:
            names: list[str] = []
            seen: set[str] = set()
            for line in raw_text.splitlines():
                for chunk in re.split(r"[,\t;]", line):
                    name = chunk.strip().strip('"').strip("'")
                    if not name:
                        continue
                    lowered = name.lower()
                    if lowered in {"name", "device", "devices", "computer", "hostname"}:
                        continue
                    if lowered in seen:
                        continue
                    seen.add(lowered)
                    names.append(name)
            return names

        def import_csv_devices() -> None:
            csv_path = filedialog.askopenfilename(
                title="Importer un CSV de devices",
                filetypes=[("CSV files", "*.csv"), ("Text files", "*.txt"), ("All files", "*.*")],
            )
            if not csv_path:
                return
            try:
                csv_text = Path(csv_path).read_text(encoding="utf-8-sig")
            except OSError:
                messagebox.showerror("CollMember", f"Unable to read file:\n{csv_path}")
                return
            imported_names: list[str] = []
            seen: set[str] = set()
            for row in csv.reader(csv_text.splitlines()):
                for cell in row:
                    for chunk in re.split(r"[,\t;]", cell):
                        name = chunk.strip().strip('"').strip("'")
                        if not name:
                            continue
                        lowered = name.lower()
                        if lowered in {"name", "device", "devices", "computer", "hostname"}:
                            continue
                        if lowered in seen:
                            continue
                        seen.add(lowered)
                        imported_names.append(name)
            if not imported_names:
                messagebox.showwarning("CollMember", "No device found in CSV.")
                return
            current_names = parse_device_names(devices_editor.get("1.0", "end"))
            merged = current_names + [name for name in imported_names if name.lower() not in {n.lower() for n in current_names}]
            devices_editor.delete("1.0", "end")
            devices_editor.insert("1.0", "\n".join(merged))

        import_button = tk.Button(top_actions, text="Importer CSV", command=import_csv_devices, font=("Segoe UI", 9))
        import_button.pack(side="left")
        self._set_widget_icon(import_button, "📥", "Importer CSV", size=14)

        def submit_device_list_query() -> None:
            rule_name = rule_name_var.get().strip()
            if not rule_name:
                messagebox.showerror("CollMember", "Le Rule Name est obligatoire.")
                return
            device_names = parse_device_names(devices_editor.get("1.0", "end"))
            if not device_names:
                messagebox.showerror("CollMember", "No device detected in the list.")
                return

            escaped_devices = [name.replace("'", "''") for name in device_names]
            in_values = "',\n       '".join(escaped_devices)
            query_text = (
                "select SMS_R_System.ResourceId,\n"
                "       SMS_R_System.Name\n"
                "from SMS_R_System\n"
                "where SMS_R_System.Name in ('"
                + in_values
                + "')"
            )

            profile = self.get_active_profile()
            server = profile.get("server", "").strip()
            site_code = profile.get("site_code", "").strip()
            if not server or not site_code:
                messagebox.showerror("CollMember", "Incomplete SCCM profile (server/site_code).")
                return

            confirm = messagebox.askyesno(
                "Confirm creation",
                f"Create query '{rule_name}' with {len(device_names)} device(s)?",
                parent=dialog,
            )
            if not confirm:
                return

            escaped_collection = collection_name.replace("'", "''")
            escaped_rule_name = rule_name.replace("'", "''")
            escaped_query = query_text.replace("'", "''")
            submit_button.configure(state="disabled")

            script = f"""
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$SiteCode = "{site_code}"
$ProviderMachineName = "{server}"
if ((Get-Module ConfigurationManager) -eq $null) {{
    Import-Module "$($ENV:SMS_ADMIN_UI_PATH)\\..\\ConfigurationManager.psd1" -ErrorAction Stop
}}
$existingDrive = Get-PSDrive -Name $SiteCode -PSProvider CMSite -ErrorAction SilentlyContinue
if ($existingDrive -and $existingDrive.Root -and $existingDrive.Root.Trim().ToLowerInvariant() -ne $ProviderMachineName.Trim().ToLowerInvariant()) {{
    Remove-PSDrive -Name $SiteCode -PSProvider CMSite -Force -ErrorAction Stop
    $existingDrive = $null
}}
if ($existingDrive -eq $null) {{
    New-PSDrive -Name $SiteCode -PSProvider CMSite -Root $ProviderMachineName -ErrorAction Stop | Out-Null
}}
Set-Location "$($SiteCode):\\"
$collection = Get-CMCollection -Name '{escaped_collection}' -ErrorAction Stop | Select-Object -First 1
$collectionType = [int]$collection.CollectionType
if ($collectionType -ne 2) {{
    throw "This action is supported only for a Device Collection."
}}
$siteNamespace = "root\\SMS\\site_$SiteCode"
try {{
    Get-CimInstance -Namespace $siteNamespace -Query '{escaped_query}' -ErrorAction Stop | Select-Object -First 1 | Out-Null
}}
catch {{
    throw "Invalid query. Query was not created. Details: $($_.Exception.Message)"
}}
Add-CMDeviceCollectionQueryMembershipRule -CollectionId $collection.CollectionID -RuleName '{escaped_rule_name}' -QueryExpression '{escaped_query}' -ErrorAction Stop | Out-Null
Write-Output "OK"
"""

            def _done(stdout: str, stderr: str) -> None:
                submit_button.configure(state="normal")
                if stderr and not stdout:
                    messagebox.showerror("CollMember", f"Query creation error:\n{stderr}")
                    return
                messagebox.showinfo("CollMember", "Device list query created.")
                dialog.destroy()
                self.load_collmember_collection_details(collection_name)

            self._run_ps_async(script, _done)

        bottom_actions = tk.Frame(dialog, bg=t["surface"])
        bottom_actions.grid(row=5, column=0, sticky="ew", padx=12, pady=(0, 12))
        cancel_button = tk.Button(bottom_actions, text="Cancel", command=dialog.destroy, font=("Segoe UI", 9))
        cancel_button.pack(side="left")
        submit_button = tk.Button(
            bottom_actions,
            text="Submit query",
            command=submit_device_list_query,
            font=("Segoe UI", 10, "bold"),
            bg=t["accent_blue"],
            fg="#FFFFFF",
            activebackground=t["accent_blue"],
            activeforeground="#FFFFFF",
            relief="flat",
            padx=12,
            pady=6,
        )
        submit_button.pack(side="right")

    def _filter_collmember_machines(self, _event: tk.Event | None = None) -> None:
        needle = self.collmember_machine_filter_var.get().strip().lower()
        for row in self.collmember_machines_tree.get_children():
            self.collmember_machines_tree.delete(row)
        if needle:
            filtered = [name for name in self.collmember_machine_names if needle in name.lower()]
        else:
            filtered = list(self.collmember_machine_names)
        if not filtered:
            self.collmember_machines_tree.insert("", "end", values=("No machine",))
            return
        for machine_name in filtered:
            self.collmember_machines_tree.insert("", "end", values=(machine_name,))

    def on_tab_hover_enter(self, tab_name: str) -> None:
        if tab_name != self.current_tab:
            tab_data = self.tab_buttons[tab_name]
            tab_data["canvas"].itemconfigure(tab_data["shape"], fill=self.theme["tabs_btn_hover"])
            tab_data["canvas"].itemconfigure(tab_data["text"], fill=self.theme["tabs_btn_text"])

    def on_tab_hover_leave(self, tab_name: str) -> None:
        if tab_name != self.current_tab:
            tab_data = self.tab_buttons[tab_name]
            tab_data["canvas"].itemconfigure(tab_data["shape"], fill=self.theme["tabs_btn_bg"])
            tab_data["canvas"].itemconfigure(tab_data["text"], fill=self.theme["tabs_btn_text"])

    def _on_infra_menu_frame_configure(self, _event: tk.Event) -> None:
        self.infra_menu_canvas.configure(scrollregion=self.infra_menu_canvas.bbox("all"))

    def _on_infra_menu_canvas_configure(self, event: tk.Event) -> None:
        self.infra_menu_canvas.itemconfigure(self.infra_menu_window, width=event.width)

    def _on_infra_menu_mousewheel(self, event: tk.Event) -> str:
        if event.delta == 0:
            return "break"
        scroll_units = -1 if event.delta > 0 else 1
        self.infra_menu_canvas.yview_scroll(scroll_units, "units")
        return "break"

    def _on_collmember_output_mousewheel(self, event: tk.Event) -> str:
        if event.delta == 0:
            return "break"
        scroll_units = -1 if event.delta > 0 else 1
        self.collmember_output_canvas.yview_scroll(scroll_units, "units")
        return "break"

    def _make_text_output_readonly(self, widget: tk.Text) -> None:
        def on_key(event: tk.Event) -> str | None:
            ctrl_pressed = bool(event.state & 0x4)
            shift_pressed = bool(event.state & 0x1)
            key = event.keysym.lower()

            # Allow standard copy/selection shortcuts
            if ctrl_pressed and key in {"c", "a", "insert"}:
                return None
            if shift_pressed and key in {"left", "right", "up", "down", "home", "end", "prior", "next"}:
                return None
            if key in {"left", "right", "up", "down", "prior", "next", "home", "end", "shift_l", "shift_r", "control_l", "control_r"}:
                return None
            if key in {"backspace", "delete", "return", "kp_enter", "tab"}:
                return "break"
            if event.char:
                return "break"
            return "break"

        widget.bind("<Key>", on_key)
        widget.bind("<<Paste>>", lambda _event: "break")
        widget.bind("<<Cut>>", lambda _event: "break")
        widget.bind("<Control-v>", lambda _event: "break")
        widget.bind("<Control-x>", lambda _event: "break")
        widget.bind("<Button-2>", lambda _event: "break")

    # ── Shared helpers ───────────────────────────────────────────────────────

    def _configure_treeview_style(
        self, name: str, row_height: int, t: dict, widget: ttk.Treeview | None = None, heading: bool = False
    ) -> None:
        """Apply theme colours to a ttk.Treeview style and optionally bind a widget to it."""
        self.style.configure(
            name,
            background=t["surface_2"],
            fieldbackground=t["surface_2"],
            foreground=t["text"],
            bordercolor=t["border"],
            rowheight=row_height,
            font=("Segoe UI", 10),
        )
        if heading:
            self.style.configure(
                f"{name}.Heading",
                background=t["surface_3"],
                foreground=t["text"],
                relief="flat",
                font=("Segoe UI", 10, "bold"),
            )
        self.style.map(name, background=[("selected", t["accent_blue"])], foreground=[("selected", "#FFFFFF")])
        if widget is not None:
            widget.configure(style=name)

    def _apply_vertical_menu_theme(self) -> None:
        """Update only the vertical menu button highlights without a full theme rebuild."""
        t = self.theme
        for item, button in self.vertical_menu_buttons:
            active = item == self.vertical_menu_selected
            button.configure(
                bg=t["sidebar_active"] if active else t["surface"],
                fg="#FFFFFF" if active else t["text"],
                activebackground=t["surface_3"],
                activeforeground=t["text"],
                cursor="hand2",
            )

    def _run_ps_async(self, script: str, callback) -> None:
        """Run a PowerShell -Command script in a daemon thread; calls callback(stdout, stderr) on the main thread."""
        def _worker() -> None:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True, text=True, check=False,
            )
            if not self.is_closing:
                self.after(0, lambda: callback(result.stdout.strip(), result.stderr.strip()))
        threading.Thread(target=_worker, daemon=True).start()

    def _get_selected_ps1(self) -> "Path | None":
        """Return the Path of the currently selected PS1 script, or None (with error shown)."""
        selection = self.ps1_tree.selection()
        if not selection:
            self.append_output(self.ps1_output, "Select a .ps1 script.", tag="error")
            return None
        path = self.ps1_script_map.get(selection[0])
        if path is None:
            self.append_output(self.ps1_output, "Invalid script.", tag="error")
        return path

    def _apply_powershell_syntax_highlighting(self, widget: tk.Text, content: str) -> None:
        if self.theme_name == "dark":
            colors = {
                "keyword": "#60A5FA", "cmdlet": "#007348", "variable": "#FBBF24",
                "string": "#F472B6",  "comment": "#94A3B8", "operator": "#C084FC", "number": "#22D3EE",
            }
        else:
            colors = {
                "keyword": "#1D4ED8", "cmdlet": "#007348", "variable": "#B45309",
                "string": "#BE185D",  "comment": "#6B7280", "operator": "#7C3AED", "number": "#0E7490",
            }
        for tag, color in colors.items():
            widget.tag_configure(tag, foreground=color)
        for tag, pattern in _PS1_HIGHLIGHT_PATTERNS:
            for match in pattern.finditer(content):
                widget.tag_add(tag, f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def append_output(self, widget: tk.Text, content: str, tag: str | None = None) -> None:
        text = content.rstrip() + "\n"
        start = widget.index("end-1c")
        widget.insert("end", text)
        if tag:
            widget.tag_add(tag, start, f"{start}+{len(text)}c")
        widget.see("end")

    def check_sccm_connection(self) -> None:
        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        self.output_text.delete("1.0", "end")

        if not server or not site_code:
            self.append_output(
                self.output_text,
                "SCCM connection failed: incomplete profile. Open Settings to define server and site code.",
                tag="error",
            )
            return

        self.run_check_button.configure(state="disabled")
        self._set_widget_icon(self.run_check_button, "⏳", "…", size=16)
        script = (
            f"$ok = Test-Connection -ComputerName '{server}' -Count 1 -Quiet; "
            "if ($ok) { "
            f"Write-Output 'SCCM connection OK'; Write-Output 'Server: {server}'; Write-Output 'Site code: {site_code}'; "
            "} else { Write-Error 'Unable to reach SCCM server.'; exit 1 }"
        )

        def _done(stdout: str, stderr: str) -> None:
            self.run_check_button.configure(state="normal")
            self._set_widget_icon(self.run_check_button, "▶️", "Run Check", size=16)
            has_error = bool(stderr) or not stdout
            if has_error:
                msg = f"SCCM connection failed\n{stderr}" if stderr else "SCCM connection failed"
                self.append_output(self.output_text, msg, tag="error")
            else:
                self.append_output(self.output_text, stdout)

        self._run_ps_async(script, _done)

    def _normalize_collvariable_name(self, name: str) -> str:
        cleaned = name.strip()
        normalized = re.sub(r"[\s_-]*\d+$", "", cleaned)
        return normalized or cleaned

    def _clear_collvariable_output_tables(self) -> None:
        for row in self.collvariable_tab1_tree.get_children():
            self.collvariable_tab1_tree.delete(row)
        for row in self.collvariable_tab2_tree.get_children():
            self.collvariable_tab2_tree.delete(row)
        self.collvariable_names_values = []
        self.collvariable_groups = []

    def _populate_collvariable_tab1(self, group_name: str | None = None) -> None:
        for row in self.collvariable_tab1_tree.get_children():
            self.collvariable_tab1_tree.delete(row)
        rows = self.collvariable_names_values
        if group_name:
            rows = [
                (name, value)
                for name, value in rows
                if self._normalize_collvariable_name(name).lower() == group_name.lower()
            ]
        if not rows:
            self.collvariable_tab1_tree.insert("", "end", values=("No name", "No value"))
            return
        for name, value in rows:
            self.collvariable_tab1_tree.insert("", "end", values=(name, value))

    def _populate_collvariable_tab2(self) -> None:
        for row in self.collvariable_tab2_tree.get_children():
            self.collvariable_tab2_tree.delete(row)
        if not self.collvariable_groups:
            self.collvariable_tab2_tree.insert("", "end", values=("No name",))
            return
        for group_name in self.collvariable_groups:
            self.collvariable_tab2_tree.insert("", "end", values=(group_name,))

    def _get_selected_collvariable_group(self) -> str | None:
        selection = self.collvariable_tab2_tree.selection()
        if not selection:
            return None
        values = self.collvariable_tab2_tree.item(selection[0], "values")
        if not values:
            return None
        selected_group = str(values[0]).strip()
        if not selected_group or selected_group.startswith("No "):
            return None
        return selected_group

    def _get_selected_collvariable_name(self) -> str | None:
        selection = self.collvariable_tab1_tree.selection()
        if not selection:
            return None
        values = self.collvariable_tab1_tree.item(selection[0], "values")
        if not values:
            return None
        selected_name = str(values[0]).strip()
        if not selected_name or selected_name.startswith("No "):
            return None
        return selected_name

    def _apply_collvariable_name_filters(self) -> None:
        self._filter_collvariable_collections()

    def _matches_collvariable_category_filters(self, collection_name: str, active_filters: set[str]) -> bool:
        if not active_filters:
            return True
        lowered = collection_name.lower()
        # OR logic: any selected category match keeps the collection.
        return any(token in lowered for token in active_filters)

    def _build_next_collvariable_name(self, raw_name: str, start_number: int = 1) -> str:
        candidate = raw_name.strip()
        base_name = self._normalize_collvariable_name(candidate)
        if not base_name:
            return ""
        if start_number < 1:
            start_number = 1

        trailing_match = re.search(r"(\d+)$", candidate)
        current_max = int(trailing_match.group(1)) if trailing_match else (start_number - 1)
        width = max(2, len(trailing_match.group(1))) if trailing_match else 2

        for existing_name, _ in self.collvariable_names_values:
            existing_clean = existing_name.strip()
            if self._normalize_collvariable_name(existing_clean).lower() != base_name.lower():
                continue
            existing_match = re.search(r"(\d+)$", existing_clean)
            if not existing_match:
                continue
            existing_number = int(existing_match.group(1))
            existing_width = len(existing_match.group(1))
            if existing_number > current_max:
                current_max = existing_number
            if existing_width > width:
                width = existing_width

        next_number = max(current_max + 1, start_number)
        return f"{base_name}{next_number:0{width}d}"

    def load_collvariable_collection_variables(self, collection_names: list[str]) -> None:
        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        self._clear_collvariable_output_tables()
        if not collection_names:
            self._populate_collvariable_tab1()
            self._populate_collvariable_tab2()
            return
        if not server or not site_code:
            messagebox.showerror(
                "CollVariable",
                "SCCM connection failed: incomplete profile. Open Settings to define server and site code.",
            )
            return

        self.collvariable_search_button.configure(state="disabled")
        self.collvariable_listbox.configure(state="disabled")
        self._set_widget_icon(self.collvariable_search_button, "⏳", "", size=16, compound="center")
        escaped_collections = ",".join("'" + name.replace("'", "''") + "'" for name in collection_names)
        script = f"""
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$SiteCode = "{site_code}"
$ProviderMachineName = "{server}"
if ((Get-Module ConfigurationManager) -eq $null) {{
    Import-Module "$($ENV:SMS_ADMIN_UI_PATH)\\..\\ConfigurationManager.psd1" -ErrorAction Stop
}}
$existingDrive = Get-PSDrive -Name $SiteCode -PSProvider CMSite -ErrorAction SilentlyContinue
if ($existingDrive -and $existingDrive.Root -and $existingDrive.Root.Trim().ToLowerInvariant() -ne $ProviderMachineName.Trim().ToLowerInvariant()) {{
    Remove-PSDrive -Name $SiteCode -PSProvider CMSite -Force -ErrorAction Stop
    $existingDrive = $null
}}
if ($existingDrive -eq $null) {{
    New-PSDrive -Name $SiteCode -PSProvider CMSite -Root $ProviderMachineName -ErrorAction Stop | Out-Null
}}
Set-Location "$($SiteCode):\\"
$selectedCollections = @({escaped_collections})
$variables = @(
    foreach ($collectionName in $selectedCollections) {{
        Get-CMDeviceCollectionVariable -CollectionName $collectionName -ErrorAction SilentlyContinue
    }}
)
$rows = @($variables | ForEach-Object {{
    [ordered]@{{
        Name = [string]$_.Name
        Value = [string]$_.Value
    }}
}})
$rows | ConvertTo-Json -Compress -Depth 6
"""

        def _done(stdout: str, stderr: str) -> None:
            self.collvariable_search_button.configure(state="normal")
            self.collvariable_listbox.configure(state="normal")
            self._set_widget_icon(self.collvariable_search_button, "🔍", "", size=16, compound="center")
            if stderr and not stdout:
                messagebox.showerror("CollVariable", stderr.strip() or "PowerShell error.")
                return
            if not stdout:
                self._populate_collvariable_tab1()
                self._populate_collvariable_tab2()
                return
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                messagebox.showerror("CollVariable", "Unable to parse collection variables.")
                return

            rows: list[tuple[str, str]] = []
            if isinstance(data, dict):
                name = str(data.get("Name", "")).strip()
                value = str(data.get("Value", "")).strip()
                if name:
                    rows.append((name, value))
            elif isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("Name", "")).strip()
                    value = str(item.get("Value", "")).strip()
                    if name:
                        rows.append((name, value))
            self.collvariable_names_values = rows
            group_set = {
                self._normalize_collvariable_name(name)
                for name, _value in rows
                if self._normalize_collvariable_name(name)
            }
            self.collvariable_groups = sorted(group_set, key=str.lower)
            self._populate_collvariable_tab1()
            self._populate_collvariable_tab2()

        self._run_ps_async(script, _done)

    def load_collvariable_collections(self) -> None:
        filter_text = self.collvariable_filter_var.get().strip()
        active_name_filters = {
            name_filter.lower()
            for name_filter, enabled in self.collvariable_name_filter_vars.items()
            if enabled.get()
        }
        if not filter_text and not active_name_filters:
            self._clear_collvariable_output_tables()
            self.collvariable_listbox.delete(0, "end")
            self.collvariable_selected_collection_names = []
            messagebox.showwarning("CollVariable", "Collection Name filter cannot be empty when no category is selected.")
            self.collvariable_filter_entry.focus_set()
            return

        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        if not server or not site_code:
            self._clear_collvariable_output_tables()
            messagebox.showerror(
                "CollVariable",
                "SCCM connection failed: incomplete profile. Open Settings to define server and site code.",
            )
            return

        self.collvariable_search_button.configure(state="disabled")
        self.collvariable_listbox.configure(state="disabled")
        self._set_widget_icon(self.collvariable_search_button, "⏳", "", size=16, compound="center")

        script = f"""
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$SiteCode = "{site_code}"
$ProviderMachineName = "{server}"
if ((Get-Module ConfigurationManager) -eq $null) {{
    Import-Module "$($ENV:SMS_ADMIN_UI_PATH)\\..\\ConfigurationManager.psd1" -ErrorAction Stop
}}
$existingDrive = Get-PSDrive -Name $SiteCode -PSProvider CMSite -ErrorAction SilentlyContinue
if ($existingDrive -and $existingDrive.Root -and $existingDrive.Root.Trim().ToLowerInvariant() -ne $ProviderMachineName.Trim().ToLowerInvariant()) {{
    Remove-PSDrive -Name $SiteCode -PSProvider CMSite -Force -ErrorAction Stop
    $existingDrive = $null
}}
if ($existingDrive -eq $null) {{
    New-PSDrive -Name $SiteCode -PSProvider CMSite -Root $ProviderMachineName -ErrorAction Stop | Out-Null
}}
Set-Location "$($SiteCode):\\"
Get-CMCollection -ErrorAction Stop |
    Select-Object -ExpandProperty Name |
    Sort-Object -Unique |
    ConvertTo-Json -Compress
"""

        def _done(stdout: str, stderr: str) -> None:
            self.collvariable_search_button.configure(state="normal")
            self.collvariable_listbox.configure(state="normal")
            self._set_widget_icon(self.collvariable_search_button, "🔍", "", size=16, compound="center")
            if stderr and not stdout:
                messagebox.showerror("CollVariable", stderr.strip() or "PowerShell error.")
                return
            if not stdout:
                self.collvariable_collections = []
                self.collvariable_listbox.delete(0, "end")
                self.collvariable_selected_collection_names = []
                self._clear_collvariable_output_tables()
                return
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                messagebox.showerror("CollVariable", "Unable to parse collection list.")
                return
            if isinstance(data, str):
                values = [data]
            elif isinstance(data, list):
                values = [str(item).strip() for item in data if str(item).strip()]
            else:
                values = []
            self.collvariable_collections = sorted(set(values), key=str.lower)
            self._filter_collvariable_collections()

        self._run_ps_async(script, _done)

    def _filter_collvariable_collections(self, _event: tk.Event | None = None) -> None:
        needle = self.collvariable_filter_var.get().strip().lower()
        active_name_filters = {
            name_filter.lower()
            for name_filter, enabled in self.collvariable_name_filter_vars.items()
            if enabled.get()
        }
        selected_before = {
            self.collvariable_listbox.get(i)
            for i in self.collvariable_listbox.curselection()
        }
        self.collvariable_listbox.delete(0, "end")
        if not needle and not active_name_filters:
            self.collvariable_selected_collection_names = []
            self.load_collvariable_collection_variables([])
            return
        filtered = []
        for name in self.collvariable_collections:
            lowered = name.lower()
            if needle and needle not in lowered:
                continue
            if not self._matches_collvariable_category_filters(name, active_name_filters):
                continue
            filtered.append(name)
        for collection_name in filtered:
            self.collvariable_listbox.insert("end", collection_name)
        for idx, collection_name in enumerate(filtered):
            if collection_name in selected_before:
                self.collvariable_listbox.selection_set(idx)
        self.on_collvariable_collections_selected()

    def on_collvariable_collections_selected(self, _event: tk.Event | None = None) -> None:
        selected_indices = self.collvariable_listbox.curselection()
        self.collvariable_selected_collection_names = [
            self.collvariable_listbox.get(index)
            for index in selected_indices
        ]
        self.load_collvariable_collection_variables(self.collvariable_selected_collection_names)

    def add_collvariable_variable(self) -> None:
        if not self.collvariable_selected_collection_names:
            messagebox.showwarning("CollVariable", "Select at least one collection.")
            return

        group_values = list(self.collvariable_groups)
        if not group_values:
            messagebox.showwarning("CollVariable", "No variable group available in TAB2.")
            return
        default_name = self._get_selected_collvariable_group() or group_values[0]
        t = self.theme
        dialog = tk.Toplevel(self)
        dialog.title("Add variable")
        dialog.geometry("560x260")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=t["surface"])
        dialog.columnconfigure(0, weight=1)

        tk.Label(
            dialog,
            text=f"Selected collections: {len(self.collvariable_selected_collection_names)}",
            bg=t["surface"],
            fg=t["text"],
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))

        form = tk.Frame(dialog, bg=t["surface"])
        form.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        form.columnconfigure(0, weight=1)

        variable_name_var = tk.StringVar(value=default_name)
        value_var = tk.StringVar(value="")

        tk.Label(form, text="Variable Name", bg=t["surface"], fg=t["muted_text"]).grid(row=0, column=0, sticky="w")
        variable_name_combo = ttk.Combobox(
            form,
            textvariable=variable_name_var,
            values=group_values,
            state="readonly",
            font=("Segoe UI", 10),
        )
        variable_name_combo.grid(row=1, column=0, sticky="ew", pady=(2, 8))
        if default_name in group_values:
            variable_name_combo.current(group_values.index(default_name))
        else:
            variable_name_combo.current(0)
            variable_name_var.set(group_values[0])

        tk.Label(form, text="Value", bg=t["surface"], fg=t["muted_text"]).grid(row=2, column=0, sticky="w")
        value_entry = tk.Entry(form, textvariable=value_var, font=("Segoe UI", 10))
        value_entry.grid(row=3, column=0, sticky="ew", pady=(2, 8))

        footer = tk.Frame(dialog, bg=t["surface"])
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

        def submit_add() -> None:
            base_name = variable_name_combo.get().strip()
            if not base_name and group_values:
                base_name = group_values[0]
            value_text = value_var.get().strip()
            if not base_name:
                messagebox.showerror("CollVariable", "Variable Name is required.")
                variable_name_combo.focus_set()
                return
            if not value_text:
                messagebox.showerror("CollVariable", "Value is required.")
                value_entry.focus_set()
                return

            next_name = self._build_next_collvariable_name(base_name)
            if not next_name:
                messagebox.showerror("CollVariable", "Unable to build variable name.")
                return

            confirm = messagebox.askyesno(
                "Confirm creation",
                f"Add variable '{next_name}' to {len(self.collvariable_selected_collection_names)} collection(s)?",
                parent=dialog,
            )
            if not confirm:
                return

            profile = self.get_active_profile()
            server = profile.get("server", "").strip()
            site_code = profile.get("site_code", "").strip()
            if not server or not site_code:
                messagebox.showerror(
                    "CollVariable",
                    "SCCM connection failed: incomplete profile. Open Settings to define server and site code.",
                )
                return

            submit_button.configure(state="disabled")
            escaped_collections = ",".join(
                "'" + collection_name.replace("'", "''") + "'"
                for collection_name in self.collvariable_selected_collection_names
            )
            escaped_variable_name = next_name.replace("'", "''")
            escaped_value = value_text.replace("'", "''")
            escaped_base_name = base_name.replace("'", "''")
            success_token = "__COLLVARIABLE_ADD_OK__"
            script = (
                self._build_collmember_connection_script(server, site_code)
                + f"""
$selectedCollections = @({escaped_collections})
$baseName = '{escaped_base_name}'
$newCmd = Get-Command New-CMDeviceCollectionVariable -ErrorAction Stop
$newParams = $newCmd.Parameters.Keys
$nameParam = if ($newParams -contains 'VariableName') {{ 'VariableName' }} elseif ($newParams -contains 'Name') {{ 'Name' }} else {{ throw "New-CMDeviceCollectionVariable missing variable name parameter." }}
$valueParam = if ($newParams -contains 'Value') {{ 'Value' }} elseif ($newParams -contains 'VariableValue') {{ 'VariableValue' }} elseif ($newParams -contains 'NewVariableValue') {{ 'NewVariableValue' }} else {{ throw "New-CMDeviceCollectionVariable missing value parameter." }}
$hasCollectionName = $newParams -contains 'CollectionName'
$hasCollectionId = $newParams -contains 'CollectionId'
$removeCmd = Get-Command Remove-CMDeviceCollectionVariable -ErrorAction Stop
$removeParams = $removeCmd.Parameters.Keys
$removeNameParam = if ($removeParams -contains 'VariableName') {{ 'VariableName' }} elseif ($removeParams -contains 'Name') {{ 'Name' }} else {{ throw "Remove-CMDeviceCollectionVariable missing variable name parameter." }}
$removeHasCollectionName = $removeParams -contains 'CollectionName'
$removeHasCollectionId = $removeParams -contains 'CollectionId'
$removeHasConfirm = $removeParams -contains 'Confirm'
$removeHasForce = $removeParams -contains 'Force'
function Get-CollvariableCollectionInvoke {{
    param(
        [string]$CollectionName,
        [bool]$HasCollectionName,
        [bool]$HasCollectionId
    )
    $invoke = @{{ ErrorAction = 'Stop' }}
    if ($HasCollectionName) {{
        $invoke['CollectionName'] = $CollectionName
        return $invoke
    }}
    if ($HasCollectionId) {{
        $collection = Get-CMCollection -Name $CollectionName -ErrorAction Stop | Select-Object -First 1
        $invoke['CollectionId'] = $collection.CollectionID
        return $invoke
    }}
    throw "Collection parameter is missing on cmdlet."
}}
function Get-CollvariableNormalizedName {{
    param([string]$Name)
    $cleaned = [string]$Name
    $cleaned = $cleaned.Trim()
    $normalized = [regex]::Replace($cleaned, '[\\s_-]*\\d+$', '')
    if ([string]::IsNullOrWhiteSpace($normalized)) {{
        return $cleaned
    }}
    return $normalized
}}
foreach ($collectionName in $selectedCollections) {{
    $invoke = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $hasCollectionName -HasCollectionId $hasCollectionId
    $invoke[$nameParam] = '{escaped_variable_name}'
    $invoke[$valueParam] = '{escaped_value}'
    New-CMDeviceCollectionVariable @invoke | Out-Null

    $variables = @(
        Get-CMDeviceCollectionVariable -CollectionName $collectionName -ErrorAction SilentlyContinue
    )
    $numericRows = @()
    foreach ($row in $variables) {{
        $rowName = [string]$row.Name
        $normalized = Get-CollvariableNormalizedName -Name $rowName
        if ($normalized.ToLowerInvariant() -ne $baseName.ToLowerInvariant()) {{
            continue
        }}
        $match = [regex]::Match($rowName, '(\\d+)$')
        if (-not $match.Success) {{
            continue
        }}
        $numericRows += [pscustomobject]@{{
            Name = $rowName
            Value = [string]$row.Value
            Number = [int]$match.Groups[1].Value
            Width = [int]$match.Groups[1].Value.Length
        }}
    }}

    $orderedRows = @($numericRows | Sort-Object Number, Name)
    $expected = 1
    $renamePlan = @()
    foreach ($row in $orderedRows) {{
        $targetWidth = if ($row.Width -gt 2) {{ $row.Width }} else {{ 2 }}
        $newName = "{{0}}{{1}}" -f $baseName, $expected.ToString("D{{0}}" -f $targetWidth)
        if ($row.Name -ne $newName) {{
            $renamePlan += [pscustomobject]@{{
                OldName = $row.Name
                NewName = $newName
                Value = $row.Value
            }}
        }}
        $expected += 1
    }}

    if ($renamePlan.Count -gt 0) {{
        $batchId = [guid]::NewGuid().ToString('N')
        $staged = @()
        $index = 0
        foreach ($plan in $renamePlan) {{
            $tmpName = "TmpCV" + $batchId.Substring(0,8) + $index.ToString()
            $removeOld = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
            $removeOld[$removeNameParam] = $plan.OldName
            if ($removeHasConfirm) {{ $removeOld['Confirm'] = $false }}
            if ($removeHasForce) {{ $removeOld['Force'] = $true }}
            Remove-CMDeviceCollectionVariable @removeOld | Out-Null

            $newTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $hasCollectionName -HasCollectionId $hasCollectionId
            $newTmp[$nameParam] = $tmpName
            $newTmp[$valueParam] = $plan.Value
            New-CMDeviceCollectionVariable @newTmp | Out-Null

            $staged += [pscustomobject]@{{
                TempName = $tmpName
                FinalName = $plan.NewName
                Value = $plan.Value
            }}
            $index += 1
        }}
        foreach ($item in $staged) {{
            $removeTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
            $removeTmp[$removeNameParam] = $item.TempName
            if ($removeHasConfirm) {{ $removeTmp['Confirm'] = $false }}
            if ($removeHasForce) {{ $removeTmp['Force'] = $true }}
            Remove-CMDeviceCollectionVariable @removeTmp | Out-Null

            $newFinal = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $hasCollectionName -HasCollectionId $hasCollectionId
            $newFinal[$nameParam] = $item.FinalName
            $newFinal[$valueParam] = $item.Value
            New-CMDeviceCollectionVariable @newFinal | Out-Null
        }}
    }}
}}
Write-Output "{success_token}"
"""
            )

            def _done(stdout: str, stderr: str) -> None:
                submit_button.configure(state="normal")
                if stderr:
                    details = stderr.strip()
                    if stdout:
                        details = f"{details}\n\n{stdout.strip()}"
                    messagebox.showerror("CollVariable", details or "PowerShell error.")
                    return
                if success_token not in stdout:
                    messagebox.showerror("CollVariable", stdout.strip() or "Variable creation failed.")
                    return
                messagebox.showinfo("CollVariable", f"Variable created: {next_name}")
                dialog.destroy()
                self.load_collvariable_collection_variables(self.collvariable_selected_collection_names)

            self._run_ps_async(script, _done)

        cancel_button = tk.Button(footer, text="Cancel", command=dialog.destroy, font=("Segoe UI", 9))
        cancel_button.pack(side="left")
        submit_button = tk.Button(
            footer,
            text="Submit",
            command=submit_add,
            font=("Segoe UI", 10, "bold"),
            bg=t["accent_blue"],
            fg="#FFFFFF",
            activebackground=t["accent_blue"],
            activeforeground="#FFFFFF",
            relief="flat",
            padx=12,
            pady=6,
        )
        submit_button.pack(side="right")

        variable_name_combo.focus_set()

    def new_collvariable_variable(self) -> None:
        if not self.collvariable_selected_collection_names:
            messagebox.showwarning("CollVariable", "Select at least one collection.")
            return

        t = self.theme
        dialog = tk.Toplevel(self)
        dialog.title("New variable")
        dialog.geometry("560x260")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=t["surface"])
        dialog.columnconfigure(0, weight=1)

        tk.Label(
            dialog,
            text=f"Selected collections: {len(self.collvariable_selected_collection_names)}",
            bg=t["surface"],
            fg=t["text"],
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))

        form = tk.Frame(dialog, bg=t["surface"])
        form.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 8))
        form.columnconfigure(0, weight=1)

        variable_name_var = tk.StringVar(value="")
        value_var = tk.StringVar(value="")

        tk.Label(form, text="Variable Name", bg=t["surface"], fg=t["muted_text"]).grid(row=0, column=0, sticky="w")
        variable_name_entry = tk.Entry(form, textvariable=variable_name_var, font=("Segoe UI", 10))
        variable_name_entry.grid(row=1, column=0, sticky="ew", pady=(2, 8))

        tk.Label(form, text="Value", bg=t["surface"], fg=t["muted_text"]).grid(row=2, column=0, sticky="w")
        value_entry = tk.Entry(form, textvariable=value_var, font=("Segoe UI", 10))
        value_entry.grid(row=3, column=0, sticky="ew", pady=(2, 8))

        footer = tk.Frame(dialog, bg=t["surface"])
        footer.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 12))

        def submit_new() -> None:
            variable_name = variable_name_var.get().strip()
            value_text = value_var.get().strip()
            if not variable_name:
                messagebox.showerror("CollVariable", "Variable Name is required.")
                variable_name_entry.focus_set()
                return
            if not value_text:
                messagebox.showerror("CollVariable", "Value is required.")
                value_entry.focus_set()
                return

            next_name = self._build_next_collvariable_name(variable_name, start_number=1)
            if not next_name:
                messagebox.showerror("CollVariable", "Unable to build variable name.")
                return

            confirm = messagebox.askyesno(
                "Confirm creation",
                f"Add variable '{next_name}' to {len(self.collvariable_selected_collection_names)} collection(s)?",
                parent=dialog,
            )
            if not confirm:
                return

            profile = self.get_active_profile()
            server = profile.get("server", "").strip()
            site_code = profile.get("site_code", "").strip()
            if not server or not site_code:
                messagebox.showerror(
                    "CollVariable",
                    "SCCM connection failed: incomplete profile. Open Settings to define server and site code.",
                )
                return

            submit_button.configure(state="disabled")
            escaped_collections = ",".join(
                "'" + collection_name.replace("'", "''") + "'"
                for collection_name in self.collvariable_selected_collection_names
            )
            escaped_variable_name = next_name.replace("'", "''")
            escaped_value = value_text.replace("'", "''")
            escaped_base_name = self._normalize_collvariable_name(variable_name).replace("'", "''")
            success_token = "__COLLVARIABLE_NEW_OK__"
            script = (
                self._build_collmember_connection_script(server, site_code)
                + f"""
$selectedCollections = @({escaped_collections})
$baseName = '{escaped_base_name}'
$newCmd = Get-Command New-CMDeviceCollectionVariable -ErrorAction Stop
$newParams = $newCmd.Parameters.Keys
$nameParam = if ($newParams -contains 'VariableName') {{ 'VariableName' }} elseif ($newParams -contains 'Name') {{ 'Name' }} else {{ throw "New-CMDeviceCollectionVariable missing variable name parameter." }}
$valueParam = if ($newParams -contains 'Value') {{ 'Value' }} elseif ($newParams -contains 'VariableValue') {{ 'VariableValue' }} elseif ($newParams -contains 'NewVariableValue') {{ 'NewVariableValue' }} else {{ throw "New-CMDeviceCollectionVariable missing value parameter." }}
$hasCollectionName = $newParams -contains 'CollectionName'
$hasCollectionId = $newParams -contains 'CollectionId'
$removeCmd = Get-Command Remove-CMDeviceCollectionVariable -ErrorAction Stop
$removeParams = $removeCmd.Parameters.Keys
$removeNameParam = if ($removeParams -contains 'VariableName') {{ 'VariableName' }} elseif ($removeParams -contains 'Name') {{ 'Name' }} else {{ throw "Remove-CMDeviceCollectionVariable missing variable name parameter." }}
$removeHasCollectionName = $removeParams -contains 'CollectionName'
$removeHasCollectionId = $removeParams -contains 'CollectionId'
$removeHasConfirm = $removeParams -contains 'Confirm'
$removeHasForce = $removeParams -contains 'Force'
function Get-CollvariableCollectionInvoke {{
    param(
        [string]$CollectionName,
        [bool]$HasCollectionName,
        [bool]$HasCollectionId
    )
    $invoke = @{{ ErrorAction = 'Stop' }}
    if ($HasCollectionName) {{
        $invoke['CollectionName'] = $CollectionName
        return $invoke
    }}
    if ($HasCollectionId) {{
        $collection = Get-CMCollection -Name $CollectionName -ErrorAction Stop | Select-Object -First 1
        $invoke['CollectionId'] = $collection.CollectionID
        return $invoke
    }}
    throw "Collection parameter is missing on cmdlet."
}}
function Get-CollvariableNormalizedName {{
    param([string]$Name)
    $cleaned = [string]$Name
    $cleaned = $cleaned.Trim()
    $normalized = [regex]::Replace($cleaned, '[\\s_-]*\\d+$', '')
    if ([string]::IsNullOrWhiteSpace($normalized)) {{
        return $cleaned
    }}
    return $normalized
}}
foreach ($collectionName in $selectedCollections) {{
    $invoke = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $hasCollectionName -HasCollectionId $hasCollectionId
    $invoke[$nameParam] = '{escaped_variable_name}'
    $invoke[$valueParam] = '{escaped_value}'
    New-CMDeviceCollectionVariable @invoke | Out-Null

    $variables = @(
        Get-CMDeviceCollectionVariable -CollectionName $collectionName -ErrorAction SilentlyContinue
    )
    $numericRows = @()
    foreach ($row in $variables) {{
        $rowName = [string]$row.Name
        $normalized = Get-CollvariableNormalizedName -Name $rowName
        if ($normalized.ToLowerInvariant() -ne $baseName.ToLowerInvariant()) {{
            continue
        }}
        $match = [regex]::Match($rowName, '(\\d+)$')
        if (-not $match.Success) {{
            continue
        }}
        $numericRows += [pscustomobject]@{{
            Name = $rowName
            Value = [string]$row.Value
            Number = [int]$match.Groups[1].Value
            Width = [int]$match.Groups[1].Value.Length
        }}
    }}

    $orderedRows = @($numericRows | Sort-Object Number, Name)
    $expected = 1
    $renamePlan = @()
    foreach ($row in $orderedRows) {{
        $targetWidth = if ($row.Width -gt 2) {{ $row.Width }} else {{ 2 }}
        $newName = "{0}{1}" -f $baseName, $expected.ToString("D{0}" -f $targetWidth)
        if ($row.Name -ne $newName) {{
            $renamePlan += [pscustomobject]@{{
                OldName = $row.Name
                NewName = $newName
                Value = $row.Value
            }}
        }}
        $expected += 1
    }}

    if ($renamePlan.Count -gt 0) {{
        $batchId = [guid]::NewGuid().ToString('N')
        $staged = @()
        $index = 0
        foreach ($plan in $renamePlan) {{
            $tmpName = "TmpCV" + $batchId.Substring(0,8) + $index.ToString()
            $removeOld = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
            $removeOld[$removeNameParam] = $plan.OldName
            if ($removeHasConfirm) {{ $removeOld['Confirm'] = $false }}
            if ($removeHasForce) {{ $removeOld['Force'] = $true }}
            Remove-CMDeviceCollectionVariable @removeOld | Out-Null

            $newTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $hasCollectionName -HasCollectionId $hasCollectionId
            $newTmp[$nameParam] = $tmpName
            $newTmp[$valueParam] = $plan.Value
            New-CMDeviceCollectionVariable @newTmp | Out-Null

            $staged += [pscustomobject]@{{
                TempName = $tmpName
                FinalName = $plan.NewName
                Value = $plan.Value
            }}
            $index += 1
        }}
        foreach ($item in $staged) {{
            $removeTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
            $removeTmp[$removeNameParam] = $item.TempName
            if ($removeHasConfirm) {{ $removeTmp['Confirm'] = $false }}
            if ($removeHasForce) {{ $removeTmp['Force'] = $true }}
            Remove-CMDeviceCollectionVariable @removeTmp | Out-Null

            $newFinal = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $hasCollectionName -HasCollectionId $hasCollectionId
            $newFinal[$nameParam] = $item.FinalName
            $newFinal[$valueParam] = $item.Value
            New-CMDeviceCollectionVariable @newFinal | Out-Null
        }}
    }}
}}
Write-Output "{success_token}"
"""
            )

            def _done(stdout: str, stderr: str) -> None:
                submit_button.configure(state="normal")
                if stderr:
                    details = stderr.strip()
                    if stdout:
                        details = f"{details}\n\n{stdout.strip()}"
                    messagebox.showerror("CollVariable", details or "PowerShell error.")
                    return
                if success_token not in stdout:
                    messagebox.showerror("CollVariable", stdout.strip() or "Variable creation failed.")
                    return
                messagebox.showinfo("CollVariable", f"Variable created: {next_name}")
                dialog.destroy()
                self.load_collvariable_collection_variables(self.collvariable_selected_collection_names)

            self._run_ps_async(script, _done)

        cancel_button = tk.Button(footer, text="Cancel", command=dialog.destroy, font=("Segoe UI", 9))
        cancel_button.pack(side="left")
        submit_button = tk.Button(
            footer,
            text="Submit",
            command=submit_new,
            font=("Segoe UI", 10, "bold"),
            bg=t["accent_blue"],
            fg="#FFFFFF",
            activebackground=t["accent_blue"],
            activeforeground="#FFFFFF",
            relief="flat",
            padx=12,
            pady=6,
        )
        submit_button.pack(side="right")

        variable_name_entry.focus_set()

    def remove_collvariable_variable(self) -> None:
        if not self.collvariable_selected_collection_names:
            messagebox.showwarning("CollVariable", "Select at least one collection.")
            return

        selected_name = self._get_selected_collvariable_name()
        if not selected_name:
            messagebox.showwarning("CollVariable", "Select a variable in TAB 1.")
            return

        base_name = self._normalize_collvariable_name(selected_name)
        confirm = messagebox.askyesno(
            "Confirm remove",
            (
                f"Remove variable '{selected_name}' from "
                f"{len(self.collvariable_selected_collection_names)} collection(s)?\n\n"
                "The numbering will be checked and adjusted if needed."
            ),
        )
        if not confirm:
            return

        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        if not server or not site_code:
            messagebox.showerror(
                "CollVariable",
                "SCCM connection failed: incomplete profile. Open Settings to define server and site code.",
            )
            return

        self.collvariable_remove_button.configure(state="disabled")
        escaped_collections = ",".join(
            "'" + collection_name.replace("'", "''") + "'"
            for collection_name in self.collvariable_selected_collection_names
        )
        escaped_selected_name = selected_name.replace("'", "''")
        escaped_base_name = base_name.replace("'", "''")
        script = (
            self._build_collmember_connection_script(server, site_code)
            + f"""
$selectedCollections = @({escaped_collections})
$targetName = '{escaped_selected_name}'
$baseName = '{escaped_base_name}'
$removeCmd = Get-Command Remove-CMDeviceCollectionVariable -ErrorAction Stop
$removeParams = $removeCmd.Parameters.Keys
$removeNameParam = if ($removeParams -contains 'VariableName') {{ 'VariableName' }} elseif ($removeParams -contains 'Name') {{ 'Name' }} else {{ throw "Remove-CMDeviceCollectionVariable missing variable name parameter." }}
$removeHasCollectionName = $removeParams -contains 'CollectionName'
$removeHasCollectionId = $removeParams -contains 'CollectionId'
$removeHasConfirm = $removeParams -contains 'Confirm'
$removeHasForce = $removeParams -contains 'Force'
$newCmd = Get-Command New-CMDeviceCollectionVariable -ErrorAction Stop
$newParams = $newCmd.Parameters.Keys
$newNameParam = if ($newParams -contains 'VariableName') {{ 'VariableName' }} elseif ($newParams -contains 'Name') {{ 'Name' }} else {{ throw "New-CMDeviceCollectionVariable missing variable name parameter." }}
$newValueParam = if ($newParams -contains 'Value') {{ 'Value' }} elseif ($newParams -contains 'VariableValue') {{ 'VariableValue' }} elseif ($newParams -contains 'NewVariableValue') {{ 'NewVariableValue' }} else {{ throw "New-CMDeviceCollectionVariable missing value parameter." }}
$newHasCollectionName = $newParams -contains 'CollectionName'
$newHasCollectionId = $newParams -contains 'CollectionId'
function Get-CollvariableCollectionInvoke {{
    param(
        [string]$CollectionName,
        [bool]$HasCollectionName,
        [bool]$HasCollectionId
    )
    $invoke = @{{ ErrorAction = 'Stop' }}
    if ($HasCollectionName) {{
        $invoke['CollectionName'] = $CollectionName
        return $invoke
    }}
    if ($HasCollectionId) {{
        $collection = Get-CMCollection -Name $CollectionName -ErrorAction Stop | Select-Object -First 1
        $invoke['CollectionId'] = $collection.CollectionID
        return $invoke
    }}
    throw "Collection parameter is missing on cmdlet."
}}
function Get-CollvariableNormalizedName {{
    param([string]$Name)
    $cleaned = [string]$Name
    $cleaned = $cleaned.Trim()
    $normalized = [regex]::Replace($cleaned, '[\\s_-]*\\d+$', '')
    if ([string]::IsNullOrWhiteSpace($normalized)) {{
        return $cleaned
    }}
    return $normalized
}}
foreach ($collectionName in $selectedCollections) {{
    $removeInvoke = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
    $removeInvoke[$removeNameParam] = $targetName
    if ($removeHasConfirm) {{ $removeInvoke['Confirm'] = $false }}
    if ($removeHasForce) {{ $removeInvoke['Force'] = $true }}
    Remove-CMDeviceCollectionVariable @removeInvoke | Out-Null

    $variables = @(
        Get-CMDeviceCollectionVariable -CollectionName $collectionName -ErrorAction SilentlyContinue
    )
    $numericRows = @()
    foreach ($row in $variables) {{
        $rowName = [string]$row.Name
        $normalized = Get-CollvariableNormalizedName -Name $rowName
        if ($normalized.ToLowerInvariant() -ne $baseName.ToLowerInvariant()) {{
            continue
        }}
        $match = [regex]::Match($rowName, '(\\d+)$')
        if (-not $match.Success) {{
            continue
        }}
        $numericRows += [pscustomobject]@{{
            Name = $rowName
            Value = [string]$row.Value
            Number = [int]$match.Groups[1].Value
            Width = [int]$match.Groups[1].Value.Length
        }}
    }}

    $orderedRows = @($numericRows | Sort-Object Number, Name)
    $expected = 1
    $renamePlan = @()
    foreach ($row in $orderedRows) {{
        $targetWidth = if ($row.Width -gt 2) {{ $row.Width }} else {{ 2 }}
        $newName = "{{0}}{{1}}" -f $baseName, $expected.ToString("D{{0}}" -f $targetWidth)
        if ($row.Name -ne $newName) {{
            $renamePlan += [pscustomobject]@{{
                OldName = $row.Name
                NewName = $newName
                Value = $row.Value
            }}
        }}
        $expected += 1
    }}

    if ($renamePlan.Count -gt 0) {{
        $batchId = [guid]::NewGuid().ToString('N')
        $staged = @()
        $index = 0
        foreach ($plan in $renamePlan) {{
            $tmpName = "TmpCV" + $batchId.Substring(0,8) + $index.ToString()
            $removeOld = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
            $removeOld[$removeNameParam] = $plan.OldName
            if ($removeHasConfirm) {{ $removeOld['Confirm'] = $false }}
            if ($removeHasForce) {{ $removeOld['Force'] = $true }}
            Remove-CMDeviceCollectionVariable @removeOld | Out-Null

            $newTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $newHasCollectionName -HasCollectionId $newHasCollectionId
            $newTmp[$newNameParam] = $tmpName
            $newTmp[$newValueParam] = $plan.Value
            New-CMDeviceCollectionVariable @newTmp | Out-Null

            $staged += [pscustomobject]@{{
                TempName = $tmpName
                FinalName = $plan.NewName
                Value = $plan.Value
            }}
            $index += 1
        }}
        foreach ($item in $staged) {{
            $removeTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
            $removeTmp[$removeNameParam] = $item.TempName
            if ($removeHasConfirm) {{ $removeTmp['Confirm'] = $false }}
            if ($removeHasForce) {{ $removeTmp['Force'] = $true }}
            Remove-CMDeviceCollectionVariable @removeTmp | Out-Null

            $newFinal = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $newHasCollectionName -HasCollectionId $newHasCollectionId
            $newFinal[$newNameParam] = $item.FinalName
            $newFinal[$newValueParam] = $item.Value
            New-CMDeviceCollectionVariable @newFinal | Out-Null
        }}
    }}
}}
Write-Output "OK"
"""
        )

        def _done(stdout: str, stderr: str) -> None:
            self.collvariable_remove_button.configure(state="normal")
            if stderr:
                details = stderr.strip()
                if stdout:
                    details = f"{details}\n\n{stdout.strip()}"
                messagebox.showerror("CollVariable", details or "PowerShell error.")
                return
            messagebox.showinfo("CollVariable", f"Variable removed: {selected_name}")
            self.load_collvariable_collection_variables(self.collvariable_selected_collection_names)

        self._run_ps_async(script, _done)

    def renumber_collvariable_variables(self) -> None:
        if not self.collvariable_selected_collection_names:
            messagebox.showwarning("CollVariable", "Select at least one collection.")
            return

        confirm = messagebox.askyesno(
            "Confirm re-number",
            (
                f"Analyze and re-number variables for "
                f"{len(self.collvariable_selected_collection_names)} collection(s)?\n\n"
                "Numbering will be adjusted from 01 for each variable base name."
            ),
        )
        if not confirm:
            return

        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        if not server or not site_code:
            messagebox.showerror(
                "CollVariable",
                "SCCM connection failed: incomplete profile. Open Settings to define server and site code.",
            )
            return

        self.collvariable_renumber_button.configure(state="disabled")
        escaped_collections = ",".join(
            "'" + collection_name.replace("'", "''")
            + "'"
            for collection_name in self.collvariable_selected_collection_names
        )
        success_token = "__COLLVARIABLE_RENUMBER_OK__"
        script = (
            self._build_collmember_connection_script(server, site_code)
            + f"""
$selectedCollections = @({escaped_collections})
$removeCmd = Get-Command Remove-CMDeviceCollectionVariable -ErrorAction Stop
$removeParams = $removeCmd.Parameters.Keys
$removeNameParam = if ($removeParams -contains 'VariableName') {{ 'VariableName' }} elseif ($removeParams -contains 'Name') {{ 'Name' }} else {{ throw "Remove-CMDeviceCollectionVariable missing variable name parameter." }}
$removeHasCollectionName = $removeParams -contains 'CollectionName'
$removeHasCollectionId = $removeParams -contains 'CollectionId'
$removeHasConfirm = $removeParams -contains 'Confirm'
$removeHasForce = $removeParams -contains 'Force'
$newCmd = Get-Command New-CMDeviceCollectionVariable -ErrorAction Stop
$newParams = $newCmd.Parameters.Keys
$newNameParam = if ($newParams -contains 'VariableName') {{ 'VariableName' }} elseif ($newParams -contains 'Name') {{ 'Name' }} else {{ throw "New-CMDeviceCollectionVariable missing variable name parameter." }}
$newValueParam = if ($newParams -contains 'Value') {{ 'Value' }} elseif ($newParams -contains 'VariableValue') {{ 'VariableValue' }} elseif ($newParams -contains 'NewVariableValue') {{ 'NewVariableValue' }} else {{ throw "New-CMDeviceCollectionVariable missing value parameter." }}
$newHasCollectionName = $newParams -contains 'CollectionName'
$newHasCollectionId = $newParams -contains 'CollectionId'
function Get-CollvariableCollectionInvoke {{
    param(
        [string]$CollectionName,
        [bool]$HasCollectionName,
        [bool]$HasCollectionId
    )
    $invoke = @{{ ErrorAction = 'Stop' }}
    if ($HasCollectionName) {{
        $invoke['CollectionName'] = $CollectionName
        return $invoke
    }}
    if ($HasCollectionId) {{
        $collection = Get-CMCollection -Name $CollectionName -ErrorAction Stop | Select-Object -First 1
        $invoke['CollectionId'] = $collection.CollectionID
        return $invoke
    }}
    throw "Collection parameter is missing on cmdlet."
}}
function Get-CollvariableNormalizedName {{
    param([string]$Name)
    $cleaned = [string]$Name
    $cleaned = $cleaned.Trim()
    $normalized = [regex]::Replace($cleaned, '[\\s_-]*\\d+$', '')
    if ([string]::IsNullOrWhiteSpace($normalized)) {{
        return $cleaned
    }}
    return $normalized
}}
foreach ($collectionName in $selectedCollections) {{
    $variables = @(
        Get-CMDeviceCollectionVariable -CollectionName $collectionName -ErrorAction SilentlyContinue
    )
    $numericRows = @()
    foreach ($row in $variables) {{
        $rowName = [string]$row.Name
        $match = [regex]::Match($rowName, '(\\d+)$')
        if (-not $match.Success) {{
            continue
        }}
        $numericRows += [pscustomobject]@{{
            Name = $rowName
            Value = [string]$row.Value
            Number = [int]$match.Groups[1].Value
            Width = [int]$match.Groups[1].Value.Length
            BaseName = [string](Get-CollvariableNormalizedName -Name $rowName)
        }}
    }}

    $baseGroups = @($numericRows | Group-Object {{ $_.BaseName.ToLowerInvariant() }})
    foreach ($group in $baseGroups) {{
        $orderedRows = @($group.Group | Sort-Object Number, Name)
        if ($orderedRows.Count -eq 0) {{
            continue
        }}
        $baseName = [string]$orderedRows[0].BaseName
        if ([string]::IsNullOrWhiteSpace($baseName)) {{
            continue
        }}
        $expected = 1
        $renamePlan = @()
        foreach ($item in $orderedRows) {{
            $targetWidth = if ($item.Width -gt 2) {{ $item.Width }} else {{ 2 }}
            $newName = "{{0}}{{1}}" -f $baseName, $expected.ToString("D{{0}}" -f $targetWidth)
            if ($item.Name -ne $newName) {{
                $renamePlan += [pscustomobject]@{{
                    OldName = $item.Name
                    NewName = $newName
                    Value = $item.Value
                }}
            }}
            $expected += 1
        }}

        if ($renamePlan.Count -eq 0) {{
            continue
        }}

        $batchId = [guid]::NewGuid().ToString('N')
        $staged = @()
        $index = 0
        foreach ($plan in $renamePlan) {{
            $tmpName = "TmpCV" + $batchId.Substring(0,8) + $index.ToString()
            $removeOld = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
            $removeOld[$removeNameParam] = $plan.OldName
            if ($removeHasConfirm) {{ $removeOld['Confirm'] = $false }}
            if ($removeHasForce) {{ $removeOld['Force'] = $true }}
            Remove-CMDeviceCollectionVariable @removeOld | Out-Null

            $newTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $newHasCollectionName -HasCollectionId $newHasCollectionId
            $newTmp[$newNameParam] = $tmpName
            $newTmp[$newValueParam] = $plan.Value
            New-CMDeviceCollectionVariable @newTmp | Out-Null

            $staged += [pscustomobject]@{{
                TempName = $tmpName
                FinalName = $plan.NewName
                Value = $plan.Value
            }}
            $index += 1
        }}
        foreach ($item in $staged) {{
            $removeTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
            $removeTmp[$removeNameParam] = $item.TempName
            if ($removeHasConfirm) {{ $removeTmp['Confirm'] = $false }}
            if ($removeHasForce) {{ $removeTmp['Force'] = $true }}
            Remove-CMDeviceCollectionVariable @removeTmp | Out-Null

            $newFinal = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $newHasCollectionName -HasCollectionId $newHasCollectionId
            $newFinal[$newNameParam] = $item.FinalName
            $newFinal[$newValueParam] = $item.Value
            New-CMDeviceCollectionVariable @newFinal | Out-Null
        }}
    }}
}}
Write-Output "{success_token}"
"""
        )

        def _done(stdout: str, stderr: str) -> None:
            self.collvariable_renumber_button.configure(state="normal")
            if stderr:
                details = stderr.strip()
                if stdout:
                    details = f"{details}\n\n{stdout.strip()}"
                messagebox.showerror("CollVariable", details or "PowerShell error.")
                return
            if success_token not in stdout:
                messagebox.showerror("CollVariable", stdout.strip() or "Re-number operation failed.")
                return
            messagebox.showinfo("CollVariable", "Variable numbering updated.")
            self.load_collvariable_collection_variables(self.collvariable_selected_collection_names)

        self._run_ps_async(script, _done)

    def replace_collvariable_variable(self) -> None:
        if not self.collvariable_selected_collection_names:
            messagebox.showwarning("CollVariable", "Select at least one collection.")
            return

        selected_rows = self.collvariable_tab1_tree.selection()
        selected_names: list[str] = []
        for row_id in selected_rows:
            values = self.collvariable_tab1_tree.item(row_id, "values")
            if not values:
                continue
            name = str(values[0]).strip()
            if not name or name.startswith("No "):
                continue
            selected_names.append(name)
        if not selected_names:
            selected_group = self._get_selected_collvariable_group()
            if selected_group:
                selected_names = [
                    name
                    for name, _ in self.collvariable_names_values
                    if self._normalize_collvariable_name(name).lower() == selected_group.lower()
                ]
        ordered_unique_names = list(dict.fromkeys(selected_names))
        if not ordered_unique_names:
            messagebox.showwarning("CollVariable", "Select one or more variables in TAB 1.")
            return

        t = self.theme
        dialog = tk.Toplevel(self)
        dialog.title("Replace variable value")
        dialog_width = 560
        dialog_height = 360
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        pos_x = max((screen_width - dialog_width) // 2, 0)
        pos_y = max((screen_height - dialog_height) // 2, 0)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{pos_x}+{pos_y}")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=t["surface"])
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)

        tk.Label(
            dialog,
            text=f"Selected collections: {len(self.collvariable_selected_collection_names)}",
            bg=t["surface"],
            fg=t["text"],
            anchor="w",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 8))

        tk.Label(
            dialog,
            text="Variables",
            bg=t["surface"],
            fg=t["muted_text"],
            anchor="w",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))

        variables_frame = tk.Frame(dialog, bg=t["surface"])
        variables_frame.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 8))
        variables_frame.rowconfigure(0, weight=1)
        variables_frame.columnconfigure(0, weight=1)

        variables_listbox = tk.Listbox(
            variables_frame,
            selectmode="extended",
            exportselection=False,
            activestyle="none",
            font=("Segoe UI", 10),
            bg=t["surface_2"],
            fg=t["text"],
            selectbackground=t["accent_blue"],
            selectforeground="#FFFFFF",
            highlightthickness=1,
            highlightbackground=t["border"],
            highlightcolor=t["accent_blue"],
            relief="flat",
            bd=0,
        )
        variables_listbox.grid(row=0, column=0, sticky="nsew")
        variables_scrollbar = ttk.Scrollbar(
            variables_frame,
            orient="vertical",
            command=variables_listbox.yview,
        )
        variables_scrollbar.grid(row=0, column=1, sticky="ns")
        variables_listbox.configure(yscrollcommand=variables_scrollbar.set)
        for idx, name in enumerate(ordered_unique_names):
            variables_listbox.insert("end", name)
            variables_listbox.selection_set(idx)

        value_frame = tk.Frame(dialog, bg=t["surface"])
        value_frame.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 8))
        value_frame.columnconfigure(0, weight=1)
        tk.Label(value_frame, text="New value", bg=t["surface"], fg=t["muted_text"]).grid(row=0, column=0, sticky="w")
        value_var = tk.StringVar(value="")
        value_entry = tk.Entry(value_frame, textvariable=value_var, font=("Segoe UI", 10))
        value_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))

        footer = tk.Frame(dialog, bg=t["surface"])
        footer.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))

        def submit_replace() -> None:
            selected_indices = variables_listbox.curselection()
            target_names = [
                variables_listbox.get(index)
                for index in selected_indices
            ]
            if not target_names:
                messagebox.showerror("CollVariable", "Select at least one variable.")
                return
            new_value = value_var.get().strip()
            if not new_value:
                messagebox.showerror("CollVariable", "New value is required.")
                value_entry.focus_set()
                return

            confirm = messagebox.askyesno(
                "Confirm replace",
                (
                    f"Replace value for {len(target_names)} variable(s) in "
                    f"{len(self.collvariable_selected_collection_names)} collection(s)?"
                ),
                parent=dialog,
            )
            if not confirm:
                return

            profile = self.get_active_profile()
            server = profile.get("server", "").strip()
            site_code = profile.get("site_code", "").strip()
            if not server or not site_code:
                messagebox.showerror(
                    "CollVariable",
                    "SCCM connection failed: incomplete profile. Open Settings to define server and site code.",
                )
                return

            submit_button.configure(state="disabled")
            escaped_collections = ",".join(
                "'" + collection_name.replace("'", "''") + "'"
                for collection_name in self.collvariable_selected_collection_names
            )
            escaped_names = ",".join(
                "'" + name.replace("'", "''") + "'"
                for name in target_names
            )
            escaped_value = new_value.replace("'", "''")
            success_token = "__COLLVARIABLE_REPLACE_OK__"
            script = (
                self._build_collmember_connection_script(server, site_code)
                + f"""
$selectedCollections = @({escaped_collections})
$targetNames = @({escaped_names})
$newValue = '{escaped_value}'
$setCmd = Get-Command Set-CMDeviceCollectionVariable -ErrorAction Stop
$setParams = $setCmd.Parameters.Keys
$nameParam = if ($setParams -contains 'VariableName') {{ 'VariableName' }} elseif ($setParams -contains 'Name') {{ 'Name' }} else {{ throw "Set-CMDeviceCollectionVariable missing variable name parameter." }}
$valueParam = if ($setParams -contains 'Value') {{ 'Value' }} elseif ($setParams -contains 'VariableValue') {{ 'VariableValue' }} elseif ($setParams -contains 'NewVariableValue') {{ 'NewVariableValue' }} else {{ throw "Set-CMDeviceCollectionVariable missing value parameter." }}
$hasCollectionName = $setParams -contains 'CollectionName'
$hasCollectionId = $setParams -contains 'CollectionId'
$hasConfirm = $setParams -contains 'Confirm'
$hasForce = $setParams -contains 'Force'
function Get-CollvariableCollectionInvoke {{
    param(
        [string]$CollectionName,
        [bool]$HasCollectionName,
        [bool]$HasCollectionId
    )
    $invoke = @{{ ErrorAction = 'Stop' }}
    if ($HasCollectionName) {{
        $invoke['CollectionName'] = $CollectionName
        return $invoke
    }}
    if ($HasCollectionId) {{
        $collection = Get-CMCollection -Name $CollectionName -ErrorAction Stop | Select-Object -First 1
        $invoke['CollectionId'] = $collection.CollectionID
        return $invoke
    }}
    throw "Collection parameter is missing on cmdlet."
}}
function Get-CollvariableNormalizedName {{
    param([string]$Name)
    $cleaned = [string]$Name
    $cleaned = $cleaned.Trim()
    $normalized = [regex]::Replace($cleaned, '[\\s_-]*\\d+$', '')
    if ([string]::IsNullOrWhiteSpace($normalized)) {{
        return $cleaned
    }}
    return $normalized
}}
$removeCmd = Get-Command Remove-CMDeviceCollectionVariable -ErrorAction Stop
$removeParams = $removeCmd.Parameters.Keys
$removeNameParam = if ($removeParams -contains 'VariableName') {{ 'VariableName' }} elseif ($removeParams -contains 'Name') {{ 'Name' }} else {{ throw "Remove-CMDeviceCollectionVariable missing variable name parameter." }}
$removeHasCollectionName = $removeParams -contains 'CollectionName'
$removeHasCollectionId = $removeParams -contains 'CollectionId'
$removeHasConfirm = $removeParams -contains 'Confirm'
$removeHasForce = $removeParams -contains 'Force'
$newCmdR = Get-Command New-CMDeviceCollectionVariable -ErrorAction Stop
$newParamsR = $newCmdR.Parameters.Keys
$newNameParam = if ($newParamsR -contains 'VariableName') {{ 'VariableName' }} elseif ($newParamsR -contains 'Name') {{ 'Name' }} else {{ throw "New-CMDeviceCollectionVariable missing variable name parameter." }}
$newValueParam = if ($newParamsR -contains 'Value') {{ 'Value' }} elseif ($newParamsR -contains 'VariableValue') {{ 'VariableValue' }} elseif ($newParamsR -contains 'NewVariableValue') {{ 'NewVariableValue' }} else {{ throw "New-CMDeviceCollectionVariable missing value parameter." }}
$newHasCollectionName = $newParamsR -contains 'CollectionName'
$newHasCollectionId = $newParamsR -contains 'CollectionId'
$allBaseNames = @($targetNames | ForEach-Object {{ Get-CollvariableNormalizedName -Name $_ }} | Select-Object -Unique)
foreach ($collectionName in $selectedCollections) {{
    foreach ($targetName in $targetNames) {{
        $invoke = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $hasCollectionName -HasCollectionId $hasCollectionId
        $invoke[$nameParam] = $targetName
        $invoke[$valueParam] = $newValue
        if ($hasConfirm) {{ $invoke['Confirm'] = $false }}
        if ($hasForce) {{ $invoke['Force'] = $true }}
        Set-CMDeviceCollectionVariable @invoke | Out-Null
    }}

    foreach ($baseName in $allBaseNames) {{
        $variables = @(
            Get-CMDeviceCollectionVariable -CollectionName $collectionName -ErrorAction SilentlyContinue
        )
        $numericRows = @()
        foreach ($row in $variables) {{
            $rowName = [string]$row.Name
            $normalized = Get-CollvariableNormalizedName -Name $rowName
            if ($normalized.ToLowerInvariant() -ne $baseName.ToLowerInvariant()) {{
                continue
            }}
            $match = [regex]::Match($rowName, '(\\d+)$')
            if (-not $match.Success) {{
                continue
            }}
            $numericRows += [pscustomobject]@{{
                Name = $rowName
                Value = [string]$row.Value
                Number = [int]$match.Groups[1].Value
                Width = [int]$match.Groups[1].Value.Length
            }}
        }}

        $orderedRows = @($numericRows | Sort-Object Number, Name)
        $expected = 1
        $renamePlan = @()
        foreach ($row in $orderedRows) {{
            $targetWidth = if ($row.Width -gt 2) {{ $row.Width }} else {{ 2 }}
            $newName = "{0}{1}" -f $baseName, $expected.ToString("D{0}" -f $targetWidth)
            if ($row.Name -ne $newName) {{
                $renamePlan += [pscustomobject]@{{
                    OldName = $row.Name
                    NewName = $newName
                    Value = $row.Value
                }}
            }}
            $expected += 1
        }}

        if ($renamePlan.Count -gt 0) {{
            $batchId = [guid]::NewGuid().ToString('N')
            $staged = @()
            $index = 0
            foreach ($plan in $renamePlan) {{
                $tmpName = "TmpCV" + $batchId.Substring(0,8) + $index.ToString()
                $removeOld = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
                $removeOld[$removeNameParam] = $plan.OldName
                if ($removeHasConfirm) {{ $removeOld['Confirm'] = $false }}
                if ($removeHasForce) {{ $removeOld['Force'] = $true }}
                Remove-CMDeviceCollectionVariable @removeOld | Out-Null

                $newTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $newHasCollectionName -HasCollectionId $newHasCollectionId
                $newTmp[$newNameParam] = $tmpName
                $newTmp[$newValueParam] = $plan.Value
                New-CMDeviceCollectionVariable @newTmp | Out-Null

                $staged += [pscustomobject]@{{
                    TempName = $tmpName
                    FinalName = $plan.NewName
                    Value = $plan.Value
                }}
                $index += 1
            }}
            foreach ($item in $staged) {{
                $removeTmp = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $removeHasCollectionName -HasCollectionId $removeHasCollectionId
                $removeTmp[$removeNameParam] = $item.TempName
                if ($removeHasConfirm) {{ $removeTmp['Confirm'] = $false }}
                if ($removeHasForce) {{ $removeTmp['Force'] = $true }}
                Remove-CMDeviceCollectionVariable @removeTmp | Out-Null

                $newFinal = Get-CollvariableCollectionInvoke -CollectionName $collectionName -HasCollectionName $newHasCollectionName -HasCollectionId $newHasCollectionId
                $newFinal[$newNameParam] = $item.FinalName
                $newFinal[$newValueParam] = $item.Value
                New-CMDeviceCollectionVariable @newFinal | Out-Null
            }}
        }}
    }}
}}
Write-Output "{success_token}"
"""
            )

            def _done(stdout: str, stderr: str) -> None:
                submit_button.configure(state="normal")
                if stderr:
                    details = stderr.strip()
                    if stdout:
                        details = f"{details}\n\n{stdout.strip()}"
                    messagebox.showerror("CollVariable", details or "PowerShell error.")
                    return
                if success_token not in stdout:
                    messagebox.showerror("CollVariable", stdout.strip() or "Replace operation failed.")
                    return
                messagebox.showinfo("CollVariable", "Variable value(s) replaced.")
                dialog.destroy()
                self.load_collvariable_collection_variables(self.collvariable_selected_collection_names)

            self._run_ps_async(script, _done)

        cancel_button = tk.Button(footer, text="Cancel", command=dialog.destroy, font=("Segoe UI", 9))
        cancel_button.pack(side="left")
        submit_button = tk.Button(
            footer,
            text="Submit",
            command=submit_replace,
            font=("Segoe UI", 10, "bold"),
            bg=t["accent_blue"],
            fg="#FFFFFF",
            activebackground=t["accent_blue"],
            activeforeground="#FFFFFF",
            relief="flat",
            padx=12,
            pady=6,
        )
        submit_button.pack(side="right")

        value_entry.focus_set()

    def _on_collvariable_group_selected(self, _event: tk.Event | None = None) -> None:
        selection = self.collvariable_tab2_tree.selection()
        if not selection:
            self._populate_collvariable_tab1()
            return
        values = self.collvariable_tab2_tree.item(selection[0], "values")
        if not values:
            self._populate_collvariable_tab1()
            return
        group_name = str(values[0]).strip()
        if not group_name or group_name.startswith("No "):
            self._populate_collvariable_tab1()
            return
        self._populate_collvariable_tab1(group_name)

    def load_collmember_collections(self) -> None:
        filter_text = self.collmember_filter_var.get().strip()
        if not filter_text:
            self._clear_collmember_output_tables()
            self.collmember_combo.configure(values=())
            self.collmember_combo.set("")
            messagebox.showwarning("CollMember", "Collection filter cannot be empty.")
            self.collmember_filter_entry.focus_set()
            return

        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        self._clear_collmember_output_tables()
        if not server or not site_code:
            self._set_collmember_output_error(
                "SCCM connection failed: incomplete profile. Open Settings to define server and site code."
            )
            return
        self.collmember_search_button.configure(state="disabled")
        self.collmember_combo.configure(state="disabled")
        self._set_widget_icon(self.collmember_search_button, "⏳", "", size=16, compound="center")

        script = f"""
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$SiteCode = "{site_code}"
$ProviderMachineName = "{server}"
if ((Get-Module ConfigurationManager) -eq $null) {{
    Import-Module "$($ENV:SMS_ADMIN_UI_PATH)\\..\\ConfigurationManager.psd1" -ErrorAction Stop
}}
$existingDrive = Get-PSDrive -Name $SiteCode -PSProvider CMSite -ErrorAction SilentlyContinue
if ($existingDrive -and $existingDrive.Root -and $existingDrive.Root.Trim().ToLowerInvariant() -ne $ProviderMachineName.Trim().ToLowerInvariant()) {{
    Remove-PSDrive -Name $SiteCode -PSProvider CMSite -Force -ErrorAction Stop
    $existingDrive = $null
}}
if ($existingDrive -eq $null) {{
    New-PSDrive -Name $SiteCode -PSProvider CMSite -Root $ProviderMachineName -ErrorAction Stop | Out-Null
}}
Set-Location "$($SiteCode):\\"
Get-CMCollection -ErrorAction Stop |
    Select-Object -ExpandProperty Name |
    Sort-Object -Unique |
    ConvertTo-Json -Compress
"""

        def _done(stdout: str, stderr: str) -> None:
            self.collmember_search_button.configure(state="normal")
            self.collmember_combo.configure(state="readonly")
            self._set_widget_icon(self.collmember_search_button, "🔍", "", size=16, compound="center")
            if stderr and not stdout:
                self._set_collmember_output_error(stderr.strip() or "PowerShell error.")
                return
            if not stdout:
                self.collmember_collections = []
                self.collmember_combo.configure(values=())
                self.collmember_combo.set("")
                self.collmember_types_tree.insert("", "end", values=("Info", "No collection"))
                self.collmember_queries_tree.insert("", "end", values=("Info", "No query"))
                self.collmember_machines_tree.insert("", "end", values=("No machine",))
                return
            try:
                data = json.loads(stdout)
            except json.JSONDecodeError:
                self._set_collmember_output_error("Unable to parse collection list.")
                return
            if isinstance(data, str):
                values = [data]
            elif isinstance(data, list):
                values = [str(item).strip() for item in data if str(item).strip()]
            else:
                values = []
            self.collmember_collections = sorted(set(values), key=str.lower)
            self._filter_collmember_collections()
            self.collmember_types_tree.insert("", "end", values=("Collections loaded", str(len(self.collmember_collections))))
            self.collmember_queries_tree.insert("", "end", values=("Info", "Select a collection to view details."))
            self.collmember_machine_filter_var.set("")
            self.collmember_machines_tree.insert("", "end", values=("Select a collection to view machines.",))

        self._run_ps_async(script, _done)

    def _filter_collmember_collections(self, _event: tk.Event | None = None) -> None:
        needle = self.collmember_filter_var.get().strip().lower()
        if not needle:
            self.collmember_combo.configure(values=())
            self.collmember_combo.set("")
            return
        filtered = [name for name in self.collmember_collections if needle in name.lower()]
        current = self.collmember_combo.get().strip()
        self.collmember_combo.configure(values=filtered)
        if current in filtered:
            self.collmember_combo.set(current)
        elif filtered:
            self.collmember_combo.set(filtered[0])
        else:
            self.collmember_combo.set("")

    def on_collmember_collection_selected(self, _event: tk.Event | None = None) -> None:
        collection_name = self.collmember_combo.get().strip()
        if not collection_name:
            return
        self.load_collmember_collection_details(collection_name)

    def load_collmember_collection_details(self, collection_name: str) -> None:
        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()
        self._clear_collmember_output_tables()
        self.collmember_selected_collection_name = collection_name
        self.collmember_selected_collection_id = ""
        self.collmember_selected_collection_type = "Inconnu"
        self.collmember_selected_collection_type_code = 0
        self._update_collmember_member_buttons()
        if not server or not site_code:
            self._set_collmember_output_error(
                "SCCM connection failed: incomplete profile. Open Settings to define server and site code."
            )
            return

        escaped_name = collection_name.replace("'", "''")
        self.collmember_search_button.configure(state="disabled")
        self.collmember_combo.configure(state="disabled")
        self._set_widget_icon(self.collmember_search_button, "⏳", "", size=16, compound="center")

        script = f"""
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$SiteCode = "{site_code}"
$ProviderMachineName = "{server}"
if ((Get-Module ConfigurationManager) -eq $null) {{
    Import-Module "$($ENV:SMS_ADMIN_UI_PATH)\\..\\ConfigurationManager.psd1" -ErrorAction Stop
}}
$existingDrive = Get-PSDrive -Name $SiteCode -PSProvider CMSite -ErrorAction SilentlyContinue
if ($existingDrive -and $existingDrive.Root -and $existingDrive.Root.Trim().ToLowerInvariant() -ne $ProviderMachineName.Trim().ToLowerInvariant()) {{
    Remove-PSDrive -Name $SiteCode -PSProvider CMSite -Force -ErrorAction Stop
    $existingDrive = $null
}}
if ($existingDrive -eq $null) {{
    New-PSDrive -Name $SiteCode -PSProvider CMSite -Root $ProviderMachineName -ErrorAction Stop | Out-Null
}}
Set-Location "$($SiteCode):\\"
$collection = Get-CMCollection -Name '{escaped_name}' -ErrorAction Stop | Select-Object -First 1
$collectionType = [int]$collection.CollectionType
$collectionTypeName = switch ($collectionType) {{
    1 {{ "User" }}
    2 {{ "Device" }}
    default {{ "Inconnu" }}
}}
$directRules = @(Get-CMCollectionDirectMembershipRule -CollectionId $collection.CollectionID -ErrorAction SilentlyContinue)
$includeRules = @(Get-CMCollectionIncludeMembershipRule -CollectionId $collection.CollectionID -ErrorAction SilentlyContinue)
$excludeRules = @(Get-CMCollectionExcludeMembershipRule -CollectionId $collection.CollectionID -ErrorAction SilentlyContinue)
$queryRules = @(Get-CMCollectionQueryMembershipRule -CollectionId $collection.CollectionID -ErrorAction SilentlyContinue)
$members = @(Get-CMCollectionMember -CollectionId $collection.CollectionID -ErrorAction SilentlyContinue)
$payload = [ordered]@{{
    CollectionId = $collection.CollectionID
    CollectionType = $collectionType
    CollectionTypeName = $collectionTypeName
    Types = [ordered]@{{
        "Direct membership" = ($directRules.Count -gt 0)
        "Include" = ($includeRules.Count -gt 0)
        "Exclude" = ($excludeRules.Count -gt 0)
        "Query" = ($queryRules.Count -gt 0)
    }}
    Queries = @($queryRules | ForEach-Object {{
        [ordered]@{{
            RuleName = $_.RuleName
            Query = $_.QueryExpression
        }}
    }})
    Machines = @($members | Where-Object {{ $_.Name }} | ForEach-Object {{ $_.Name }} | Sort-Object -Unique)
}}
$payload | ConvertTo-Json -Compress -Depth 8
"""

        def _done(stdout: str, stderr: str) -> None:
            self.collmember_search_button.configure(state="normal")
            self.collmember_combo.configure(state="readonly")
            self._set_widget_icon(self.collmember_search_button, "🔍", "", size=16, compound="center")

            if stderr and not stdout:
                self._set_collmember_output_error(stderr.strip() or "PowerShell error.")
                return
            if not stdout:
                self._set_collmember_output_error("No data received for this collection.")
                return

            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                self._set_collmember_output_error("Unable to parse collection details.")
                return

            types = payload.get("Types", {}) if isinstance(payload, dict) else {}
            queries = payload.get("Queries", []) if isinstance(payload, dict) else []
            machines = payload.get("Machines", []) if isinstance(payload, dict) else []
            collection_id_text = str(payload.get("CollectionId", "")).strip() if isinstance(payload, dict) else ""
            collection_type_value = payload.get("CollectionType") if isinstance(payload, dict) else None
            collection_type_text = str(payload.get("CollectionTypeName", "")).strip() if isinstance(payload, dict) else ""
            if collection_type_text:
                pass
            elif str(collection_type_value) == "2":
                collection_type_text = "Device"
            elif str(collection_type_value) == "1":
                collection_type_text = "User"
            else:
                collection_type_text = "Inconnu"
            self.collmember_selected_collection_id = collection_id_text
            self.collmember_selected_collection_type = collection_type_text
            try:
                self.collmember_selected_collection_type_code = int(collection_type_value)
            except (TypeError, ValueError):
                self.collmember_selected_collection_type_code = 0
            self._update_collmember_member_buttons()

            type_rows = [
                ["Collection Type", collection_type_text],
                ["Direct membership", "Oui" if types.get("Direct membership") else "Non"],
                ["Include", "Oui" if types.get("Include") else "Non"],
                ["Exclude", "Oui" if types.get("Exclude") else "Non"],
                ["Query", "Oui" if types.get("Query") else "Non"],
            ]
            query_rows = []
            if isinstance(queries, list):
                for item in queries:
                    if not isinstance(item, dict):
                        continue
                    query_rows.append([
                        str(item.get("RuleName", "")).strip() or "-",
                        str(item.get("Query", "")).strip() or "-",
                    ])
            if not query_rows:
                query_rows = [["-", "No query"]]

            machine_rows = []
            if isinstance(machines, str):
                machine_name = machines.strip()
                if machine_name:
                    machine_rows.append(machine_name)
            elif isinstance(machines, list):
                for item in machines:
                    machine_name = str(item).strip()
                    if machine_name:
                        machine_rows.append(machine_name)
            machine_rows = sorted(set(machine_rows), key=str.lower)

            for row in type_rows:
                self.collmember_types_tree.insert("", "end", values=(row[0], row[1]))
            for row in query_rows:
                self.collmember_queries_tree.insert("", "end", values=(row[0], row[1]))
            self.collmember_machine_names = machine_rows
            self._filter_collmember_machines()

        self._run_ps_async(script, _done)

    def run_last10_dplm(self) -> None:
        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        site_code = profile.get("site_code", "").strip()

        for row in self.dplm_tree.get_children():
            self.dplm_tree.delete(row)
        if not server or not site_code:
            self.dplm_tree.insert("", "end", values=("Profil incomplet (server/site_code).", "", "", "", "", "", ""))
            return
        self.dplm_tree.insert("", "end", values=("Loading...", "", "", "", "", ""))
        self.dplm_refresh_button.configure(state="disabled")
        self._set_widget_icon(self.dplm_refresh_button, "⏳", "…", size=16)

        script = f"""
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$SiteCode = "{site_code}"
$ProviderMachineName = "{server}"
if ((Get-Module ConfigurationManager) -eq $null) {{
    Import-Module "$($ENV:SMS_ADMIN_UI_PATH)\\..\\ConfigurationManager.psd1" -ErrorAction Stop
}}
$existingDrive = Get-PSDrive -Name $SiteCode -PSProvider CMSite -ErrorAction SilentlyContinue
if ($existingDrive -and $existingDrive.Root -and $existingDrive.Root.Trim().ToLowerInvariant() -ne $ProviderMachineName.Trim().ToLowerInvariant()) {{
    Remove-PSDrive -Name $SiteCode -PSProvider CMSite -Force -ErrorAction Stop
    $existingDrive = $null
}}
if ($existingDrive -eq $null) {{
    New-PSDrive -Name $SiteCode -PSProvider CMSite -Root $ProviderMachineName -ErrorAction Stop | Out-Null
}}
Set-Location "$($SiteCode):\\"

$deps = Get-CMDeployment -ErrorAction Stop |
    Sort-Object DeploymentTime -Descending |
    Select-Object -First 10 |
    Select-Object `
        @{{N="Name";       E={{ if ($_.ApplicationName) {{ $_.ApplicationName }} elseif ($_.PackageName) {{ $_.PackageName }} else {{ $_.AssignmentName }} }}}},
        @{{N="Collection"; E={{ $_.CollectionName }}}},
        @{{N="Start";      E={{ if ($_.DeploymentTime) {{ $_.DeploymentTime.ToString("yyyy-MM-dd HH:mm") }} else {{ "-" }} }}}},
        @{{N="Targeted";   E={{ $_.NumberTargeted }}}},
        @{{N="InProgress"; E={{ $_.NumberInProgress }}}},
        @{{N="Success";    E={{ $_.NumberSuccess }}}},
        @{{N="Errors";     E={{ $_.NumberErrors }}}}

$deps | ConvertTo-Json -Compress
"""
        self._run_ps_async(script, self._dplm_populate)

    def _dplm_populate(self, stdout: str, stderr: str) -> None:
        if self.is_closing:
            return
        self.dplm_refresh_button.configure(state="normal")
        self._set_widget_icon(self.dplm_refresh_button, "🔄", "Refresh", size=16)
        for row in self.dplm_tree.get_children():
            self.dplm_tree.delete(row)

        if stderr and not stdout:
            self.dplm_tree.insert("", "end", values=("PowerShell error — see Tool Output", "", "", "", "", "", ""))
            self.append_output(self.output_text, stderr, tag="error")
            return

        if not stdout:
            self.dplm_tree.insert("", "end", values=("No deployment found.", "", "", "", "", "", ""))
            return

        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                data = [data]
        except json.JSONDecodeError:
            self.dplm_tree.insert("", "end", values=("Unable to parse response.", "", "", "", "", "", ""))
            self.append_output(self.output_text, stdout, tag="error")
            return

        for item in data:
            self.dplm_tree.insert("", "end", values=(
                item.get("Name", ""),
                item.get("Collection", ""),
                item.get("Start", ""),
                item.get("Targeted", ""),
                item.get("InProgress", ""),
                item.get("Success", ""),
                item.get("Errors", ""),
            ))

    def refresh_ps1_list(self) -> None:
        for item in self.ps1_tree.get_children():
            self.ps1_tree.delete(item)
        self.ps1_script_map = {}

        root = self.ps1_search_root
        self.ps1_recursive_search = True
        self.ps1_folder_label.configure(text=f"Search: {root} | Recursive: ON")

        if not root.exists() or not root.is_dir():
            self.ps1_tree.insert("", "end", text="Folder not found")
            return

        scripts = sorted(root.rglob("*.ps1"))
        dir_nodes = {}

        for script in scripts:
            rel_path = script.relative_to(root)
            parent = ""
            for folder_name in rel_path.parts[:-1]:
                dir_key = f"{parent}/{folder_name}"
                if dir_key not in dir_nodes:
                    dir_nodes[dir_key] = self.ps1_tree.insert(parent, "end", text=folder_name, open=False)
                parent = dir_nodes[dir_key]
            item_id = self.ps1_tree.insert(parent, "end", text=f"📜 {rel_path.name}")
            self.ps1_script_map[item_id] = script

        if not scripts:
            self.ps1_tree.insert("", "end", text="No .ps1 script found")

    def browse_ps1_folder(self) -> None:
        chosen = filedialog.askdirectory(
            title="Select PowerShell scripts folder",
            initialdir=str(self.ps1_search_root),
        )
        if not chosen:
            return
        self.ps1_search_root = Path(chosen)
        self.save_settings()
        self.refresh_ps1_list()

    def clear_saved_ps1_folder(self) -> None:
        self.ps1_search_root = self.ps1_dir
        self.save_settings()
        self.refresh_ps1_list()

    def clear_ps1_output(self) -> None:
        self.ps1_output.delete("1.0", "end")

    def run_selected_ps1(self) -> None:
        self.ps1_output.delete("1.0", "end")
        script_path = self._get_selected_ps1()
        if script_path is None:
            return

        profile = self.get_active_profile()
        command = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(script_path),
            "-SccmServer", profile.get("server", ""),
            "-SiteCode", profile.get("site_code", ""),
        ]

        def _worker() -> None:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if not self.is_closing:
                self.after(0, lambda: _done(result))

        def _done(result) -> None:
            if result.stdout:
                self.append_output(self.ps1_output, result.stdout)
            if result.stderr:
                self.append_output(self.ps1_output, result.stderr, tag="error")
            if result.returncode != 0 and not result.stderr:
                self.append_output(self.ps1_output, f"Script failed (code {result.returncode}).", tag="error")
            if not result.stdout and not result.stderr:
                self.append_output(self.ps1_output, "No script output.")

        threading.Thread(target=_worker, daemon=True).start()

    def open_selected_ps1_in_ise(self) -> None:
        self.ps1_output.delete("1.0", "end")
        script_path = self._get_selected_ps1()
        if script_path is None:
            return
        try:
            subprocess.Popen(["powershell_ise.exe", str(script_path)])
            self.append_output(self.ps1_output, f"Opening in PowerShell ISE: {script_path}")
        except FileNotFoundError:
            self.append_output(self.ps1_output, "PowerShell ISE not found on this machine.", tag="error")
        except Exception as err:
            self.append_output(self.ps1_output, f"Unable to open PowerShell ISE: {err}", tag="error")

    def open_selected_ps1_preview(self) -> None:
        self.ps1_output.delete("1.0", "end")
        script_path = self._get_selected_ps1()
        if script_path is None:
            return

        try:
            content = script_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = script_path.read_text(encoding="cp1252")
            except OSError as err:
                self.append_output(self.ps1_output, f"Unable to read script: {err}", tag="error")
                return
        except OSError as err:
            self.append_output(self.ps1_output, f"Unable to read script: {err}", tag="error")
            return

        preview = tk.Toplevel(self)
        preview.title(f"Preview - {script_path.name}")
        preview.geometry("980x700")
        preview.minsize(700, 500)
        preview.configure(bg=self.theme["surface"])

        container = tk.Frame(preview, bg=self.theme["surface"], padx=12, pady=12)
        container.pack(fill="both", expand=True)

        header = tk.Label(
            container,
            text=f"Preview: {script_path}",
            font=("Segoe UI", 10, "bold"),
            anchor="w",
            bg=self.theme["surface"],
            fg=self.theme["text"],
        )
        header.pack(fill="x", pady=(0, 8))

        text_container = tk.Frame(container, bg=self.theme["surface"])
        text_container.pack(fill="both", expand=True)

        preview_text = tk.Text(
            text_container,
            wrap="none",
            font=("Consolas", 11),
            relief="flat",
            bg=self.theme["output_bg"],
            fg=self.theme["text"],
            insertbackground=self.theme["text"],
        )
        y_scroll = ttk.Scrollbar(text_container, orient="vertical", command=preview_text.yview)
        x_scroll = ttk.Scrollbar(text_container, orient="horizontal", command=preview_text.xview)
        preview_text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        preview_text.pack(side="left", fill="both", expand=True)
        y_scroll.pack(side="right", fill="y")
        x_scroll.pack(side="bottom", fill="x")

        preview_text.insert("1.0", content)
        self._apply_powershell_syntax_highlighting(preview_text, content)
        self._make_text_output_readonly(preview_text)
        self.append_output(self.ps1_output, f"Preview opened: {script_path.name}")

    def ping_sccm_server(self) -> None:
        self.infra_output.delete("1.0", "end")
        profile = self.get_active_profile()
        server = profile.get("server", "").strip()
        if not server:
            self.append_output(self.infra_output, "SCCM server not set.")
            return
        script = f"Test-Connection -ComputerName '{server}' -Count 2"

        def _done(stdout: str, stderr: str) -> None:
            if stdout:
                self.append_output(self.infra_output, stdout)
            if stderr:
                self.append_output(self.infra_output, stderr)

        self._run_ps_async(script, _done)

    def select_infra_tool(self, key: str) -> None:
        self.infra_selected_tool_key = key
        _, _, label = self.infra_tools_map[key]
        self.infra_tool_title.configure(text=label)
        self.infra_output.delete("1.0", "end")
        self.apply_infra_menu_theme()

    def launch_infra_tool(self) -> None:
        key = self.infra_selected_tool_key
        self.infra_output.delete("1.0", "end")
        if key is None:
            self.append_output(self.infra_output, "Select a tool from the menu.")
            return
        path, tool_type, label = self.infra_tools_map[key]
        if tool_type == "builtin":
            self.ping_sccm_server()
            return
        if path is None or not path.exists():
            self.append_output(self.infra_output, f"File not found: {path}")
            return
        try:
            if tool_type == "exe":
                subprocess.Popen([str(path)], cwd=str(path.parent))
                self.append_output(self.infra_output, f"Launched: {path.name}")
            elif tool_type == "vbs":
                subprocess.Popen(["cscript.exe", str(path)])
                self.append_output(self.infra_output, f"Launched (VBS): {path.name}")
            elif tool_type == "msi":
                subprocess.Popen(["msiexec.exe", "/i", str(path)])
                self.append_output(self.infra_output, f"Installation started: {path.name}")
        except Exception as err:
            self.append_output(self.infra_output, f"Error: {err}")

    def apply_infra_menu_theme(self) -> None:
        if not self.infra_menu_buttons:
            return
        t = self.theme
        self.infra_left_panel.configure(bg=t["surface"])
        self.infra_menu_canvas.configure(bg=t["surface"], highlightbackground=t["border"], highlightcolor=t["border"])
        self.infra_menu_frame.configure(bg=t["surface"])
        self.infra_launch_button.configure(
            bg=t["accent_blue"],
            fg="#FFFFFF",
            activebackground=t["accent_blue"],
            activeforeground="#FFFFFF",
            relief="flat",
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            font=("Segoe UI", 11, "bold"),
            pady=8,
        )
        for key, btn in self.infra_menu_buttons:
            active = key == self.infra_selected_tool_key
            btn.configure(
                bg=t["sidebar_active"] if active else t["surface"],
                fg="#FFFFFF" if active else t["text"],
                activebackground=t["surface_3"],
                activeforeground=t["text"],
                cursor="hand2",
            )

    def open_cmtrace(self) -> None:
        self.cmtrace_output.delete("1.0", "end")
        if not self._is_cmtrace_reachable():
            started = self.start_cmtrace_dev(clear_output=False)
            if not started:
                return
        url = f"http://{self.cmtrace_listen}/"
        webbrowser.open(url)
        self.append_output(self.cmtrace_output, f"Ouverture navigateur: {url}")

    def open_cmtrace_in_app(self) -> None:
        self.load_cmtrace_local_in_app()

    def start_cmtrace_dev(self, clear_output: bool = True) -> bool:
        if clear_output:
            self.cmtrace_output.delete("1.0", "end")

        if not self.cmtrace_dev_dir.exists():
            self.append_output(self.cmtrace_output, f"Folder not found: {self.cmtrace_dev_dir}")
            return False

        docker_compose_cmd = self._find_docker_compose_executable()
        if docker_compose_cmd is None:
            self.append_output(self.cmtrace_output, "Docker not found, trying local Python server fallback...")
            return self._start_cmtrace_fallback_server()

        if not self._ensure_cmtrace_env():
            return False

        self.append_output(self.cmtrace_output, "Starting CMTraceDev via Docker Compose...")
        result = subprocess.run(
            docker_compose_cmd + ["up", "-d"],
            cwd=str(self.cmtrace_dev_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            self.append_output(self.cmtrace_output, result.stdout.strip())
        if result.stderr.strip():
            self.append_output(self.cmtrace_output, result.stderr.strip())
        if result.returncode != 0:
            self.append_output(self.cmtrace_output, "Docker Compose failed, trying local Python server fallback...")
            return self._start_cmtrace_fallback_server()

        for _ in range(30):
            if self._is_cmtrace_reachable():
                self.cmtrace_start_mode = "docker"
                self.append_output(self.cmtrace_output, f"CMTraceDev started: http://{self.cmtrace_listen}/")
                return True
            time.sleep(0.2)

        self.append_output(self.cmtrace_output, "CMTraceDev started but URL is not reachable immediately.")
        return True

    def stop_cmtrace_dev(self) -> None:
        self.cmtrace_output.delete("1.0", "end")
        if not self.cmtrace_dev_dir.exists():
            self.append_output(self.cmtrace_output, f"Folder not found: {self.cmtrace_dev_dir}")
            return
        fallback_stopped = self._stop_cmtrace_fallback_server(log_to_output=False)
        if fallback_stopped:
            self.append_output(self.cmtrace_output, "CMTraceDev fallback (Python) stopped.")

        docker_compose_cmd = self._find_docker_compose_executable()
        if docker_compose_cmd is None:
            if not fallback_stopped:
                self.append_output(self.cmtrace_output, "Docker / Docker Compose not found.")
            return

        self.append_output(self.cmtrace_output, "Stopping CMTraceDev via Docker Compose...")
        result = subprocess.run(
            docker_compose_cmd + ["down"],
            cwd=str(self.cmtrace_dev_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.stdout.strip():
            self.append_output(self.cmtrace_output, result.stdout.strip())
        if result.stderr.strip():
            self.append_output(self.cmtrace_output, result.stderr.strip())
        if result.returncode == 0:
            self.append_output(self.cmtrace_output, "CMTraceDev stopped.")
        else:
            self.append_output(self.cmtrace_output, "Failed to stop CMTraceDev.")

    def _start_cmtrace_fallback_server(self) -> bool:
        if self._is_cmtrace_reachable():
            self.cmtrace_start_mode = "fallback"
            self.append_output(self.cmtrace_output, f"CMTraceDev already active on http://{self.cmtrace_listen}/")
            return True

        host, port_text = self.cmtrace_listen.split(":")
        port = int(port_text)
        source_dir = self.cmtrace_dev_dir / "src"
        if not source_dir.exists():
            self.append_output(self.cmtrace_output, f"Source folder not found: {source_dir}")
            return False

        command = [
            sys.executable,
            "-m",
            "http.server",
            str(port),
            "--bind",
            host,
            "--directory",
            str(source_dir),
        ]
        try:
            self.cmtrace_fallback_process = subprocess.Popen(
                command,
                cwd=str(self.cmtrace_dev_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as err:
            self.append_output(self.cmtrace_output, f"Unable to start Python fallback: {err}")
            return False

        for _ in range(20):
            if self._is_cmtrace_reachable():
                self.cmtrace_start_mode = "fallback"
                self.append_output(self.cmtrace_output, f"CMTraceDev fallback started: http://{self.cmtrace_listen}/")
                return True
            time.sleep(0.15)

        self.append_output(self.cmtrace_output, "Python fallback started but URL is not reachable.")
        return False

    def _stop_cmtrace_fallback_server(self, log_to_output: bool = True) -> bool:
        if self.cmtrace_fallback_process is None or self.cmtrace_fallback_process.poll() is not None:
            return False
        self.cmtrace_fallback_process.terminate()
        self.cmtrace_fallback_process = None
        if log_to_output:
            self.append_output(self.cmtrace_output, "Python fallback stopped.")
        return True

    def _is_cmtrace_reachable(self) -> bool:
        host, port_text = self.cmtrace_listen.split(":")
        port = int(port_text)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            return sock.connect_ex((host, port)) == 0

    def _find_docker_compose_executable(self) -> list[str] | None:
        def command_ok(cmd: list[str]) -> bool:
            try:
                result = subprocess.run(cmd + ["version"], capture_output=True, text=True, check=False)
                return result.returncode == 0
            except OSError:
                return False

        if command_ok(["docker", "compose"]):
            return ["docker", "compose"]
        if command_ok(["docker-compose"]):
            return ["docker-compose"]

        for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"), os.environ.get("LocalAppData")):
            if not base:
                continue
            docker_exe = Path(base) / "Docker" / "Docker" / "resources" / "bin" / "docker.exe"
            compose_exe = Path(base) / "Docker" / "Docker" / "resources" / "bin" / "docker-compose.exe"
            if docker_exe.exists() and command_ok([str(docker_exe), "compose"]):
                return [str(docker_exe), "compose"]
            if compose_exe.exists() and command_ok([str(compose_exe)]):
                return [str(compose_exe)]
        return None

    def _ensure_cmtrace_env(self) -> bool:
        env_path = self.cmtrace_dev_dir / ".env"
        env_example = self.cmtrace_dev_dir / ".env.example"
        if env_path.exists():
            return True
        if not env_example.exists():
            self.append_output(self.cmtrace_output, ".env.example file not found in CMTraceDev.")
            return False
        try:
            shutil.copyfile(env_example, env_path)
            self.append_output(self.cmtrace_output, ".env file created from .env.example.")
            return True
        except OSError as err:
            self.append_output(self.cmtrace_output, f"Unable to create .env: {err}")
            return False

    def open_settings(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Settings SCCM")
        dialog_width = 460
        dialog_height = 320
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        pos_x = max((screen_width - dialog_width) // 2, 0)
        pos_y = max((screen_height - dialog_height) // 2, 0)
        dialog.geometry(f"{dialog_width}x{dialog_height}+{pos_x}+{pos_y}")
        dialog.transient(self)
        dialog.grab_set()
        t = self.theme
        dialog.configure(bg=t["surface"])

        tk.Label(dialog, text="Profile", bg=t["surface"], fg=t["text"], font=("Segoe UI", 12, "bold")).pack(
            anchor="w", padx=18, pady=(16, 4)
        )

        profile_names = [profile["name"] for profile in self.profiles_data["profiles"]]
        selected_profile_var = tk.StringVar(value=self.active_profile_name)
        profile_box = ttk.Combobox(dialog, textvariable=selected_profile_var, values=profile_names, state="readonly")
        profile_box.pack(fill="x", padx=18, pady=(0, 8))

        name_var = tk.StringVar(value=self.active_profile.get("name", ""))
        server_var = tk.StringVar(value=self.active_profile.get("server", ""))
        site_var = tk.StringVar(value=self.active_profile.get("site_code", ""))

        # Track which profile was originally selected so a rename replaces it correctly.
        original_name = selected_profile_var.get()

        def load_profile() -> None:
            nonlocal original_name
            selected = selected_profile_var.get()
            profile = next((item for item in self.profiles_data["profiles"] if item["name"] == selected), None)
            if profile is None:
                messagebox.showerror("Error", "Profile not found.")
                return
            original_name = selected
            name_var.set(profile.get("name", ""))
            server_var.set(profile.get("server", ""))
            site_var.set(profile.get("site_code", ""))
            self.active_profile_name = selected
            self.active_profile = profile
            self.update_profile_labels()

        profile_box.bind("<<ComboboxSelected>>", lambda _event: load_profile())

        def save_profile() -> None:
            name = name_var.get().strip()
            server = server_var.get().strip()
            site_code = site_var.get().strip()
            if not name:
                messagebox.showerror("Error", "Profile name is required.")
                return
            if not server:
                messagebox.showerror("Error", "SCCM server is required.")
                return
            if not site_code:
                messagebox.showerror("Error", "Site code is required.")
                return

            new_profile = {"name": name, "server": server, "site_code": site_code}
            # Replace the original entry (handles renames without duplicating).
            original_index = next(
                (i for i, p in enumerate(self.profiles_data["profiles"]) if p["name"] == original_name), None
            )
            if original_index is not None:
                self.profiles_data["profiles"][original_index] = new_profile
            else:
                self.profiles_data["profiles"].append(new_profile)

            self.active_profile_name = name
            self.active_profile = new_profile
            self.profiles_data["active_profile"] = name
            self.save_profiles()
            self.save_settings()
            self.update_profile_labels()
            messagebox.showinfo("Success", "Profile saved.")
            dialog.destroy()

        form = tk.Frame(dialog, bg=t["surface"])
        form.pack(fill="both", expand=True, padx=18, pady=4)
        form.columnconfigure(0, weight=1)

        tk.Label(form, text="Profile name", bg=t["surface"], fg=t["muted_text"]).grid(row=0, column=0, sticky="w")
        tk.Entry(form, textvariable=name_var).grid(row=1, column=0, sticky="ew", pady=(2, 8))

        tk.Label(form, text="SCCM server", bg=t["surface"], fg=t["muted_text"]).grid(row=2, column=0, sticky="w")
        tk.Entry(form, textvariable=server_var).grid(row=3, column=0, sticky="ew", pady=(2, 8))

        tk.Label(form, text="Site code", bg=t["surface"], fg=t["muted_text"]).grid(row=4, column=0, sticky="w")
        tk.Entry(form, textvariable=site_var).grid(row=5, column=0, sticky="ew", pady=(2, 8))

        footer = tk.Frame(dialog, bg=t["surface"])
        footer.pack(fill="x", padx=18, pady=(0, 18))
        tk.Button(footer, text="Load", width=12, command=load_profile).pack(side="left")
        tk.Button(footer, text="Save", width=12, command=save_profile).pack(side="right")

    def on_app_close(self) -> None:
        self.is_closing = True
        self._stop_cmtrace_fallback_server(log_to_output=False)
        if self.cmtrace_webview_handle and windll.user32.IsWindow(self.cmtrace_webview_handle):
            windll.user32.PostMessageW(self.cmtrace_webview_handle, 0x0010, 0, 0)
        self.destroy()

    def run(self) -> None:
        self.mainloop()


if __name__ == "__main__":
    app = SCCMToolboxApp()
    app.run()
