"""Health-information resources: MedlinePlus Connect (patient education),
ClinicalTrials.gov (trials), DailyMed (full drug labels). Free, no key.
See :mod:`app.services.health_resources.service`.
"""

from app.services.health_resources.service import HealthResourcesService

__all__ = ["HealthResourcesService"]
