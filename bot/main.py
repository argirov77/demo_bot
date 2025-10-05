import asyncio, os, json, datetime as dt, random
from pathlib import Path
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot")
PAY_BASE_URL = os.getenv("PUBLIC_PAY_BASE_URL", "http://localhost:9088")
TZ = os.getenv("TZ", "Europe/Sofia")

dp = Dispatcher()

DATA_PATH = Path("/app/data/demo.json")
DATA_LOCK = asyncio.Lock()
SESSION_STATE: dict[tuple[int, int], dict] = {}
SESSION_LOCK = asyncio.Lock()


def _session_key(call: types.CallbackQuery) -> tuple[int, int] | None:
    if call.message is None:
        return None
    return (call.message.chat.id, call.message.message_id)


async def session_get(call: types.CallbackQuery) -> dict | None:
    key = _session_key(call)
    if key is None:
        return None
    async with SESSION_LOCK:
        state = SESSION_STATE.get(key)
        return dict(state) if state else None


async def session_update(call: types.CallbackQuery, **updates) -> dict:
    key = _session_key(call)
    if key is None:
        return {}
    async with SESSION_LOCK:
        state = SESSION_STATE.setdefault(key, {})
        state.update(updates)
        return dict(state)


async def session_clear(call: types.CallbackQuery):
    key = _session_key(call)
    if key is None:
        return
    async with SESSION_LOCK:
        SESSION_STATE.pop(key, None)

def _now():
    # без pytz, просто локально
    return dt.datetime.now()

async def read_data():
    async with DATA_LOCK:
        if not DATA_PATH.exists():
            DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
            DATA_PATH.write_text(json.dumps({"services": [], "bookings": []}, ensure_ascii=False, indent=2), encoding="utf-8")
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))

async def write_data(data: dict):
    async with DATA_LOCK:
        DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ==== UI ====

def main_menu():
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗓 Записаться", callback_data="menu_book")],
        [InlineKeyboardButton(text="📅 Свободные даты", callback_data="menu_free")],
        [InlineKeyboardButton(text="💳 Прайс-лист", callback_data="menu_price")],
        [InlineKeyboardButton(text="🧑‍💼 Мои записи", callback_data="menu_my")],
        [InlineKeyboardButton(text="❔ Помощь", callback_data="menu_help")]
    ])
    return kb

def back_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="« Назад в меню", callback_data="menu_main")]
    ])

def services_kb(services: list[dict]):
    rows = [[InlineKeyboardButton(text=f"{s['name']} — {s['price']/100:.2f} лв", callback_data=f"svc_{s['id']}")] for s in services]
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="menu_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def dates_kb(days: int = 7):
    today = _now().date()
    rows = []
    for i in range(days):
        d = today + dt.timedelta(days=i)
        rows.append([InlineKeyboardButton(text=d.strftime("%d %b (%a)"), callback_data=f"date_{d.isoformat()}")])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="menu_book")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def times_kb(day: dt.date, service_minutes: int):
    # генерим сетку 10:00-19:00, шаг 30 мин, фильтр по длительности
    start = dt.datetime.combine(day, dt.time(10,0))
    end = dt.datetime.combine(day, dt.time(19,0))
    slots = []
    t = start
    while t + dt.timedelta(minutes=service_minutes) <= end:
        label = t.strftime("%H:%M")
        slots.append([InlineKeyboardButton(text=label, callback_data=f"time_{int(t.timestamp())}")])
        t += dt.timedelta(minutes=30)
    slots.append([InlineKeyboardButton(text="« Назад к датам", callback_data="menu_book_dates")])
    return InlineKeyboardMarkup(inline_keyboard=slots)

# ==== /start и меню ====

@dp.message(CommandStart())
async def start(m: types.Message):
    await m.answer("Привет! Это демо-бот записи.\nВыберите действие:", reply_markup=main_menu())

@dp.callback_query(F.data == "menu_main")
async def menu_main(call: types.CallbackQuery):
    await session_clear(call)
    await call.message.edit_text("Главное меню:", reply_markup=main_menu())
    await call.answer()

