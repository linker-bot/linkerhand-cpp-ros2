#!/usr/bin/env python3
import argparse
import threading
import tkinter as tk
from tkinter import ttk

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState


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


class HandControlPublisher(Node):
    def __init__(self, topic):
        super().__init__("hand_control_gui")
        self.topic = None
        self.publisher = None
        self.set_topic(topic)

    def set_topic(self, topic):
        if topic == self.topic:
            return
        if self.publisher is not None:
            self.destroy_publisher(self.publisher)
        self.topic = topic
        self.publisher = self.create_publisher(JointState, topic, 10)

    def publish_command(self, positions, speeds, torques):
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.position = [float(v) for v in positions]
        msg.velocity = [float(v) for v in speeds]
        msg.effort = [float(v) for v in torques]
        self.publisher.publish(msg)


class HandControlGui:
    def __init__(self, node, model, side, topic, live_publish, publish_rate_hz):
        self.node = node
        self.closed = False

        self.root = tk.Tk()
        self.root.title("LinkerHand Control")
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.minsize(820, 520)

        self.model_var = tk.StringVar(value=model)
        self.side_var = tk.StringVar(value=side)
        self.topic_var = tk.StringVar(value=topic)
        self.live_var = tk.BooleanVar(value=live_publish)
        self.rate_var = tk.IntVar(value=max(1, int(publish_rate_hz)))
        self.joint_count = JOINT_COUNTS[model]

        self.main = None
        self.table_container = None
        self.position_vars = [tk.IntVar(value=255) for _ in range(self.joint_count)]
        self.speed_vars = [tk.IntVar(value=255) for _ in range(self.joint_count)]
        self.torque_vars = [tk.IntVar(value=255) for _ in range(self.joint_count)]

        self._build()
        self.publish_loop()

    def _build(self):
        self.main = ttk.Frame(self.root, padding=12)
        self.main.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._build_config(self.main)
        self._build_joint_table()
        self._build_controls(self.main)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self.main, textvariable=self.status).grid(row=3, column=0, sticky="w", pady=(8, 0))

    def _build_config(self, parent):
        config = ttk.Frame(parent)
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
        ttk.Label(config, textvariable=self.summary).grid(
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
        controls = ttk.Frame(parent)
        controls.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        controls.columnconfigure(5, weight=1)

        ttk.Button(controls, text="Open", command=lambda: self.set_all_positions(255)).grid(
            row=0, column=0, padx=3
        )
        ttk.Button(controls, text="Half", command=lambda: self.set_all_positions(128)).grid(
            row=0, column=1, padx=3
        )
        ttk.Button(controls, text="Close", command=lambda: self.set_all_positions(0)).grid(
            row=0, column=2, padx=3
        )
        ttk.Button(controls, text="Publish", command=self.publish).grid(row=0, column=3, padx=3)
        ttk.Button(controls, text="Quit", command=self.close).grid(row=0, column=4, padx=3)

    def _create_scrollable_table(self, parent):
        self.table_container = ttk.Frame(parent)
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
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        return table

    def _add_slider(self, parent, row, column, variable):
        frame = ttk.Frame(parent)
        frame.grid(row=row, column=column, padx=4, pady=2, sticky="ew")
        frame.columnconfigure(0, weight=1)
        scale = ttk.Scale(
            frame,
            from_=0,
            to=255,
            orient="horizontal",
            variable=variable,
        )
        scale.grid(row=0, column=0, sticky="ew")
        spin = ttk.Spinbox(
            frame,
            from_=0,
            to=255,
            width=4,
            textvariable=variable,
        )
        spin.grid(row=0, column=1, padx=(4, 0))

    def apply_side_topic(self):
        self.topic_var.set(f"/{self.side_var.get()}_hand_control")
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
        self._build_joint_table()
        self.update_summary()

    def resize_vars(self, values, default):
        resized = []
        for index in range(self.joint_count):
            value = values[index] if index < len(values) else default
            resized.append(tk.IntVar(value=value))
        return resized

    def update_summary(self):
        self.summary.set(
            f"{self.side_var.get()} {self.model_var.get()} | "
            f"{self.joint_count} joints | {self.topic_var.get()}"
        )

    def set_all_positions(self, value):
        for var in self.position_vars:
            var.set(value)
        self.publish()

    def publish(self):
        positions = [var.get() for var in self.position_vars]
        speeds = [var.get() for var in self.speed_vars]
        torques = [var.get() for var in self.torque_vars]
        self.node.publish_command(positions, speeds, torques)
        self.status.set(
            f"Published position={positions} speed={speeds} torque={torques}"
        )

    def publish_loop(self):
        if self.closed:
            return
        if self.live_var.get():
            self.publish()
        period_ms = max(1, round(1000 / max(1, self.rate_var.get())))
        self.root.after(period_ms, self.publish_loop)

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
    parser.add_argument("--model", default="O6", choices=sorted(JOINT_COUNTS))
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
    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    gui = HandControlGui(
        node=node,
        model=args.model,
        side=args.side,
        topic=topic,
        live_publish=not args.no_live,
        publish_rate_hz=args.rate,
    )
    try:
        gui.run()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
