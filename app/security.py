import secrets

from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def create_session_token() -> str:
    return secrets.token_urlsafe(32)
