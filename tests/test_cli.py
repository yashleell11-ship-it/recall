from recall.cli import (
    build_parser,
    cmd_approve,
    cmd_init,
    cmd_queue,
    cmd_recheck,
)
from recall.config import load_config
from recall.db import connect
from recall.lpu import SUBJECTS


def cfg_for(tmp_path):
    return load_config({"DEEPSEEK_API_KEY": "k", "RECALL_DB": str(tmp_path / "t.db")})


def test_parser_accepts_ingest_arguments():
    args = build_parser().parse_args(["ingest", "--topic", "CSE111", "notes.pdf"])
    assert args.topic == "CSE111"
    assert args.path == "notes.pdf"


def test_init_creates_the_lpu_subjects(tmp_path):
    cfg = cfg_for(tmp_path)
    assert cmd_init(build_parser().parse_args(["init"]), cfg) == 0
    codes = {r["code"] for r in connect(cfg.db_path)
             .execute("SELECT code FROM topics").fetchall()}
    assert codes == set(SUBJECTS)


def test_init_is_idempotent(tmp_path):
    cfg = cfg_for(tmp_path)
    args = build_parser().parse_args(["init"])
    cmd_init(args, cfg)
    assert cmd_init(args, cfg) == 0


def test_queue_on_empty_db_reports_zero(tmp_path, capsys):
    cfg = cfg_for(tmp_path)
    cmd_init(build_parser().parse_args(["init"]), cfg)
    cmd_queue(build_parser().parse_args(["queue"]), cfg)
    assert "0 pending shown" in capsys.readouterr().out


def test_approve_only_touches_pending_cards(tmp_path, capsys):
    cfg = cfg_for(tmp_path)
    cmd_init(build_parser().parse_args(["init"]), cfg)
    conn = connect(cfg.db_path)
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'f.pdf','pdf','abc','2026-09-04')")
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref) "
                 "VALUES (1,1,0,'t','p1')")
    for cid, state in ((1, "pending"), (2, "rejected")):
        conn.execute("INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,"
                     "cloze_text,arm,state,created_at) VALUES "
                     f"({cid},1,1,'qa','Q?','A',NULL,'learned','{state}','2026-09-04')")
    conn.commit()
    cmd_approve(build_parser().parse_args(["approve", "1", "2"]), cfg)
    states = {r["id"]: r["state"] for r in
              connect(cfg.db_path).execute("SELECT id, state FROM cards").fetchall()}
    assert states == {1: "active", 2: "rejected"}


def test_fit_refuses_on_thin_data_with_a_distinct_exit_code(tmp_path, capsys):
    """Refusing to fit 17 parameters to a handful of reviews is correct behaviour,
    and a nightly timer needs to tell it apart from a real failure."""
    from recall.cli import cmd_fit
    cfg = cfg_for(tmp_path)
    cmd_init(build_parser().parse_args(["init"]), cfg)
    code = cmd_fit(build_parser().parse_args(["fit"]), cfg)
    assert code == 3
    assert "not enough data" in capsys.readouterr().out


def test_fit_parser_defaults():
    args = build_parser().parse_args(["fit"])
    assert args.min_reviews == 200
    assert args.dry_run is False


def _card(conn, cid, question, answer="A short answer", state="active"):
    conn.execute("INSERT INTO cards (id,chunk_id,topic_id,kind,question,answer,"
                 "cloze_text,arm,state,created_at) VALUES "
                 "(?,1,1,'qa',?,?,NULL,'learned',?,'2026-09-07')",
                 (cid, question, answer, state))


def _deck(cfg):
    """A source, a chunk, and nothing else — the fixture every card needs."""
    conn = connect(cfg.db_path)
    conn.execute("INSERT INTO sources (id,user_id,topic_id,filename,kind,sha256,"
                 "added_at) VALUES (1,1,1,'f.pdf','pdf','abc','2026-09-07')")
    conn.execute("INSERT INTO chunks (id,source_id,ordinal,text,page_ref) "
                 "VALUES (1,1,0,'t','p1')")
    return conn


def test_recheck_finds_cards_a_later_gate_would_have_caught(tmp_path, capsys):
    """The four cards that motivated the dangling-reference gate were already
    in a real deck when it was written. A gate that only runs on new work
    leaves them there."""
    cfg = cfg_for(tmp_path)
    cmd_init(build_parser().parse_args(["init"]), cfg)
    conn = _deck(cfg)
    _card(conn, 1, "What is the formula for the elements of the matrix A in Q1?")
    _card(conn, 2, "What is the rank of a 3x3 identity matrix?")
    conn.commit()

    cmd_recheck(build_parser().parse_args(["recheck"]), cfg)
    out = capsys.readouterr().out
    assert "1 of 2 cards no longer pass" in out
    # A dry run by default: a card being reviewed is not deleted on a whim.
    states = {r["id"]: r["state"] for r in
              connect(cfg.db_path).execute("SELECT id, state FROM cards")}
    assert states == {1: "active", 2: "active"}


def test_recheck_apply_rejects_only_the_failures(tmp_path, capsys):
    cfg = cfg_for(tmp_path)
    cmd_init(build_parser().parse_args(["init"]), cfg)
    conn = _deck(cfg)
    _card(conn, 1, "In Q6, what is the expression for A^n?")
    _card(conn, 2, "What is the rank of a 3x3 identity matrix?")
    conn.commit()

    cmd_recheck(build_parser().parse_args(["recheck", "--apply"]), cfg)
    rows = {r["id"]: (r["state"], r["reject_reason"]) for r in
            connect(cfg.db_path).execute(
                "SELECT id, state, reject_reason FROM cards")}
    assert rows[1][0] == "rejected"
    assert rows[1][1].startswith("recheck: ")
    assert rows[2] == ("active", None)


def test_recheck_leaves_a_clean_deck_alone(tmp_path, capsys):
    cfg = cfg_for(tmp_path)
    cmd_init(build_parser().parse_args(["init"]), cfg)
    conn = _deck(cfg)
    _card(conn, 1, "What is the rank of a 3x3 identity matrix?")
    conn.commit()
    cmd_recheck(build_parser().parse_args(["recheck", "--apply"]), cfg)
    assert "all still pass" in capsys.readouterr().out
    assert connect(cfg.db_path).execute(
        "SELECT state FROM cards WHERE id = 1").fetchone()["state"] == "active"


def test_recheck_ignores_already_rejected_cards(tmp_path, capsys):
    """Re-running must not re-report what it already dealt with."""
    cfg = cfg_for(tmp_path)
    cmd_init(build_parser().parse_args(["init"]), cfg)
    conn = _deck(cfg)
    _card(conn, 1, "What is the matrix A in Q1?", state="rejected")
    conn.commit()
    cmd_recheck(build_parser().parse_args(["recheck"]), cfg)
    assert "0 cards checked, all still pass" in capsys.readouterr().out
