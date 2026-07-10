#!/usr/bin/env python3
import argparse
import os
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

import rclpy
from rclpy.node import Node
from rclpy.parameter_client import AsyncParameterClient
from sensor_msgs.msg import JointState
from std_msgs.msg import Float32MultiArray
from std_msgs.msg import String


JOINT_COUNTS = {
    "L6": 6,
    "O6": 6,
    "L7": 7,
    "L10": 10,
    "L20": 20,
    "L21": 21,
    "L25": 25,
    "G20": 16,
    "O20": 34,
}

# Per-model position slider defaults (joint order matches README). Length should
# equal JOINT_COUNTS[model]; position_defaults() pads with 255 / truncates as a
# safety net.
POSITION_DEFAULTS = {model: [255] * count for model, count in JOINT_COUNTS.items()}
POSITION_DEFAULTS["G20"] = [255, 255, 255, 255, 255, 255, 130, 125, 125,
                            125, 255, 255, 255, 255, 255, 255]


def position_defaults(model):
    count = JOINT_COUNTS.get(model, 0)
    values = POSITION_DEFAULTS.get(model, [])
    return [values[i] if i < len(values) else 255 for i in range(count)]


FINGER_NAMES = ("拇指", "食指", "中指", "无名指", "小指")
STATE_LABELS = {"position": "位置", "speed": "速度", "torque": "力矩"}


class HandControlPublisher(Node):
    def __init__(self, topic):
        super().__init__("hand_control_gui")
        self.topic = None
        self.publisher = None
        self.state_topic = None
        self.touch_topic = None
        self.info_topic = None
        self.state_subscription = None
        self.touch_subscription = None
        self.info_subscription = None
        self.latest_state = None
        self.latest_touch = []
        self.latest_info = ""
        self.data_lock = threading.Lock()
        self.set_topic(topic)

    def set_topic(self, topic):
        if topic == self.topic:
            return
        if self.publisher is not None:
            self.destroy_publisher(self.publisher)
        self.topic = topic
        self.publisher = self.create_publisher(JointState, topic, 10)

    def set_feedback_topics(self, state_topic, touch_topic, info_topic):
        if state_topic != self.state_topic:
            if self.state_subscription is not None:
                self.destroy_subscription(self.state_subscription)
            self.state_topic = state_topic
            self.state_subscription = self.create_subscription(
                JointState, state_topic, self.state_callback, 10
            )
        if touch_topic != self.touch_topic:
            if self.touch_subscription is not None:
                self.destroy_subscription(self.touch_subscription)
            self.touch_topic = touch_topic
            self.touch_subscription = self.create_subscription(
                Float32MultiArray, touch_topic, self.touch_callback, 10
            )
        if info_topic != self.info_topic:
            if self.info_subscription is not None:
                self.destroy_subscription(self.info_subscription)
            self.info_topic = info_topic
            self.info_subscription = self.create_subscription(
                String, info_topic, self.info_callback, 10
            )

    def state_callback(self, msg):
        with self.data_lock:
            self.latest_state = msg

    def touch_callback(self, msg):
        with self.data_lock:
            self.latest_touch = list(msg.data)

    def info_callback(self, msg):
        with self.data_lock:
            self.latest_info = msg.data

    def get_feedback(self):
        with self.data_lock:
            return self.latest_state, list(self.latest_touch), self.latest_info

    def publish_command(self, positions, speeds, torques):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.position = [float(v) for v in positions]
        msg.velocity = [float(v) for v in speeds]
        msg.effort = [float(v) for v in torques]
        self.publisher.publish(msg)

    def get_remote_parameter(self, node_name, parameter_name, timeout_sec=1.0):
        client = AsyncParameterClient(self, node_name)
        wait_for_service = getattr(client, "wait_for_service", None)
        if wait_for_service is None:
            wait_for_service = client.wait_for_services
        if not wait_for_service(timeout_sec=timeout_sec):
            return None
        future = client.get_parameters([parameter_name])
        rclpy.spin_until_future_complete(self, future, timeout_sec=timeout_sec)
        if not future.done() or future.result() is None:
            return None
        values = future.result().values
        if not values:
            return None
        return values[0].string_value


