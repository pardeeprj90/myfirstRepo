"""Backward-compatible entrypoint for the WSR workflow module.

Production code now lives in ``src/wsr_assurance/workflow.py``.
This wrapper keeps existing imports stable while the project transitions
to a package-based layout.
"""

from src.wsr_assurance.workflow import *  # noqa: F401,F403


if __name__ == "__main__":
    from src.wsr_assurance.workflow import main

    main()
