"""Jordanian Digital Heritage Platform: Celery workers.

A thin task layer over the API's services (ADR-0001 D17): every database write goes through
``jdhp_api`` service functions under the restricted worker role.
"""

__version__ = "0.1.0"
