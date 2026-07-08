import asyncio
from contextlib import asynccontextmanager

from aiogram.types import MenuButtonWebApp, Update, WebAppInfo
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.api.routes import admin, banners, chat, generate, me, payments, referral, tools
from app.bot.instance import bot
from app.bot.setup import create_dispatcher
from app.config import settings
from app.db.session import get_session
from app.services.keys.key_healthcheck import run_key_healthcheck
from app.services.payments.setup import register_all_gateways
from app.webhooks import yookassa as yookassa_webhook
from app.webhooks import piapi as piapi_webhook

register_all_gateways()
dp = create_dispatcher()

_polling_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _polling_task

    async with get_session() as session:
        await run_key_healthcheck(session)

    if settings.frontend_url.startswith("https://"):
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="Открыть", web_app=WebAppInfo(url=settings.frontend_url))
        )

    if settings.bot_mode == "webhook":
        webhook_url = f"{settings.webapp_url}/webhook/{settings.webhook_secret}"
        await bot.set_webhook(webhook_url, secret_token=settings.webhook_secret)
    else:
        await bot.delete_webhook(drop_pending_updates=True)
        _polling_task = asyncio.create_task(dp.start_polling(bot))

    yield

    if _polling_task:
        _polling_task.cancel()
    await bot.session.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url] if settings.frontend_url else [],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


app.include_router(me.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(tools.router, prefix="/api")
app.include_router(banners.router, prefix="/api")
app.include_router(referral.router, prefix="/api")
app.include_router(payments.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(generate.router, prefix="/api")
app.include_router(yookassa_webhook.router)
app.include_router(piapi_webhook.router)


@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request) -> dict:
    if secret != settings.webhook_secret:
        raise HTTPException(status_code=404)
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}


@app.get("/payment/return", response_class=HTMLResponse)
async def payment_return() -> str:
    # ЮKassa не подтверждает оплату по возврату сюда — активация идёт только
    # через webhook (см. app/webhooks/yookassa.py). Эта страница лишь просит
    # пользователя вернуться в Telegram.
    return (
        "<html><body style='font-family:sans-serif;text-align:center;padding-top:40px'>"
        "<p>Оплата обрабатывается. Вернитесь в Telegram — доступ активируется автоматически.</p>"
        f"<p><a href='https://t.me/{settings.bot_username}'>Открыть бота</a></p>"
        "</body></html>"
    )
