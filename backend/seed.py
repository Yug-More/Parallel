"""Explicit, non-destructive local account creation. No default passwords."""

import argparse
import getpass
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from api.workspaces import create_workspace
from config import load_settings
from database import create_db_engine
from models import User, UserCredential
from security import Registration, hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-development", action="store_true", required=True)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    settings = load_settings()
    if settings.environment != "development":
        parser.error("Seeding is restricted to APP_ENV=development")
    payload = Registration(
        email=args.email, name=args.name, password=getpass.getpass("New password: ")
    )
    engine = create_db_engine(settings.database_url)
    try:
        with Session(engine) as db:
            if db.query(User).filter(func.lower(User.email) == payload.email).first():
                print("Account already exists; no changes made.")
                return
            user = User(id=str(uuid4()), name=payload.name, email=payload.email)
            db.add(user)
            db.flush()
            db.add(UserCredential(user_id=user.id, password_hash=hash_password(payload.password)))
            create_workspace(db, user, "Personal workspace")
            db.commit()
            print("Development account created. Existing records were preserved.")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
