"""Environment bootstrap data for TDMS.

Seeds are **not** migrations. `apps/api/alembic/` owns database *structure*;
this package owns the small amount of *data* a fresh environment needs before
anyone can use it. Keeping them apart means a schema rebuild never silently
re-inserts business data, and a data correction never rewrites schema history.
"""

from __future__ import annotations
