import enum
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Numeric, String, Enum as SAEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class RequestStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELED = "canceled"


class Currency(str, enum.Enum):
    RUB = "RUB"
    USD = "USD"
    EUR = "EUR"


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[int] = mapped_column(primary_key=True)
    address: Mapped[str] = mapped_column(String(128))
    balance: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    onchain_requests: Mapped[list["OnchainRequest"]] = relationship(back_populates="wallet")
    fiat_transactions: Mapped[list["FiatTransaction"]] = relationship(back_populates="wallet")


class OnchainRequest(Base):
    __tablename__ = "onchain_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"))
    sum: Mapped[float] = mapped_column(Numeric(18, 2))
    recipient_wallet: Mapped[str] = mapped_column(String(128))
    status: Mapped[RequestStatus] = mapped_column(
        SAEnum(RequestStatus), default=RequestStatus.IN_PROGRESS
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    group_message_id: Mapped[int | None] = mapped_column(nullable=True)

    wallet: Mapped["Wallet"] = relationship(back_populates="onchain_requests")
    attachments: Mapped[list["OnchainReportPhoto"]] = relationship(
        back_populates="request", cascade="all, delete-orphan"
    )


class FiatTransaction(Base):
    __tablename__ = "fiat_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    wallet_id: Mapped[int] = mapped_column(ForeignKey("wallets.id"))
    sum_usdt: Mapped[float] = mapped_column(Numeric(18, 2))
    amount_received: Mapped[float] = mapped_column(Numeric(18, 2))
    currency: Mapped[Currency] = mapped_column(SAEnum(Currency))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    wallet: Mapped["Wallet"] = relationship(back_populates="fiat_transactions")
    attachments: Mapped[list["FiatReportPhoto"]] = relationship(
        back_populates="transaction", cascade="all, delete-orphan"
    )


class OnchainReportPhoto(Base):
    __tablename__ = "onchain_report_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("onchain_requests.id"))
    file_id: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    request: Mapped["OnchainRequest"] = relationship(back_populates="attachments")


class FiatReportPhoto(Base):
    __tablename__ = "fiat_report_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("fiat_transactions.id"))
    file_id: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    transaction: Mapped["FiatTransaction"] = relationship(back_populates="attachments")
