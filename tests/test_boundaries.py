import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "recall"


def test_only_llm_client_imports_httpx():
    """Network access is a boundary. A boundary that isn't tested isn't a boundary."""
    offenders = [
        str(p.relative_to(SRC))
        for p in SRC.rglob("*.py")
        if "httpx" in p.read_text() and p.name != "client.py"
    ]
    assert offenders == [], f"httpx must stay in llm/client.py, found in {offenders}"
