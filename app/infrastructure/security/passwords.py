import asyncio

from pwdlib import PasswordHash

_password_hasher = PasswordHash.recommended()


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(_password_hasher.hash, password)


async def verify_password(password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(
        _password_hasher.verify,
        password,
        hashed_password,
    )
