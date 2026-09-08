import argparse
import pathlib
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


def cmd_claim_owner(args, cfg) -> int:
    """One-time: give the pre-auth owner account (id 1, created by `init`) a
    real email + password, so it can log in through open registration's
    /api/auth/login instead of the implicit single-user model. Idempotent —
    refuses if a password is already set, so it's safe to run by accident."""
    import getpass

    from recall.auth import hash_password, normalize_email

    password = args.password or getpass.getpass("Password: ")
    if len(password) < 8:
        print("password must be at least 8 characters", file=sys.stderr)
        return 2
    conn = _conn(cfg)
    row = conn.execute("SELECT password_hash FROM users WHERE id = 1").fetchone()
    if row is None:
        print("no user with id 1 — run `recall init` first", file=sys.stderr)
        return 2
    if row["password_hash"] is not None:
        print("owner already has a password set; not overwriting", file=sys.stderr)
        return 2
    conn.execute(
        "UPDATE users SET email = ?, password_hash = ?, created_at = COALESCE(created_at, ?)"
        " WHERE id = 1",
        (normalize_email(args.email), hash_password(password), _now_iso()),
    )
    conn.commit()
    print(f"owner account (id 1) can now log in as {normalize_email(args.email)}")
    return 0


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def cmd_set_password(args, cfg) -> int:
    """Reset an account's password.

    Deliberately separate from claim-owner, which refuses to touch an account
    that already has one — that guard is right for "claim this account" and
    wrong for "I want a new password".

    Resetting also deletes that account's sessions. If you are resetting
    because you think the old password got out, leaving the sessions it
    opened still valid would defeat the point; you will be signed out
    everywhere and sign back in once.
    """
    import getpass

    from recall.auth import hash_password

    password = args.password or getpass.getpass("New password: ")
    if len(password) < 8:
        print("password must be at least 8 characters", file=sys.stderr)
        return 2
    if not args.password:
        again = getpass.getpass("Again: ")
        if again != password:
            print("passwords did not match", file=sys.stderr)
            return 2

    conn = _conn(cfg)
    row = conn.execute(
        "SELECT id, name FROM users WHERE email = ? OR name = ?",
        (args.who.strip().lower(), args.who),
    ).fetchone()
    if row is None:
        print(f"no account matching {args.who!r}", file=sys.stderr)
        return 2

    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                 (hash_password(password), row["id"]))
    killed = conn.execute("DELETE FROM sessions WHERE user_id = ?",
                          (row["id"],)).rowcount
    conn.commit()
    print(f"password reset for {row['name']}"
          + (f"; {killed} existing session(s) signed out" if killed else ""))
    return 0


def cmd_set_email(args, cfg) -> int:
    """Change the login email on an account.

    Exists because `claim-owner` refuses to overwrite an account that already
    has a password — which is the right guard for a password and the wrong one
    for a typo in an email address.
    """
    import sqlite3

    from recall.auth import normalize_email

    email = normalize_email(args.email)
    conn = _conn(cfg)
    try:
        cur = conn.execute("UPDATE users SET email = ? WHERE name = ?",
                           (email, args.user))
    except sqlite3.IntegrityError:
        print(f"{email} is already used by another account", file=sys.stderr)
        return 2
    conn.commit()
    if cur.rowcount == 0:
        print(f"no user named {args.user!r}", file=sys.stderr)
        return 2
    print(f"{args.user} now logs in as {email}")
    return 0


def cmd_recheck(args, cfg) -> int:
    """Re-run the free gates over cards that are already in the deck.

    A gate added today does nothing for a card generated last week, and the
    card that motivated the dangling-reference gate — "What is the formula for
    the elements of the 3x3 matrix A in Q1?" — was sitting in a real deck,
    being reviewed, unanswerable, while the gate that would have caught it ran
    only on new work.

    Costs nothing: these are the regex gates, not the judges. Prints what it
    would do and changes nothing unless --apply is passed, because rejecting a
    card a student has been reviewing is not a thing to do silently.
    """
    from recall.generate.generate import Candidate
    from recall.verify.heuristics import check_answerable, check_atomic

    conn = _conn(cfg)
    rows = conn.execute(
        "SELECT c.id, c.kind, c.question, c.answer, c.cloze_text, c.state, t.code"
        " FROM cards c JOIN topics t ON t.id = c.topic_id"
        " WHERE c.state IN ('active','pending','suspended') AND t.user_id = 1"
        " ORDER BY c.id"
    ).fetchall()

    failures = []
    for r in rows:
        c = Candidate(r["kind"], r["question"], r["answer"], r["cloze_text"])
        reason = check_answerable(c) or check_atomic(c)
        if reason:
            failures.append((r, reason))

    if not failures:
        print(f"{len(rows)} cards checked, all still pass")
        return 0

    print(f"{len(failures)} of {len(rows)} cards no longer pass:")
    for r, reason in failures:
        print(f"  [{r['id']}] {r['code']}: {reason}")
        print(f"        {r['question']}")
    if not args.apply:
        print("\nnothing changed. Re-run with --apply to reject these.")
        return 0

    for r, reason in failures:
        conn.execute(
            "UPDATE cards SET state = 'rejected', reject_reason = ? WHERE id = ?",
            (f"recheck: {reason}", r["id"]),
        )
    conn.commit()
    print(f"\nrejected {len(failures)} cards")
    return 0


