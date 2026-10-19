"""Concurrency cap shared by the fan-out bulk verbs.

Lives in its own module so the bulk tool modules (``bulk_tag_machines``,
``bulk_untag_machines``, ``bulk_power_control_machines``,
``bulk_release_machines``) can import the constant without depending on
each other.
"""

from __future__ import annotations

_FANOUT_CONCURRENCY = 10
