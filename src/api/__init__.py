"""
VPN Management Studio REST API Module
FastAPI-based API for all VPN Management Studio operations
"""

from .main import app, create_app

__all__ = ["app", "create_app"]
