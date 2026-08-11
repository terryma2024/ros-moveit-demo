"""Immutable backend profiles and adapters for SO-101 Teleop."""

from .registry import BACKEND_IDS, load_backend_profile

__all__ = ["BACKEND_IDS", "load_backend_profile"]
