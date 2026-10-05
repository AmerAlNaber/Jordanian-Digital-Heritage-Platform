"""Staff tool: which reader session does a leaked tile belong to? (SEC-11, ADR-0006)

    python -m jdhp_worker.tools.detect_mark leaked.webp --session s8abc...
    python -m jdhp_worker.tools.detect_mark leaked.webp --all-active --work w8xyz...

Re-derives each candidate session's forensic key from the master key and the session row,
runs the detector and prints the z-score. A score at or above the threshold identifies the
session, its user and its grant; the tool prints no key material.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pyvips
from sqlalchemy import select

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import ReaderSessionState
from jdhp_api.core.tokens import ForensicKeys
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.reader import forensic
from jdhp_api.modules.reader.models import ReaderSession
from jdhp_worker.settings import get_worker_settings


async def candidates(
    database: Database,
    *,
    session_public_id: str | None,
    work_public_id: str | None,
    all_active: bool,
) -> list[ReaderSession]:
    async with database.session(RlsContext.system()) as session:
        stmt = select(ReaderSession)
        if session_public_id:
            stmt = stmt.where(ReaderSession.public_id == session_public_id)
        if work_public_id:
            work = (
                await session.scalars(select(Work).where(Work.public_id == work_public_id))
            ).first()
            if work is None:
                return []
            stmt = stmt.where(ReaderSession.work_id == work.id)
        if all_active and not session_public_id:
            stmt = stmt.where(ReaderSession.state == ReaderSessionState.ACTIVE)
        return list((await session.scalars(stmt.order_by(ReaderSession.created_at.desc()))).all())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("image", type=Path, help="the leaked tile or page image")
    parser.add_argument("--session", help="public name of one reader session to test")
    parser.add_argument("--work", help="restrict candidates to one work's sessions")
    parser.add_argument("--all-active", action="store_true", help="test every active session")
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args(argv)
    if not (args.session or args.all_active or args.work):
        parser.error("name a --session, a --work or --all-active")
    settings = get_worker_settings()
    database = Database(settings.worker_sqlalchemy_url, pooled=False)
    image = pyvips.Image.new_from_file(str(args.image))
    rows = asyncio.run(
        candidates(
            database,
            session_public_id=args.session,
            work_public_id=args.work,
            all_active=args.all_active,
        )
    )[: args.limit]
    keys = ForensicKeys(settings)
    report: list[dict[str, Any]] = []
    for row in rows:
        detection = forensic.detect(image, keys.session_key(row.id))
        report.append(
            {
                "session": row.public_id,
                "state": str(row.state),
                "score": round(detection.score, 2),
                "match": detection.present,
            }
        )
    report.sort(key=lambda r: -float(r["score"]))
    sys.stdout.write(json.dumps({"candidates": len(rows), "results": report[:20]}, indent=2) + "\n")
    asyncio.run(database.dispose())
    return 0 if any(r["match"] for r in report) else 1


if __name__ == "__main__":  # pragma: no cover - command line entry point
    raise SystemExit(main())
