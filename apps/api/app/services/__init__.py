"""Business rules.

Validation, permission enforcement, timetable clash checking and bulk-import
staging belong here rather than in the routers, so the same rule is applied to
every caller (SRS 2.3, ACC-06).
"""
