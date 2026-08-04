from datetime import datetime, timedelta, timezone
from io import BytesIO

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.db.models import FiatTransaction, OnchainRequest, RequestStatus
from bot.utils import format_amount, to_msk

PERIOD_DAYS = {"day": 1, "week": 7, "month": 30}


async def build_report(session: AsyncSession, period: str) -> BytesIO:
    days = PERIOD_DAYS[period]
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    rows: list[tuple[datetime, str, str, str]] = []

    onchain_result = await session.execute(
        select(OnchainRequest)
        .options(selectinload(OnchainRequest.wallet))
        .where(
            OnchainRequest.status == RequestStatus.DONE,
            OnchainRequest.completed_at >= cutoff,
        )
    )
    for req in onchain_result.scalars():
        rows.append(
            (req.completed_at, req.wallet.address, format_amount(req.sum), req.recipient_wallet)
        )

    fiat_result = await session.execute(
        select(FiatTransaction)
        .options(selectinload(FiatTransaction.wallet))
        .where(FiatTransaction.created_at >= cutoff)
    )
    for tx in fiat_result.scalars():
        recipient = f"fiat transaction {format_amount(tx.amount_received)}{tx.currency.value}"
        rows.append((tx.created_at, tx.wallet.address, format_amount(tx.sum_usdt), recipient))

    rows.sort(key=lambda r: r[0])

    wb = Workbook()
    ws = wb.active
    ws.title = "Report"
    ws.append(["Datetime", "Wallet from", "Transaction sum (USDT)", "Recipient"])
    for dt, wallet_from, amount, recipient in rows:
        local_dt = to_msk(dt)
        ws.append([local_dt.strftime("%Y-%m-%d %H:%M:%S"), wallet_from, amount, recipient])

    buffer = BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer
