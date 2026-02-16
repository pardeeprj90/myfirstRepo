"""Backward-compatible entrypoint for the Delivery Assurance agent.

Production code now lives in ``src/wsr_assurance/delivery_assurance.py``.
This wrapper keeps existing imports stable while the project transitions
to a package-based layout.
"""

from src.wsr_assurance.delivery_assurance import *  # noqa: F401,F403
