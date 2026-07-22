"""Shared desktop Matplotlib backend selection for interactive workflow GUIs."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


NONINTERACTIVE_BACKENDS = {"agg", "cairo", "pdf", "pgf", "ps", "svg", "template"}


def _configure_windows_tk_runtime() -> bool:
    """Make bundled Tcl/Tk libraries discoverable on Windows.

    Tcl 8.6 can mis-normalize a path component that begins with a dot (the
    Codex runtime lives below ``.cache``).  Windows extended paths bypass that
    normalization bug while still using the runtime's original Tcl/Tk files.
    System Python installations with a user-provided Tcl library are left
    untouched.
    """
    if os.name != "nt" or os.environ.get("TCL_LIBRARY"):
        return False

    runtime_tcl_root = Path(sys.base_prefix) / "tcl"
    tcl_candidates = sorted(runtime_tcl_root.glob("tcl8.*"), reverse=True)
    tk_candidates = sorted(runtime_tcl_root.glob("tk8.*"), reverse=True)
    real_tcl = next((path for path in tcl_candidates if (path / "init.tcl").is_file()), None)
    real_tk = next((path for path in tk_candidates if (path / "tk.tcl").is_file()), None)
    if real_tcl is None or real_tk is None:
        return False

    def extended(path: Path) -> str:
        value = path.resolve().as_posix()
        if value.startswith("//?/"):
            return value
        if value.startswith("//"):
            return f"//?/UNC/{value[2:]}"
        return f"//?/{value}"

    os.environ["TCL_LIBRARY"] = extended(real_tcl)
    os.environ.setdefault("TK_LIBRARY", extended(real_tk))
    return True


def interactive_pyplot(gui_name: str = "Workflow GUI") -> Any:
    """Return pyplot on a desktop backend after headless plotting was used.

    The workflow intentionally uses Agg for reports.  A later review GUI must
    switch back to TkAgg instead of silently treating ``plt.show()`` as a
    completed/cancelled annotation.
    """
    try:
        if os.name == "nt":
            _configure_windows_tk_runtime()
            # A clean GUI subprocess can declare DPI awareness before Tk is
            # imported.  Without this, Windows 150% scaling can put the right
            # image and bottom buttons outside the actual window.
            import ctypes

            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                ctypes.windll.user32.SetProcessDPIAware()
        import matplotlib.pyplot as plt

        if str(plt.get_backend()).casefold() in NONINTERACTIVE_BACKENDS:
            plt.switch_backend("TkAgg")
    except (ImportError, RuntimeError) as exc:
        raise RuntimeError(
            f"{gui_name} requires a working Tk desktop backend. "
            "Install/enable tkinter and do not force MPLBACKEND=Agg for interactive runs."
        ) from exc
    return plt