def cmd_ingest_corpus(args, cfg) -> int:
    """Ingest a whole collected corpus, one manifest line at a time.

    The corpus is a directory of freely-licensed course material plus a
    `manifest.jsonl` saying, per file, which subject and which units it serves
    (see /home/yash/recall-corpus/BRIEF.md for the shape). This walks it.

    Three things make it safe to point at a thousand files:

    - **It costs what it says it will.** A dry run reads every file locally,
      counts the chunks a real run would generate, and prices them from what
      generation has actually cost so far. Nothing is spent until you have
      seen that number.
    - **It stops.** --max-cost is a hard ceiling across the whole run, checked
      before each file, not after.
    - **It resumes.** ingest_source keys on the file's sha256, so a file
      already ingested is a no-op and re-running continues where it stopped.
      Interrupt it whenever you like.
    """
    import json as _json

    from recall.ingest.chunk import chunk_pages
    from recall.ingest.pdf import DOCUMENT_SUFFIXES, read_document
    from recall.llm.client import DeepSeekClient, LlmUnavailable
    from recall.pipeline import _cost, ingest_source

    manifest = pathlib.Path(args.manifest).expanduser()
    if not manifest.exists():
        print(f"no manifest at {manifest}", file=sys.stderr)
        return 2
    root = manifest.parent

    conn = _conn(cfg)
    topics = {r["code"]: r["id"] for r in conn.execute(
        "SELECT id, code FROM topics WHERE user_id = 1")}

    entries, skipped = [], []
    for line in manifest.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            e = _json.loads(line)
        except _json.JSONDecodeError:
            skipped.append((line[:60], "not valid json"))
            continue
        code = str(e.get("subject", "")).upper()
        path = (root / str(e.get("path", ""))).resolve()
        if code not in topics:
            skipped.append((e.get("path"), f"no topic {code!r}"))
        elif not path.is_file():
            skipped.append((e.get("path"), "file is missing"))
        elif path.suffix.lower() not in DOCUMENT_SUFFIXES:
            skipped.append((e.get("path"), f"cannot read {path.suffix}"))
        else:
            entries.append((code, path, e))

    if args.subject:
        want = {c.strip().upper() for c in args.subject.split(",")}
        entries = [x for x in entries if x[0] in want]

    if args.limit:
        entries = entries[: args.limit]

    for what, why in skipped[:10]:
        print(f"  skipped {what}: {why}")
    if len(skipped) > 10:
        print(f"  ... and {len(skipped) - 10} more skipped")
    if not entries:
        print("nothing to ingest")
        return 0

    # Already ingested? ingest_source would no-op, but say so up front rather
    # than in a progress line, because it changes the estimate.
    have = {r["sha256"] for r in conn.execute(
        "SELECT sha256 FROM sources WHERE user_id = 1")}
    from recall.ingest.pdf import file_sha256

    fresh = [(c, p, e) for c, p, e in entries if file_sha256(str(p)) not in have]
    done = len(entries) - len(fresh)

    print(f"{len(entries)} files in the manifest"
          + (f", {done} already ingested" if done else ""))
    if not fresh:
        print("nothing new to do")
        return 0

    # Price it from what this database has actually paid per chunk, which
    # beats a constant guessed at the time this was written: the real figure
    # moves with the model, the prices and how long the prompts have grown.
    # `chunks.generated_at` is set exactly once per chunk the pipeline has
    # paid for, so the two numbers line up.
    row = conn.execute(
        "SELECT (SELECT SUM(cost_estimate) FROM gen_runs) AS spent,"
        " (SELECT COUNT(*) FROM chunks WHERE generated_at IS NOT NULL) AS n"
    ).fetchone()
    if row["n"] and row["spent"]:
        per_chunk = row["spent"] / row["n"]
        basis = f"measured over {row['n']} chunks already generated"
    else:
        per_chunk = 0.0035
        basis = "a default, since nothing has been generated here yet"
    chunks_total = 0
    for _code, path, _e in fresh:
        try:
            chunks_total += len(chunk_pages(read_document(str(path))))
        except Exception as exc:  # noqa: BLE001 — an unreadable file is data
            print(f"  unreadable, will be skipped: {path.name} ({exc})")
    estimate = chunks_total * per_chunk
    print(f"{len(fresh)} new files, {chunks_total} chunks, roughly "
          f"${estimate:.2f} at ${per_chunk:.4f}/chunk ({basis})"
          f" — the cap is ${args.max_cost:.2f}")
    if args.dry_run:
        print("dry run; nothing spent")
        return 0

    client = DeepSeekClient(cfg)
    spent = 0.0
    ingested = failed = 0
    for code, path, e in fresh:
        if spent >= args.max_cost:
            print(f"stopped at the ${args.max_cost:.2f} cap; run again to continue")
            break
        try:
            result = ingest_source(conn, cfg, client, user_id=1,
                                   topic_id=topics[code], path=str(path))
        except LlmUnavailable as exc:
            print(f"  {path.name}: {exc.detail}")
            print("stopping — every remaining file would fail the same way")
            break
        except Exception as exc:  # noqa: BLE001 — one bad file must not end the run
            print(f"  {path.name}: skipped ({exc})")
            failed += 1
            continue
        spent += result.cost_usd
        ingested += 1
        print(f"  [{code}] {path.name}: +{result.accepted} kept, "
              f"{result.rejected} rejected, ${result.cost_usd:.4f}"
              + ("  (hit the per-source cap)" if result.stopped_early else ""))

    print(f"\ningested {ingested} files"
          + (f", {failed} failed" if failed else "")
          + f", spent ${spent:.4f}")
    return 0


