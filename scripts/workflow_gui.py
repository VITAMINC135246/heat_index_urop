#!/usr/bin/env python3
"""Small Tk desktop launcher for the ordinary-user heat workflow."""

from __future__ import annotations

import json
import os
import queue
import signal
import subprocess
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / "scripts" / "run_user_workflow.py"
SDK_CONFIG = PROJECT_ROOT / "config" / "part_d_sdk.local.json"


class WorkflowGUI:
    MODES = {
        "单组 V/T 图片": "group",
        "多组 V/T 图片": "groups",
        "数据集目录": "dataset",
        "五张已验收 pilot": "five-pilots",
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Heat Index UROP")
        self.root.geometry("920x720")
        self.root.minsize(760, 600)
        self.process: subprocess.Popen[bytes] | None = None
        self.messages: queue.Queue[tuple[str, object]] = queue.Queue()
        self.latest_run: Path | None = None

        self.mode = tk.StringVar(value=next(iter(self.MODES)))
        self.visible = tk.StringVar()
        self.thermal = tk.StringVar()
        self.dataset = tk.StringVar()
        self.tat3 = tk.StringVar()
        self.part_c_draft = tk.StringVar()
        self.production = tk.BooleanVar(value=False)
        self.redraw = tk.BooleanVar(value=False)
        self.polygon_all = tk.BooleanVar(value=False)
        self.target_name = tk.StringVar(value="HKUST football field")
        self.target_id = tk.StringVar(value="hkust-football-field-natural-turf")
        self.surface_cover = tk.StringVar(value="grass_low_vegetation")
        self.luhk = tk.StringVar(value="GIC / open space")
        self.confidence = tk.StringVar(value="medium")
        self.status = tk.StringVar(value="就绪")
        self.sdk_status = tk.StringVar()
        self.response = tk.StringVar()
        self.group_pairs: list[tuple[str, str]] = []

        self._build()
        self._update_mode()
        self._check_sdk()
        self.root.after(100, self._drain_messages)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(10, weight=1)

        ttk.Label(outer, text="本地热环境分析", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10)
        )
        ttk.Label(outer, text="运行模式").grid(row=1, column=0, sticky="w", pady=4)
        mode_box = ttk.Combobox(outer, textvariable=self.mode, values=list(self.MODES), state="readonly")
        mode_box.grid(row=1, column=1, sticky="ew", pady=4)
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self._update_mode())

        self.visible_widgets = self._path_row(outer, 2, "可见光 V", self.visible, self._choose_visible)
        self.multi_frame = ttk.LabelFrame(outer, text="多组 V/T 输入", padding=6)
        self.multi_frame.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=4)
        self.multi_frame.columnconfigure(0, weight=1)
        self.pair_tree = ttk.Treeview(
            self.multi_frame,
            columns=("visible", "thermal"),
            show="headings",
            height=5,
        )
        self.pair_tree.heading("visible", text="可见光 V")
        self.pair_tree.heading("thermal", text="热图 T")
        self.pair_tree.column("visible", width=360, stretch=True)
        self.pair_tree.column("thermal", width=360, stretch=True)
        self.pair_tree.grid(row=0, column=0, columnspan=2, sticky="nsew")
        ttk.Button(self.multi_frame, text="添加 V/T 对…", command=self._add_pair).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Button(self.multi_frame, text="移除选中", command=self._remove_pairs).grid(
            row=1, column=1, sticky="e", pady=(6, 0)
        )
        self.thermal_widgets = self._path_row(outer, 3, "热图 T", self.thermal, self._choose_thermal)
        self.dataset_widgets = self._path_row(outer, 4, "数据集目录", self.dataset, self._choose_dataset)
        self.tat3_widgets = self._path_row(outer, 5, "TAT3 报告", self.tat3, self._choose_tat3)
        self.draft_widgets = self._path_row(outer, 6, "Part C 草稿", self.part_c_draft, self._choose_draft)

        self.polygon_frame = ttk.LabelFrame(outer, text="多组目标多边形（Part C*）", padding=6)
        self.polygon_frame.grid(row=7, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        self.polygon_frame.columnconfigure(1, weight=1)
        self.polygon_frame.columnconfigure(3, weight=1)
        ttk.Checkbutton(
            self.polygon_frame,
            text="全部图片使用同一目标类型并分别绘制多边形",
            variable=self.polygon_all,
        ).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Label(self.polygon_frame, text="目标名称").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(self.polygon_frame, textvariable=self.target_name).grid(row=1, column=1, sticky="ew", padx=(6, 14))
        ttk.Label(self.polygon_frame, text="稳定目标 ID").grid(row=1, column=2, sticky="w", pady=3)
        ttk.Entry(self.polygon_frame, textvariable=self.target_id).grid(row=1, column=3, sticky="ew", padx=(6, 0))
        ttk.Label(self.polygon_frame, text="表面覆盖").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(self.polygon_frame, textvariable=self.surface_cover).grid(row=2, column=1, sticky="ew", padx=(6, 14))
        ttk.Label(self.polygon_frame, text="LUHK").grid(row=2, column=2, sticky="w", pady=3)
        ttk.Entry(self.polygon_frame, textvariable=self.luhk).grid(row=2, column=3, sticky="ew", padx=(6, 0))
        ttk.Label(self.polygon_frame, text="审核置信度").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Combobox(
            self.polygon_frame,
            textvariable=self.confidence,
            values=("low", "medium", "high"),
            state="readonly",
        ).grid(row=3, column=1, sticky="w", padx=(6, 14))

        options = ttk.Frame(outer)
        options.grid(row=8, column=0, columnspan=3, sticky="ew", pady=(8, 4))
        ttk.Checkbutton(options, text="写入正式 production 输出", variable=self.production).pack(side="left")
        ttk.Checkbutton(options, text="忽略已接受缓存并重新审核", variable=self.redraw).pack(side="left", padx=18)

        readiness = ttk.Frame(outer)
        readiness.grid(row=9, column=0, columnspan=3, sticky="ew", pady=5)
        ttk.Label(readiness, textvariable=self.sdk_status).pack(side="left")
        ttk.Button(readiness, text="重新检查", command=self._check_sdk).pack(side="right")

        log_frame = ttk.LabelFrame(outer, text="运行日志", padding=6)
        log_frame.grid(row=10, column=0, columnspan=3, sticky="nsew", pady=(6, 8))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap="word", state="disabled", font=("Consolas", 10))
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        response_frame = ttk.Frame(outer)
        response_frame.grid(row=11, column=0, columnspan=3, sticky="ew", pady=4)
        response_frame.columnconfigure(1, weight=1)
        ttk.Label(response_frame, text="程序提问时回复").grid(row=0, column=0, sticky="w")
        response_entry = ttk.Entry(response_frame, textvariable=self.response)
        response_entry.grid(row=0, column=1, sticky="ew", padx=8)
        response_entry.bind("<Return>", lambda _event: self._send_response())
        ttk.Button(response_frame, text="发送", command=self._send_response).grid(row=0, column=2)

        actions = ttk.Frame(outer)
        actions.grid(row=12, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        self.start_button = ttk.Button(actions, text="开始运行", command=self._start)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(actions, text="停止", command=self._stop, state="disabled")
        self.stop_button.pack(side="left", padx=8)
        self.open_button = ttk.Button(actions, text="打开最近结果", command=self._open_results, state="disabled")
        self.open_button.pack(side="left")
        ttk.Label(actions, textvariable=self.status).pack(side="right")

    def _path_row(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, command):
        label_widget = ttk.Label(parent, text=label)
        entry = ttk.Entry(parent, textvariable=variable)
        button = ttk.Button(parent, text="浏览…", command=command)
        label_widget.grid(row=row, column=0, sticky="w", pady=4)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        button.grid(row=row, column=2, padx=(8, 0), pady=4)
        return (label_widget, entry, button)

    @staticmethod
    def _show(widgets, visible: bool) -> None:
        for widget in widgets:
            if visible:
                widget.grid()
            else:
                widget.grid_remove()

    def _update_mode(self) -> None:
        mode = self.MODES[self.mode.get()]
        group = mode == "group"
        groups = mode == "groups"
        dataset = mode == "dataset"
        self._show(self.visible_widgets, group)
        if groups:
            self.multi_frame.grid()
            self.polygon_frame.grid()
        else:
            self.multi_frame.grid_remove()
            self.polygon_frame.grid_remove()
        self._show(self.thermal_widgets, group)
        self._show(self.dataset_widgets, dataset)
        self._show(self.tat3_widgets, group or groups or dataset)
        self._show(self.draft_widgets, group)

    def _choose_visible(self) -> None:
        value = filedialog.askopenfilename(title="选择可见光图片", filetypes=[("JPEG", "*.jpg *.jpeg"), ("All", "*.*")])
        if value:
            self.visible.set(value)

    def _choose_thermal(self) -> None:
        value = filedialog.askopenfilename(title="选择热图", filetypes=[("JPEG", "*.jpg *.jpeg"), ("All", "*.*")])
        if value:
            self.thermal.set(value)

    def _choose_dataset(self) -> None:
        value = filedialog.askdirectory(title="选择数据集目录")
        if value:
            self.dataset.set(value)

    def _choose_tat3(self) -> None:
        values = filedialog.askopenfilenames(title="选择一个或多个 TAT3 DOCX", filetypes=[("Word report", "*.docx")])
        if values:
            self.tat3.set(";".join(values))

    def _choose_draft(self) -> None:
        value = filedialog.askopenfilename(title="选择 Part C 草稿", filetypes=[("Review JSON", "*.json")])
        if value:
            self.part_c_draft.set(value)

    def _add_pair(self) -> None:
        visible = filedialog.askopenfilename(
            title="选择这一组的可见光 V 图片",
            filetypes=[("JPEG", "*.jpg *.jpeg"), ("All", "*.*")],
        )
        if not visible:
            return
        thermal = filedialog.askopenfilename(
            title="选择与它匹配的热图 T",
            filetypes=[("JPEG", "*.jpg *.jpeg"), ("All", "*.*")],
        )
        if not thermal:
            return
        pair = (str(Path(visible)), str(Path(thermal)))
        self.group_pairs.append(pair)
        self.pair_tree.insert("", "end", values=pair)

    def _remove_pairs(self) -> None:
        selected = list(self.pair_tree.selection())
        indices = sorted((self.pair_tree.index(item) for item in selected), reverse=True)
        for item in selected:
            self.pair_tree.delete(item)
        for index in indices:
            self.group_pairs.pop(index)

    def _check_sdk(self) -> bool:
        try:
            payload = json.loads(SDK_CONFIG.read_text(encoding="utf-8"))
            executable = Path(str(payload["dji_irp_exe"]))
            ready = executable.is_file()
            self.sdk_status.set(f"SDK：{'就绪' if ready else '缺少 dji_irp.exe'} — {executable}")
            return ready
        except (OSError, KeyError, ValueError, json.JSONDecodeError) as exc:
            self.sdk_status.set(f"SDK：配置不可用 — {exc}")
            return False

    def _command(self) -> list[str]:
        mode = self.MODES[self.mode.get()]
        command = [sys.executable, str(WORKFLOW)]
        if self.production.get():
            command.append("--production")
        command.append(mode)
        if mode == "group":
            visible = Path(self.visible.get().strip())
            thermal = Path(self.thermal.get().strip())
            if not visible.is_file() or not thermal.is_file():
                raise ValueError("请选择存在的 V/T 图片。")
            command.extend([str(visible), str(thermal)])
            for report in filter(None, (value.strip() for value in self.tat3.get().split(";"))):
                command.extend(["--tat3-report", report])
            draft = self.part_c_draft.get().strip()
            if draft:
                command.extend(["--resume-part-c", draft])
            if self.redraw.get():
                command.append("--redraw-review")
        elif mode == "groups":
            if not self.group_pairs:
                raise ValueError("请至少添加一组 V/T 图片。")
            for visible_value, thermal_value in self.group_pairs:
                visible = Path(visible_value)
                thermal = Path(thermal_value)
                if not visible.is_file() or not thermal.is_file():
                    raise ValueError(f"多组列表中存在缺失文件：{visible} / {thermal}")
                command.extend(["--group", str(visible), str(thermal)])
            for report in filter(None, (value.strip() for value in self.tat3.get().split(";"))):
                command.extend(["--tat3-report", report])
            if self.redraw.get():
                command.append("--redraw-review")
            if self.polygon_all.get():
                if not self.target_name.get().strip() or not self.target_id.get().strip():
                    raise ValueError("Part C* 多组分析需要目标名称和稳定目标 ID。")
                command.extend(
                    [
                        "--polygon-all",
                        "--target-name", self.target_name.get().strip(),
                        "--target-id", self.target_id.get().strip(),
                        "--surface-cover", self.surface_cover.get().strip(),
                        "--luhk", self.luhk.get().strip(),
                        "--confidence", self.confidence.get(),
                    ]
                )
        elif mode == "dataset":
            dataset = Path(self.dataset.get().strip())
            if not dataset.is_dir():
                raise ValueError("请选择存在的数据集目录。")
            command.append(str(dataset))
            for report in filter(None, (value.strip() for value in self.tat3.get().split(";"))):
                command.extend(["--tat3-report", report])
            if self.redraw.get():
                command.append("--redraw-review")
        return command

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _start(self) -> None:
        if self.process is not None:
            return
        try:
            command = self._command()
        except ValueError as exc:
            messagebox.showerror("无法开始", str(exc), parent=self.root)
            return
        self._append_log("\n=== 开始新任务 ===\n")
        self.status.set("运行中")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.open_button.configure(state="disabled")
        threading.Thread(target=self._worker, args=(command,), daemon=True).start()

    def _worker(self, command: list[str]) -> None:
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        try:
            self.process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=flags,
            )
            assert self.process.stdout is not None
            while chunk := os.read(self.process.stdout.fileno(), 4096):
                self.messages.put(("log", chunk.decode("utf-8", errors="replace")))
            code = self.process.wait()
            self.messages.put(("done", code))
        except Exception as exc:  # GUI boundary: render unexpected launch errors.
            self.messages.put(("error", str(exc)))

    def _send_response(self) -> None:
        value = self.response.get()
        process = self.process
        if process is None or process.stdin is None or process.poll() is not None:
            return
        try:
            process.stdin.write((value + "\n").encode("utf-8"))
            process.stdin.flush()
            self._append_log(f"> {value}\n")
            self.response.set("")
        except OSError as exc:
            messagebox.showerror("无法发送", str(exc), parent=self.root)

    def _stop(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        if not messagebox.askyesno("停止任务", "停止当前运行？已完成的 Canonical 缓存不会删除。", parent=self.root):
            return
        try:
            if os.name == "nt":
                process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                process.terminate()
            self.status.set("正在停止")
        except OSError:
            pass

    def _newest_run(self) -> Path | None:
        relative = "outputs/runs/v0_3" if self.production.get() else "outputs/runs/v0_3_user_acceptance/workflow_runs"
        root = PROJECT_ROOT / relative
        candidates = [path for path in root.glob("run_*") if path.is_dir()]
        return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None

    def _open_results(self) -> None:
        run = self.latest_run or self._newest_run()
        if run is None:
            messagebox.showinfo("没有结果", "尚未找到运行目录。", parent=self.root)
            return
        if os.name == "nt":
            os.startfile(run)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(run)])

    def _drain_messages(self) -> None:
        try:
            while True:
                kind, payload = self.messages.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "done":
                    self.process = None
                    self.latest_run = self._newest_run()
                    self.status.set("完成" if payload == 0 else f"结束，退出码 {payload}")
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self.open_button.configure(state="normal" if self.latest_run else "disabled")
                elif kind == "error":
                    self.process = None
                    self.status.set("启动失败")
                    self.start_button.configure(state="normal")
                    self.stop_button.configure(state="disabled")
                    self._append_log(f"ERROR: {payload}\n")
        except queue.Empty:
            pass
        self.root.after(100, self._drain_messages)

    def _close(self) -> None:
        if self.process is not None and self.process.poll() is None:
            messagebox.showwarning("任务仍在运行", "请先停止当前任务。", parent=self.root)
            return
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    WorkflowGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
