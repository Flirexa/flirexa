"""
Flirexa REST API Module
FastAPI-based API for all Flirexa operations
"""

from .main import app, create_app

__all__ = ["app", "create_app"]
