from recall.cli import build_parser, cmd_approve, cmd_init, cmd_queue
from recall.config import load_config
from recall.db import connect


def cfg_for(tmp_path):
    return load_config({"DEEPSEEK_API_KEY": "k", "RECALL_DB": str(tmp_path / "t.db")})


def test_parser_accepts_ingest_arguments():
    args = build_parser().parse_args(["ingest", "--topic", "CSE111", "notes.pdf"])
    assert args.topic == "CSE111"
    assert args.path == "notes.pdf"


def test_init_creates_all_five_topics(tmp_path):
    cfg = cfg_for(tmp_path)
    assert cmd_init(build_parser().parse_args(["init"]), cfg) == 0
    codes = {r["code"] for r in connect(cfg.db_path)
             .execute("SELECT code FROM topics").fetchall()}
    assert codes == {"MATHS", "CSE111", "INT108", "INT335", "HTML"}


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
