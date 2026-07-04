from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from decimal import Decimal


# ---- Warehouse ----
class WarehouseCreate(BaseModel):
    name: str; name_th: Optional[str] = None; code: str
    address: Optional[str] = None; contact_person: Optional[str] = None
    contact_phone: Optional[str] = None

class WarehouseUpdate(BaseModel):
    name: Optional[str] = None; name_th: Optional[str] = None
    address: Optional[str] = None; contact_person: Optional[str] = None
    contact_phone: Optional[str] = None; is_active: Optional[bool] = None

class WarehouseResponse(BaseModel):
    id: int; name: str; name_th: Optional[str] = None; code: str
    address: Optional[str] = None; contact_person: Optional[str] = None
    is_active: bool; created_at: Optional[datetime] = None
    class Config: from_attributes = True


# ---- Customer ----
class CustomerCreate(BaseModel):
    customer_code: str; company_name: str; warehouse_id: Optional[int] = None
    contact_person: Optional[str] = None; contact_info: Optional[str] = None
    credit_status: bool = False; credit_limit: float = 0; remark: Optional[str] = None

class CustomerUpdate(BaseModel):
    company_name: Optional[str] = None; contact_person: Optional[str] = None
    contact_info: Optional[str] = None; credit_status: Optional[bool] = None
    credit_limit: Optional[float] = None; remark: Optional[str] = None

class CustomerResponse(BaseModel):
    id: int; warehouse_id: int; customer_code: str; company_name: str
    contact_person: Optional[str] = None; contact_info: Optional[str] = None
    credit_status: bool; credit_limit: float; remark: Optional[str] = None
    tags: Optional[dict] = None; created_at: Optional[datetime] = None
    class Config: from_attributes = True


# ---- Payment Account ----
class PaymentAccountCreate(BaseModel):
    account_name: str; account_type: str; account_number: str
    opening_balance: float = 0

class PaymentAccountResponse(BaseModel):
    id: int; warehouse_id: int; account_name: str; account_type: str
    account_number: str; opening_balance: float; created_at: Optional[datetime] = None
    class Config: from_attributes = True


# ---- Supplier ----
class SupplierCreate(BaseModel):
    name: str; contact_person: Optional[str] = None
    contact_info: Optional[str] = None; address: Optional[str] = None
    payment_terms: Optional[str] = None

class SupplierUpdate(BaseModel):
    name: Optional[str] = None; contact_person: Optional[str] = None
    contact_info: Optional[str] = None; address: Optional[str] = None
    payment_terms: Optional[str] = None; is_active: Optional[str] = None

class SupplierResponse(BaseModel):
    id: int; warehouse_id: Optional[int] = None; name: str
    contact_person: Optional[str] = None; contact_info: Optional[str] = None
    address: Optional[str] = None; payment_terms: Optional[str] = None
    ai_evaluation: Optional[dict] = None; is_active: str
    created_at: Optional[datetime] = None
    class Config: from_attributes = True


# ---- Recharge Declaration ----
class RechargeCreate(BaseModel):
    customer_id: int; declare_date: str; amount: float
    currency: str = "THB"; payment_method: Optional[str] = None
    payment_time: Optional[str] = None; transaction_no: Optional[str] = None
    account_tail: Optional[str] = None; screenshot: Optional[str] = None
    remark: Optional[str] = None

class RechargeResponse(BaseModel):
    id: int; warehouse_id: int; customer_id: int; declare_date: str
    amount: float; currency: str; payment_method: Optional[str] = None
    payment_time: Optional[str] = None; transaction_no: Optional[str] = None
    account_tail: Optional[str] = None; screenshot: Optional[str] = None
    remark: Optional[str] = None; match_status: str
    customer_name: Optional[str] = None; declarer_name: Optional[str] = None
    created_at: Optional[datetime] = None
    class Config: from_attributes = True


# ---- Incoming Flow ----
class IncomingCreate(BaseModel):
    received_date: str; amount: float; currency: str = "THB"
    payer_name: Optional[str] = None; payment_method: Optional[str] = None
    remark: Optional[str] = None

class IncomingBatchImport(BaseModel):
    records: List[dict]

class IncomingResponse(BaseModel):
    id: int; warehouse_id: int; received_date: str; amount: float
    currency: str; payer_name: Optional[str] = None
    payment_method: Optional[str] = None; remark: Optional[str] = None
    match_status: str; entrant_name: Optional[str] = None
    created_at: Optional[datetime] = None
    class Config: from_attributes = True


# ---- Reconciliation ----
class ReconciliationRequest(BaseModel):
    month: str  # YYYY-MM
    warehouse_id: int

class ReconciliationResultResponse(BaseModel):
    id: int; warehouse_id: int; reconciliation_month: str
    declaration_id: Optional[int] = None; flow_id: Optional[int] = None
    match_status: str; amount_diff: float = 0
    handling_note: Optional[str] = None; confirmed_by: Optional[int] = None
    declaration: Optional[dict] = None; flow: Optional[dict] = None
    created_at: Optional[datetime] = None
    class Config: from_attributes = True

class ManualMatchRequest(BaseModel):
    declaration_id: int; flow_id: int
    handling_note: Optional[str] = None

class UnmatchRequest(BaseModel):
    record_id: int


# ---- Exchange Rate ----
class ExchangeRateCreate(BaseModel):
    month: str; from_currency: str; to_currency: str; rate: float


# ---- Income Records ----
class IncomeRecordCreate(BaseModel):
    category_id: int; account_id: int; customer_id: Optional[int] = None
    amount: float; currency: str = "THB"; income_date: str
    voucher: Optional[str] = None; remark: Optional[str] = None

class IncomeRecordResponse(BaseModel):
    id: int; warehouse_id: int; category_id: int; account_id: int
    customer_id: Optional[int] = None; amount: float; currency: str
    income_date: str; voucher: Optional[str] = None; remark: Optional[str] = None
    category_name: Optional[str] = None; account_name: Optional[str] = None
    customer_name: Optional[str] = None; created_at: Optional[datetime] = None
    class Config: from_attributes = True


# ---- Expense Records ----
class ExpenseRecordCreate(BaseModel):
    category_id: int; account_id: int; supplier_id: Optional[int] = None
    amount: float; currency: str = "THB"; expense_date: str
    voucher: Optional[str] = None; remark: Optional[str] = None

class ExpenseRecordResponse(BaseModel):
    id: int; warehouse_id: int; category_id: int; account_id: int
    supplier_id: Optional[int] = None; amount: float; currency: str
    expense_date: str; voucher: Optional[str] = None; remark: Optional[str] = None
    category_name: Optional[str] = None; account_name: Optional[str] = None
    supplier_name: Optional[str] = None; created_at: Optional[datetime] = None
    class Config: from_attributes = True


# ---- Category ----
class CategoryCreate(BaseModel):
    type: str  # income/expense
    name: str; sort_order: int = 0

class CategoryResponse(BaseModel):
    id: int; warehouse_id: int; type: str; name: str
    sort_order: int; status: str
    class Config: from_attributes = True


# ---- Dashboard ----
class DashboardStats(BaseModel):
    total_recharge_month: float = 0; total_incoming_month: float = 0
    unmatched_count: int = 0; pending_market_review: int = 0
    pending_group_orders: int = 0

class WarehouseSummary(BaseModel):
    warehouse_id: int; warehouse_name: str
    recharge_total: float = 0; incoming_total: float = 0
    unmatched_count: int = 0
