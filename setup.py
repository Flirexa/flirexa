#!/usr/bin/env python3
"""
Flirexa Setup
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="flirexa",
    version="1.5.0",
    author="Flirexa",
    author_email="support@flirexa.biz",
    description="Open-core VPN management for WireGuard, AmneziaWG, Hysteria2, TUIC",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/Flirexa/flirexa",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "flirexa=src.cli.main:main",
            "vpnmanager=src.cli.main:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Environment :: Web Environment",
        "Framework :: FastAPI",
        "Intended Audience :: System Administrators",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Internet :: Proxy Servers",
        "Topic :: System :: Networking",
    ],
)
