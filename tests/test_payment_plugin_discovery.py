from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

from src.modules.payment.plugin_discovery import importable_payment_modules


def test_discovers_source_and_native_payment_modules(tmp_path: Path):
    (tmp_path / "stripe_provider.py").write_text("", encoding="utf-8")
    (tmp_path / "paylio_provider.abi3.so").write_bytes(b"\x7fELF")
    (tmp_path / "__init__.py").write_text("", encoding="utf-8")

    assert [name for name, _ in importable_payment_modules(tmp_path)] == [
        "paylio_provider",
        "stripe_provider",
    ]


def test_native_module_wins_when_source_and_extension_both_exist(tmp_path: Path):
    suffix = ".abi3.so" if ".abi3.so" in EXTENSION_SUFFIXES else EXTENSION_SUFFIXES[0]
    source = tmp_path / "stripe_provider.py"
    native = tmp_path / f"stripe_provider{suffix}"
    source.write_text("", encoding="utf-8")
    native.write_bytes(b"\x7fELF")

    assert importable_payment_modules(tmp_path) == [("stripe_provider", native)]
