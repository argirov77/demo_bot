import asyncio
import os

from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot")
PAY_BASE_URL = os.getenv("PUBLIC_PAY_BASE_URL", "http://localhost:9088")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Please update your .env file before running the bot.")

dp = Dispatcher()

@dp.message(CommandStart())
async def start(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплата (демо)", callback_data="paydemo")]
    ])
    await m.answer("Привет! Это демо-бот записи. Нажми «Оплата (демо)».", reply_markup=kb)

@dp.callback_query(lambda c: c.data == "paydemo")
async def paydemo(call: types.CallbackQuery):
    order_id = 123
    amount = 6000
    link = f"{PAY_BASE_URL}/pay?order_id={order_id}&amount={amount}&currency=BGN&return_url=https://t.me/{BOT_USERNAME}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить (демо)", url=link)]
    ])
    await call.message.edit_text(
        f"Демо-оплата заказа #{order_id}\nСумма: {amount/100:.2f} лв.",
        reply_markup=kb,
    )
    await call.answer()

async def main():
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
