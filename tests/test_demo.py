from recall.cli import build_parser, cmd_init
from recall.config import load_config
from recall.db import connect
from recall.demo import SAMPLE_CARDS, clear_demo, seed_demo


def seeded(tmp_path):
    cfg = load_config({"DEEPSEEK_API_KEY": "k", "RECALL_DB": str(tmp_path / "t.db")})
    cmd_init(build_parser().parse_args(["init"]), cfg)
    return connect(cfg.db_path)


def test_seed_inserts_active_cards(tmp_path):
    conn = seeded(tmp_path)
    assert seed_demo(conn) == len(SAMPLE_CARDS)
    n = conn.execute("SELECT COUNT(*) n FROM cards WHERE state='active'").fetchone()["n"]
    assert n == len(SAMPLE_CARDS)


def test_seed_is_idempotent(tmp_path):
    conn = seeded(tmp_path)
    seed_demo(conn)
    assert seed_demo(conn) == 0


def test_seed_covers_every_topic(tmp_path):
    conn = seeded(tmp_path)
    seed_demo(conn)
    codes = {r["code"] for r in conn.execute(
        "SELECT DISTINCT t.code FROM cards c JOIN topics t ON t.id=c.topic_id"
    ).fetchall()}
    assert codes == {"MTH165", "CSE111", "INT108", "INT335", "CSE326"}


def test_clear_removes_everything_it_added(tmp_path):
    conn = seeded(tmp_path)
    seed_demo(conn)
    assert clear_demo(conn) == len(SAMPLE_CARDS)
    assert conn.execute("SELECT COUNT(*) n FROM cards").fetchone()["n"] == 0
    assert conn.execute("SELECT COUNT(*) n FROM sources").fetchone()["n"] == 0


def test_cloze_samples_carry_markup(tmp_path):
    conn = seeded(tmp_path)
    seed_demo(conn)
    rows = conn.execute("SELECT cloze_text FROM cards WHERE kind='cloze'").fetchall()
    assert rows and all("{{c1::" in r["cloze_text"] for r in rows)
