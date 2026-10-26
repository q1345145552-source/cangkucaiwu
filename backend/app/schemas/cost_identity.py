from typing import Optional
from pydantic import BaseModel,Field

class CostFields(BaseModel):
    supplier_id:Optional[int]=None
    invoice_identity:Optional[dict]=None
    cost_confirmation:Optional[dict]=None
    request_key:Optional[str]=Field(default=None,max_length=100)
