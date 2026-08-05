# Transaction Tracking Telegram Bot

Bot for tracking onchain (TRC20/USDT) and fiat transactions between two roles — **Owner** and **Executor** — with wallet management and Excel reporting.

## Stack

- Python 3.12, [aiogram 3](https://docs.aiogram.dev/) (FSM-based forms, inline keyboards)
- SQLite (via SQLAlchemy async + aiosqlite)
- openpyxl for `.xlsx` reports
- Docker / docker-compose for deployment

## 1. Create the bot and group chat

1. In Telegram, open **@BotFather** → `/newbot` → follow the prompts → copy the token it gives you (looks like `123456789:AA...`). This is `BOT_TOKEN`.
2. Create a Telegram **group chat** for the Owner and Executor to talk freely in and receive bot notifications.
3. Add the bot to that group (Add member → search the bot by username) and make it an **admin** (needed to reliably post/edit messages).
4. Get the group's `chat_id`:
   - Send any message in the group.
   - Open `https://api.telegram.org/bot<BOT_TOKEN>/getUpdates` in a browser (with your real token).
   - Find `"chat":{"id":-100XXXXXXXXXX, ...}` in the response — that negative number is `GROUP_CHAT_ID`.
5. Get the Telegram user IDs of the Owner and the Executor:
   - Each of them opens a private chat with **@userinfobot** (or similar) and sends any message; it replies with their numeric `id`.
   - Alternatively, have each person send `/start` to your bot once, then check the bot logs / `getUpdates` for their `from.id`.

## 2. Configure

```bash
cp .env.example .env
```

Fill in `.env`:

```
BOT_TOKEN=123456789:AA...
OWNER_ID=111111111
EXECUTOR_ID=222222222
GROUP_CHAT_ID=-1001234567890
DB_PATH=data/bot.db
```

## 3. Run with Docker

```bash
docker compose up --build -d
```

The SQLite database persists in `./data/bot.db` on the host (mounted volume).

The container uses `network_mode: host`, so it shares the host's network stack directly — this avoids Docker bridge/DNS routing issues that can otherwise cause `TelegramNetworkError: Request timeout error` on some hosts.

### If the bot can't reach Telegram at all

If logs show a repeating `TelegramNetworkError` / connection timeout and the container keeps restarting, your ISP is most likely blocking `api.telegram.org` directly (common in some countries). Check from the host:

```bash
curl -m 8 -o /dev/null -w "HTTP %{http_code}\n" https://api.telegram.org
```

If this also times out, the bot needs a proxy to reach Telegram. Set `PROXY_URL` in `.env` to an HTTP(S) or SOCKS5 proxy you control (e.g. a lightweight proxy on a VPS outside the blocked region):

```
PROXY_URL=socks5://user:pass@your-proxy-host:1080
```

Then rebuild: `docker compose up --build -d`.

#### Using a Hysteria2 proxy

Hysteria2 isn't a SOCKS/HTTP proxy protocol, so it can't be plugged into `PROXY_URL` directly. Instead, `docker-compose.yml` runs the official Hysteria2 client as a sidecar (`hysteria` service) which exposes a local SOCKS5 proxy that the bot then connects to:

1. `cp hysteria/config.example.yaml hysteria/config.yaml`
2. Fill in `hysteria/config.yaml` from your `hysteria2://` share link:
   - `hysteria2://AUTH@SERVER:PORT?insecure=1#name` →
     `server: SERVER:PORT`, `auth: AUTH`, `tls.insecure: true` (only if `insecure=1` was in the link).
3. Keep `.env`'s `PROXY_URL=socks5://127.0.0.1:1080` — both containers use `network_mode: host`, so the bot reaches the Hysteria2 client's local SOCKS5 port via `localhost`.
4. `docker compose up --build -d` (pulls the `tobyxdd/hysteria` client image on first run)

`hysteria/config.yaml` is gitignored since it holds your real proxy credentials.

Logs:

```bash
docker compose logs -f
```

Stop:

```bash
docker compose down
```

## 4. Using the bot

- Each actor opens a **private chat** with the bot and sends `/start` — the bot shows a menu based on their role (Owner or Executor).
- All functional actions (creating transactions, managing wallets, downloading reports) happen in that **private chat**.
- The bot posts all notifications (new request, status changes, new wallet, balance changes, transfers) into the **group chat**, where both actors can also talk freely — the bot does not react to plain messages there.

### Owner
- **New transaction** — create an onchain (TRC20/USDT) transfer request; funds are held on the wallet until the Executor completes or the Owner cancels it.
- **Download report** — export an `.xlsx` report for the last day / week / month.

### Executor
- **Fiat transaction** — record a bank transfer or cash payout, converted from USDT.
- **Add wallet** — register a new wallet with an optional initial deposit.
- **Delete wallet** — soft-delete a wallet: it stops being offered for any action, but past transactions against it still show up in reports.
- **Change balance** — adjust a wallet's balance up or down (enter a negative number, e.g. `-500`, to subtract); can't push the balance below zero.
- **Tr. between wallets** — move funds from one wallet to another.
- **Download report** — same as above.
- Reacts to **"Attach a report"** on a request card in the group chat by sending a screenshot in the private chat with the bot, which marks the request as Done and settles the wallet balance.

## Project layout

```
bot/
  config.py          # env config
  main.py             # entrypoint
  db/                 # SQLAlchemy models + async engine
  services/            # business logic: wallets, reports, group notifications
  keyboards/            # reply/inline keyboards
  handlers/             # aiogram routers per feature
  middlewares/          # role resolution (Owner/Executor/unknown)
```
