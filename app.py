import os
import json
import tkinter as tk
from tkinter import ttk, messagebox
import customtkinter as ctk
from PIL import Image
from engine import ReplayEngine, PLAY_FPS
import queue
import threading
import time

try:
    import keyboard
    HAS_GLOBAL_KEYS = True
except ImportError:
    HAS_GLOBAL_KEYS = False

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

FRAME = 1.0 / PLAY_FPS
SPEEDS = {"100%": 1.0, "75%": 0.75, "50%": 0.5, "25%": 0.25, "10%": 0.10}

DEFAULT_HOTKEYS = {
    "mark_1": "F1", "mark_5": "F5", "mark_7": "F6", "mark_10": "F7", "mark_15": "F8",
    "play_pause": "space", "prep_clip": "Return", "delete_clip": "Delete",
    "set_in": "i", "set_out": "o", "nudge_in_back": "q", "nudge_in_fwd": "w",
    "speed_100": "z", "speed_75": "x", "speed_50": "c", "speed_25": "v"
}

class VMixClipEditor(ctk.CTkToplevel):
    """vMix-style Playlist Storyboard & Transition Sequence Editor."""
    def __init__(self, parent, deck_ref):
        super().__init__(parent)
        self.deck = deck_ref
        self.engine = deck_ref.engine
        self.title("VALO-REPLAY // vMix Storyboard & Transition Editor")
        self.geometry("900x600")
        self.minsize(800, 500)
        self.attributes("-topmost", True)

        self.sequence_items = []
        self._load_from_selection()
        self._build_ui()
        self._refresh_list()

    def _load_from_selection(self):
        sel_evs = self.deck._selected_events()
        if not sel_evs:
            sel_evs = self.deck.cur_events
        for ev in sel_evs:
            ang = ev.get("angle")
            if not ang or ang not in ev["masters"]:
                ang = next(iter(ev["masters"]))
            self.sequence_items.append({
                "ev": ev,
                "label": ev["label"],
                "angle": ang,
                "in": ev["in"],
                "out": ev["out"],
                "dur": ev["out"] - ev["in"],
                "speed": ev.get("speed", 1.0),
                "trans": "DISSOLVE",
                "trans_dur": 0.5
            })

    def _build_ui(self):
        top_bar = ctk.CTkFrame(self, fg_color="#121217", height=40)
        top_bar.pack(fill="x", padx=10, pady=(10, 5))
        ctk.CTkLabel(top_bar, text="vMix STORYBOARD REPLAY SEQUENCE", font=("Arial", 13, "bold"), text_color="#2A9D8F").pack(side="left", padx=10)
        
        main_box = ctk.CTkFrame(self, fg_color="transparent")
        main_box.pack(fill="both", expand=True, padx=10, pady=5)

        cols = ("idx", "label", "angle", "in", "out", "dur", "speed", "trans", "tdur")
        self.tree = ttk.Treeview(main_box, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("idx", text="#")
        self.tree.heading("label", text="CLIP LABEL")
        self.tree.heading("angle", text="CAM")
        self.tree.heading("in", text="IN")
        self.tree.heading("out", text="OUT")
        self.tree.heading("dur", text="DUR")
        self.tree.heading("speed", text="SPD")
        self.tree.heading("trans", text="TRANSITION")
        self.tree.heading("tdur", text="T-DUR")

        self.tree.column("idx", width=35, anchor="center")
        self.tree.column("label", width=180, anchor="w")
        self.tree.column("angle", width=70, anchor="center")
        self.tree.column("in", width=60, anchor="center")
        self.tree.column("out", width=60, anchor="center")
        self.tree.column("dur", width=60, anchor="center")
        self.tree.column("speed", width=50, anchor="center")
        self.tree.column("trans", width=90, anchor="center")
        self.tree.column("tdur", width=50, anchor="center")

        self.tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(main_box, orient="vertical", command=self.tree.yview)
        sb.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # Editor Sidebar Controls
        side = ctk.CTkFrame(self, fg_color="#181824", width=220)
        side.pack(fill="x", padx=10, pady=5)

        r1 = ctk.CTkFrame(side, fg_color="transparent")
        r1.pack(fill="x", padx=10, pady=5)
        ctk.CTkButton(r1, text="⬆ Move Up", width=90, command=self._move_up).pack(side="left", padx=4)
        ctk.CTkButton(r1, text="⬇ Move Down", width=90, command=self._move_down).pack(side="left", padx=4)
        ctk.CTkButton(r1, text="✕ Remove", width=90, fg_color="#7A1F2B", command=self._remove_item).pack(side="left", padx=4)

        r2 = ctk.CTkFrame(side, fg_color="transparent")
        r2.pack(fill="x", padx=10, pady=5)
        ctk.CTkLabel(r2, text="Transition:", font=("Arial", 11, "bold")).pack(side="left", padx=(4, 6))
        self.trans_opt = ctk.CTkOptionMenu(r2, values=["DISSOLVE", "CUT"], width=110, command=self._update_current)
        self.trans_opt.set("DISSOLVE")
        self.trans_opt.pack(side="left", padx=4)

        ctk.CTkLabel(r2, text="Trans Sec:", font=("Arial", 11, "bold")).pack(side="left", padx=(10, 6))
        self.tdur_opt = ctk.CTkOptionMenu(r2, values=["0.25", "0.50", "0.75", "1.00"], width=80, command=self._update_current)
        self.tdur_opt.set("0.50")
        self.tdur_opt.pack(side="left", padx=4)

        ctk.CTkLabel(r2, text="Segment Speed:", font=("Arial", 11, "bold")).pack(side="left", padx=(10, 6))
        self.spd_opt = ctk.CTkOptionMenu(r2, values=["100%", "75%", "50%", "25%"], width=80, command=self._update_current)
        self.spd_opt.set("100%")
        self.spd_opt.pack(side="left", padx=4)

        bot = ctk.CTkFrame(self, fg_color="#121217", height=50)
        bot.pack(fill="x", padx=10, pady=(5, 10))
        self.total_lbl = ctk.CTkLabel(bot, text="TOTAL DURATION: 0.0s", font=("Consolas", 12, "bold"), text_color="#A0A0AB")
        self.total_lbl.pack(side="left", padx=15)

        ctk.CTkButton(bot, text="Render & Prep to OBS 📤", fg_color="#457B9D", font=("Arial", 12, "bold"), command=self._render_sequence).pack(side="right", padx=10, pady=8)

    def _refresh_list(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        tot = 0.0
        for i, it in enumerate(self.sequence_items):
            dur = (it["out"] - it["in"]) / it["speed"]
            tot += dur
            spd_txt = f"{int(round(it['speed'] * 100))}%"
            self.tree.insert("", "end", iid=str(i), values=(
                i + 1, it["label"], it["angle"], f"{it['in']:.2f}", f"{it['out']:.2f}",
                f"{dur:.2f}s", spd_txt, it["trans"], f"{it['trans_dur']}s"
            ))
        self.total_lbl.configure(text=f"TOTAL DURATION: {tot:.2f}s | {len(self.sequence_items)} CLIPS")

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        it = self.sequence_items[idx]
        self.trans_opt.set(it["trans"])
        self.tdur_opt.set(f"{it['trans_dur']:.2f}")
        self.spd_opt.set(f"{int(round(it['speed'] * 100))}%")
        self.deck.select_event(it["ev"])

    def _update_current(self, *args):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        it = self.sequence_items[idx]
        it["trans"] = self.trans_opt.get()
        it["trans_dur"] = float(self.tdur_opt.get())
        it["speed"] = SPEEDS[self.spd_opt.get()]
        self._refresh_list()
        self.tree.selection_set(str(idx))

    def _move_up(self):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        if idx > 0:
            self.sequence_items[idx], self.sequence_items[idx-1] = self.sequence_items[idx-1], self.sequence_items[idx]
            self._refresh_list()
            self.tree.selection_set(str(idx-1))

    def _move_down(self):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        if idx < len(self.sequence_items) - 1:
            self.sequence_items[idx], self.sequence_items[idx+1] = self.sequence_items[idx+1], self.sequence_items[idx]
            self._refresh_list()
            self.tree.selection_set(str(idx+1))

    def _remove_item(self):
        sel = self.tree.selection()
        if not sel: return
        idx = int(sel[0])
        self.sequence_items.pop(idx)
        self._refresh_list()

    def _render_sequence(self):
        if not self.sequence_items: return
        items = []
        tot = 0.0
        for it in self.sequence_items:
            ev = it["ev"]
            ang = it["angle"]
            path, start, end = self.engine.angle_range(ev, ang)
            items.append({
                "path": path, "start": it["in"], "end": it["out"], "speed": it["speed"]
            })
            tot += (it["out"] - it["in"]) / it["speed"]

        self.deck.last_prep_duration = tot
        trans_type = self.sequence_items[0]["trans"]
        trans_dur = self.sequence_items[0]["trans_dur"]

        def work():
            out = self.engine.render_playlist(items, transition=trans_type, trans_dur=trans_dur)
            self.deck.ui(self.deck._check_render_success, out)
            self.deck.ui(lambda: messagebox.showinfo("Render Finished", "Sequence prepped and ready to play in OBS!"))
        
        threading.Thread(target=work, daemon=True).start()
        self.destroy()

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, engine, app_ref):
        super().__init__(parent)
        self.title("VALO-REPLAY // System Configuration")
        self.geometry("820x780")
        self.minsize(750, 680)
        self.engine = engine
        self.app_ref = app_ref
        self.grab_set()

        ctk.CTkLabel(self, text="CONFIGURATION & SYSTEM CONTROL", font=("Arial", 14, "bold")).pack(pady=(12, 4))

        self.tabs = ctk.CTkTabview(self)
        self.tabs.pack(fill="both", expand=True, padx=14, pady=6)
        
        tab_modes = self.tabs.add("Modes & Sources")
        tab_feeds = self.tabs.add("Custom Feeds")
        tab_keys = self.tabs.add("Hotkeys")
        tab_net = self.tabs.add("Network & OBS")
        tab_io = self.tabs.add("Storage & Buffer")

        # TAB: MODES & SOURCES
        ctk.CTkLabel(tab_modes, text="BROADCAST MODES (Auto-generates camera arrays)", font=("Arial", 11, "bold"), text_color="#A0A0AB").pack(anchor="w", padx=8, pady=(6, 2))
        self.mode_frame = ctk.CTkScrollableFrame(tab_modes, height=220)
        self.mode_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkButton(tab_modes, text="➕ Add Custom Mode", fg_color="#457B9D", font=("Arial", 11, "bold"), command=self._add_blank_mode).pack(pady=4)

        ctk.CTkLabel(tab_modes, text="INPUT SOURCES (Base URL Templates)", font=("Arial", 11, "bold"), text_color="#A0A0AB").pack(anchor="w", padx=8, pady=(15, 2))
        self.source_frame = ctk.CTkScrollableFrame(tab_modes, height=220)
        self.source_frame.pack(fill="x", padx=6, pady=4)
        ctk.CTkButton(tab_modes, text="➕ Add Input Source", fg_color="#457B9D", font=("Arial", 11, "bold"), command=self._add_blank_source).pack(pady=4)

        self.mode_widgets = []
        self.source_widgets = []
        self._refresh_modes_sources()

        # TAB: CUSTOM FEEDS
        gf = ctk.CTkFrame(tab_feeds, fg_color="#181824", corner_radius=6)
        gf.pack(fill="x", padx=6, pady=(6, 10))
        ctk.CTkLabel(gf, text="GLOBAL DECODE OPTIONS (Applies to all auto-generated Modes)", font=("Arial", 11, "bold"), text_color="#A0A0AB").pack(anchor="w", padx=10, pady=(6, 2))

        r_g = ctk.CTkFrame(gf, fg_color="transparent")
        r_g.pack(fill="x", padx=6, pady=(2, 6))
        ctk.CTkLabel(r_g, text="HW Decode:", text_color="#A0A0AB", font=("Arial", 11)).pack(side="left", padx=(4, 4))
        self.g_hw = ctk.CTkOptionMenu(r_g, values=["None", "CUDA (NVIDIA)", "QSV (Intel)", "DXVA2 (Windows)"], width=130)
        self.g_hw.set(getattr(self.engine, 'settings', {}).get('default_hwaccel', 'None'))
        self.g_hw.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(r_g, text="FPS:", text_color="#A0A0AB", font=("Arial", 11)).pack(side="left", padx=(0, 4))
        self.g_fps = ctk.CTkOptionMenu(r_g, values=["30", "60", "24"], width=60)
        self.g_fps.set(getattr(self.engine, 'settings', {}).get('default_fps', '30'))
        self.g_fps.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(r_g, text="Flags:", text_color="#A0A0AB", font=("Arial", 11)).pack(side="left", padx=(0, 4))
        self.g_flags = ctk.CTkEntry(r_g, placeholder_text="e.g. -fflags nobuffer", width=150)
        self.g_flags.insert(0, getattr(self.engine, 'settings', {}).get('default_flags', ''))
        self.g_flags.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkLabel(tab_feeds, text="ACTIVE VIDEO FEEDS (Used ONLY when 'CUSTOM Config' Mode is selected)", font=("Arial", 11, "bold"), text_color="#A0A0AB").pack(anchor="w", padx=8, pady=(6, 2))
        self.feed_list = ctk.CTkScrollableFrame(tab_feeds)
        self.feed_list.pack(fill="both", expand=True, padx=6, pady=4)
        ctk.CTkButton(tab_feeds, text="➕ Add Blank Feed", fg_color="#457B9D", font=("Arial", 11, "bold"), command=self._add_blank_feed).pack(pady=10)

        self.feed_widgets = []
        self._refresh_feeds()

        # TAB: HOTKEYS
        sc_keys = ctk.CTkScrollableFrame(tab_keys)
        sc_keys.pack(fill="both", expand=True, padx=6, pady=6)
        
        self.hk_entries = {}
        current_hk = self.engine.settings.get('hotkeys', DEFAULT_HOTKEYS)

        hk_layout = [
            ("Marking & Capture", [("mark_1", "Mark 1s"), ("mark_5", "Mark 5s"), ("mark_7", "Mark 7s"), ("mark_10", "Mark 10s"), ("mark_15", "Mark 15s")]),
            ("Transport", [("play_pause", "Play / Pause"), ("prep_clip", "Prep to OBS"), ("delete_clip", "Delete Clip")]),
            ("Trimming", [("set_in", "Set IN point"), ("set_out", "Set OUT point"), ("nudge_in_back", "Nudge IN (-0.5s)"), ("nudge_in_fwd", "Nudge IN (+0.5s)")]),
            ("Playback Speeds", [("speed_100", "100% Speed"), ("speed_75", "75% Speed"), ("speed_50", "50% Speed"), ("speed_25", "25% Speed")])
        ]

        for cat, items in hk_layout:
            cf = ctk.CTkFrame(sc_keys, fg_color="#181824", corner_radius=6)
            cf.pack(fill="x", pady=4, padx=4)
            ctk.CTkLabel(cf, text=cat, font=("Arial", 11, "bold"), text_color="#2A9D8F").pack(anchor="w", padx=8, pady=(4, 2))
            for k_id, desc in items:
                r = ctk.CTkFrame(cf, fg_color="transparent")
                r.pack(fill="x", padx=8, pady=2)
                ctk.CTkLabel(r, text=desc, width=150, anchor="w").pack(side="left")
                e = ctk.CTkEntry(r, width=120, font=("Consolas", 11, "bold"))
                e.insert(0, current_hk.get(k_id, DEFAULT_HOTKEYS[k_id]))
                e.pack(side="left")
                self.hk_entries[k_id] = e

        # TAB: NETWORK & OBS
        ctk.CTkLabel(tab_net, text="OBS WebSocket Server (v5):", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        obs_frame = ctk.CTkFrame(tab_net, fg_color="transparent")
        obs_frame.pack(fill="x", padx=10)
        self.obs_host = ctk.CTkEntry(obs_frame, width=150, placeholder_text="127.0.0.1")
        self.obs_host.insert(0, getattr(self.engine, 'settings', {}).get('obs_host', '127.0.0.1'))
        self.obs_host.pack(side="left")
        ctk.CTkLabel(obs_frame, text=":").pack(side="left", padx=5)
        self.obs_port = ctk.CTkEntry(obs_frame, width=80, placeholder_text="4455")
        self.obs_port.insert(0, str(getattr(self.engine, 'settings', {}).get('obs_port', 4455)))
        self.obs_port.pack(side="left")

        ctk.CTkLabel(tab_net, text="OBS Scene Routing (Replay / Live):", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        scene_frame = ctk.CTkFrame(tab_net, fg_color="transparent")
        scene_frame.pack(fill="x", padx=10)
        self.obs_replay_scene = ctk.CTkEntry(scene_frame, width=150, placeholder_text="REPLAY")
        self.obs_replay_scene.insert(0, getattr(self.engine, 'settings', {}).get('obs_replay_scene', 'REPLAY'))
        self.obs_replay_scene.pack(side="left")
        ctk.CTkLabel(scene_frame, text="⇄").pack(side="left", padx=5)
        self.obs_live_scene = ctk.CTkEntry(scene_frame, width=150, placeholder_text="LIVE_GAME")
        self.obs_live_scene.insert(0, getattr(self.engine, 'settings', {}).get('obs_live_scene', 'LIVE_GAME'))
        self.obs_live_scene.pack(side="left")

        ctk.CTkLabel(tab_net, text="OBS Media Source Name:", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        self.obs_media_source = ctk.CTkEntry(tab_net, width=310, placeholder_text="Instant Replay Video")
        self.obs_media_source.insert(0, getattr(self.engine, 'settings', {}).get('obs_media_source', 'Instant Replay Video'))
        self.obs_media_source.pack(anchor="w", padx=10)

        # TAB: STORAGE & BUFFER
        ctk.CTkLabel(tab_io, text="Buffer Directory (Temp .ts stream segments):", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        self.buf_dir = ctk.CTkEntry(tab_io, width=420)
        self.buf_dir.insert(0, self.engine.base_buffer_dir)
        self.buf_dir.pack(anchor="w", padx=10)

        ctk.CTkLabel(tab_io, text="Events Directory (Rendered MP4s & Workspace JSON):", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        self.ev_dir = ctk.CTkEntry(tab_io, width=420)
        self.ev_dir.insert(0, self.engine.base_events_dir)
        self.ev_dir.pack(anchor="w", padx=10)

        ctk.CTkLabel(tab_io, text="Program Out Destination File:", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        self.out_file = ctk.CTkEntry(tab_io, width=420)
        self.out_file.insert(0, self.engine.program_out_file)
        self.out_file.pack(anchor="w", padx=10)

        ctk.CTkLabel(tab_io, text="Rolling Buffer Length (Seconds):", font=("Arial", 11, "bold")).pack(anchor="w", padx=10, pady=(10, 2))
        self.buf_len = ctk.CTkSlider(tab_io, from_=10, to=120, number_of_steps=11)
        self.buf_len.set(getattr(self.engine, 'settings', {}).get('buffer_seconds', 30))
        self.buf_len.pack(fill="x", padx=10, pady=5)
        self.buf_lbl = ctk.CTkLabel(tab_io, text=f"Current: {int(self.buf_len.get())}s")
        self.buf_lbl.pack(pady=2)
        self.buf_len.configure(command=lambda v: self.buf_lbl.configure(text=f"Current: {int(v)}s"))

        ctk.CTkButton(self, text="Save Settings & Apply", fg_color="#2A9D8F", hover_color="#1E7268", height=38, font=("Arial", 12, "bold"), command=self.save_settings).pack(pady=10)

    def _delete_row(self, row, widget_list):
        row.destroy()
        for i, w in enumerate(widget_list):
            if w["row"] == row:
                widget_list.pop(i)
                break

    def _refresh_modes_sources(self):
        for w in self.mode_frame.winfo_children(): w.destroy()
        for w in self.source_frame.winfo_children(): w.destroy()
        self.mode_widgets.clear()
        self.source_widgets.clear()

        default_modes = {
            "ONLINE Profile": {"count": 3, "prefix": "OBS_", "start_port": 9001},
            "LAN Profile": {"count": 10, "prefix": "Player_", "start_port": 9001}
        }
        modes = self.engine.settings.get('modes', default_modes)
        for name, cfg in modes.items():
            self._create_mode_row(name, cfg)

        default_sources = {
            "NETWORK Stream": "udp://0.0.0.0:{port}?overrun_nonfatal=1&fifo_size=50000000",
            "LOCAL Screen": "local_desktop",
            "TEST Bars": "test"
        }
        sources = self.engine.settings.get('sources', default_sources)
        for name, url in sources.items():
            self._create_source_row(name, url)

    def _create_mode_row(self, name, cfg):
        row = ctk.CTkFrame(self.mode_frame, fg_color="#181824", corner_radius=6)
        row.pack(fill="x", pady=3, padx=2)

        w_name = ctk.CTkEntry(row, width=160, font=("Arial", 11, "bold"), placeholder_text="Mode Name")
        w_name.insert(0, name)
        w_name.pack(side="left", padx=4, pady=4)

        ctk.CTkLabel(row, text="Count:", text_color="#A0A0AB").pack(side="left", padx=(6, 2))
        w_count = ctk.CTkEntry(row, width=40)
        w_count.insert(0, str(cfg.get("count", 1)))
        w_count.pack(side="left", padx=2)

        ctk.CTkLabel(row, text="Prefix:", text_color="#A0A0AB").pack(side="left", padx=(6, 2))
        w_prefix = ctk.CTkEntry(row, width=80)
        w_prefix.insert(0, cfg.get("prefix", "Cam_"))
        w_prefix.pack(side="left", padx=2)

        ctk.CTkLabel(row, text="Start Port:", text_color="#A0A0AB").pack(side="left", padx=(6, 2))
        w_port = ctk.CTkEntry(row, width=60)
        w_port.insert(0, str(cfg.get("start_port", 9000)))
        w_port.pack(side="left", padx=2)

        btn = ctk.CTkButton(row, text="✕", width=28, fg_color="#7A1F2B", command=lambda r=row: self._delete_row(r, self.mode_widgets))
        btn.pack(side="right", padx=4)

        self.mode_widgets.append({"row": row, "name": w_name, "count": w_count, "prefix": w_prefix, "port": w_port})

    def _create_source_row(self, name, url):
        row = ctk.CTkFrame(self.source_frame, fg_color="#181824", corner_radius=6)
        row.pack(fill="x", pady=3, padx=2)

        w_name = ctk.CTkEntry(row, width=160, font=("Arial", 11, "bold"), placeholder_text="Source Name")
        w_name.insert(0, name)
        w_name.pack(side="left", padx=4, pady=4)

        w_url = ctk.CTkEntry(row, placeholder_text="URL Template (Use {port})")
        w_url.insert(0, url)
        w_url.pack(side="left", fill="x", expand=True, padx=4)

        btn = ctk.CTkButton(row, text="✕", width=28, fg_color="#7A1F2B", command=lambda r=row: self._delete_row(r, self.source_widgets))
        btn.pack(side="right", padx=4)

        self.source_widgets.append({"row": row, "name": w_name, "url": w_url})

    def _add_blank_mode(self):
        self._create_mode_row("New Profile", {"count": 5, "prefix": "Cam_", "start_port": 8000})

    def _add_blank_source(self):
        self._create_source_row("New Stream Type", "udp://0.0.0.0:{port}")

    def _refresh_feeds(self):
        for w in self.feed_list.winfo_children(): w.destroy()
        self.feed_widgets.clear()
        saved = self.engine.settings.get('saved_feeds', [])
        if not saved:
            ctk.CTkLabel(self.feed_list, text="No custom feeds configured. Click 'Add Blank Feed' below.", text_color="gray").pack(pady=20)
            return
        for idx, f in enumerate(saved):
            self._create_feed_row(idx, f)

    def _create_feed_row(self, idx, f):
        box = ctk.CTkFrame(self.feed_list, fg_color="#181824", corner_radius=6)
        box.pack(fill="x", padx=4, pady=4)
        
        r1 = ctk.CTkFrame(box, fg_color="transparent")
        r1.pack(fill="x", padx=6, pady=(6, 2))
        
        w_name = ctk.CTkEntry(r1, width=120, font=("Arial", 12, "bold"), placeholder_text="Feed ID")
        w_name.insert(0, f.get("name", ""))
        w_name.pack(side="left", padx=(0, 5))
        
        w_url = ctk.CTkEntry(r1, placeholder_text="Stream URL (e.g. udp://0.0.0.0:9001)")
        w_url.insert(0, f.get("url", ""))
        w_url.pack(side="left", fill="x", expand=True, padx=(0, 5))

        def set_url(val, target=w_url, menu_ref=None):
            target.delete(0, "end")
            if val == "UDP": target.insert(0, "udp://0.0.0.0:9001?overrun_nonfatal=1")
            elif val == "SRT": target.insert(0, "srt://0.0.0.0:9001?mode=listener")
            elif val == "SCREEN": target.insert(0, "local_desktop")
            elif val == "TEST": target.insert(0, "test")
            if menu_ref: menu_ref.set("Presets...") 
            
        proto = ctk.CTkOptionMenu(r1, values=["Presets...", "UDP", "SRT", "SCREEN", "TEST"], width=100)
        proto.configure(command=lambda val: set_url(val, w_url, proto))
        proto.pack(side="left", padx=(0, 5))

        ctk.CTkButton(r1, text="✕", width=28, fg_color="#7A1F2B", hover_color="#B81D2A", command=lambda r=box: self._delete_row(r, self.feed_widgets)).pack(side="right")
        
        r2 = ctk.CTkFrame(box, fg_color="transparent")
        r2.pack(fill="x", padx=6, pady=(2, 6))
        
        conf = f.get("config", {})
        ctk.CTkLabel(r2, text="HW Decode:", text_color="#A0A0AB", font=("Arial", 11)).pack(side="left", padx=(0, 5))
        w_hw = ctk.CTkOptionMenu(r2, values=["None", "CUDA (NVIDIA)", "QSV (Intel)", "DXVA2 (Windows)"], width=130)
        w_hw.set(conf.get("hwaccel", "None"))
        w_hw.pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(r2, text="FPS:", text_color="#A0A0AB", font=("Arial", 11)).pack(side="left", padx=(0, 5))
        w_fps = ctk.CTkOptionMenu(r2, values=["30", "60", "24"], width=60)
        w_fps.set(conf.get("fps", "30"))
        w_fps.pack(side="left", padx=(0, 15))
        
        ctk.CTkLabel(r2, text="Flags:", text_color="#A0A0AB", font=("Arial", 11)).pack(side="left", padx=(0, 5))
        w_flags = ctk.CTkEntry(r2, placeholder_text="e.g. -fflags nobuffer", width=150)
        w_flags.insert(0, conf.get("custom_flags", ""))
        w_flags.pack(side="left", fill="x", expand=True)
        
        self.feed_widgets.append({"row": box, "name": w_name, "url": w_url, "hw": w_hw, "fps": w_fps, "flags": w_flags})

    def _add_blank_feed(self):
        self._create_feed_row(-1, {"name": f"Camera_{len(self.feed_widgets)+1}", "url": "", "config": {}})

    def save_settings(self):
        new_modes = {}
        for w in self.mode_widgets:
            name = w["name"].get().strip()
            if not name: continue
            new_modes[name] = {"count": int(w["count"].get() or 1), "prefix": w["prefix"].get(), "start_port": int(w["port"].get() or 9000)}
        self.engine.settings['modes'] = new_modes

        new_sources = {}
        for w in self.source_widgets:
            name = w["name"].get().strip()
            if not name: continue
            new_sources[name] = w["url"].get().strip()
        self.engine.settings['sources'] = new_sources

        new_saved = []
        for w in self.feed_widgets:
            name = w["name"].get().strip()
            if not name: continue
            new_saved.append({"name": name, "url": w["url"].get().strip(), "config": {"hwaccel": w["hw"].get(), "fps": w["fps"].get(), "custom_flags": w["flags"].get().strip()}})
        self.engine.settings['saved_feeds'] = new_saved
        
        self.engine.settings['default_hwaccel'] = self.g_hw.get()
        self.engine.settings['default_fps'] = self.g_fps.get()
        self.engine.settings['default_flags'] = self.g_flags.get().strip()

        self.engine.settings['buffer_seconds'] = int(self.buf_len.get())
        self.engine.base_buffer_dir = self.buf_dir.get().strip()
        self.engine.base_events_dir = self.ev_dir.get().strip()
        self.engine.program_out_file = self.out_file.get().strip()
        self.engine.settings['obs_host'] = self.obs_host.get().strip() or "127.0.0.1"
        self.engine.settings['obs_port'] = int(self.obs_port.get().strip() or 4455)
        self.engine.settings['obs_replay_scene'] = self.obs_replay_scene.get().strip() or "REPLAY"
        self.engine.settings['obs_live_scene'] = self.obs_live_scene.get().strip() or "LIVE_GAME"
        self.engine.settings['obs_media_source'] = self.obs_media_source.get().strip() or "Instant Replay Video"
        
        hk = {}
        for k_id, entry in self.hk_entries.items():
            hk[k_id] = entry.get().strip()
        self.engine.settings['hotkeys'] = hk

        self.app_ref._save_state()  
        self.app_ref._bind_shortcuts() 
        self.app_ref.refresh_top_dropdowns()
        self.app_ref.apply_configuration()
        self.destroy()

class ValoReplayDeck(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("VALO-REPLAY // Broadcast Replay System")
        self.geometry("1400x800") 
        self.minsize(1200, 700)
        self.after(0, lambda: self.state("zoomed") if os.name == "nt" else self.attributes('-zoomed', True))

        self.engine = ReplayEngine()
        self.ui_q = queue.Queue()

        self.obs_client = None
        self.is_buffering = False
        self.selected_event = None
        self.angle = None
        self.speed = 1.0
        self.live_mode = True
        
        # Debounce Trackers
        self.preview_size = (960, 540)
        self._last_fit = None
        self._last_preview_fit = None
        self._preview_resize_time = 0
        self._tile_size = None
        self._last_mv_fit = None
        self._mv_resize_time = 0

        self.playlist = []
        self.pl_idx = -1
        self.pl_running = False

        self.live_tile_labels = {}
        self._tile_serial = {}
        self.workspaces = [{"name": "Workspace 1", "events": []}]
        self.ws_idx = 0
        self.sel_ids = set()
        self.anchor_id = None
        self.queue = self.playlist
        self.on_air_id = None
        self.state_file = os.path.join(self.engine.base_events_dir, "workspaces.json")
        self.angle_btns = {}
        self._last_serial = -1
        self._scrub_job = None
        self._scrubbing = False

        self.last_prep_file = os.path.abspath(self.engine.program_out_file)

        self._load_state()
        self._setup_treeview_style()
        self._build_ui()
        self._bind_shortcuts()
        self._rebuild_ws_ui()
        
        self.engine.configure_mode(self.mode_menu.get(), self.source_menu.get())
        self._rebuild_multiview_tiles()

        self._pump()
        self._tick_ui()
        self._update_multiview_loop()
        self._poll_buffer_status()
        self._auto_save_loop()

    def _auto_save_loop(self):
        self._save_state()
        self.after(300000, self._auto_save_loop)

    def _save_state(self):
        try:
            data = {"ws_idx": self.ws_idx, "counter": self.engine._counter, "workspaces": self.workspaces, "settings": self.engine.settings}
            tmp = self.state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f)
            os.replace(tmp, self.state_file)
        except Exception as ex: print("save error:", ex)

    def _load_state(self):
        try:
            with open(self.state_file, encoding="utf-8") as f: data = json.load(f)
            self.engine.settings = data.get("settings", {'buffer_seconds': 30})
            wss, top = [], int(data.get("counter", 0))
            for ws in data.get("workspaces", []):
                evs = [e for e in ws.get("events", []) if e.get("masters") and all(os.path.exists(p) for p in e["masters"].values())]
                for e in evs:
                    try: top = max(top, int(e["id"][1:]))
                    except ValueError: pass
                wss.append({"name": ws.get("name", "Workspace"), "events": evs})
            if wss:
                self.workspaces = wss
                self.ws_idx = min(int(data.get("ws_idx", 0)), len(wss) - 1)
            self.engine._counter = top
        except Exception:
            self.engine.settings = {'buffer_seconds': 30}

    def _get_mode_list(self):
        default_modes = {"ONLINE Profile": 1, "LAN Profile": 1}
        modes_dict = self.engine.settings.get('modes', default_modes)
        return list(modes_dict.keys()) + ["CUSTOM Config"]

    def _get_source_list(self):
        default_sources = {"NETWORK Stream": 1, "LOCAL Screen": 1, "TEST Bars": 1}
        sources_dict = self.engine.settings.get('sources', default_sources)
        return list(sources_dict.keys())

    def refresh_top_dropdowns(self):
        modes = self._get_mode_list()
        self.mode_menu.configure(values=modes)
        if self.mode_menu.get() not in modes:
            self.mode_menu.set(modes[0])

        sources = self._get_source_list()
        self.source_menu.configure(values=sources)
        if self.source_menu.get() not in sources:
            self.source_menu.set(sources[0])

    def _setup_treeview_style(self):
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Treeview", background="#1A1A24", foreground="#E0E0E8", rowheight=28, fieldbackground="#1A1A24", borderwidth=0, font=("Arial", 10))
        style.configure("Treeview.Heading", background="#2B2B36", foreground="#A0A0AB", font=("Arial", 10, "bold"), borderwidth=0)
        style.map("Treeview", background=[('selected', '#2A9D8F')], foreground=[('selected', '#FFFFFF')])
        style.map("Treeview.Heading", background=[('active', '#3F3F4E')])

    def ui(self, fn, *args):
        self.ui_q.put((fn, args))

    def _pump(self):
        try:
            while True:
                fn, args = self.ui_q.get_nowait()
                try: fn(*args)
                except Exception as e: print("UI error:", e)
        except queue.Empty: pass
        self.after(25, self._pump)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # TOP GLOBAL TOOLBAR
        top = ctk.CTkFrame(self, height=50, fg_color="#121217", corner_radius=0)
        top.grid(row=0, column=0, sticky="ew")
        top.pack_propagate(False)

        ctk.CTkLabel(top, text="MODE:", font=("Arial", 12, "bold"), text_color="#A0A0AB").pack(side="left", padx=(15, 5))
        self.mode_menu = ctk.CTkOptionMenu(top, values=["Loading..."], command=lambda _: self.apply_configuration())
        self.mode_menu.pack(side="left", pady=10, padx=5)

        ctk.CTkLabel(top, text="SOURCE:", font=("Arial", 12, "bold"), text_color="#A0A0AB").pack(side="left", padx=(15, 5))
        self.source_menu = ctk.CTkOptionMenu(top, values=["Loading..."], command=lambda _: self.apply_configuration())
        self.source_menu.pack(side="left", pady=10, padx=5)

        self.refresh_top_dropdowns()

        self.live_switch = ctk.CTkSwitch(top, text="MARK FROM LIVE", font=("Arial", 12, "bold"), command=self._on_live_toggle)
        self.live_switch.select()
        self.live_switch.pack(side="left", padx=25)

        self.status_label = ctk.CTkLabel(top, text="STATUS: Idle", text_color="gray", font=("Arial", 12, "bold"))
        self.status_label.pack(side="right", padx=15)

        self.settings_btn = ctk.CTkButton(top, text="⚙ SETTINGS", width=100, fg_color="#333342", hover_color="#484B6A", font=("Arial", 11, "bold"), command=self.open_settings)
        self.settings_btn.pack(side="right", pady=10, padx=10)

        self.obs_btn = ctk.CTkButton(top, text="🔌 CONNECT OBS", width=120, fg_color="#457B9D", font=("Arial", 11, "bold"), command=self.connect_obs)
        self.obs_btn.pack(side="right", pady=10, padx=10)

        self.buffer_btn = ctk.CTkButton(top, text="▶ START BUFFERING", width=140, fg_color="#2A9D8F", hover_color="#1E7268", font=("Arial", 11, "bold"), command=self.toggle_buffering)
        self.buffer_btn.pack(side="right", pady=10, padx=10)

        # MAIN DUAL PANE
        main_pane = tk.PanedWindow(self, orient="horizontal", sashwidth=8, sashrelief="flat", bg="#121217", bd=0)
        main_pane.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

        left_monitor = ctk.CTkFrame(main_pane, fg_color="#0D0E15", corner_radius=0)
        main_pane.add(left_monitor, minsize=400, stretch="always")

        players_frame = ctk.CTkFrame(left_monitor, fg_color="transparent")
        players_frame.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        
        self.player_a_box = ctk.CTkFrame(players_frame, fg_color="#000000", corner_radius=4)
        self.player_a_box.pack(side="left", fill="both", expand=True, padx=2)
        ctk.CTkLabel(self.player_a_box, text="A (PREVIEW / CUE)", fg_color="#FF9F1C", text_color="black", font=("Arial", 10, "bold"), height=20, corner_radius=2).pack(anchor="nw", padx=4, pady=4)
        self.preview_lbl = ctk.CTkLabel(self.player_a_box, text="No Clip Loaded", text_color="#444444")
        self.preview_lbl.pack(fill="both", expand=True)

        self.player_b_box = ctk.CTkFrame(players_frame, fg_color="#000000", corner_radius=4)
        self.player_b_box.pack(side="right", fill="both", expand=True, padx=2)
        ctk.CTkLabel(self.player_b_box, text="B (ON AIR)", fg_color="#E63946", text_color="white", font=("Arial", 10, "bold"), height=20, corner_radius=2).pack(anchor="nw", padx=4, pady=4)
        ctk.CTkLabel(self.player_b_box, text="ROUTED TO OBS", text_color="#444444", font=("Arial", 16, "bold")).pack(fill="both", expand=True)

        mv_frame = ctk.CTkFrame(left_monitor, fg_color="transparent")
        mv_frame.pack(side="bottom", fill="both", expand=True, padx=5, pady=5)
        self.multiview_grid = ctk.CTkFrame(mv_frame, fg_color="transparent")
        self.multiview_grid.pack(fill="both", expand=True)

        right_monitor = ctk.CTkFrame(main_pane, fg_color="#181820", corner_radius=0)
        main_pane.add(right_monitor, minsize=550, stretch="always")

        ws_bar = ctk.CTkFrame(right_monitor, fg_color="#1E1E28", height=45, corner_radius=0)
        ws_bar.pack(fill="x")
        ws_bar.pack_propagate(False)
        
        self.ws_tabs = ctk.CTkSegmentedButton(ws_bar, values=["Workspace 1"], command=self._on_ws_tab)
        self.ws_tabs.pack(side="left", padx=10, pady=8)
        ctk.CTkButton(ws_bar, text="＋", width=30, height=28, command=self.add_workspace).pack(side="left", pady=8, padx=2)
        ctk.CTkButton(ws_bar, text="🗑", width=30, height=28, fg_color="#7A1F2B", command=self.delete_workspace).pack(side="left", pady=8, padx=2)

        self.marks_frame = ctk.CTkFrame(ws_bar, fg_color="transparent")
        self.marks_frame.pack(side="right", padx=10)
        self._rebuild_mark_buttons()

        search_bar = ctk.CTkFrame(right_monitor, fg_color="transparent")
        search_bar.pack(fill="x", padx=10, pady=(10, 0))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", lambda name, index, mode: self._refresh_event_rows())
        ctk.CTkEntry(search_bar, textvariable=self.search_var, placeholder_text="🔍 Search tags or labels...", width=200).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(search_bar, text="Tag: Clutch", command=lambda: self._add_tag("Clutch")).pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(search_bar, text="Tag: Fail", command=lambda: self._add_tag("Fail")).pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(search_bar, text="➕ Custom Tag", fg_color="#2A9D8F", command=self._add_custom_tag).pack(side="left", fill="x", expand=True, padx=5)

        grid_frame = ctk.CTkFrame(right_monitor, fg_color="transparent")
        grid_frame.pack(fill="both", expand=True, padx=10, pady=10)

        cols = ("id", "label", "tags", "in", "out", "dur", "cams")
        self.tree = ttk.Treeview(grid_frame, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("id", text="ID")
        self.tree.heading("label", text="CLIP LABEL")
        self.tree.heading("tags", text="TAGS")
        self.tree.heading("in", text="IN")
        self.tree.heading("out", text="OUT")
        self.tree.heading("dur", text="DUR")
        self.tree.heading("cams", text="ANGLES")

        self.tree.column("id", width=50, anchor="center")
        self.tree.column("label", width=130, anchor="w")
        self.tree.column("tags", width=120, anchor="w")
        self.tree.column("in", width=50, anchor="center")
        self.tree.column("out", width=50, anchor="center")
        self.tree.column("dur", width=50, anchor="center")
        self.tree.column("cams", width=50, anchor="center")

        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(grid_frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double_click)

        # -------------------------------------------------------------
        # RESPONSIVE CONTROLLER DECK & vMix NLE INTEGRATION
        # -------------------------------------------------------------
        deck = ctk.CTkFrame(right_monitor, fg_color="#121217", corner_radius=8)
        deck.pack(side="bottom", fill="x", expand=False, padx=10, pady=(0, 10))

        tl_frame = ctk.CTkFrame(deck, fg_color="transparent")
        tl_frame.pack(fill="x", padx=15, pady=(15, 5))
        self.time_lbl = ctk.CTkLabel(tl_frame, text="00:00 / 00:00", font=("Consolas", 12, "bold"), text_color="#A0A0AB")
        self.time_lbl.pack(side="left")
        self.timeline = ctk.CTkSlider(tl_frame, from_=0, to=1, command=self._on_scrub)
        self.timeline.set(0)
        self.timeline.pack(side="left", fill="x", expand=True, padx=15)
        self.clip_info = ctk.CTkLabel(tl_frame, text="—", font=("Arial", 12, "bold"), text_color="#E0E0E8")
        self.clip_info.pack(side="right")

        ctrl_frame = ctk.CTkFrame(deck, fg_color="transparent")
        ctrl_frame.pack(fill="x", expand=True, padx=15, pady=5)
        
        ctrl_frame.grid_columnconfigure(0, weight=1) 
        ctrl_frame.grid_columnconfigure(1, weight=1) 
        ctrl_frame.grid_columnconfigure(2, weight=1) 

        # LEFT SIDE: Trimming & Playhead Splitting
        mark_box = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        mark_box.grid(row=0, column=0, sticky="w")
        ctk.CTkButton(mark_box, text="[ IN ]", width=55, height=32, fg_color="#3A3D5C", font=("Arial", 11, "bold"), command=lambda: self.set_now("in")).pack(side="left", padx=2)
        ctk.CTkButton(mark_box, text="[ OUT ]", width=55, height=32, fg_color="#3A3D5C", font=("Arial", 11, "bold"), command=lambda: self.set_now("out")).pack(side="left", padx=2)
        ctk.CTkButton(mark_box, text="✂️ SUB-CLIP", width=80, height=32, fg_color="#6D597A", hover_color="#4E3F59", font=("Arial", 11, "bold"), command=self.duplicate_clip).pack(side="left", padx=2)
        ctk.CTkButton(mark_box, text="✂ SPLIT", width=65, height=32, fg_color="#B5179E", hover_color="#7209B7", font=("Arial", 11, "bold"), command=self.split_at_playhead).pack(side="left", padx=2)

        # CENTER: Transport
        trans_box = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        trans_box.grid(row=0, column=1, sticky="n")
        ctk.CTkButton(trans_box, text="⏮", width=40, height=32, fg_color="#2B2B36", command=self.cue).pack(side="left", padx=2)
        ctk.CTkButton(trans_box, text="◀|", width=40, height=32, fg_color="#2B2B36", command=lambda: self.nudge("in", -FRAME)).pack(side="left", padx=2)
        self.play_btn = ctk.CTkButton(trans_box, text="⏯ PLAY", width=100, height=32, fg_color="#2A9D8F", font=("Arial", 11, "bold"), command=self.toggle_play)
        self.play_btn.pack(side="left", padx=6)
        ctk.CTkButton(trans_box, text="|▶", width=40, height=32, fg_color="#2B2B36", command=lambda: self.nudge("in", FRAME)).pack(side="left", padx=2)

        # RIGHT SIDE: Speeds
        speed_box = ctk.CTkFrame(ctrl_frame, fg_color="transparent")
        speed_box.grid(row=0, column=2, sticky="e")
        self.speed_selector = ctk.CTkSegmentedButton(speed_box, values=list(SPEEDS), command=lambda v: self.set_speed_value(SPEEDS[v]), height=32)
        self.speed_selector.set("100%")
        self.speed_selector.pack(side="left")

        # BOTTOM ACTION BAR
        action_frame = ctk.CTkFrame(deck, fg_color="transparent")
        action_frame.pack(fill="x", expand=True, padx=15, pady=(5, 10))
        
        action_frame.grid_columnconfigure(0, weight=1) 
        action_frame.grid_columnconfigure(1, weight=1) 

        self.angle_bar = ctk.CTkFrame(action_frame, fg_color="transparent")
        self.angle_bar.grid(row=0, column=0, sticky="w")
        
        air_box = ctk.CTkFrame(action_frame, fg_color="transparent")
        air_box.grid(row=0, column=1, sticky="e")
        
        ctk.CTkButton(air_box, text="🎬 NLE EDITOR", width=110, height=34, fg_color="#7209B7", hover_color="#560BAD", font=("Arial", 11, "bold"), command=self.open_nle_editor).pack(side="left", padx=3)
        ctk.CTkButton(air_box, text="🗑 DELETE", width=80, height=34, fg_color="#7A1F2B", command=self.delete_selected).pack(side="left", padx=3)
        self.export_btn = ctk.CTkButton(air_box, text="💾 EXPORT", width=80, height=34, fg_color="#3A86FF", font=("Arial", 11, "bold"), command=self.export_clip)
        self.export_btn.pack(side="left", padx=3)
        self.prep_mosaic_btn = ctk.CTkButton(air_box, text="🔲 MOSAIC", width=80, height=34, fg_color="#6D597A", font=("Arial", 11, "bold"), command=self.send_mosaic_to_program)
        self.prep_mosaic_btn.pack(side="left", padx=3)
        self.prep_btn = ctk.CTkButton(air_box, text="1. PREP 📤", width=100, height=34, fg_color="#457B9D", font=("Arial", 11, "bold"), command=self.send_to_program)
        self.prep_btn.pack(side="left", padx=3)
        self.obs_play_btn = ctk.CTkButton(air_box, text="2. PLAY IN OBS 🔴", width=130, height=34, fg_color="#E63946", font=("Arial", 11, "bold"), command=self.trigger_obs_scene)
        self.obs_play_btn.pack(side="left", padx=(3, 0))

    def open_nle_editor(self):
        VMixClipEditor(self, self)

    def split_at_playhead(self):
        """Splices the currently active event in-place at the playhead position into two clips."""
        ev = self.selected_event
        p = self.engine.player
        if not ev or p.path != self._cur_path(): return
        
        split_pos = self._timeline_pos()
        if split_pos <= ev["in"] + 0.2 or split_pos >= ev["out"] - 0.2:
            messagebox.showwarning("Split Error", "Playhead is too close to IN or OUT point to split.")
            return

        old_out = ev["out"]
        ev["out"] = split_pos

        new_ev = dict(ev)
        new_ev["id"] = self.engine.next_id()
        new_ev["label"] = f"{ev['label']} (Part 2)"
        new_ev["in"] = split_pos
        new_ev["out"] = old_out
        new_ev["tags"] = list(ev.get("tags", []))
        
        ws = self.workspaces[self.ws_idx]
        cur_idx = ws["events"].index(ev)
        ws["events"].insert(cur_idx + 1, new_ev)

        self._save_state()
        self._refresh_event_rows()
        self.select_event(ev)

    def _rebuild_mark_buttons(self):
        for w in self.marks_frame.winfo_children(): w.destroy()
        hk = self.engine.settings.get('hotkeys', DEFAULT_HOTKEYS)
        b_data = [(1, hk.get("mark_1", "F1")), (5, hk.get("mark_5", "F5")), (7, hk.get("mark_7", "F6")), (10, hk.get("mark_10", "F7")), (15, hk.get("mark_15", "F8"))]
        
        for sec, key in b_data:
            ctk.CTkButton(self.marks_frame, text=f"⚡ -{sec}s ({key})", font=("Arial", 12, "bold"), width=80, height=30, fg_color="#E63946", hover_color="#B81D2A", command=lambda s=sec: self.mark(s)).pack(side="left", fill="both", expand=True, padx=2)

    def connect_obs(self):
        try:
            import obsws_python as obs
            host = getattr(self.engine, 'settings', {}).get('obs_host', '127.0.0.1')
            port = getattr(self.engine, 'settings', {}).get('obs_port', 4455)
            self.obs_client = obs.ReqClient(host=host, port=port, password="", timeout=3)
            self.obs_btn.configure(text="🔌 OBS CONNECTED", fg_color="#2A9D8F")
        except Exception as e:
            self.obs_btn.configure(text="❌ OBS FAILED", fg_color="#E63946")

    def toggle_buffering(self):
        if not self.is_buffering:
            self.is_buffering = True
            self.buffer_btn.configure(text="⏹ STOP BUFFERING", fg_color="#E63946", hover_color="#B81D2A")
            self.engine.start_all()
            self.status_label.configure(text="STATUS: Buffering Started", text_color="#00FFAA")
        else:
            self.is_buffering = False
            self.buffer_btn.configure(text="▶ START BUFFERING", fg_color="#2A9D8F", hover_color="#1E7268")
            self.engine.stop_all()
            self.status_label.configure(text="STATUS: Idle (Stopped)", text_color="gray")

    def open_settings(self):
        SettingsWindow(self, self.engine, self)

    def _fit169(self, w, h):
        w, h = max(40, int(w)), max(24, int(h))
        if w * 9 / 16 <= h: return (w, int(w * 9 / 16))
        return (int(h * 16 / 9), h)

    def _draw_preview(self):
        p = self.engine.player
        img = p.latest_pil_image
        if img is None: return
        W, H = self.player_a_box.winfo_width(), self.player_a_box.winfo_height()
        if W < 50 or H < 30: return
        fit = self._fit169(W - 8, H - 28) 
        
        if fit != getattr(self, '_last_preview_fit', None):
            self._last_preview_fit = fit
            self._preview_resize_time = time.time()
            return
            
        if time.time() - getattr(self, '_preview_resize_time', 0) < 0.15:
            return

        if p.serial == self._last_serial and fit == self._last_fit: return
        self._last_serial, self._last_fit = p.serial, fit
        self.preview_lbl.configure(image=ctk.CTkImage(light_image=img, dark_image=img, size=fit), text="")

    def _grid_cols(self, n):
        return max(1, n) if n <= 3 else (4 if n <= 8 else 5)

    def _rebuild_multiview_tiles(self):
        for w in self.multiview_grid.winfo_children(): w.destroy()
        self.live_tile_labels.clear()
        self._tile_serial.clear()
        channels = list(self.engine.channels.keys())
        cols = self._grid_cols(len(channels))
        rows = max(1, -(-len(channels) // cols))
        for c in range(max(6, cols)): self.multiview_grid.grid_columnconfigure(c, weight=1 if c < cols else 0, uniform="c" if c < cols else "")
        for r in range(max(8, rows)): self.multiview_grid.grid_rowconfigure(r, weight=1 if r < rows else 0, uniform="r" if r < rows else "")
        for idx, ch_id in enumerate(channels):
            tile = ctk.CTkFrame(self.multiview_grid, fg_color="#16161E", corner_radius=6)
            tile.grid(row=idx // cols, column=idx % cols, padx=3, pady=3, sticky="nsew")
            head = ctk.CTkFrame(tile, fg_color="#25283D", corner_radius=3)
            head.pack(fill="x", padx=3, pady=(3, 1))
            ctk.CTkLabel(head, text=f"{idx + 1 if idx < 9 else 0} · {ch_id}", font=("Arial", 11, "bold")).pack(side="left", padx=6)
            lbl = ctk.CTkLabel(tile, text="Connecting...", text_color="gray", font=("Arial", 10))
            lbl.pack(fill="both", expand=True, padx=3, pady=3)
            self.live_tile_labels[ch_id] = lbl

    def _update_multiview_loop(self):
        n = len(self.engine.channels)
        if n:
            cols = self._grid_cols(n)
            rows = max(1, -(-n // cols))
            W, H = self.multiview_grid.winfo_width(), self.multiview_grid.winfo_height()
            if W > 60 and H > 60:
                size = self._fit169(W // cols - 16, H // rows - 16 - 28)
                
                if size != getattr(self, '_last_mv_fit', None):
                    self._last_mv_fit = size
                    self._mv_resize_time = time.time()
                
                if time.time() - getattr(self, '_mv_resize_time', 0) >= 0.15:
                    if size != self._tile_size:
                        self._tile_size = size
                        self._tile_serial.clear()
                    for ch_id, ch in list(self.engine.channels.items()):
                        img = ch.latest_pil_image
                        lbl = self.live_tile_labels.get(ch_id)
                        if lbl is not None and img is not None and self._tile_serial.get(ch_id) is not img:
                            self._tile_serial[ch_id] = img
                            lbl.configure(image=ctk.CTkImage(light_image=img, dark_image=img, size=size), text="")
        self.after(150, self._update_multiview_loop)

    def apply_configuration(self):
        self.engine.player.stop()
        self.engine.configure_mode(self.mode_menu.get(), self.source_menu.get())
        self._rebuild_multiview_tiles()
        if self.is_buffering:
            self.engine.start_all()

    def _on_live_toggle(self):
        self.live_mode = bool(self.live_switch.get())

    def _poll_buffer_status(self):
        if not self.is_buffering:
            self.status_label.configure(text="STATUS: Idle (Stopped)", text_color="gray")
        else:
            n = self.engine.get_buffer_health()
            if n < 3: self.status_label.configure(text="⚠️ Warming up buffer...", text_color="#FFB703")
            else: self.status_label.configure(text=f"🟢 {self.mode_menu.get()} LIVE | Buffer: {n}s", text_color="#00FFAA")
        self.after(1000, self._poll_buffer_status)

    def mark(self, seconds):
        if not self.is_buffering:
            messagebox.showwarning("Engine Stopped", "You must click 'START BUFFERING' before capturing a clip.")
            return
        ws = self.workspaces[self.ws_idx]
        threading.Thread(target=self._mark_worker, args=(float(seconds), ws), daemon=True).start()

    def _mark_worker(self, seconds, ws):
        p = self.engine.player
        ev = self.selected_event
        if not self.live_mode and ev and self.angle in ev["masters"] and p.path == ev["masters"][self.angle]:
            new = self.engine.mark_from(ev, self._timeline_pos(), seconds)
        else: new = self.engine.mark_live(seconds)
        if new: self.ui(self._on_new_event, new, ws)

    def _on_new_event(self, ev, ws):
        ws["events"].append(ev)
        self._save_state()
        current = ws is self.workspaces[self.ws_idx]
        if current: self._refresh_event_rows()
        p = self.engine.player
        busy = p.is_playing and not p.paused
        if current and not busy and not self.pl_running: self.select_event(ev)

    def duplicate_clip(self):
        evs = self._selected_events()
        if not evs: return
        
        for ev in evs:
            new_ev = dict(ev)
            new_ev["id"] = self.engine.next_id()
            new_ev["label"] = ev["label"] + " (Copy)"
            new_ev["tags"] = list(ev.get("tags", []))
            new_ev["angle"] = self.angle if self.angle in ev["masters"] else next(iter(ev["masters"]))
            
            ws = self.workspaces[self.ws_idx]
            ws["events"].append(new_ev)
            
        self._save_state()
        self._refresh_event_rows()
        self.select_event(self.workspaces[self.ws_idx]["events"][-1])

    def _add_tag(self, tag):
        evs = self._selected_events()
        for ev in evs:
            if "tags" not in ev: ev["tags"] = []
            if tag not in ev["tags"]: ev["tags"].append(tag)
        if evs:
            self._save_state()
            self._refresh_event_rows()

    def _add_custom_tag(self):
        evs = self._selected_events()
        if not evs: return
        dialog = ctk.CTkInputDialog(text="Enter custom tag:", title="Custom Tag")
        tag = dialog.get_input()
        if tag: self._add_tag(tag.strip())

    @property
    def cur_events(self): return self.workspaces[self.ws_idx]["events"]

    def _selected_events(self):
        sel = self.tree.selection()
        ids = [self.tree.item(i, "values")[0] for i in sel]
        return [e for e in self.cur_events if e["id"] in ids]

    def _refresh_event_rows(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        query = self.search_var.get().lower()
        for ev in self.cur_events:
            tags = ", ".join(ev.get("tags", []))
            if query:
                if query not in ev["label"].lower() and query not in tags.lower(): continue
            dur = f"{ev['out'] - ev['in']:.2f}s"
            cams = str(len(ev["masters"]))
            self.tree.insert("", "end", iid=ev["id"], values=(ev["id"], ev["label"], tags, f"{ev['in']:.2f}", f"{ev['out']:.2f}", dur, cams))
        if self.selected_event and self.tree.exists(self.selected_event["id"]):
            self.tree.selection_set(self.selected_event["id"])
            self.tree.see(self.selected_event["id"])
        self.clip_info.configure(text=f"CLIPS: {len(self.cur_events)}")

    def _on_tree_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        ev_id = sel[0]
        ev = next((e for e in self.cur_events if e["id"] == ev_id), None)
        if ev and (not self.selected_event or self.selected_event["id"] != ev_id): self.select_event(ev)

    def _on_tree_double_click(self, event):
        item = self.tree.selection()[0]
        ev = next((e for e in self.cur_events if e["id"] == item), None)
        if ev:
            name = ctk.CTkInputDialog(text="Label (e.g. NES 2K):", title="Rename clip").get_input()
            if name:
                ev["label"] = name
                self._save_state()
                self._refresh_event_rows()

    def _cur_path(self):
        ev = self.selected_event
        return ev["masters"].get(self.angle) if ev else None

    def _timeline_pos(self):
        ev = self.selected_event
        off = ev["offsets"].get(self.angle, 0.0) if ev else 0.0
        return max(0.0, self.engine.player.position() - off)

    def _play_range(self, t_in, t_out, paused=False, speed=None):
        ev = self.selected_event
        if not ev or self.angle not in ev["masters"]: return
        off = ev["offsets"].get(self.angle, 0.0)
        self.engine.player.play(ev["masters"][self.angle], off + t_in, None if t_out is None else off + t_out, speed or self.speed, paused=paused, size=self.preview_size)

    def select_event(self, ev, cue=True):
        self.selected_event = ev
        if ev.get("angle") in ev["masters"]: self.angle = ev["angle"]
        elif self.angle not in ev["masters"]: self.angle = next(iter(ev["masters"]))
        if "speed" in ev:
            self.speed = ev["speed"]
            try: self.speed_selector.set(f"{int(round(self.speed * 100))}%")
            except Exception: pass
        self.timeline.configure(from_=0, to=max(ev["length"], 0.1))
        self._build_angle_buttons()
        if cue: self.cue()

    def _build_angle_buttons(self):
        for b in self.angle_btns.values(): b.destroy()
        self.angle_btns.clear()
        ev = self.selected_event
        for name in (ev["masters"] if ev else []):
            short = name.replace("Player_", "P").replace("OBS_", "OBS")
            b = ctk.CTkButton(self.angle_bar, text=short, width=50, height=34, font=("Arial", 11, "bold"), command=lambda n=name: self.select_angle(n))
            b.pack(side="left", padx=2)
            self.angle_btns[name] = b
        self._highlight_angle()

    def _highlight_angle(self):
        for n, b in self.angle_btns.items(): b.configure(fg_color="#2A9D8F" if n == self.angle else "#3A86FF")

    def select_angle(self, name):
        ev = self.selected_event
        if not ev or name not in ev["masters"] or name == self.angle: return
        p = self.engine.player
        same = p.path == self._cur_path() and not p.finished
        t = self._timeline_pos() if same else None
        paused = p.paused or not p.is_playing
        self.angle = name
        ev["angle"] = name
        self._highlight_angle()
        if t is None: self.cue()
        else: self._play_range(t, ev["out"], paused=paused)

    def cue(self):
        ev = self.selected_event
        if ev: self._play_range(ev["in"], ev["out"], paused=True)

    def toggle_play(self):
        p = self.engine.player
        ev = self.selected_event
        if not ev: return
        if p.path != self._cur_path() or p.finished or not p.is_playing: self._play_range(ev["in"], ev["out"])
        else: p.paused = not p.paused

    def set_speed_value(self, v):
        self.speed = v
        if self.selected_event: self.selected_event["speed"] = v
        try: self.speed_selector.set(f"{int(round(v * 100))}%")
        except Exception: pass
        p = self.engine.player
        if p.path and p.is_playing: p.play(p.path, p.position(), p.end, v, paused=p.paused, size=self.preview_size)

    def nudge(self, which, delta):
        ev = self.selected_event
        if not ev: return
        if which == "in": ev["in"] = min(max(0.0, ev["in"] + delta), ev["out"] - 0.1)
        else: ev["out"] = max(min(ev["length"], ev["out"] + delta), ev["in"] + 0.1)
        self._after_trim(which)

    def set_now(self, which):
        ev = self.selected_event
        p = self.engine.player
        if not ev or p.path != self._cur_path(): return
        t = self._timeline_pos()
        if which == "in": ev["in"] = min(max(0.0, t), ev["out"] - 0.1)
        else: ev["out"] = max(min(ev["length"], t), ev["in"] + 0.1)
        self._after_trim(which)

    def _after_trim(self, which):
        ev = self.selected_event
        self._save_state()
        self._refresh_event_rows()
        if which == "in": self._play_range(ev["in"], ev["out"], paused=True)
        else: self._play_range(max(ev["in"], ev["out"] - 0.2), ev["out"], paused=True)

    def _on_scrub(self, val):
        self._scrubbing = True
        if self._scrub_job: self.after_cancel(self._scrub_job)
        self._scrub_job = self.after(120, lambda: self._do_scrub(val))

    def _do_scrub(self, val):
        self._play_range(val, None, paused=True)
        self._scrubbing = False

    def _reset_prep_btn(self):
        self.prep_btn.configure(text="1. PREP 📤")

    def _check_render_success(self, out_path):
        self._reset_prep_btn()
        if out_path and os.path.exists(out_path):
            self.last_prep_file = os.path.abspath(out_path)

    def send_to_program(self):
        evs = self._selected_events()
        if not evs: 
            messagebox.showwarning("No Clips Selected", "Select a clip first.")
            return
            
        self.prep_btn.configure(text="⏳ RENDERING...")

        if len(evs) == 1:
            ev = evs[0]
            ang = ev.get("angle")
            if not ang or ang not in ev["masters"]: ang = next(iter(ev["masters"]))
            path, start, end = self.engine.angle_range(ev, ang)
            speed = ev.get("speed", self.speed)
            
            self.last_prep_duration = (end - start) / speed
            
            def work():
                out_path = self.engine.render_program(path, start, end, speed)
                self.ui(self._check_render_success, out_path)
            threading.Thread(target=work, daemon=True).start()
        else:
            items = []
            total_dur = 0.0
            for ev in evs:
                ang = ev.get("angle")
                if not ang or ang not in ev["masters"]: ang = next(iter(ev["masters"]))
                sp = ev.get("speed", self.speed)
                path, start, end = self.engine.angle_range(ev, ang)
                items.append({"path": path, "start": start, "end": end, "speed": sp})
                total_dur += (end - start) / sp
                
            self.last_prep_duration = total_dur
            
            def work():
                out_path = self.engine.render_playlist(items, transition="DISSOLVE", trans_dur=0.5)
                self.ui(self._check_render_success, out_path)
            threading.Thread(target=work, daemon=True).start()

    def send_mosaic_to_program(self):
        evs = self._selected_events()
        if not evs: return
        ev = evs[0]
        angles = list(ev["masters"].keys())[:4] 
        if len(angles) < 2:
            messagebox.showwarning("Mosaic Error", "Need at least 2 camera angles to create a mosaic.")
            return
            
        self.prep_mosaic_btn.configure(text="⏳ RENDERING...")
        
        path, start, end = self.engine.angle_range(ev, self.angle if self.angle in ev["masters"] else angles[0])
        speed = ev.get("speed", self.speed)
        self.last_prep_duration = (end - start) / speed
        
        def work():
            out_path = self.engine.render_program_mosaic(ev, angles, start, end, speed)
            self.ui(lambda p=out_path: self._check_mosaic_success(p))
            
        threading.Thread(target=work, daemon=True).start()

    def _check_mosaic_success(self, out_path):
        self.prep_mosaic_btn.configure(text="🔲 MOSAIC")
        if out_path and os.path.exists(out_path):
            self.last_prep_file = os.path.abspath(out_path)

    def export_clip(self):
        evs = self._selected_events()
        if not evs: return
        
        export_dir = os.path.join(os.path.expanduser("~"), "Desktop", "VALO_EXPORTS")
        os.makedirs(export_dir, exist_ok=True)
        
        self.export_btn.configure(text="⏳ EXPORTING...")
        
        def work():
            for ev in evs:
                ang = ev.get("angle")
                if not ang or ang not in ev["masters"]: ang = next(iter(ev["masters"]))
                path, start, end = self.engine.angle_range(ev, ang)
                speed = ev.get("speed", self.speed)
                
                safe_label = "".join([c for c in ev['label'] if c.isalpha() or c.isdigit() or c==' ']).rstrip()
                out_path = os.path.join(export_dir, f"{safe_label}_{ang}.mp4")
                
                self.engine.render_clip(path, start, end, speed, out_path)
            
            self.ui(lambda: self.export_btn.configure(text="💾 EXPORT"))
            self.ui(lambda: messagebox.showinfo("Export Complete", f"Clips exported to:\n{export_dir}"))
            
        threading.Thread(target=work, daemon=True).start()

    def trigger_obs_scene(self):
        if not hasattr(self, 'obs_client') or not self.obs_client:
            messagebox.showwarning("OBS Disconnected", "Connect OBS first.")
            return

        def work():
            try:
                rep_scene = getattr(self.engine, 'settings', {}).get('obs_replay_scene', 'REPLAY')
                live_scene = getattr(self.engine, 'settings', {}).get('obs_live_scene', 'LIVE_GAME')
                source_name = getattr(self.engine, 'settings', {}).get('obs_media_source', 'Instant Replay Video')
                dur = getattr(self, 'last_prep_duration', 5.0)
                file_path = getattr(self, 'last_prep_file', os.path.abspath(self.engine.program_out_file))

                try: self.obs_client.set_input_settings(name=source_name, settings={"local_file": file_path}, overlay=True)
                except: pass

                self.obs_client.set_current_program_scene(rep_scene)
                time.sleep(dur)
                self.obs_client.set_current_program_scene(live_scene)
            except Exception as e: print(f"OBS Transition Failed: {e}")

        threading.Thread(target=work, daemon=True).start()

    def delete_selected(self):
        evs = self._selected_events()
        if not evs: return
        if not messagebox.askyesno("Delete", f"Delete {len(evs)} clip(s)?"): return
        ids = {e["id"] for e in evs}
        for ws in self.workspaces: ws["events"] = [e for e in ws["events"] if e["id"] not in ids]
        if self.selected_event and self.selected_event["id"] in ids:
            self.selected_event = None
            self.engine.player.stop()
            self.preview_lbl.configure(image="", text="No Clip Loaded")
        self._save_state()
        self._refresh_event_rows()

    def add_workspace(self):
        name = f"Workspace {len(self.workspaces) + 1}"
        self.workspaces.append({"name": name, "events": []})
        self._save_state()
        self._rebuild_ws_ui()
        self.ws_tabs.set(name)
        self._on_ws_tab(name)

    def delete_workspace(self):
        if len(self.workspaces) < 2: return
        self.workspaces.pop(self.ws_idx)
        self.ws_idx = max(0, self.ws_idx - 1)
        self._save_state()
        self._rebuild_ws_ui()

    def _rebuild_ws_ui(self):
        names = [w["name"] for w in self.workspaces]
        self.ws_tabs.configure(values=names)
        self.ws_tabs.set(names[self.ws_idx])
        self._refresh_event_rows()

    def _on_ws_tab(self, name):
        names = [w["name"] for w in self.workspaces]
        if name in names:
            self.ws_idx = names.index(name)
            self._save_state()
            self._refresh_event_rows()

    def _tick_ui(self):
        p = self.engine.player
        self._draw_preview()
        ev = self.selected_event
        if ev and p.path and p.path == self._cur_path() and not self.pl_running:
            t = min(self._timeline_pos(), ev["length"])
            fmt_t = f"{int(t//60):02d}:{t%60:05.2f}"
            fmt_len = f"{int(ev['length']//60):02d}:{ev['length']%60:05.2f}"
            self.time_lbl.configure(text=f"{fmt_t} / {fmt_len}")
            if not self._scrubbing: self.timeline.set(t)
        self.after(40, self._tick_ui)

    def _bind_shortcuts(self):
        if hasattr(self, '_bound_keys'):
            for k in self._bound_keys:
                try: self.unbind(k)
                except: pass
        self._bound_keys = []
        
        hk = self.engine.settings.get('hotkeys', DEFAULT_HOTKEYS)
        
        def tk_bind(k_id, action):
            key = hk.get(k_id, "")
            if not key: return
            tk_str = key
            if len(key) == 1 and key.isalnum(): tk_str = f"<KeyPress-{key.lower()}>"
            elif not key.startswith("<"): tk_str = f"<{key}>"
            try:
                self.bind(tk_str, action)
                self._bound_keys.append(tk_str)
            except: pass

        tk_bind("mark_1", lambda e: self.mark(1))
        tk_bind("mark_5", lambda e: self.mark(5))
        tk_bind("mark_7", lambda e: self.mark(7))
        tk_bind("mark_10", lambda e: self.mark(10))
        tk_bind("mark_15", lambda e: self.mark(15))
        
        tk_bind("play_pause", lambda e: self.toggle_play())
        tk_bind("prep_clip", lambda e: self.send_to_program())
        tk_bind("delete_clip", lambda e: self.delete_selected())
        
        tk_bind("set_in", lambda e: self.set_now("in"))
        tk_bind("set_out", lambda e: self.set_now("out"))
        tk_bind("nudge_in_back", lambda e: self.nudge("in", -0.5))
        tk_bind("nudge_in_fwd", lambda e: self.nudge("in", 0.5))
        
        tk_bind("speed_100", lambda e: self.set_speed_value(1.0))
        tk_bind("speed_75", lambda e: self.set_speed_value(0.75))
        tk_bind("speed_50", lambda e: self.set_speed_value(0.5))
        tk_bind("speed_25", lambda e: self.set_speed_value(0.25))

        self._rebuild_mark_buttons()

    def on_closing(self):
        self.engine.player.stop()
        self.engine.stop_all()
        self.destroy()

if __name__ == "__main__":
    app = ValoReplayDeck()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()