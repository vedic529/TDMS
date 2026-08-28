"""Command-line allocation import. Same service as the website."""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.services.allocation_import import apply_rows, validate_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description="Import allocation records.")
    parser.add_argument("file")
    parser.add_argument("--package", required=True)
    parser.add_argument("--mode", choices=["REPLACE", "MERGE"], default="REPLACE")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    payload = Path(args.file).read_bytes()
    session: Session = SessionLocal()
    try:
        review, _, _ = validate_bytes(session, training_package=args.package, file_name=Path(args.file).name, payload=payload)
        print(review.status, review.rows_read, "rows", "refused" if review.refused else "ok")
        if args.apply and not review.refused:
            user = session.query(User).filter(User.access_level.in_(["DATA_EDITOR", "ADMIN", "SUPER_ADMIN"])).first()
            result = apply_rows(
                session,
                training_package=args.package,
                file_name=Path(args.file).name,
                file_size_bytes=len(payload),
                payload=payload,
                apply_mode=args.mode,
                user=user,
            )
            session.commit()
            print(result)
    finally:
        session.close()


if __name__ == "__main__":
    main()
