"""An in-memory SMTP server stand-in: records logins and messages, never touches the network."""

from email.message import EmailMessage
from types import TracebackType
from typing import ClassVar


class FakeSMTP:
    instances: ClassVar[list["FakeSMTP"]] = []

    def __init__(self, host: str, port: int) -> None:
        self.host, self.port = host, port
        self.logins: list[tuple[str, str]] = []
        self.sent: list[EmailMessage] = []
        FakeSMTP.instances.append(self)

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(
        self, t: type[BaseException] | None, e: BaseException | None, tb: TracebackType | None
    ) -> None:
        return None

    def login(self, user: str, password: str) -> None:
        self.logins.append((user, password))

    def send_message(self, msg: EmailMessage) -> None:
        self.sent.append(msg)

    @classmethod
    def all_sent(cls) -> list[EmailMessage]:
        return [m for i in cls.instances for m in i.sent]

    @classmethod
    def reset(cls) -> None:
        cls.instances = []
