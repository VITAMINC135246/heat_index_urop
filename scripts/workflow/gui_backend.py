"""Shared desktop Matplotlib backend selection for interactive workflow GUIs."""

from __future__ import annotations

import os
from typing import Any


NONINTERACTIVE_BACKENDS = {"agg", "cairo", "pdf", "pgf", "ps", "svg", "template"}


def interactive_pyplot(gui_name: str = "Workflow GUI") -> Any:
    """Return pyplot on a desktop backend after headless plotting was used.

    The workflow intentionally uses Agg for reports.  A later review GUI must
    switch back to TkAgg instead of silently treating ``plt.show()`` as a
    completed/cancelled annotation.
    """
    try:
        if os.name == "nt":
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
