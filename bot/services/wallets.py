from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import (
    Currency,
    FiatReportPhoto,
    FiatTransaction,
    OnchainReportPhoto,
    OnchainRequest,
    RequestStatus,
    Wallet,
    utcnow,
)


class InsufficientFundsError(Exception):
    pass


async def list_wallets(session: AsyncSession) -> list[Wallet]:
    result = await session.execute(select(Wallet).order_by(Wallet.id))
    return list(result.scalars().all())


async def get_wallet(session: AsyncSession, wallet_id: int) -> Wallet:
    wallet = await session.get(Wallet, wallet_id)
    if wallet is None:
        raise ValueError(f"Wallet {wallet_id} not found")
    return wallet


async def held_amount(session: AsyncSession, wallet_id: int) -> Decimal:
    result = await session.execute(
        select(func.coalesce(func.sum(OnchainRequest.sum), 0)).where(
            OnchainRequest.wallet_id == wallet_id,
            OnchainRequest.status == RequestStatus.IN_PROGRESS,
        )
    )
    return Decimal(str(result.scalar_one()))


async def available_balance(session: AsyncSession, wallet_id: int) -> Decimal:
    wallet = await get_wallet(session, wallet_id)
    held = await held_amount(session, wallet_id)
    return Decimal(str(wallet.balance)) - held


async def add_wallet(session: AsyncSession, address: str, deposit: Decimal) -> Wallet:
    wallet = Wallet(address=address, balance=deposit)
    session.add(wallet)
    await session.commit()
    await session.refresh(wallet)
    return wallet


async def change_balance(session: AsyncSession, wallet_id: int, refill_sum: Decimal) -> Wallet:
    wallet = await get_wallet(session, wallet_id)
    wallet.balance = Decimal(str(wallet.balance)) + refill_sum
    await session.commit()
    await session.refresh(wallet)
    return wallet


async def transfer_between_wallets(
    session: AsyncSession, from_wallet_id: int, to_wallet_id: int, amount: Decimal
) -> tuple[Wallet, Wallet]:
    avail = await available_balance(session, from_wallet_id)
    if amount > avail:
        raise InsufficientFundsError()
    from_wallet = await get_wallet(session, from_wallet_id)
    to_wallet = await get_wallet(session, to_wallet_id)
    from_wallet.balance = Decimal(str(from_wallet.balance)) - amount
    to_wallet.balance = Decimal(str(to_wallet.balance)) + amount
    await session.commit()
    await session.refresh(from_wallet)
    await session.refresh(to_wallet)
    return from_wallet, to_wallet


async def create_onchain_request(
    session: AsyncSession, wallet_id: int, amount: Decimal, recipient_wallet: str
) -> OnchainRequest:
    avail = await available_balance(session, wallet_id)
    if amount > avail:
        raise InsufficientFundsError()
    request = OnchainRequest(wallet_id=wallet_id, sum=amount, recipient_wallet=recipient_wallet)
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


async def get_onchain_request(session: AsyncSession, request_id: int) -> OnchainRequest:
    request = await session.get(OnchainRequest, request_id)
    if request is None:
        raise ValueError(f"Request {request_id} not found")
    return request


async def cancel_onchain_request(session: AsyncSession, request_id: int) -> OnchainRequest:
    request = await get_onchain_request(session, request_id)
    if request.status != RequestStatus.IN_PROGRESS:
        raise ValueError("Request is not in progress")
    request.status = RequestStatus.CANCELED
    await session.commit()
    await session.refresh(request)
    return request


async def settle_onchain_request(
    session: AsyncSession, request_id: int, report_file_ids: list[str]
) -> OnchainRequest:
    request = await get_onchain_request(session, request_id)
    if request.status != RequestStatus.IN_PROGRESS:
        raise ValueError("Request is not in progress")
    wallet = await get_wallet(session, request.wallet_id)
    wallet.balance = Decimal(str(wallet.balance)) - Decimal(str(request.sum))
    request.status = RequestStatus.DONE
    request.completed_at = utcnow()
    for file_id in report_file_ids:
        session.add(OnchainReportPhoto(request_id=request.id, file_id=file_id))
    await session.commit()
    await session.refresh(request)
    return request


async def create_fiat_transaction(
    session: AsyncSession,
    wallet_id: int,
    sum_usdt: Decimal,
    amount_received: Decimal,
    currency: Currency,
    report_file_ids: list[str],
) -> FiatTransaction:
    avail = await available_balance(session, wallet_id)
    if sum_usdt > avail:
        raise InsufficientFundsError()
    wallet = await get_wallet(session, wallet_id)
    wallet.balance = Decimal(str(wallet.balance)) - sum_usdt
    tx = FiatTransaction(
        wallet_id=wallet_id,
        sum_usdt=sum_usdt,
        amount_received=amount_received,
        currency=currency,
    )
    session.add(tx)
    await session.flush()
    for file_id in report_file_ids:
        session.add(FiatReportPhoto(transaction_id=tx.id, file_id=file_id))
    await session.commit()
    await session.refresh(tx)
    return tx
