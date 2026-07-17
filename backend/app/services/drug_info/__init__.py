"""Drug-information service: DrugBank (DDI) + openFDA (recalls/labels/events)
+ RxNorm (name normalization). See :mod:`app.services.drug_info.service`.
"""

from app.services.drug_info.service import DrugInfoService

__all__ = ["DrugInfoService"]
