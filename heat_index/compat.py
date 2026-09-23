"""Compatibility only: old imports/CLIs share a single implementation module."""
from importlib import import_module
import runpy
import sys


def expose(name, namespace, target):
    if name == "__main__":
        runpy.run_module(target, run_name="__main__")
    else:
        module = import_module(target)
        namespace.update({key: value for key, value in vars(module).items()
                          if not key.startswith("__")})
        sys.modules[name] = module
