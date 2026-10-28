"""Keep generated test evidence outside the Git tree by default."""
import os
import tempfile
from pathlib import Path

def evidence_dir(name):
    root=Path(os.environ.get("PERMISSIONS_EVIDENCE_DIR",str(Path(tempfile.gettempdir())/"warehouse-finance-test-evidence")))
    path=root/name
    path.mkdir(parents=True,exist_ok=True)
    return path
