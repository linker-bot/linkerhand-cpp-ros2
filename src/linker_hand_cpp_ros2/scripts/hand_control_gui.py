#!/usr/bin/env python3
import argparse
import threading
import tkinter as tk
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

FINGER_NAMES = ("Thumb", "Index", "Middle", "Ring", "Little")


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
    def __init__(self, node, model, side, topic, live_publish, publish_rate_hz):
        self.node = node
        self.closed = False

        self.root = tk.Tk()
        self.root.title("LinkerHand Control Panel")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.minsize(980, 720)
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
        self.command_dirty = False

        self.main = None
        self.table_container = None
        self.feedback_container = None
        self.position_vars = [tk.IntVar(value=255) for _ in range(self.joint_count)]
        self.speed_vars = [tk.IntVar(value=255) for _ in range(self.joint_count)]
        self.torque_vars = [tk.IntVar(value=255) for _ in range(self.joint_count)]
        self.watch_command_vars()
        self.state_vars = {
            "position": tk.StringVar(value="-"),
            "speed": tk.StringVar(value="-"),
            "torque": tk.StringVar(value="-"),
        }
        self.info_vars = []
        self.touch_labels = []
        self.touch_canvases = []
        self.latest_touch_values = []
        self.update_feedback_topics()

        self._build()
        self.publish_loop()
        self.refresh_feedback()

    def _build(self):
        self.main = ttk.Frame(self.root, padding=10)
        self.main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        self._build_config(self.main)
        self._build_joint_table()
        self._build_feedback(self.main)
        self._build_controls(self.main)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self.main, textvariable=self.status, style="Status.TLabel").grid(
            row=4, column=0, sticky="ew", pady=(8, 0)
        )

    def configure_style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TLabelframe", padding=8)
        style.configure("TLabelframe.Label", font=("TkDefaultFont", 10, "bold"))
        style.configure("Header.TLabel", font=("TkDefaultFont", 10, "bold"))
        style.configure("Status.TLabel", foreground="#555555")

    def _build_config(self, parent):
        config = ttk.LabelFrame(parent, text="Configuration")
        config.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        config.columnconfigure(5, weight=1)

        ttk.Label(config, text="Side").grid(row=0, column=0, padx=(0, 4), sticky="w")
        side_box = ttk.Combobox(
            config,
            textvariable=self.side_var,
            values=("left", "right"),
            state="readonly",
            width=7,
        )
        side_box.grid(row=0, column=1, padx=(0, 10), sticky="w")
        side_box.bind("<<ComboboxSelected>>", lambda _event: self.apply_side_topic())

        ttk.Label(config, text="Model").grid(row=0, column=2, padx=(0, 4), sticky="w")
        model_box = ttk.Combobox(
            config,
            textvariable=self.model_var,
            values=sorted(JOINT_COUNTS),
            state="readonly",
            width=7,
        )
        model_box.grid(row=0, column=3, padx=(0, 10), sticky="w")
        model_box.bind("<<ComboboxSelected>>", lambda _event: self.apply_model())

        ttk.Label(config, text="Rate").grid(row=0, column=4, padx=(0, 4), sticky="w")
        ttk.Spinbox(config, from_=1, to=200, width=5, textvariable=self.rate_var).grid(
            row=0, column=5, sticky="w"
        )
        ttk.Label(config, text="Hz").grid(row=0, column=6, padx=(4, 10), sticky="w")
        ttk.Checkbutton(config, text="Live", variable=self.live_var).grid(
            row=0, column=7, padx=(0, 10), sticky="w"
        )

        ttk.Label(config, text="Topic").grid(row=1, column=0, padx=(0, 4), pady=(6, 0), sticky="w")
        topic_entry = ttk.Entry(config, textvariable=self.topic_var)
        topic_entry.grid(row=1, column=1, columnspan=6, pady=(6, 0), sticky="ew")
        ttk.Button(config, text="Apply", command=self.apply_topic).grid(
            row=1, column=7, padx=(0, 10), pady=(6, 0), sticky="w"
        )

        self.summary = tk.StringVar()
        ttk.Label(config, textvariable=self.summary, style="Status.TLabel").grid(
            row=2, column=0, columnspan=8, pady=(6, 0), sticky="w"
        )
        self.update_summary()

    def _build_joint_table(self):
        if self.table_container is not None:
            self.table_container.destroy()

        columns = ("joint", "position", "speed", "torque")
        table = self._create_scrollable_table(self.main)
        self.main.rowconfigure(1, weight=1)
        for col in range(4):
            table.columnconfigure(col, weight=1 if col else 0)

        for col, text in enumerate(columns):
            ttk.Label(table, text=text).grid(row=0, column=col, padx=4, pady=4)

        for index in range(self.joint_count):
            row = index + 1
            ttk.Label(table, text=f"J{index + 1}").grid(row=row, column=0, padx=4, sticky="w")
            self._add_slider(table, row, 1, self.position_vars[index])
            self._add_slider(table, row, 2, self.speed_vars[index])
            self._add_slider(table, row, 3, self.torque_vars[index])

    def _build_controls(self, parent):
        controls = ttk.LabelFrame(parent, text="Commands")
        controls.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        controls.columnconfigure(5, weight=1)

        ttk.Button(controls, text="Open", command=lambda: self.set_all_positions(255)).grid(
            row=0, column=0, padx=(0, 6), pady=2
        )
        ttk.Button(controls, text="Half", command=lambda: self.set_all_positions(128)).grid(
            row=0, column=1, padx=6, pady=2
        )
        ttk.Button(controls, text="Close", command=lambda: self.set_all_positions(0)).grid(
            row=0, column=2, padx=6, pady=2
        )
        ttk.Button(controls, text="Publish", command=self.publish).grid(
            row=0, column=3, padx=6, pady=2
        )
        ttk.Button(controls, text="Quit", command=self.close).grid(
            row=0, column=4, padx=6, pady=2
        )

    def _create_scrollable_table(self, parent):
        self.table_container = ttk.LabelFrame(parent, text="Command Values")
        self.table_container.grid(row=1, column=0, sticky="nsew")
        self.table_container.columnconfigure(0, weight=1)
        self.table_container.rowconfigure(0, weight=1)

        canvas = tk.Canvas(self.table_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self.table_container, orient="vertical", command=canvas.yview)
        table = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=table, anchor="nw")

        table.bind(
            "<Configure>",
            lambda _event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>",
            lambda event: canvas.itemconfigure(window_id, width=event.width),
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        scrollbar.grid(row=0, column=1, sticky="ns")
        return table

    def _add_slider(self, parent, row, column, variable):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, padx=4, pady=2, sticky="ew")
        frame.columnconfigure(0, weight=1)
        validate_int = (self.root.register(self.validate_byte_text), "%P")
        scale = ttk.Scale(
            frame,
            from_=0,
            to=255,
            orient="horizontal",
            command=lambda value, var=variable: self.set_int_value(var, value),
        )
        scale.set(variable.get())
        scale.grid(row=0, column=0, sticky="ew")
        # variable.trace_add(
        #     "write",
        #     lambda *_args, var=variable, widget=scale: widget.set(var.get())
        # )
        variable.trace_add(
            "write",
            lambda *_args, var=variable, widget=scale: widget.set(var.get()),
        )
        spin = ttk.Spinbox(
            frame,
            from_=0,
            to=255,
            width=4,
            textvariable=variable,
            validate="key",
            validatecommand=validate_int,
        )
        spin.grid(row=0, column=1, padx=(4, 0))

    def set_int_value(self, variable, value):
        variable.set(max(0, min(255, int(round(float(value))))))

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
        old_positions = [var.get() for var in self.position_vars]
        old_speeds = [var.get() for var in self.speed_vars]
        old_torques = [var.get() for var in self.torque_vars]
        self.joint_count = JOINT_COUNTS[self.model_var.get()]
        self.position_vars = self.resize_vars(old_positions, 255)
        self.speed_vars = self.resize_vars(old_speeds, 255)
        self.torque_vars = self.resize_vars(old_torques, 255)
        self.watch_command_vars()
        self._build_joint_table()
        self._build_feedback(self.main)
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
        self.summary.set(
            f"{self.side_var.get()} {self.model_var.get()} | "
            f"{self.joint_count} joints | {self.topic_var.get()} | "
            f"{self.state_topic_var.get()} | {self.touch_topic_var.get()} | "
            f"{self.info_topic_var.get()}"
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

    def set_all_positions(self, value):
        for var in self.position_vars:
            var.set(value)
        self.publish()

    def publish(self):
        self.command_dirty = False
        positions = [var.get() for var in self.position_vars]
        speeds = [var.get() for var in self.speed_vars]
        torques = [var.get() for var in self.torque_vars]
        self.node.publish_command(positions, speeds, torques)
        self.status.set(f"Published {len(positions)} joints to {self.node.topic}")

    def publish_loop(self):
        if self.closed:
            return
        if self.live_var.get() and self.command_dirty:
            self.publish()
        period_ms = max(1, round(1000 / max(1, self.rate_var.get())))
        self.root.after(period_ms, self.publish_loop)

    def _build_feedback(self, parent):
        if self.feedback_container is not None:
            self.feedback_container.destroy()

        self.feedback_container = ttk.LabelFrame(parent, text="Feedback")
        self.feedback_container.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        self.feedback_container.columnconfigure(0, weight=3)
        self.feedback_container.columnconfigure(1, weight=2)
        self.feedback_container.rowconfigure(0, weight=1)

        state_frame = ttk.LabelFrame(self.feedback_container, text="State / Info")
        state_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        state_frame.columnconfigure(1, weight=1)
        for row, (name, var) in enumerate(self.state_vars.items()):
            ttk.Label(state_frame, text=name).grid(row=row, column=0, padx=4, pady=2, sticky="w")
            ttk.Label(state_frame, textvariable=var, width=64).grid(
                row=row, column=1, padx=4, pady=2, sticky="ew"
            )

        self.info_vars = []
        for index in range(6):
            var = tk.StringVar(value="-")
            self.info_vars.append(var)
            row = len(self.state_vars) + index
            ttk.Label(state_frame, text=f"info {index + 1}").grid(
                row=row, column=0, padx=4, pady=2, sticky="w"
            )
            ttk.Label(state_frame, textvariable=var, width=64).grid(
                row=row, column=1, padx=4, pady=2, sticky="ew"
            )

        touch_frame = ttk.LabelFrame(self.feedback_container, text="Touch")
        touch_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        touch_frame.rowconfigure(0, weight=1)
        self.touch_canvases = []
        canvas_width, canvas_height = self.touch_canvas_size()
        for finger in range(5):
            touch_frame.columnconfigure(finger, weight=1)
            finger_frame = ttk.LabelFrame(touch_frame, text=FINGER_NAMES[finger])
            finger_frame.grid(row=0, column=finger, padx=3, pady=3, sticky="nsew")
            finger_frame.columnconfigure(0, weight=1)
            finger_frame.rowconfigure(0, weight=1)
            canvas = tk.Canvas(
                finger_frame,
                width=canvas_width,
                height=canvas_height,
                highlightthickness=0,
            )
            canvas.grid(row=0, column=0, padx=2, pady=2, sticky="nsew")
            canvas.bind("<Configure>", lambda _event: self.redraw_touch_matrix())
            self.touch_canvases.append(canvas)

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
            var.set(lines[index] if index < len(lines) else "-")

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
            return 56, 120
        return 72, 144

    def draw_heatmap(self, canvas, matrix):
        display_rows, display_cols = self.display_shape()
        width = max(1, canvas.winfo_width())
        height = max(1, canvas.winfo_height())
        padding = 4
        usable_width = max(1, width - padding * 2)
        usable_height = max(1, height - padding * 2)
        target_ratio = display_cols / display_rows
        usable_ratio = usable_width / usable_height
        if usable_ratio > target_ratio:
            draw_height = usable_height
            draw_width = draw_height * target_ratio
        else:
            draw_width = usable_width
            draw_height = draw_width / target_ratio
        x_offset = (width - draw_width) / 2
        y_offset = (height - draw_height) / 2
        cell_w = draw_width / display_cols
        cell_h = draw_height / display_rows
        canvas.delete("all")
        for row in range(display_rows):
            for col in range(display_cols):
                value = self.display_value(matrix, row, col)
                x1 = x_offset + col * cell_w
                y1 = y_offset + row * cell_h
                x2 = x1 + cell_w
                y2 = y1 + cell_h
                canvas.create_rectangle(
                    x1,
                    y1,
                    x2,
                    y2,
                    fill=self.heat_color(value),
                    outline="#333333",
                    width=1,
                )

    def display_value(self, matrix, display_row, display_col):
        if display_row < len(matrix) and display_col < len(matrix[display_row]):
            return matrix[display_row][display_col]
        return 0

    def heat_color(self, value):
        value = max(0, min(255, int(value)))
        if value <= 127:
            ratio = value / 127.0
            red = int(255 * ratio)
            green = int(80 + 175 * ratio)
            blue = int(255 * (1 - ratio))
        else:
            ratio = (value - 127) / 128.0
            red = 255
            green = int(255 * (1 - ratio))
            blue = 0
        return f"#{red:02x}{green:02x}{blue:02x}"

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
        help="only publish when pressing Publish/Open/Half/Close",
    )
    parser.add_argument("--rate", type=int, default=50, help="live publish rate in Hz")
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
