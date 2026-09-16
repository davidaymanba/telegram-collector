import asyncio
from dataclasses import dataclass

from telethon.errors import SessionPasswordNeededError

from app.telegram.authentication import web_login_start, web_login_verify


@dataclass
class FakeSentCode:
    phone_code_hash: str = "hash-123"


class FakeLoginClient:
    instances = []

    def __init__(self, settings) -> None:
        self.authorized = False
        self.calls = []
        self.__class__.instances.append(self)

    async def connect(self) -> None:
        self.calls.append(("connect",))

    async def disconnect(self) -> None:
        self.calls.append(("disconnect",))

    async def is_user_authorized(self) -> bool:
        return self.authorized

    async def send_code_request(self, phone: str) -> FakeSentCode:
        self.calls.append(("send_code", phone))
        return FakeSentCode()

    async def sign_in(self, **kwargs):
        self.calls.append(("sign_in", kwargs))
        if "password" not in kwargs:
            raise SessionPasswordNeededError(request=None)
        self.authorized = True


def client_factory(settings):
    return FakeLoginClient(settings)


def test_web_login_requires_and_accepts_two_factor_password(test_settings) -> None:
    FakeLoginClient.instances.clear()

    start = asyncio.run(
        web_login_start(test_settings, "+201000000000", client_factory=client_factory)
    )
    password_required = asyncio.run(
        web_login_verify(test_settings, "12345", client_factory=client_factory)
    )
    complete = asyncio.run(
        web_login_verify(
            test_settings,
            "12345",
            password="telegram-password",
            client_factory=client_factory,
        )
    )

    assert start == {"status": "code_required"}
    assert password_required == {"status": "password_required"}
    assert complete == {"status": "authorized"}
    assert FakeLoginClient.instances[0].calls[1] == ("send_code", "+201000000000")
    assert FakeLoginClient.instances[-1].calls[1][0] == "sign_in"


def test_web_login_returns_authorized_for_existing_session(test_settings) -> None:
    class AuthorizedClient(FakeLoginClient):
        async def is_user_authorized(self) -> bool:
            return True

    assert asyncio.run(
        web_login_start(test_settings, "+201000000000", client_factory=AuthorizedClient)
    ) == {"status": "authorized"}
