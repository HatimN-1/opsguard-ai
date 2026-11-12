"""Unified OpsGuard AI entrypoint: professional 12-pipeline ADF operations app.

The earlier learning/demo pages remain in backend modules and tests, but the
user-facing interface is now exclusively the fixed-company business scenario.
"""

from __future__ import annotations

from app.dashboard.enterprise_app import main

if __name__ == "__main__":
    main()