def cmd_backfill_detail(args, cfg) -> int:
    """Write the worked explanation onto cards that predate the detail field.

    One paid call per card, so it prints what it will cost before spending
    anything and stops at --max-cost. Resumable: by default it only picks up
    cards where detail IS NULL, so re-running continues where it stopped.
    --rewrite redoes cards that already have one, which is what you want after
    the explanation prompt changes.
    """
    from recall.llm.client import DeepSeekClient
    from recall.teach.prompts import EXPLAIN_KNOWLEDGE_SYSTEM, EXPLAIN_KNOWLEDGE_USER
    from recall.pipeline import _cost

    conn = _conn(cfg)
    # --rewrite is for the day the explanation prompt changes: the details
    # already on the cards were written to the old contract, and only a
    # re-run replaces them. Without it this stays resumable and cheap.
    have = "" if args.rewrite else " c.detail IS NULL AND"
    rows = conn.execute(
        "SELECT c.id, c.question, c.answer, t.code FROM cards c"
        " JOIN topics t ON t.id = c.topic_id"
        f" WHERE{have} c.state IN ('active','pending')"
        " AND t.user_id = 1 ORDER BY c.id"
    ).fetchall()
    if not rows:
        print("every card already has a detail; nothing to do")
        return 0

    print(f"{len(rows)} cards need a detail. Roughly ${len(rows) * 0.0004:.3f} "
          f"at current prices, stopping at ${args.max_cost:.2f}.")
    if args.dry_run:
        return 0

    client = DeepSeekClient(cfg)
    pt = ct = 0
    written = 0
    for r in rows:
        if _cost(cfg, pt, ct) >= args.max_cost:
            print(f"stopped at the ${args.max_cost:.2f} cap; run again to continue")
            break
        try:
            resp = client.complete_json(
                EXPLAIN_KNOWLEDGE_SYSTEM,
                EXPLAIN_KNOWLEDGE_USER.format(topic_code=r["code"],
                                              question=r["question"],
                                              answer=r["answer"]),
            )
        except Exception as exc:  # noqa: BLE001 — one bad card must not end the run
            print(f"  [{r['id']}] skipped: {exc}")
            continue
        pt += resp.prompt_tokens
        ct += resp.completion_tokens
        import json as _json
        try:
            detail = (_json.loads(resp.content) or {}).get("explanation")
        except _json.JSONDecodeError:
            detail = None
        if not isinstance(detail, str) or not detail.strip():
            print(f"  [{r['id']}] skipped: model returned no explanation")
            continue
        conn.execute("UPDATE cards SET detail = ? WHERE id = ?",
                     (detail.strip(), r["id"]))
        conn.commit()  # per card, so an interrupted run keeps what it paid for
        written += 1
    print(f"wrote {written} details, cost ${_cost(cfg, pt, ct):.4f}")
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
    # Scoped to the owner (user 1). This is local, owner-only tooling, but the
    # database it opens now holds other people's decks too, and triaging a
    # stranger's cards from the terminal is not what this command is for.
    rows = conn.execute(
        "SELECT c.id, t.code, c.kind, c.question, c.answer, ch.page_ref "
        "FROM cards c JOIN topics t ON t.id = c.topic_id "
        "JOIN chunks ch ON ch.id = c.chunk_id "
        "WHERE c.state = 'pending' AND t.user_id = 1 "
        "ORDER BY c.id LIMIT ?", (args.limit,)
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
        "WHERE id = ? AND state = 'pending' "
        "AND topic_id IN (SELECT id FROM topics WHERE user_id = 1)",
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
    n = export_apkg(_conn(cfg), args.out, 1, topic_code=args.topic)
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


def cmd_lessons(args, cfg) -> int:
    """Write a lesson for one syllabus unit, or several.

    A CLI command and not an endpoint, deliberately: a lesson takes one to two
    minutes to write, and the per-user daily cap is $1.00 with no resume path,
    so a student pressing a button and waiting is the wrong shape. The request
    path reads rows this writes.
    """
    import json as _json

    from recall.llm.client import DeepSeekClient
    from recall.teach.lessons import latest_lesson, write_lesson

    # init_db, not a bare connect: `lessons` is a new table, and a database
    # made before it exists would otherwise answer with a raw sqlite
    # traceback. Idempotent — it is exactly what the container entrypoint
    # runs on every boot.
    conn = _conn(cfg)
    init_db(conn)
    row = conn.execute(
        "SELECT id, meta FROM topics WHERE user_id = ? AND code = ?",
        (args.user_id, args.topic)).fetchone()
    if row is None:
        print(f"no topic {args.topic!r} for user {args.user_id}")
        return 1
    meta = _json.loads(row["meta"]) if row["meta"] else {}
    units = meta.get("units") or []
    if not units:
        print(f"{args.topic} has no syllabus units recorded")
        return 1

    wanted = args.units or [1]
    bad = [u for u in wanted if not 1 <= u <= len(units)]
    if bad:
        print(f"{args.topic} has {len(units)} units; no unit "
              f"{', '.join(str(b) for b in bad)}")
        return 1

    # Dry run first, always available: what it would write and what it would
    # cost, with no key needed and no call made. Same discipline as
    # cmd_ingest_corpus — nothing here spends money without being asked twice.
    if args.dry_run:
        print(f"{args.topic} — {meta.get('full_name', args.topic)} "
              f"({meta.get('exam_format', 'unknown')} paper)")
        for u in wanted:
            have = latest_lesson(conn, args.user_id, row["id"], units[u - 1])
            state = f"have one ({have['status']})" if have else "none yet"
            print(f"  unit {u}: {units[u - 1]}  [{state}]")
        n = len(wanted)
        print(f"\nwould write {n} lesson{'s' if n != 1 else ''}, "
              f"{1 + (0 if args.no_rederive else 2)} calls each, "
              f"about ${0.004 * n:.3f} total")
        conn.close()
        return 0

    client = DeepSeekClient(cfg)
    failures = 0
    for u in wanted:
        print(f"unit {u}: {units[u - 1]} … ", end="", flush=True)
        result = write_lesson(conn, client, cfg, user_id=args.user_id,
                              topic_id=row["id"], topic_code=args.topic,
                              meta=meta, unit_number=u,
                              rederive=not args.no_rederive)
        print(f"{result.status}  ${result.cost_usd:.4f}")
        for note in result.notes:
            print(f"    - {note}")
        if result.status == "rejected":
            failures += 1
    conn.close()
    return 1 if failures else 0


def cmd_lesson_show(args, cfg) -> int:
    """Print a stored lesson as a student would read it."""
    import json as _json

    from recall.teach.lessons import latest_lesson

    conn = _conn(cfg)
    init_db(conn)
    row = conn.execute(
        "SELECT id, meta FROM topics WHERE user_id = ? AND code = ?",
        (args.user_id, args.topic)).fetchone()
    if row is None:
        print(f"no topic {args.topic!r}")
        return 1
    units = (_json.loads(row["meta"]) if row["meta"] else {}).get("units") or []
    if not 1 <= args.unit <= len(units):
        print(f"{args.topic} has {len(units)} units")
        return 1
    lesson = latest_lesson(conn, args.user_id, row["id"], units[args.unit - 1])
    conn.close()
    if lesson is None:
        print(f"no lesson yet for {args.topic} unit {args.unit}")
        return 1

    body = lesson["body"]
    bar = "=" * 74
    print(bar)
    print(f"{args.topic} · Unit {args.unit} · {lesson['unit']}")
    print(f"[{lesson['status']}] written {lesson['created_at'][:16]}")
    if lesson["notes"]:
        print(f"NOTES: {lesson['notes']}")
    print(bar)
    print(f"\n{body.get('why', '')}\n")
    for s in body.get("sections") or []:
        print(f"\n— {s.get('heading', '')} " + "-" * max(0, 68 - len(str(s.get('heading', '')))))
        print(s.get("body", ""))
    for i, w in enumerate(body.get("worked") or [], 1):
        print(f"\n\nWORKED EXAMPLE {i}\n{w.get('question', '')}\n")
        for step in w.get("steps") or []:
            print(f"   {step}")
        print(f"\n   ANSWER: {w.get('answer', '')}")
    print("\n\nCHECK YOURSELF")
    for i, c in enumerate(body.get("check") or [], 1):
        print(f"\n{i}. {c.get('question', '')}")
        print(f"   answer: {c.get('answer', '')}")
        print(f"   tests:  {c.get('why', '')}")
    print()
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

    s = sub.add_parser("claim-owner",
                       help="give the pre-auth owner account (id 1) an email+password")
    s.add_argument("--email", required=True)
    s.add_argument("--password", default=None,
                   help="omit to be prompted (avoids the value landing in shell history)")
    s.set_defaults(func=cmd_claim_owner)

    s = sub.add_parser("set-password", help="reset an account's password")
    s.add_argument("who", help="the account's email or name")
    s.add_argument("--password", default=None,
                   help="omit to be prompted twice (keeps it out of shell history)")
    s.set_defaults(func=cmd_set_password)

    s = sub.add_parser("set-email", help="change an account's login email")
    s.add_argument("--user", default="yash")
    s.add_argument("--email", required=True)
    s.set_defaults(func=cmd_set_email)

    s = sub.add_parser("ingest-corpus",
                       help="ingest a collected corpus from its manifest")
    s.add_argument("--manifest", default="~/recall-corpus/manifest.jsonl")
    s.add_argument("--subject", help="only these codes, comma separated")
    s.add_argument("--max-cost", type=float, default=5.0)
    s.add_argument("--limit", type=int, help="only the first N files")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(func=cmd_ingest_corpus)

    s = sub.add_parser("recheck",
                       help="re-run the free gates over cards already in the deck")
    s.add_argument("--apply", action="store_true",
                   help="actually reject what fails (default is a dry run)")
    s.set_defaults(func=cmd_recheck)

    s = sub.add_parser("backfill-detail",
                       help="write the worked explanation onto older cards")
    s.add_argument("--max-cost", type=float, default=0.50)
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--rewrite", action="store_true",
                   help="redo cards that already have a detail")
    s.set_defaults(func=cmd_backfill_detail)

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

    s = sub.add_parser("lessons", help="write a lesson for a syllabus unit")
    s.add_argument("topic")
    s.add_argument("--unit", type=int, action="append", dest="units",
                   help="1-based unit number; repeat for several")
    s.add_argument("--user-id", type=int, default=1)
    s.add_argument("--dry-run", action="store_true",
                   help="say what it would write and cost; makes no call")
    s.add_argument("--no-rederive", action="store_true",
                   help="skip the independent re-solve of each worked example")
    s.set_defaults(func=cmd_lessons)

    s = sub.add_parser("lesson-show", help="print a stored lesson")
    s.add_argument("topic")
    s.add_argument("--unit", type=int, default=1)
    s.add_argument("--user-id", type=int, default=1)
    s.set_defaults(func=cmd_lesson_show)

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
