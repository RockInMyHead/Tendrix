
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
from aiogram.filters import CommandStart
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
        "2. Нажмите «Связать с Telegram»\n"
        "3. Отсканируйте QR-код или отправьте мне 8-значный код."
    )

@dp.message(F.text)
async def text_handler(message: types.Message):
    code = message.text.strip()
    if len(code) == 8 and code.isdigit():
        await link_account(message, code)
    else:
        await message.answer("⚠️ Пожалуйста, отправьте корректный 8-значный код из личного кабинета.")

async def link_account(message: types.Message, code: str):
    session = SessionLocal()
    try:
        # Debug: list all valid codes
        all_codes = session.query(User.telegram_connect_code).filter(User.telegram_connect_code.isnot(None)).all()
        logger.info(f"Looking for code: {code}. Available codes: {all_codes}")

        user = session.query(User).filter(User.telegram_connect_code == code).first()
        if user:
            user.telegram_id = message.from_user.id
            # Clear the code so it can't be reused for takeover
            user.telegram_connect_code = None 
            session.commit()
            
            await message.answer(f"✅ Аккаунт **{user.username}** успешно привязан!\n\nТеперь вы будете получать уведомления о новых тендерах прямо сюда.")
            logger.info(f"User {user.username} linked to TG ID {message.from_user.id}")
        else:
            await message.answer("❌ Неверный код или он уже был использован.\nПопробуйте сгенерировать новый в личном кабинете.")
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
