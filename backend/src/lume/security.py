import hashlib
import secrets

from sqlalchemy import select

from .models import Grant, Message, Principal, Space


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        self.code, self.message, self.status = code, message, status
        super().__init__(code)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_user(session, name: str, admin: bool = False):
    token = secrets.token_urlsafe(32)
    user = Principal(name=name, token_hash=token_hash(token), admin=admin)
    session.add(user)
    session.flush()
    return user, token


def authenticate(session, token: str) -> Principal:
    user = session.scalar(
        select(Principal).where(
            Principal.token_hash == token_hash(token), Principal.active.is_(True)
        )
    )
    if not user:
        raise DomainError("UNAUTHENTICATED", "令牌无效或已停用", 401)
    return user


def require_space(session, user_id: str, space_id: str, maintain: bool = False):
    permission = Grant.maintain if maintain else Grant.read
    space = session.scalar(
        select(Space)
        .join(Grant)
        .where(Space.id == space_id, Grant.user_id == user_id, permission.is_(True))
    )
    if not space:
        raise DomainError("NOT_FOUND", "对象不可用", 404)
    return space


def readable_spaces(session, user_id: str, requested: list[str]) -> list[str]:
    return list(
        session.scalars(
            select(Grant.space_id).where(
                Grant.user_id == user_id, Grant.read.is_(True), Grant.space_id.in_(requested)
            )
        )
    )


def check_dependencies(session, user_id: str, dependencies: list[dict]):
    user = session.get(Principal, user_id)
    if not user or not user.active:
        raise DomainError("DEPENDENCY_UNAVAILABLE", "来源资格或版本已变化")
    for dependency in dependencies:
        message = session.get(Message, dependency["message_id"])
        if not message or not message.active or message.version != dependency["version"]:
            raise DomainError("DEPENDENCY_UNAVAILABLE", "来源资格或版本已变化")
        require_space(session, user_id, message.space_id)


def dependency_union(*groups: list[dict]) -> list[dict]:
    keys = {(d["message_id"], int(d["version"])) for group in groups for d in group}
    return [{"message_id": key, "version": version} for key, version in sorted(keys)]
