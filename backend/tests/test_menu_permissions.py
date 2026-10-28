"""菜单完整性、旧权限兼容以及真实 HTTP/隔离数据库账号回归。"""
import asyncio
import json
import re
from pathlib import Path

from app.core.menu_registry import MENU_PERMISSIONS, STAFF_PERMISSIONS

LEGACY_NAMES = [
    "到账流水", "备用金管理", "报销管理", "运营收支",
    "账期管理", "操作日志", "供应商管理", "其他收支",
]
ROOT = Path(__file__).resolve().parents[2]


def test_menu_coverage_and_legacy_compatibility():
    assert STAFF_PERMISSIONS == dict(zip(LEGACY_NAMES, LEGACY_NAMES))
    assert list(STAFF_PERMISSIONS) == LEGACY_NAMES
    from app.core.permissions import STAFF_PERMISSIONS as old_import
    assert old_import is STAFF_PERMISSIONS
    layout = (ROOT / "frontend/src/components/layout/DashboardLayout.tsx").read_text()
    # Only functional menus belong to the permission registry; employee identity links are separate.
    layout = layout[layout.index("const navItems:"):layout.index("\n];", layout.index("const navItems:")) + 3]
    rows = re.findall(
        r'key: "([^"]+)"[^\n]+?href: "([^"]+)"[^\n]+?roles: \[([^\]]+)\]', layout
    )
    expected = {}
    for key, path, roles in rows:
        entry = expected.setdefault(key, {"path": path, "roles": set()})
        assert entry["path"] == path
        entry["roles"].update(re.findall(r'"([^"]+)"', roles))
    actual = {p.menu_key: p for p in MENU_PERMISSIONS}
    assert len(actual) == len(MENU_PERMISSIONS)
    assert set(actual) == set(expected) | {"leave", "attendance_enabled", "sku_catalog_manage"}
    for key, item in expected.items():
        assert actual[key].path == item["path"]
        assert set(actual[key].roles) == item["roles"]
    assert actual["leave"].path == "/attendance"
    assert actual["recharge"].as_dict()["default_roles"] == ["warehouse_admin"]
    assert actual["incoming"].as_dict()["default_roles"] == ["warehouse_admin"]
    assert actual["payable"].as_dict()["default_roles"] == ["warehouse_admin"]
    settings = (ROOT / "frontend/src/app/(dashboard)/settings/page.tsx").read_text()
    assert "PERM_LABELS" not in settings
    assert 'api.get<MenuPermission[]>("/users/permissions")' in settings
    assert "ActionPermissionsEditor" in settings
    identity = actual["attendance_enabled"]
    assert identity.label == "纳入考勤" and not identity.selectable and identity.path == ""
    for item in MENU_PERMISSIONS:
        if item.menu_key == "attendance_enabled":
            continue
        if item.menu_key == "sku_catalog_manage":
            assert item.path == "" and item.selectable
            assert (ROOT / "frontend/src/app/(dashboard)/supplier-skus/page.tsx").is_file()
            continue
        assert (ROOT / "frontend/src/app/(dashboard)" / item.path.lstrip("/") / "page.tsx").is_file()


def test_http_permissions_and_account_lifecycle(tmp_path, monkeypatch):
    import pytest
    pytest.importorskip("aiosqlite")
    pytest.importorskip("greenlet")
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    import app.database as database
    from app.main import app
    from app.core.security import create_access_token, hash_password
    from app.models import User, Warehouse, UserWarehouse

    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
        factory = async_sessionmaker(engine, expire_on_commit=False)
        monkeypatch.setattr(database, "async_session_factory", lambda: factory)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(database.Base.metadata.create_all)
            async with factory() as db:
                wh = Warehouse(id=1, name="测试仓", code="TEST")
                admin = User(id=1, username="test_admin", display_name="测试管理员",
                             password_hash=hash_password("test-password"),
                             role="warehouse_admin", warehouse_id=1)
                db.add_all([wh, admin, UserWarehouse(user_id=1, warehouse_id=1)])
                await db.commit()
            headers = {"Authorization": "Bearer " + create_access_token({"sub": "1"})}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/v1/users/permissions", headers=headers)
                assert response.status_code == 200, response.text
                items = response.json()
                assert len(items) == len(MENU_PERMISSIONS)
                assert {i["menu_key"] for i in items}=={p.menu_key for p in MENU_PERMISSIONS}
                for item in items:
                    assert {"key", "label", "menu_key", "path", "roles", "default_roles", "selectable"} <= item.keys()
                    assert isinstance(item["selectable"], bool)
                assert {i["key"]: i["label"] for i in items if i["key"] in LEGACY_NAMES} == STAFF_PERMISSIONS
                print("\nGET /api/v1/users/permissions 前两项:\n" + json.dumps(items[:2], ensure_ascii=False, indent=2))
                assert (await client.get("/api/v1/users/permissions")).status_code == 403
                created = await client.post("/api/v1/users", headers=headers, json={
                    "username": "test_staff", "display_name": "测试财务", "password": "test-password",
                    "role": "staff", "warehouse_ids": [1], "action_permissions": ["incoming:view","incoming:operate"], "permission_reason":"SYNTHETIC lifecycle",
                })
                assert created.status_code == 200, created.text
                uid = created.json()["id"]
                async def saved_user():
                    result = await client.get("/api/v1/users", headers=headers)
                    assert result.status_code == 200, result.text
                    return next(u for u in result.json()["data"] if u["id"] == uid)
                assert (await saved_user())["action_access"]["grants"] == ["incoming:operate","incoming:view"]
                for permissions in (["incoming:view"], [], ["incoming:view","incoming:operate"]):
                    updated = await client.put(f"/api/v1/users/{uid}", headers=headers,
                                               json={"display_name": "已编辑", "action_permissions": permissions, "permission_reason":"SYNTHETIC lifecycle change"})
                    assert updated.status_code == 200, updated.text
                    assert set((await saved_user())["action_access"]["grants"]) == set(permissions)
                staff_headers = {"Authorization": "Bearer " + create_access_token({"sub": str(uid)})}
                assert (await client.get("/api/v1/users/permissions", headers=staff_headers)).status_code == 200
                disabled = await client.put(f"/api/v1/users/{uid}", headers=headers, json={"is_active": False})
                assert disabled.status_code == 200, disabled.text
                assert (await saved_user())["is_active"] is False
                assert (await client.get("/api/v1/users/permissions", headers=staff_headers)).status_code == 401
                deleted = await client.delete(f"/api/v1/users/{uid}", headers=headers)
                assert deleted.status_code == 200, deleted.text
                result = await client.get("/api/v1/users", headers=headers)
                assert all(u["id"] != uid for u in result.json()["data"])
                assert (await client.get("/health")).status_code == 200
        finally:
            await engine.dispose()

    asyncio.run(run())
