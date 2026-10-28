"""Exact live registration comparison, separate from request/branch coverage reports."""
def assert_registered_catalogue():
    from fastapi.routing import APIRoute
    from app.main import app
    from app.core.action_access import CATALOG
    actual={(method,r.path) for r in app.routes if isinstance(r,APIRoute) for method in r.methods}
    documented={(method,r['path']) for r in CATALOG['routes'] for method in r['methods']}
    assert actual==documented,{'unregistered':sorted(actual-documented),'stale':sorted(documented-actual)}