# ==== Прайс-лист ====

@dp.callback_query(F.data == "menu_price")
async def menu_price(call: types.CallbackQuery):
    data = await read_data()
    lines = ["💳 *Прайс-лист:*"]
    for s in data["services"]:
        lines.append(f"- {s['name']}: {s['price']/100:.2f} лв · {s['duration_min']} мин")
    text = "\n".join(lines)
    await call.message.edit_text(text, reply_markup=back_menu(), parse_mode="Markdown")
    await call.answer()

# ==== Помощь ====

@dp.callback_query(F.data == "menu_help")
async def menu_help(call: types.CallbackQuery):
    text = ("❔ *Помощь*\n"
            "• Нажмите «Записаться» → выберите услугу, дату и время → оплатите (демо).\n"
            "• «Свободные даты» показывает ближайшие 7 дней.\n"
            "• «Мои записи» — список ваших броней; можно отменить.\n")
    await call.message.edit_text(text, reply_markup=back_menu(), parse_mode="Markdown")
    await call.answer()

# ==== Мои записи ====

@dp.callback_query(F.data == "menu_my")
async def menu_my(call: types.CallbackQuery):
    data = await read_data()
    uid = call.from_user.id
    bookings = [b for b in data["bookings"] if b["user_id"] == uid and b["status"] != "canceled"]
    if not bookings:
        await call.message.edit_text("У вас пока нет записей.", reply_markup=back_menu())
        await call.answer(); return
    rows = []
    for b in bookings:
        when = dt.datetime.fromtimestamp(b["start_ts"]).strftime("%d.%m %H:%M")
        rows.append([InlineKeyboardButton(text=f"Отменить {when} · #{b['id']}", callback_data=f"cancel_{b['id']}")])
    rows.append([InlineKeyboardButton(text="« Назад", callback_data="menu_main")])
    kb = InlineKeyboardMarkup(inline_keyboard=rows)
    await call.message.edit_text("Ваши активные записи:", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_booking(call: types.CallbackQuery):
    bid = int(call.data.split("_",1)[1])
    data = await read_data()
    for b in data["bookings"]:
        if b["id"] == bid:
            b["status"] = "canceled"
            break
    await write_data(data)
    await call.message.edit_text("Запись отменена.", reply_markup=back_menu())
    await call.answer()

# ==== Свободные даты (быстрое отображение) ====

@dp.callback_query(F.data == "menu_free")
async def menu_free(call: types.CallbackQuery):
    # На демо просто показываем ближайшие 7 дат
    await call.message.edit_text("Выберите дату:", reply_markup=dates_kb(days=7))
    await call.answer()

# ==== Запись: услуга → дата → время → оплата ====

@dp.callback_query(F.data == "menu_book")
async def menu_book(call: types.CallbackQuery):
    data = await read_data()
    await session_clear(call)
    await call.message.edit_text("Выберите услугу:", reply_markup=services_kb(data["services"]))
    await call.answer()

@dp.callback_query(F.data == "menu_book_dates")
async def menu_book_dates(call: types.CallbackQuery):
    conf = await session_get(call)
    suffix = f" для услуги «{conf['svc_name']}»" if conf and conf.get("svc_name") else ""
    await call.message.edit_text(f"Выберите дату{suffix}:", reply_markup=dates_kb(days=7))
    await call.answer()

@dp.callback_query(F.data.startswith("svc_"))
async def choose_service(call: types.CallbackQuery):
    svc_id = int(call.data.split("_",1)[1])
    data = await read_data()
    svc = next((s for s in data["services"] if s["id"] == svc_id), None)
    if not svc:
        await call.answer("Услуга не найдена", show_alert=True)
        return
    await session_update(call,
                         svc_id=svc["id"],
                         svc_name=svc["name"],
                         duration=svc["duration_min"],
                         price=svc["price"])
    await call.message.edit_text(
        (f"Вы выбрали: {svc['name']}\n"
         f"Длительность: {svc['duration_min']} мин\n"
         f"Стоимость: {svc['price']/100:.2f} лв\n\n"
         "Теперь выберите дату:"),
        reply_markup=dates_kb())
    await call.answer()

# перехват выбора даты — сохраняем в conf
@dp.callback_query(F.data.startswith("date_"))
async def choose_date(call: types.CallbackQuery):
    d = dt.date.fromisoformat(call.data.split("_",1)[1])
    conf = await session_get(call)
    if not conf or "svc_id" not in conf:
        data = await read_data()
        default = data["services"][0]
        conf = await session_update(call,
                                    svc_id=default["id"],
                                    svc_name=default["name"],
                                    duration=default["duration_min"],
                                    price=default["price"])
    await session_update(call, date=d.isoformat())
    await call.message.edit_text(
        (f"Услуга: {conf['svc_name']}\n"
         f"Дата: {d.strftime('%d %b (%a)')}\n"
         "Выберите время:"),
        reply_markup=times_kb(d, conf["duration"]))
    await call.answer()

@dp.callback_query(F.data.startswith("time_"))
async def choose_time(call: types.CallbackQuery):
    ts = int(call.data.split("_",1)[1])
    conf = await session_get(call)
    if not conf or not {"duration", "price", "svc_name"}.issubset(conf):
        await call.answer("Сессия истекла, начните заново.", show_alert=True); return
    start_ts = ts
    end_ts = ts + conf["duration"] * 60
    total = conf["price"]
    order_id = random.randint(10000,99999)

    text = (f"Итог:\n"
            f"• Услуга: {conf['svc_name']}\n"
            f"• Когда: {dt.datetime.fromtimestamp(start_ts).strftime('%d.%m %H:%M')}\n"
            f"• Длительность: {conf['duration']} мин\n"
            f"• Сумма: {total/100:.2f} лв\n\n"
            f"Нажмите «Оплатить (демо)» для подтверждения.")
    # ссылка на оплату
    link = f"{PAY_BASE_URL}/pay?order_id={order_id}&amount={total}&currency=BGN&return_url=https://t.me/{BOT_USERNAME}"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Оплатить (демо)", url=link)],
        [InlineKeyboardButton(text="« Назад в меню", callback_data="menu_main")]
    ])
    # сохраним бронь как pending (в демо — сразу confirmed после «оплаты» вручную не триггерим)
    data = await read_data()
    next_id = (max([b["id"] for b in data["bookings"]] or [0]) + 1)
    data["bookings"].append({
        "id": next_id,
        "user_id": call.from_user.id,
        "service_id": conf["svc_id"],
        "service_name": conf["svc_name"],
        "start_ts": start_ts,
        "end_ts": end_ts,
        "status": "pending",
        "order_id": order_id,
        "created_at": int(_now().timestamp())
    })
    await write_data(data)

    await session_clear(call)
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()

# Команда /price, /help дублируют кнопки
@dp.message(Command("price"))
async def cmd_price(m: types.Message):
    data = await read_data()
    lines = ["💳 Прайс-лист:"]
    for s in data["services"]:
        lines.append(f"- {s['name']}: {s['price']/100:.2f} лв · {s['duration_min']} мин")
    await m.answer("\n".join(lines))

@dp.message(Command("my"))
async def cmd_my(m: types.Message):
    data = await read_data()
    uid = m.from_user.id
    bookings = [b for b in data["bookings"] if b["user_id"] == uid and b["status"] != "canceled"]
    if not bookings:
        await m.answer("У вас пока нет записей.")
        return
    lines = ["Ваши записи:"]
    for b in bookings:
        when = dt.datetime.fromtimestamp(b["start_ts"]).strftime("%d.%m %H:%M")
        lines.append(f"• #{b['id']} {b['service_name']} — {when}")
    await m.answer("\n".join(lines))

async def main():
    bot = Bot(BOT_TOKEN)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
