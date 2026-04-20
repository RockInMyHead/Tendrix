
import logging
import asyncio
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base, User

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()

# Absolute path to ensure it finds the same DB as main.py
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sql_app.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

logger.info(f"Connecting to DB at {SQLALCHEMY_DATABASE_URL}")

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: types.Message):
    # Check if a code was passed: /start 12345678
    args = message.text.split()
    if len(args) > 1:
        code = args[1]
        if len(code) == 8 and code.isdigit():
            await link_account(message, code)
            return

    await message.answer(
        "👋 Привет! Я бот Tendrix.\n\n"
        "Чтобы получать уведомления о новых тендерах, свяжите свой аккаунт.\n"
        "Для этого:\n"
        "1. Зайдите в личный кабинет на tendrix.io\n"
        "2. Нажмите «Связать с Telegram» (или «Обновить код привязки» в профиле)\n"
        "3. Отсканируйте QR-код или отправьте мне 8-значный код.\n\n"
        "Команды:\n"
        "• /verify — как привязать заново\n"
        "• /describe — есть ли у вас подписка Pro\n\n"
        "Без Pro в Telegram приходят все новые тендеры.\n"
        "С Pro — только те, что совпадают с описанием компании в профиле."
    )


@dp.message(Command("verify"))
@dp.message(Command("relink"))
async def command_verify_handler(message: types.Message):
    await message.answer(
        "🔁 Повторная привязка (верификация)\n\n"
        "1. Откройте tendrix.io → Профиль.\n"
        "2. Если Telegram уже подключён — нажмите «Обновить код привязки»; "
        "если нет — «Связать с Telegram».\n"
        "3. Отправьте боту новый 8-значный код из окна или ссылку /start с кодом.\n\n"
        "Этот Telegram отвяжется от старого аккаунта Tendrix, если вы привязываете другой."
    )


@dp.message(Command("describe"))
async def command_describe_handler(message: types.Message):
    session = SessionLocal()
    try:
        user = session.query(User).filter(User.telegram_id == message.from_user.id).first()
        if not user:
            await message.answer(
                "Аккаунт Tendrix не привязан к этому Telegram.\n"
                "Получите код в профиле на tendrix.io и отправьте его сюда."
            )
            return
        if user.is_pro:
            await message.answer(
                "У вас активна подписка Tendrix Pro.\n"
                "В Telegram вам приходят только тендеры, которые пересекаются с описанием компании в профиле."
            )
        else:
            await message.answer(
                "Подписки Pro сейчас нет.\n"
                "В Telegram вам приходят уведомления по всем новым тендерам (в рамках настроек сервиса).\n"
                "Pro можно включить в личном кабинете на сайте."
            )
    except Exception as e:
        logger.error(f"/describe error: {e}")
        await message.answer("Не удалось проверить подписку. Попробуйте позже.")
    finally:
        session.close()


@dp.message(F.text)
async def text_handler(message: types.Message):
    if message.text and message.text.startswith("/"):
        return
    code = message.text.strip()
    if len(code) == 8 and code.isdigit():
        await link_account(message, code)
    else:
        await message.answer(
            "⚠️ Отправьте 8-значный код из личного кабинета tendrix.io.\n"
            "Повторная привязка: команда /verify"
        )

async def link_account(message: types.Message, code: str):
    session = SessionLocal()
    try:
        tg_id = message.from_user.id
        user = session.query(User).filter(User.telegram_connect_code == code).first()
        if user:
            for prev in session.query(User).filter(User.telegram_id == tg_id).all():
                prev.telegram_id = None
            user.telegram_id = tg_id
            user.telegram_connect_code = None
            session.commit()

            await message.answer(
                f"✅ Аккаунт «{user.username}» успешно привязан к этому Telegram.\n\n"
                "Уведомления о тендерах будут приходить сюда. Подписку Pro можно проверить командой /describe."
            )
            logger.info(f"User {user.username} linked to TG ID {tg_id}")
        else:
            await message.answer(
                "❌ Неверный или устаревший код.\n"
                "Сгенерируйте новый в профиле tendrix.io (кнопка «Обновить код привязки» или «Связать с Telegram») "
                "и отправьте код снова. Подсказка: /verify"
            )
    except Exception as e:
        logger.error(f"Error linking account: {e}")
        await message.answer("Произошла ошибка базы данных. Попробуйте позже.")
    finally:
        session.close()

async def main():
    bot = Bot(token=TOKEN)
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    if not TOKEN:
        logger.error("Задайте TELEGRAM_BOT_TOKEN в окружении или .env")
        sys.exit(1)
    asyncio.run(main())
