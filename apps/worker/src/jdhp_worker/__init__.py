"""Jordanian Digital Heritage Platform: Celery workers.

A thin task layer over the API's services (ADR-0001 D17): every database write goes through
``jdhp_api`` service functions under the restricted worker role.
"""

__version__ = "0.1.0"

# Every worker process writes through the API's services, so the whole schema must be registered
# on the metadata before the first flush: a module that imports one model alone cannot resolve
# the foreign keys to tables it never imported (ADR-0001 D17).
from jdhp_api import models as _models  # noqa: F401