class HandControlGui:
    BG = "#eaedf3"
    CARD = "#ffffff"
    TEXT = "#111827"
    MUTED = "#4b5563"
    BORDER = "#c4cad6"
    TROUGH = "#d1d5db"
    ACCENT = "#0a5fff"
    ACCENT_HOVER = "#0846d1"
    ACCENT_PRESS = "#0637a3"
    GREEN = "#22c55e"
    GRAY_DOT = "#9ca3af"

    def __init__(self, node, model, side, topic, live_publish, publish_rate_hz):
        self.node = node
        self.closed = False

        self.root = tk.Tk()
        self.root.title("LinkerHand")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.minsize(1080, 720)
        self.root.configure(background=self.BG)

        self.font_family = self._pick_font_family()
        self.configure_style()

        self.model_var = tk.StringVar(value=model)
        self.side_var = tk.StringVar(value=side)
        self.topic_var = tk.StringVar(value=topic)
        self.state_topic_var = tk.StringVar()
        self.touch_topic_var = tk.StringVar()
        self.info_topic_var = tk.StringVar()
        self.live_var = tk.BooleanVar(value=live_publish)
        self.rate_var = tk.IntVar(value=max(1, int(publish_rate_hz)))
        self.joint_count = JOINT_COUNTS[model]
        self._current_model = model
        self.command_dirty = False

        self.middle_container = None
        self.feedback_container = None
        self.control_container = None
        self.touch_canvases = []
        self.latest_touch_values = []

        self.position_vars = [tk.IntVar(value=v) for v in position_defaults(model)]
        self.speed_vars = [tk.IntVar(value=255) for _ in range(self.joint_count)]
        self.torque_vars = [tk.IntVar(value=255) for _ in range(self.joint_count)]
        self.watch_command_vars()
        self.current_metric = "position"
        self._metric_tab_buttons = {}
        self._sliders_body = None
        self._slider_traces = []

        self.state_vars = {key: tk.StringVar(value="—") for key in STATE_LABELS}
        self.info_vars = []

        self.status_var = tk.StringVar(value="已就绪")
        self.status_dot = None
        self.live_dot = None
        self.summary_var = tk.StringVar()

        self.update_feedback_topics()
        self._build()
        self.publish_loop()
        self.refresh_feedback()

    # ---------- style ----------

    def _pick_font_family(self):
        try:
            families = set(tkfont.families(self.root))
        except tk.TclError:
            families = set()
        for name in (
            "SF Pro Text", "SF Pro Display", ".AppleSystemUIFont",
            "PingFang SC", "Helvetica Neue", "Segoe UI",
            "Noto Sans CJK SC", "Ubuntu",
        ):
            if name in families:
                return name
        return tkfont.nametofont("TkDefaultFont").actual("family")

    def _load_logo(self):
        # Resolve logo.png: prefer installed share dir, fall back to source tree
        # (for `colcon build --symlink-install` or direct script execution).
        path = None
        try:
            from ament_index_python.packages import get_package_share_directory
            candidate = os.path.join(
                get_package_share_directory("linker_hand_cpp_ros2"),
                "assets", "logo.png",
            )
            if os.path.exists(candidate):
                path = candidate
        except Exception:
            pass
        if path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            for rel in ("../assets/logo.png", "../../assets/logo.png"):
                cand = os.path.abspath(os.path.join(script_dir, rel))
                if os.path.exists(cand):
                    path = cand
                    break
        if path is None:
            return None
        try:
            img = tk.PhotoImage(file=path)
        except tk.TclError:
            return None
        # Downscale so the ~181px-tall source fits inside the 58px toolbar.
        target_h = 40
        h = img.height() or target_h
        factor = max(1, round(h / target_h))
        return img.subsample(factor, factor) if factor > 1 else img

    def configure_style(self):
        f = self.font_family
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.CARD)

        style.configure("TLabel", background=self.BG, foreground=self.TEXT, font=(f, 11))
        style.configure("Muted.TLabel", background=self.BG, foreground=self.MUTED, font=(f, 10))
        style.configure("Brand.TLabel", background=self.CARD, foreground=self.TEXT,
                        font=(f, 15, "bold"))
        style.configure("ToolbarLabel.TLabel", background=self.CARD, foreground=self.MUTED,
                        font=(f, 11))
        style.configure("Section.TLabel", background=self.BG, foreground=self.MUTED,
                        font=(f, 10, "bold"))

        style.configure(
            "Flat.TButton",
            background=self.CARD, foreground=self.TEXT,
            bordercolor=self.BORDER, lightcolor=self.BORDER, darkcolor=self.BORDER,
            borderwidth=1, padding=(14, 6), font=(f, 11), relief="flat", focusthickness=0,
        )
        style.map(
            "Flat.TButton",
            background=[("active", "#e5e7ec"), ("pressed", "#d5d8df")],
            bordercolor=[("active", self.BORDER)],
        )
        style.configure(
            "Accent.TButton",
            background=self.ACCENT, foreground="#ffffff",
            borderwidth=0, padding=(16, 6), font=(f, 11, "bold"), relief="flat",
            focusthickness=0,
        )
        style.map(
            "Accent.TButton",
            background=[("active", self.ACCENT_HOVER), ("pressed", self.ACCENT_PRESS)],
        )

        for name in ("TEntry",):
            style.configure(
                name,
                fieldbackground=self.CARD, foreground=self.TEXT,
                bordercolor=self.BORDER, lightcolor=self.BORDER, darkcolor=self.BORDER,
                insertcolor=self.TEXT, padding=6,
            )
            style.map(
                name,
                foreground=[("!disabled", self.TEXT), ("disabled", self.MUTED)],
                fieldbackground=[("!disabled", self.CARD)],
                bordercolor=[("focus", self.ACCENT)],
                lightcolor=[("focus", self.ACCENT)],
                darkcolor=[("focus", self.ACCENT)],
            )

        style.configure(
            "TCombobox",
            fieldbackground=self.CARD, background=self.CARD, foreground=self.TEXT,
            bordercolor=self.BORDER, lightcolor=self.BORDER, darkcolor=self.BORDER,
            arrowcolor=self.TEXT, padding=5,
            selectbackground=self.CARD, selectforeground=self.TEXT,
        )
        style.map(
            "TCombobox",
            foreground=[("readonly", self.TEXT), ("!disabled", self.TEXT)],
            fieldbackground=[("readonly", self.CARD), ("!disabled", self.CARD)],
            selectbackground=[("readonly", self.CARD)],
            selectforeground=[("readonly", self.TEXT)],
            bordercolor=[("focus", self.ACCENT)],
            lightcolor=[("focus", self.ACCENT)],
            darkcolor=[("focus", self.ACCENT)],
        )
        # Combobox dropdown listbox (a separate Tk widget outside ttk styling).
        self.root.option_add("*TCombobox*Listbox.background", self.CARD)
        self.root.option_add("*TCombobox*Listbox.foreground", self.TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", self.ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.font", (f, 11))

        style.configure(
            "TSpinbox",
            fieldbackground=self.CARD, background=self.CARD, foreground=self.TEXT,
            bordercolor=self.BORDER, lightcolor=self.BORDER, darkcolor=self.BORDER,
            arrowcolor=self.TEXT, padding=4,
            selectbackground=self.ACCENT, selectforeground="#ffffff",
        )
        style.map(
            "TSpinbox",
            foreground=[("!disabled", self.TEXT), ("disabled", self.MUTED)],
            fieldbackground=[("!disabled", self.CARD)],
            bordercolor=[("focus", self.ACCENT)],
            lightcolor=[("focus", self.ACCENT)],
            darkcolor=[("focus", self.ACCENT)],
        )

        # Scale: slider (thumb) uses `background`, track uses `troughcolor`.
        # Setting slider to accent blue makes it clearly visible on the white card.
        style.configure(
            "Horizontal.TScale",
            background=self.ACCENT, troughcolor=self.TROUGH,
            bordercolor=self.ACCENT, lightcolor=self.ACCENT, darkcolor=self.ACCENT,
        )
        style.map(
            "Horizontal.TScale",
            background=[("active", self.ACCENT_HOVER), ("pressed", self.ACCENT_PRESS)],
        )

        style.configure(
            "Switch.TCheckbutton",
            background=self.CARD, foreground=self.TEXT,
            indicatorbackground=self.CARD, indicatorforeground=self.ACCENT,
            font=(f, 11), focusthickness=0, padding=2,
        )
        style.map(
            "Switch.TCheckbutton",
            background=[("active", self.CARD)],
        )

        style.configure(
            "Vertical.TScrollbar",
            background=self.BG, troughcolor=self.CARD,
            bordercolor=self.CARD, arrowcolor=self.MUTED, gripcount=0,
        )
        style.map("Vertical.TScrollbar", background=[("active", self.TROUGH)])

    # ---------- build ----------

    def _build(self):
        self._build_toolbar()

        tk.Frame(self.root, background=self.BORDER, height=1).grid(
            row=1, column=0, sticky="ew"
        )

        self.main = ttk.Frame(self.root, padding=(20, 14, 20, 14), style="App.TFrame")
        self.main.grid(row=2, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(0, weight=1)

        self.middle_container = ttk.Frame(self.main, style="App.TFrame")
        self.middle_container.grid(row=0, column=0, sticky="nsew")
        self.middle_container.columnconfigure(0, weight=2)
        self.middle_container.columnconfigure(1, weight=1)
        self.middle_container.rowconfigure(0, weight=1)

        self._build_feedback(self.middle_container)
        self._build_control(self.middle_container)
        self.update_summary()

        tk.Frame(self.root, background=self.BORDER, height=1).grid(
            row=3, column=0, sticky="ew"
        )
        self._build_footer()

    def _build_footer(self):
        bar = tk.Frame(self.root, background=self.CARD, height=60)
        bar.grid(row=4, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.columnconfigure(0, weight=1)
        if self._logo_image is not None:
            tk.Label(
                bar, image=self._logo_image, background=self.CARD,
                borderwidth=0, highlightthickness=0,
            ).grid(row=0, column=0, pady=8)
        else:
            ttk.Label(bar, text="LinkerHand", style="Brand.TLabel").grid(
                row=0, column=0, pady=14
            )

    def _build_toolbar(self):
        bar = tk.Frame(self.root, background=self.CARD, height=45)
        bar.grid(row=0, column=0, sticky="ew")
        bar.grid_propagate(False)
        bar.rowconfigure(0, weight=1)
        bar.columnconfigure(4, weight=1)

        self._logo_image = self._load_logo()

        ttk.Label(bar, text="型号", style="ToolbarLabel.TLabel").grid(
            row=0, column=0, padx=(22, 6)
        )
        model_box = ttk.Combobox(
            bar, textvariable=self.model_var, values=sorted(JOINT_COUNTS),
            state="readonly", width=6,
        )
        model_box.grid(row=0, column=1, padx=(0, 22))
        model_box.bind(
            "<<ComboboxSelected>>",
            lambda _e, w=model_box: (self.apply_model(), self._clear_combo_selection(w)),
        )

        ttk.Label(bar, text="侧别", style="ToolbarLabel.TLabel").grid(
            row=0, column=2, padx=(0, 6)
        )
        side_box = ttk.Combobox(
            bar, textvariable=self.side_var, values=("left", "right"),
            state="readonly", width=6,
        )
        side_box.grid(row=0, column=3, padx=(0, 22))
        side_box.bind(
            "<<ComboboxSelected>>",
            lambda _e, w=side_box: (self.apply_side_topic(), self._clear_combo_selection(w)),
        )

        self.live_dot = tk.Canvas(
            bar, width=10, height=10, background=self.CARD, highlightthickness=0
        )
        self.live_dot.grid(row=0, column=5, padx=(0, 6))
        ttk.Checkbutton(
            bar, text="实时", variable=self.live_var, style="Switch.TCheckbutton",
            command=self._refresh_live_dot,
        ).grid(row=0, column=6, padx=(0, 22))
        self._refresh_live_dot()
        self.live_var.trace_add("write", lambda *_a: self._refresh_live_dot())

    def _refresh_live_dot(self):
        if self.live_dot is None:
            return
        color = self.GREEN if self.live_var.get() else self.GRAY_DOT
        self.live_dot.delete("all")
        self.live_dot.create_oval(1, 1, 9, 9, fill=color, outline="")

    def _clear_combo_selection(self, widget):
        try:
            widget.selection_clear()
        except tk.TclError:
            pass
        self.root.focus_set()

    def _card(self, parent):
        return tk.Frame(
            parent, background=self.CARD,
            highlightthickness=1, highlightbackground=self.BORDER,
        )

    def _build_feedback(self, parent):
        if self.feedback_container is not None:
            self.feedback_container.destroy()

        container = ttk.Frame(parent, style="App.TFrame")
        container.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        container.columnconfigure(0, weight=1)
        # Touch card (row 3) takes remaining vertical space; state card (row 1)
        # sits on top with natural single-line height.
        container.rowconfigure(3, weight=1)
        self.feedback_container = container

        ttk.Label(container, text="反馈", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        state_card = self._card(container)
        state_card.grid(row=1, column=0, sticky="ew")
        state_card.columnconfigure(0, minsize=76)
        state_card.columnconfigure(1, weight=1)

        self._feedback_value_labels = []
        self._feedback_last_width = 0

        row_idx = 0
        for key, var in self.state_vars.items():
            self._state_row(state_card, row_idx, STATE_LABELS[key], var)
            row_idx += 1

        self.info_vars = []
        for i in range(6):
            var = tk.StringVar(value="—")
            self.info_vars.append(var)
            self._state_row(state_card, row_idx, f"信息 {i + 1}", var,
                            last=(i == 5))
            row_idx += 1

        state_card.bind(
            "<Configure>",
            lambda e: self._update_feedback_wraplength(e.width),
        )

        ttk.Label(container, text="触觉", style="Section.TLabel").grid(
            row=2, column=0, sticky="w", pady=(14, 6)
        )
        touch_card = self._card(container)
        touch_card.grid(row=3, column=0, sticky="nsew")
        touch_card.rowconfigure(0, weight=1)

        self.touch_canvases = []
        cw, ch = self.touch_canvas_size()
        for finger in range(5):
            touch_card.columnconfigure(finger, weight=1)
            cell = tk.Frame(touch_card, background=self.CARD)
            cell.grid(row=0, column=finger, sticky="nsew", padx=6, pady=(12, 4))
            cell.columnconfigure(0, weight=1)
            cell.rowconfigure(0, weight=1)
            canvas = tk.Canvas(
                cell, width=cw, height=ch,
                background=self.CARD, highlightthickness=0,
            )
            canvas.grid(row=0, column=0, sticky="nsew")
            canvas.bind("<Configure>", lambda _e: self.redraw_touch_matrix())
            self.touch_canvases.append(canvas)
            tk.Label(
                touch_card, text=FINGER_NAMES[finger],
                background=self.CARD, foreground=self.MUTED,
                font=(self.font_family, 10),
            ).grid(row=1, column=finger, pady=(0, 10))

    def _update_feedback_wraplength(self, card_width):
        # Debounce: only apply when width changes meaningfully.
        if abs(card_width - self._feedback_last_width) < 4:
            return
        self._feedback_last_width = card_width
        # 14px left + 76px label col + 14px gap + 14px right ≈ 118px chrome.
        target = max(120, card_width - 118)
        for lbl in self._feedback_value_labels:
            try:
                lbl.configure(wraplength=target)
            except tk.TclError:
                pass

    def _state_row(self, parent, row, label_text, var, last=False):
        top = 10 if row == 0 else 4
        bottom = 12 if last else 4
        tk.Label(
            parent, text=label_text,
            background=self.CARD, foreground=self.MUTED,
            font=(self.font_family, 10),
        ).grid(row=row, column=0, padx=(14, 14), pady=(top, bottom), sticky="nw")
        val_lbl = tk.Label(
            parent, textvariable=var,
            background=self.CARD, foreground=self.TEXT,
            font=(self.font_family, 11), anchor="nw", justify="left",
            # width=1 lets the column's own weight decide horizontal size, so
            # long text never expands the card. wraplength is refreshed by
            # _update_feedback_wraplength() so overflow wraps to a new line
            # inside the value column instead of being clipped.
            width=1, wraplength=320,
        )
        val_lbl.grid(row=row, column=1, padx=(0, 14), pady=(top, bottom), sticky="ew")
        self._feedback_value_labels.append(val_lbl)

    def _build_control(self, parent):
        if self.control_container is not None:
            self.control_container.destroy()

        container = ttk.Frame(parent, style="App.TFrame")
        container.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)
        self.control_container = container

        ttk.Label(container, text="控制", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 6)
        )
        card = self._card(container)
        card.grid(row=1, column=0, sticky="nsew")
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)

        # Segmented tabs: 位置 / 速度 / 力矩
        seg = tk.Frame(card, background=self.TROUGH, highlightthickness=0)
        seg.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 10))
        self._metric_tab_buttons = {}
        for i, (key, label) in enumerate(
            (("position", "位置"), ("speed", "速度"), ("torque", "力矩"))
        ):
            seg.columnconfigure(i, weight=1)
            btn = tk.Label(
                seg, text=label,
                background=self.TROUGH, foreground=self.TEXT,
                font=(self.font_family, 11), padx=12, pady=6, cursor="hand2",
            )
            btn.grid(row=0, column=i, sticky="ew", padx=2, pady=2)
            btn.bind("<Button-1>", lambda _e, k=key: self._set_metric(k))
            self._metric_tab_buttons[key] = btn

        # Scrollable body host — three metric pages are stacked at the same cell
        # and switched with tkraise() so there is no destroy/rebuild flicker.
        canvas = tk.Canvas(card, background=self.CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(
            card, orient="vertical", command=canvas.yview,
            style="Vertical.TScrollbar",
        )
        body = tk.Frame(canvas, background=self.CARD)
        window_id = canvas.create_window((0, 0), window=body, anchor="nw")

        body.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda e: canvas.itemconfigure(window_id, width=e.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=1, column=0, sticky="nsew", padx=(14, 0), pady=(0, 10))
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 6), pady=(0, 10))
        self._bind_mousewheel(canvas)

        footer = tk.Frame(card, background=self.CARD)
        footer.grid(row=2, column=0, columnspan=2, sticky="ew",
                    padx=10, pady=(0, 6))
        footer.columnconfigure(0, weight=1)
        link = tk.Label(
            footer, text="复制位置",
            background=self.CARD, foreground=self.MUTED,
            font=(self.font_family, 10), cursor="hand2", padx=2, pady=2,
        )
        link.grid(row=0, column=1, sticky="e")
        link.bind("<Button-1>", lambda _e: self._copy_positions())
        link.bind("<Enter>", lambda _e: link.configure(foreground=self.ACCENT))
        link.bind("<Leave>", lambda _e: link.configure(foreground=self.MUTED))

        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self._sliders_body = body
        self._slider_traces = []
        self._metric_frames = {}
        self._metric_vars = {
            "position": self.position_vars,
            "speed": self.speed_vars,
            "torque": self.torque_vars,
        }

        self._ensure_metric_page(self.current_metric)
        self._refresh_metric_tabs()
        self._metric_frames[self.current_metric].tkraise()

    def _bind_mousewheel(self, canvas):
        def _on_wheel(event):
            if event.num == 4 or getattr(event, "delta", 0) > 0:
                canvas.yview_scroll(-3, "units")
            elif event.num == 5 or getattr(event, "delta", 0) < 0:
                canvas.yview_scroll(3, "units")

        def _bind(_e):
            canvas.bind_all("<MouseWheel>", _on_wheel)
            canvas.bind_all("<Button-4>", _on_wheel)
            canvas.bind_all("<Button-5>", _on_wheel)

        def _unbind(_e):
            canvas.unbind_all("<MouseWheel>")
            canvas.unbind_all("<Button-4>")
            canvas.unbind_all("<Button-5>")

        canvas.bind("<Enter>", _bind)
        canvas.bind("<Leave>", _unbind)

    def _ensure_metric_page(self, key):
        if key in self._metric_frames:
            return
        vars_list = self._metric_vars[key]
        page = tk.Frame(self._sliders_body, background=self.CARD)
        page.grid(row=0, column=0, sticky="nsew")
        page.columnconfigure(0, weight=0, minsize=44)
        page.columnconfigure(1, weight=1)
        for i, var in enumerate(vars_list):
            tk.Label(
                page, text=f"J{i + 1}",
                background=self.CARD, foreground=self.MUTED,
                font=(self.font_family, 11),
            ).grid(row=i, column=0, sticky="w", padx=(0, 12), pady=8)
            self._add_slider(page, i, 1, var)
        self._metric_frames[key] = page

    def _set_metric(self, key):
        if key == self.current_metric:
            return
        self.current_metric = key
        self._ensure_metric_page(key)
        self._refresh_metric_tabs()
        page = self._metric_frames.get(key)
        if page is not None:
            page.tkraise()

    def _refresh_metric_tabs(self):
        for k, btn in self._metric_tab_buttons.items():
            if k == self.current_metric:
                btn.configure(background=self.CARD, foreground=self.TEXT,
                              font=(self.font_family, 11, "bold"))
            else:
                btn.configure(background=self.TROUGH, foreground=self.MUTED,
                              font=(self.font_family, 11))

    def _add_slider(self, parent, row, column, variable):
        frame = tk.Frame(parent, background=self.CARD)
        frame.grid(row=row, column=column, padx=(0, 8), pady=4, sticky="ew")
        frame.columnconfigure(0, weight=1)
        validate_int = (self.root.register(self.validate_byte_text), "%P")

        slider_h = 24
        thumb_r = 7
        pad = thumb_r + 2
        canvas = tk.Canvas(
            frame, height=slider_h, background=self.CARD,
            highlightthickness=0, borderwidth=0,
        )
        canvas.grid(row=0, column=0, sticky="ew")

        y = slider_h // 2
        track_id = canvas.create_line(0, y, 0, y, fill=self.TROUGH,
                                      width=2, capstyle="round")
        fill_id = canvas.create_line(0, y, 0, y, fill=self.ACCENT,
                                     width=2, capstyle="round")
        thumb_id = canvas.create_oval(0, 0, 0, 0, fill=self.ACCENT, outline="")

        def _redraw():
            w = max(1, canvas.winfo_width())
            try:
                v = variable.get()
            except tk.TclError:
                v = 0
            frac = max(0.0, min(1.0, v / 255.0))
            x0, x1 = pad, w - pad
            if x1 <= x0:
                x1 = x0 + 1
            cx = x0 + frac * (x1 - x0)
            canvas.coords(track_id, x0, y, x1, y)
            canvas.coords(fill_id, x0, y, cx, y)
            canvas.coords(thumb_id, cx - thumb_r, y - thumb_r,
                          cx + thumb_r, y + thumb_r)

        def _jump(event):
            w = max(1, canvas.winfo_width())
            x0, x1 = pad, w - pad
            span = max(1, x1 - x0)
            frac = max(0.0, min(1.0, (event.x - x0) / span))
            self.set_int_value(variable, frac * 255)
            return "break"

        canvas.bind("<Configure>", lambda _e: _redraw())
        canvas.bind("<Button-1>", _jump)
        canvas.bind("<B1-Motion>", _jump)

        trace_id = variable.trace_add("write", lambda *_a: _redraw())
        self._slider_traces.append((variable, trace_id))

        ttk.Spinbox(
            frame, from_=0, to=255, width=4, textvariable=variable,
            validate="key", validatecommand=validate_int,
        ).grid(row=0, column=1, padx=(8, 0))

    # ---------- helpers ----------

    def set_int_value(self, variable, value):
        variable.set(max(0, min(255, int(round(float(value))))))

    def _copy_positions(self):
        text = ", ".join(str(var.get()) for var in self.position_vars)
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_var.set(f"已复制位置到剪贴板 ({len(self.position_vars)} 关节)")

    def validate_byte_text(self, text):
        if text == "":
            return True
        if not text.isdigit():
            return False
        return 0 <= int(text) <= 255

    def apply_side_topic(self):
        self.topic_var.set(f"/{self.side_var.get()}_hand_control")
        self.update_feedback_topics()
        self.apply_topic()

    def apply_topic(self):
        topic = self.topic_var.get().strip()
        if not topic.startswith("/"):
            topic = f"/{topic}"
            self.topic_var.set(topic)
        self.node.set_topic(topic)
        self.update_summary()

    def apply_model(self):
        model = self.model_var.get()
        if model == getattr(self, "_current_model", None):
            return
        self._current_model = model
        old_speeds = [var.get() for var in self.speed_vars]
        old_torques = [var.get() for var in self.torque_vars]
        old_touch_shape = self.touch_shape()
        old_canvas_size = self.touch_canvas_size()
        self.joint_count = JOINT_COUNTS[model]
        self.position_vars = [tk.IntVar(value=v) for v in position_defaults(model)]
        self.speed_vars = self.resize_vars(old_speeds, 255)
        self.torque_vars = self.resize_vars(old_torques, 255)
        self.watch_command_vars()
        if (self.touch_shape() != old_touch_shape
                or self.touch_canvas_size() != old_canvas_size):
            self._build_feedback(self.middle_container)
        else:
            self.redraw_touch_matrix()
        self._build_control(self.middle_container)
        self.update_summary()
        self.command_dirty = False

    def resize_vars(self, values, default):
        resized = []
        for index in range(self.joint_count):
            value = values[index] if index < len(values) else default
            resized.append(tk.IntVar(value=value))
        return resized

    def watch_command_vars(self):
        for variable in self.position_vars + self.speed_vars + self.torque_vars:
            variable.trace_add("write", self.mark_command_dirty)

    def mark_command_dirty(self, *_args):
        self.command_dirty = True

    def update_summary(self):
        self.summary_var.set(
            f"{self.side_var.get()} · {self.model_var.get()} · "
            f"{self.joint_count} 关节 · 状态 {self.state_topic_var.get()} · "
            f"触觉 {self.touch_topic_var.get()}"
        )

    def update_feedback_topics(self):
        side = self.side_var.get()
        self.state_topic_var.set(f"/{side}_hand_state")
        self.touch_topic_var.set(f"/{side}_hand_touch")
        self.info_topic_var.set(f"/{side}_hand_info")
        self.node.set_feedback_topics(
            self.state_topic_var.get(),
            self.touch_topic_var.get(),
            self.info_topic_var.get(),
        )

    def publish(self):
        self.command_dirty = False
        positions = [var.get() for var in self.position_vars]
        speeds = [var.get() for var in self.speed_vars]
        torques = [var.get() for var in self.torque_vars]
        self.node.publish_command(positions, speeds, torques)
        self.status_var.set(
            f"已发送 {len(positions)} 关节 → {self.node.topic}"
        )

    def publish_loop(self):
        if self.closed:
            return
        if self.live_var.get() and self.command_dirty:
            self.publish()
        period_ms = max(1, round(1000 / max(1, self.rate_var.get())))
        self.root.after(period_ms, self.publish_loop)

    # ---------- feedback rendering ----------

    def refresh_feedback(self):
        if self.closed:
            return
        state, touch, info = self.node.get_feedback()
        if state is not None:
            self.state_vars["position"].set(self.format_values(state.position))
            self.state_vars["speed"].set(self.format_values(state.velocity))
            self.state_vars["torque"].set(self.format_values(state.effort))
        if info:
            self.update_info_lines(info)
        if touch:
            self.update_touch_matrix(touch)
        self.root.after(100, self.refresh_feedback)

    def update_info_lines(self, info):
        lines = [part.strip() for part in info.splitlines() if part.strip()]
        for index, var in enumerate(self.info_vars):
            var.set(lines[index] if index < len(lines) else "—")

    def format_values(self, values):
        return " ".join(str(int(value)) for value in values[: self.joint_count])

    def update_touch_matrix(self, values):
        self.latest_touch_values = list(values)
        rows, cols = self.touch_shape()
        cells_per_finger = rows * cols
        for finger in range(5):
            matrix = []
            for row in range(rows):
                row_values = []
                for col in range(cols):
                    index = finger * cells_per_finger + row * cols + col
                    row_values.append(int(values[index]) if index < len(values) else 0)
                matrix.append(row_values)
            self.draw_heatmap(self.touch_canvases[finger], matrix)

    def redraw_touch_matrix(self):
        if self.latest_touch_values:
            self.update_touch_matrix(self.latest_touch_values)

    def touch_shape(self):
        if self.model_var.get() == "O6":
            return 10, 4
        return 12, 6

    def display_shape(self):
        return self.touch_shape()

    def touch_canvas_size(self):
        if self.model_var.get() == "O6":
            return 60, 130
        return 78, 156

    def draw_heatmap(self, canvas, matrix):
        display_rows, display_cols = self.display_shape()
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        padding = 4
        usable_w = max(1, width - padding * 2)
        usable_h = max(1, height - padding * 2)
        target_ratio = display_cols / display_rows
        usable_ratio = usable_w / usable_h
        if usable_ratio > target_ratio:
            draw_h = usable_h
            draw_w = draw_h * target_ratio
        else:
            draw_w = usable_w
            draw_h = draw_w / target_ratio
        x_off = (width - draw_w) / 2
        y_off = (height - draw_h) / 2
        cell_w = draw_w / display_cols
        cell_h = draw_h / display_rows
        canvas.delete("all")
        for row in range(display_rows):
            for col in range(display_cols):
                value = self.display_value(matrix, row, col)
                x1 = x_off + col * cell_w
                y1 = y_off + row * cell_h
                canvas.create_rectangle(
                    x1, y1, x1 + cell_w, y1 + cell_h,
                    fill=self.heat_color(value),
                    outline="#dfe3ea", width=1,
                )

    def display_value(self, matrix, display_row, display_col):
        if display_row < len(matrix) and display_col < len(matrix[display_row]):
            return matrix[display_row][display_col]
        return 0

    # Heatmap gradient: near-neutral idle, then cool→warm spectrum
    # (cyan → green → amber → red) so each pressure level has a distinct hue.
    _HEAT_STOPS = (
        (0.00, (0xee, 0xf2, 0xf7)),
        (0.25, (0x06, 0xb6, 0xd4)),
        (0.50, (0x22, 0xc5, 0x5e)),
        (0.75, (0xf5, 0x9e, 0x0b)),
        (1.00, (0xdc, 0x26, 0x26)),
    )

    def heat_color(self, value):
        value = max(0, min(255, int(value)))
        ratio = value / 255.0
        stops = self._HEAT_STOPS
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if ratio <= p1:
                t = (ratio - p0) / (p1 - p0) if p1 > p0 else 0.0
                r = int(c0[0] + (c1[0] - c0[0]) * t)
                g = int(c0[1] + (c1[1] - c0[1]) * t)
                b = int(c0[2] + (c1[2] - c0[2]) * t)
                return f"#{r:02x}{g:02x}{b:02x}"
        r, g, b = stops[-1][1]
        return f"#{r:02x}{g:02x}{b:02x}"

    # ---------- lifecycle ----------

    def run(self):
        self.root.mainloop()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.root.quit()
        self.root.destroy()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--side", default="left", choices=("left", "right"))
    parser.add_argument("--topic", default=None)
    parser.add_argument(
        "--model",
        default=None,
        choices=sorted(JOINT_COUNTS),
        help="hand model; auto-read HAND_JOINTS from the running hand node when omitted",
    )
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="disable auto-publish; useful for silent debugging",
    )
    parser.add_argument("--rate", type=int, default=60, help="live publish rate in Hz")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.rate <= 0:
        raise SystemExit("--rate must be greater than 0")
    topic = args.topic or f"/{args.side}_hand_control"

    rclpy.init()
    node = HandControlPublisher(topic)
    model = args.model or read_hand_model(node, args.side) or "O6"

    gui = HandControlGui(
        node=node,
        model=model,
        side=args.side,
        topic=topic,
        live_publish=not args.no_live,
        publish_rate_hz=args.rate,
    )
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()
    try:
        gui.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


def read_hand_model(node, side):
    node_name = f"/linker_hand_{side}_node"
    model = node.get_remote_parameter(node_name, "HAND_JOINTS")
    if model in JOINT_COUNTS:
        return model
    return None


if __name__ == "__main__":
    main()
