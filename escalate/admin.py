"""Hosted beta administration, run from your own computer against the hosted DATABASE_URL.

    make invite EMAIL=someone@example.com
    make uninvite EMAIL=someone@example.com
    make invites
    make migrate-hosted

If DATABASE_URL isn't a Postgres URL, the connection string is asked for with hidden input, so
the database password never lands in your shell history.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import inspect, select

from escalate.config import get_settings


def database_url() -> str:
    url = get_settings().database_url
    if url.startswith(("postgres://", "postgresql")):
        return url
    url = getpass.getpass(
        "Paste the Supabase session pooler connection string (input hidden): "
    ).strip()
    if not url.startswith(("postgres://", "postgresql")):
        sys.exit("that is not a postgresql:// connection string")
    return url


def _bind(url: str) -> None:
    from escalate.db import session as db_session

    engine = db_session.configure(url)
    schema = get_settings().db_schema
    if "invites" not in inspect(engine).get_table_names(schema=schema):
        sys.exit(f"no tables in schema {schema!r} yet: run `make migrate-hosted` first")


def main(argv: list[str] | None = None) -> int:
    os.environ["DEPLOY_MODE"] = "hosted"  # the private schema, whatever .env says
    get_settings.cache_clear()
    parser = argparse.ArgumentParser(prog="python -m escalate.admin")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("invite", "uninvite"):
        sub.add_parser(name).add_argument("email")
    sub.add_parser("invites")
    sub.add_parser("migrate")
    args = parser.parse_args(argv)

    url = database_url()
    if args.cmd == "migrate":
        from escalate.db.migrate import upgrade

        upgrade(url)
        print(f"schema {get_settings().db_schema!r} is up to date")
        return 0
    _bind(url)
    from escalate.db.models import Invite
    from escalate.db.session import session_scope
    from escalate.hosted.accounts import invite, normalise_email, uninvite

    with session_scope() as s:
        if args.cmd == "invites":
            for row in s.scalars(select(Invite).order_by(Invite.created_at)):
                print(f"{row.created_at:%Y-%m-%d}  {row.email}")
            return 0
        try:
            email = normalise_email(args.email)
        except ValueError as exc:
            sys.exit(str(exc))
        if args.cmd == "invite":
            print(f"invited {email}" if invite(s, email) else f"{email} was already invited")
        else:
            print(f"removed {email}" if uninvite(s, email) else f"{email} was not invited")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
