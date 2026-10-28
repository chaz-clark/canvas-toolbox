"""submit_on_behalf must load credentials via the shared _env_loader (~/.canvas),
not a bare .env read — otherwise a token stored outside .env reads as 'missing'."""
from pathlib import Path


def test_uses_shared_env_loader():
    src = (Path(__file__).resolve().parent.parent / "tools" / "submit_on_behalf.py").read_text()
    assert "from _env_loader import load_env" in src
    assert "load_dotenv(Path.cwd()" not in src
