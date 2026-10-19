import pytest


@pytest.fixture
def retained_reversal_code(monkeypatch):
    """仅验收保留的旧回滚实现；正常入口停用另由无覆盖的专项 HTTP 测试验证。"""
    from app.main import app
    from app.core.financial_reversals import reject_disabled_financial_reversal

    monkeypatch.setitem(app.dependency_overrides, reject_disabled_financial_reversal, lambda: None)
