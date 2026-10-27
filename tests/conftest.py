import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from database.connection import Database  # noqa: E402
from database.repository import Repository  # noqa: E402
from database.schema import migrate  # noqa: E402


@pytest.fixture
def db_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXELDESK_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "test.db"


@pytest.fixture
def repo(db_file):
    db = Database(db_file)
    migrate(db)
    yield Repository(db)
    db.close()


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
