import asyncio
from getpass import getpass

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.exc import IntegrityError

from app.infrastructure.database.models.audit_log import AuditLog
from app.infrastructure.database.models.enums import UserRole
from app.infrastructure.database.models.user import User
from app.infrastructure.database.session import (
    async_session_factory,
    dispose_database_engine,
)
from app.infrastructure.database.unit_of_work.authentication import (
    AuthenticationUnitOfWork,
)
from app.infrastructure.security.passwords import hash_password

_email_adapter = TypeAdapter(EmailStr)


async def create_admin_account(
    unit_of_work: AuthenticationUnitOfWork,
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
) -> User:
    normalized_email = email.strip().lower()
    if await unit_of_work.users.get_by_email(normalized_email):
        raise ValueError("A user with this email already exists.")

    user = User(
        email=normalized_email,
        password_hash=await hash_password(password),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        role=UserRole.ADMIN,
        is_active=True,
    )

    try:
        await unit_of_work.users.create(user)
        await unit_of_work.audit_logs.create(
            AuditLog(
                user_id=None,
                action="user.admin_created",
                entity_type="user",
                entity_id=user.id,
                new_values={
                    "changed_fields": [
                        "email",
                        "first_name",
                        "last_name",
                        "role",
                        "is_active",
                    ]
                },
                status="success",
            )
        )
        await unit_of_work.commit()
    except IntegrityError as exc:
        await unit_of_work.rollback()
        if await unit_of_work.users.get_by_email(normalized_email):
            raise ValueError("A user with this email already exists.") from exc
        raise

    return user


def _prompt_admin_details() -> dict[str, str]:
    email = input("Admin email: ").strip().lower()
    try:
        _email_adapter.validate_python(email)
    except ValidationError as exc:
        raise ValueError("Enter a valid email address.") from exc

    first_name = input("First name: ").strip()
    last_name = input("Last name: ").strip()
    if not first_name or len(first_name) > 100:
        raise ValueError("First name must contain 1 to 100 characters.")
    if not last_name or len(last_name) > 100:
        raise ValueError("Last name must contain 1 to 100 characters.")

    password = getpass("Password (12-255 characters): ")
    if not 12 <= len(password) <= 255:
        raise ValueError("Password must contain 12 to 255 characters.")
    if password != getpass("Confirm password: "):
        raise ValueError("Passwords do not match.")

    return {
        "email": email,
        "password": password,
        "first_name": first_name,
        "last_name": last_name,
    }


async def _create_admin_from_prompt() -> User:
    details = _prompt_admin_details()
    async with async_session_factory() as session:
        unit_of_work = AuthenticationUnitOfWork(session)
        return await create_admin_account(unit_of_work, **details)


async def _run() -> int:
    try:
        user = await _create_admin_from_prompt()
    except ValueError as exc:
        print(f"Admin account was not created: {exc}")
        return 1
    except IntegrityError:
        print("Admin account was not created because of a database constraint.")
        return 1
    finally:
        await dispose_database_engine()

    print(f"Admin account created for {user.email}.")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
