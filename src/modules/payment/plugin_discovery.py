"""Discover importable payment-provider modules in source or native builds."""

from __future__ import annotations

from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path


def importable_payment_modules(directory: Path) -> list[tuple[str, Path]]:
    """Return unique public module names accepted by Python's package importer."""

    candidates: dict[str, tuple[Path, bool]] = {}
    if not directory.is_dir():
        return []
    for path in directory.iterdir():
        module_name = path.stem if path.suffix == ".py" else None
        is_native = False
        for suffix in EXTENSION_SUFFIXES:
            if path.name.endswith(suffix):
                module_name = path.name[:-len(suffix)]
                is_native = True
                break
        if not module_name or module_name.startswith("_"):
            continue
        previous = candidates.get(module_name)
        if previous is None or (is_native and not previous[1]):
            candidates[module_name] = (path, is_native)
    return [(name, candidates[name][0]) for name in sorted(candidates)]
