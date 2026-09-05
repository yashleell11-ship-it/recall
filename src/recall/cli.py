import argparse
import sys

from recall.config import load_config
from recall.db import connect, init_db
from recall.demo import clear_demo, seed_demo
from recall.export.anki import export_apkg
from recall.seed import seed_topics


def _conn(cfg):
    return connect(cfg.db_path)


def cmd_init(args, cfg) -> int:
    conn = _conn(cfg)
    init_db(conn)
    conn.execute("INSERT OR IGNORE INTO users (id, name) VALUES (1, ?)", (args.user,))
    conn.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (1)")
    result = seed_topics(conn)
    from recall.lpu import SUBJECTS
    print(f"initialised {cfg.db_path} with LPU subjects: {', '.join(SUBJECTS)}")
    if result["renamed"]:
        print(f"renamed legacy topics: {', '.join(result['renamed'])}")
    return 0


def cmd_ingest(args, cfg) -> int:
    # Imported here so the rest of the CLI works without network deps loaded.
    from recall.llm.client import DeepSeekClient
    from recall.pipeline import ingest_source

    conn = _conn(cfg)
    row = conn.execute(
        "SELECT id FROM topics WHERE user_id = 1 AND code = ?", (args.topic,)
    ).fetchone()
    if row is None:
        from recall.lpu import SUBJECTS
        print(f"unknown topic {args.topic}; known: {', '.join(SUBJECTS)}",
              file=sys.stderr)
        return 2
    result = ingest_source(conn, cfg, DeepSeekClient(cfg), user_id=1,
                           topic_id=row["id"], path=args.path)
    print(f"accepted={result.accepted} rejected={result.rejected} "
          f"cost=${result.cost_usd:.4f}"
          + (" [stopped at cost cap]" if result.stopped_early else ""))
    return 0


def cmd_queue(args, cfg) -> int:
    conn = _conn(cfg)
    rows = conn.execute(
        "SELECT c.id, t.code, c.kind, c.question, c.answer, ch.page_ref "
        "FROM cards c JOIN topics t ON t.id = c.topic_id "
        "JOIN chunks ch ON ch.id = c.chunk_id "
        "WHERE c.state = 'pending' ORDER BY c.id LIMIT ?", (args.limit,)
    ).fetchall()
    for r in rows:
        print(f"[{r['id']}] {r['code']} {r['page_ref']} ({r['kind']})\n"
              f"    Q: {r['question']}\n    A: {r['answer']}")
    print(f"\n{len(rows)} pending shown")
    return 0


def cmd_approve(args, cfg) -> int:
    conn = _conn(cfg)
    state = "rejected" if args.reject else "active"
    reason = "rejected by hand" if args.reject else None
    conn.executemany(
        "UPDATE cards SET state = ?, reject_reason = ? "
        "WHERE id = ? AND state = 'pending'",
        [(state, reason, cid) for cid in args.ids],
    )
    conn.commit()
    print(f"{len(args.ids)} cards -> {state}")
    return 0


def cmd_fit(args, cfg) -> int:
    """Refit the scheduler to this user's own review history."""
    from recall.schedule.fit import fit_parameters, save_fit

    conn = _conn(cfg)
    result = fit_parameters(conn, 1, min_reviews=args.min_reviews)
    if result is None:
        n = conn.execute("SELECT COUNT(*) n FROM reviews").fetchone()["n"]
        print(f"not enough data to fit: {n} reviews, need {args.min_reviews}. "
              "Keep reviewing; the defaults are fine until then.")
        return 3  # distinct from failure, so a nightly timer can ignore it
    improved = result.val_logloss < result.baseline_logloss
    if not args.dry_run and improved:
        save_fit(conn, result)
    print(f"reviews used      {result.n_reviews}")
    print(f"held-out logloss  {result.val_logloss:.4f}")
    print(f"default logloss   {result.baseline_logloss:.4f}")
    print(f"converged         {result.converged}")
    if improved:
        gain = (result.baseline_logloss - result.val_logloss) / result.baseline_logloss
        print(f"=> fit beats the defaults by {gain:.1%}"
              + ("  (dry run, not saved)" if args.dry_run else "  — saved and now live"))
    else:
        print("=> fit does NOT beat the defaults on held-out data; NOT saved. "
              "That is the honest outcome, not an error.")
    return 0


def cmd_export(args, cfg) -> int:
    n = export_apkg(_conn(cfg), args.out, topic_code=args.topic)
    print(f"wrote {n} notes to {args.out}")
    return 0


def cmd_demo(args, cfg) -> int:
    conn = _conn(cfg)
    if args.clear:
        print(f"removed {clear_demo(conn)} sample cards")
        return 0
    n = seed_demo(conn)
    print(f"seeded {n} sample cards"
          if n else "sample cards already present (use --clear to remove)")
    return 0


def cmd_serve(args, cfg) -> int:
    import os

    import uvicorn

    from recall.api.app import bootstrap

    os.environ["RECALL_DB"] = cfg.db_path
    bootstrap(cfg.db_path)
    uvicorn.run("recall.api.app:app", host=args.host, port=args.port,
                reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="recall")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create the database and seed topics")
    s.add_argument("--user", default="yash")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("ingest", help="turn a PDF into candidate cards")
    s.add_argument("--topic", required=True)
    s.add_argument("path")
    s.set_defaults(func=cmd_ingest)

    s = sub.add_parser("queue", help="show pending cards awaiting approval")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_queue)

    s = sub.add_parser("approve", help="approve or reject pending cards by id")
    s.add_argument("ids", nargs="+", type=int)
    s.add_argument("--reject", action="store_true")
    s.set_defaults(func=cmd_approve)

    s = sub.add_parser("demo", help="seed sample cards so the app works without a key")
    s.add_argument("--clear", action="store_true")
    s.set_defaults(func=cmd_demo)

    s = sub.add_parser("serve", help="run the HTTP API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(func=cmd_serve)

    s = sub.add_parser("fit", help="refit the scheduler to your own review history")
    s.add_argument("--min-reviews", type=int, default=200)
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_fit)

    s = sub.add_parser("export", help="write an Anki .apkg")
    s.add_argument("--topic", default=None)
    s.add_argument("--out", default="recall.apkg")
    s.set_defaults(func=cmd_export)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args, load_config())


if __name__ == "__main__":
    raise SystemExit(main())
