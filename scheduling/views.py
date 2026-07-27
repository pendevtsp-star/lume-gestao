"""Compatibility facade for scheduling web views.

Concrete views are grouped by domain under :mod:`scheduling.web`. Imports
from this module remain supported so URL names and external callers keep the
same public API.
"""

from scheduling.web.agenda_creation import *  # noqa: F401,F403
from scheduling.web.availability_configuration_packages import *  # noqa: F401,F403
from scheduling.web.common import *  # noqa: F401,F403
from scheduling.web.notifications_events import *  # noqa: F401,F403
from scheduling.web.rescheduling_attendance import *  # noqa: F401,F403
