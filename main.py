import logging
import datetime
from datetime import timedelta
from dotenv import load_dotenv
import os

from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from apscheduler.schedulers.asyncio import AsyncIOScheduler  # Для утренней рассылки
from openpyxl import Workbook  # <-- Add this import

from database import init_db, get_session, User, DailyLog

# -------------------------------------------------------------------
# Настройки
# -------------------------------------------------------------------
load_dotenv()  # Load environment variables from .env file
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
print("TELEGRAM_BOT_TOKEN",TELEGRAM_BOT_TOKEN)
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set")

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TELEGRAM_BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# -------------------------------------------------------------------
# Состояния для стандартного сбора данных "на сегодня"
# -------------------------------------------------------------------
class GatherDataState(StatesGroup):
    bedtime_before_midnight = State()
    no_gadgets_after_23 = State()
    followed_diet = State()
    sport_hours = State()

# -------------------------------------------------------------------
# Состояния для сбора данных задним числом
# -------------------------------------------------------------------
class BackdatedDataState(StatesGroup):
    select_date = State()
    bedtime_before_midnight = State()
    no_gadgets_after_23 = State()
    followed_diet = State()
    sport_hours = State()

# -------------------------------------------------------------------
# Универсальная клавиатура «Да / Нет»
# -------------------------------------------------------------------
yes_no_kb = ReplyKeyboardMarkup(resize_keyboard=True)
yes_no_kb.add("Да", "Нет")

# -------------------------------------------------------------------
# Команда /start
# -------------------------------------------------------------------
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    """
    Регистрируем пользователя в базе (если ещё не зарегистрирован) и выводим приветствие.
    """
    user_id = message.from_user.id
    username = message.from_user.username

    session = get_session()
    try:
        # Проверяем, есть ли уже такой юзер
        user = session.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            user = User(telegram_id=user_id, username=username)
            session.add(user)
            session.commit()

        await message.answer(
            "Привет! Я бот для отслеживания привычек.\n"
            "Каждое утро я напомню вам внести данные.\n\n"
            "Доступные команды:\n"
            "/gather_data — внести данные за сегодня\n"
            "/gather_data_backdated — внести данные за любой из последних 7 дней\n"
            "/weekly_stats — статистика за 7 дней"
        )
    except Exception as e:
        logging.error(f"Ошибка при регистрации пользователя: {e}")
        await message.answer("Произошла ошибка при регистрации пользователя.")
    finally:
        session.close()

# -------------------------------------------------------------------
# Стандартный сбор данных «на сегодня» – ручной запуск
# -------------------------------------------------------------------
@dp.message_handler(commands=["gather_data"])
async def cmd_gather_data(message: types.Message):
    """
    Запуск пошагового опроса (FSM) для сегодняшней даты.
    """
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    await state.set_state(GatherDataState.bedtime_before_midnight.state)

    # Спрашиваем первый вопрос
    await message.answer(
        "Легли ли вы вчера до 00:00? (да/нет)",
        reply_markup=yes_no_kb
    )

# -------------------------------------------------------------------
# Шаг 1 (сегодня): Лёг ли пользователь до 00:00
# -------------------------------------------------------------------
@dp.message_handler(state=GatherDataState.bedtime_before_midnight)
async def process_bedtime_today(message: types.Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ["да", "нет"]:
        bedtime_before_midnight = (text == "да")
        await state.update_data(bedtime_before_midnight=bedtime_before_midnight)
        await GatherDataState.next()
        await message.reply(
            "Использовали ли вы вчера гаджеты после 23:00? (да/нет)",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await message.answer("Пожалуйста, выберите «да» или «нет».", reply_markup=yes_no_kb)

# -------------------------------------------------------------------
# Шаг 2 (сегодня): Гаджеты после 23:00
# -------------------------------------------------------------------
@dp.message_handler(state=GatherDataState.no_gadgets_after_23)
async def process_no_gadgets_today(message: types.Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ["да", "нет"]:
        gadgets_after_23 = (text == "да")
        no_gadgets_after_23 = not gadgets_after_23
        await state.update_data(no_gadgets_after_23=no_gadgets_after_23)
        await GatherDataState.next()
        await message.reply(
            "Питались ли вы вчера по рациону? (да/нет)",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await message.answer("Пожалуйста, выберите «да» или «нет».", reply_markup=yes_no_kb)

# -------------------------------------------------------------------
# Шаг 3 (сегодня): Питался ли по рациону
# -------------------------------------------------------------------
@dp.message_handler(state=GatherDataState.followed_diet)
async def process_followed_diet_today(message: types.Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ["да", "нет"]:
        followed_diet = (text == "да")
        await state.update_data(followed_diet=followed_diet)
        await GatherDataState.next()
        await message.reply(
            "Сколько часов вы вчера занимались спортом? (введите число)",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await message.answer("Пожалуйста, выберите «да» или «нет».", reply_markup=yes_no_kb)

# -------------------------------------------------------------------
# Шаг 4 (сегодня): Количество часов спорта
# -------------------------------------------------------------------
@dp.message_handler(state=GatherDataState.sport_hours)
async def process_sport_hours_today(message: types.Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        sport_hours = float(text)
    except ValueError:
        await message.answer("Пожалуйста, введите число (например 1.5).")
        return
    
    await state.update_data(sport_hours=sport_hours)
    data = await state.get_data()
    session = get_session()
    try:
        yesterday = datetime.date.today() - timedelta(days=1) # Calculate yesterday's date
        new_log = DailyLog(
            user_id=message.from_user.id,
            username=message.from_user.username,
            bedtime_before_midnight=data["bedtime_before_midnight"],
            no_gadgets_after_23=data["no_gadgets_after_23"],
            followed_diet=data["followed_diet"],
            sport_hours=data["sport_hours"],
            date_of_entry=yesterday, # Use yesterday's date
        )
        session.add(new_log)
        session.commit()
        await message.reply(
            f"Данные за {yesterday.strftime('%Y-%m-%d')} успешно сохранены! Спасибо!",
            reply_markup=ReplyKeyboardRemove(),
        )
    except Exception as e:
        session.rollback()
        logging.error(f"Ошибка сохранения в БД: {e}")
        await message.answer("Произошла ошибка при сохранении данных.")
        return
    finally:
        session.close()
    await state.finish()

# -------------------------------------------------------------------
# Новая команда: /gather_data_backdated (задним числом)
# -------------------------------------------------------------------
@dp.message_handler(commands=["gather_data_backdated"])
async def cmd_gather_data_backdated(message: types.Message):
    """
    Пользователь выбирает любую дату из последних 7 дней при помощи инлайн-кнопок,
    затем идёт пошаговый опрос (как обычно), но данные пишутся на выбранную дату.
    """
    state = dp.current_state(chat=message.chat.id, user=message.from_user.id)
    await state.set_state(BackdatedDataState.select_date.state)

    # Сформируем список последних 7 дней (включая сегодня)
    keyboard = InlineKeyboardMarkup(row_width=3)
    today = datetime.date.today()
    for i in range(7):
        day = today - timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        btn = InlineKeyboardButton(
            text=day_str,
            callback_data=f"select_date:{day_str}"
        )
        keyboard.insert(btn)

    await message.answer(
        "Выберите дату, за которую хотите внести данные:",
        reply_markup=keyboard
    )


@dp.message_handler(commands=["export_excel"])
async def export_excel_cmd(message: types.Message):
    user_id = message.from_user.id
    session = get_session()

    try:
        # Берём все логи пользователя (или измените фильтр по датам, если нужно)
        logs = session.query(DailyLog).filter(DailyLog.user_id == user_id).all()
    finally:
        session.close()

    if not logs:
        await message.answer("У вас нет данных для экспорта.")
        return

    # Создаём Excel-книгу
    wb = Workbook()
    ws = wb.active
    ws.title = "Habit Logs"

    # Добавим строку заголовков (пример)
    ws.append([
        "ID",
        "Дата",
        "Лёг до 00:00",
        "Не использовал гаджеты после 23:00",
        "Питался по рациону",
        "Часы спорта",
        "Дата записи (UTC)"
    ])

    # Заполняем строки из БД
    for log in logs:
        ws.append([
            log.id,
            log.date_of_entry.strftime("%Y-%m-%d"),
            "Да" if log.bedtime_before_midnight else "Нет",
            "Да" if log.no_gadgets_after_23 else "Нет",
            "Да" if log.followed_diet else "Нет",
            str(log.sport_hours),
            log.created_at.strftime("%Y-%m-%d %H:%M:%S")
        ])

    # Сохраняем во временный файл
    filename = f"export_{user_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    wb.save(filename)

    # Отправляем файл
    await message.answer_document(
        document=types.InputFile(filename),
        caption="Вот ваши данные в Excel!"
    )

    # Удаляем временный файл
    os.remove(filename)

# -------------------------------------------------------------------
# Хэндлер нажатия инлайн-кнопки (выбор даты)
# -------------------------------------------------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("select_date:"), state=BackdatedDataState.select_date)
async def process_backdated_select_date(callback_query: types.CallbackQuery, state: FSMContext):
    # Парсим дату из callback_data
    _, date_str = callback_query.data.split(":", 1)
    selected_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()

    # Сохраняем дату в FSM
    await state.update_data(selected_date=selected_date)
    # Переходим к первому вопросу (bedtime)
    await BackdatedDataState.bedtime_before_midnight.set()

    # Удалим инлайн-клавиатуру
    await callback_query.message.edit_reply_markup()
    # Задаём вопрос
    await callback_query.message.answer(
        f"Легли ли вы {date_str} до 00:00? (да/нет)",
        reply_markup=yes_no_kb
    )

# -------------------------------------------------------------------
# Шаг 1 (задним числом): Лёг ли до 00:00
# -------------------------------------------------------------------
@dp.message_handler(state=BackdatedDataState.bedtime_before_midnight)
async def process_bedtime_backdated(message: types.Message, state: FSMContext):
    text = message.text.lower().strip()
    if text in ["да", "нет"]:
        bedtime_before_midnight = (text == "да")
        await state.update_data(bedtime_before_midnight=bedtime_before_midnight)
        await BackdatedDataState.next()
        data = await state.get_data()
        date_str = data.get("selected_date", datetime.date.today()).strftime("%Y-%m-%d")
        await message.answer(
            f"Использовали ли вы {date_str} гаджеты после 23:00? (да/нет)",
            reply_markup=yes_no_kb
        )
    else:
        await message.answer("Пожалуйста, выберите «да» или «нет».", reply_markup=yes_no_kb)

# -------------------------------------------------------------------
# Шаг 2 (задним числом): Гаджеты после 23:00
# -------------------------------------------------------------------
@dp.message_handler(state=BackdatedDataState.no_gadgets_after_23)
async def process_no_gadgets_backdated(message: types.Message, state: FSMContext):
    text = message.text.lower().strip()
    if text in ["да", "нет"]:
        gadgets_after_23 = (text == "да")
        no_gadgets_after_23 = not gadgets_after_23
        await state.update_data(no_gadgets_after_23=no_gadgets_after_23)
        await BackdatedDataState.next()

        data = await state.get_data()
        date_str = data.get("selected_date", datetime.date.today()).strftime("%Y-%m-%d")
        await message.answer(
            f"Питались ли вы {date_str} по рациону? (да/нет)",
            reply_markup=yes_no_kb
        )
    else:
        await message.answer("Пожалуйста, выберите «да» или «нет».", reply_markup=yes_no_kb)

# -------------------------------------------------------------------
# Шаг 3 (задним числом): Питался по рациону
# -------------------------------------------------------------------
@dp.message_handler(state=BackdatedDataState.followed_diet)
async def process_followed_diet_backdated(message: types.Message, state: FSMContext):
    text = message.text.lower().strip()
    if text in ["да", "нет"]:
        followed_diet = (text == "да")
        await state.update_data(followed_diet=followed_diet)
        await BackdatedDataState.next()

        data = await state.get_data()
        date_str = data.get("selected_date", datetime.date.today()).strftime("%Y-%m-%d")
        await message.answer(
            f"Сколько часов занялись спортом {date_str}? (введите число)",
            reply_markup=ReplyKeyboardRemove()
        )
    else:
        await message.answer("Пожалуйста, выберите «да» или «нет».", reply_markup=yes_no_kb)

# -------------------------------------------------------------------
# Шаг 4 (задним числом): Часы спорта
# -------------------------------------------------------------------
@dp.message_handler(state=BackdatedDataState.sport_hours)
async def process_sport_hours_backdated(message: types.Message, state: FSMContext):
    text = message.text.strip().replace(",", ".")
    try:
        sport_hours = float(text)
    except ValueError:
        await message.answer("Пожалуйста, введите число (например 1.5).")
        return
    
    await state.update_data(sport_hours=sport_hours)
    data = await state.get_data()
    await state.finish()

    selected_date = data["selected_date"]
    bedtime_before_midnight = data["bedtime_before_midnight"]
    no_gadgets_after_23 = data["no_gadgets_after_23"]
    followed_diet = data["followed_diet"]

    # Сохраняем данные в БД
    session = get_session()
    try:
        log_entry = DailyLog(
            user_id=message.from_user.id,
            date_of_entry=selected_date,
            bedtime_before_midnight=bedtime_before_midnight,
            no_gadgets_after_23=no_gadgets_after_23,
            followed_diet=followed_diet,
            sport_hours=sport_hours
        )
        session.add(log_entry)
        session.commit()
    except Exception as e:
        session.rollback()
        logging.error(f"Ошибка сохранения в БД: {e}")
        await message.answer("Произошла ошибка при сохранении данных.")
        return
    finally:
        session.close()

    await message.answer(
        f"Данные за {selected_date.strftime('%Y-%m-%d')} успешно сохранены! Спасибо!"
    )

# -------------------------------------------------------------------
# Команда /weekly_stats — статистика за 7 дней
# -------------------------------------------------------------------
@dp.message_handler(commands=["weekly_stats"])
async def cmd_weekly_stats(message: types.Message):
    user_id = message.from_user.id
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)
    
    session = get_session()
    try:
        logs = session.query(DailyLog).filter(
            DailyLog.user_id == user_id,
            DailyLog.date_of_entry >= week_ago
        ).all()

        if not logs:
            await message.answer("Нет данных за последние 7 дней.")
            return

        days_count = len(logs)
        bedtime_count = sum(log.bedtime_before_midnight for log in logs)
        gadgets_count = sum(log.no_gadgets_after_23 for log in logs)
        diet_count = sum(log.followed_diet for log in logs)
        total_sport_hours = sum(log.sport_hours for log in logs)

        avg_sport = round(total_sport_hours / days_count, 2)

        text_stats = (
            f"Статистика за последние 7 дней:\n\n"
            f"Всего записей: {days_count}\n"
            f"1) Легли до 00:00: {bedtime_count} раз(а)\n"
            f"2) Не использовали гаджеты после 23:00: {gadgets_count} раз(а)\n"
            f"3) Питались по рациону: {diet_count} раз(а)\n"
            f"4) Среднее кол-во часов спорта: {avg_sport} ч/день\n"
        )
        await message.answer(text_stats)
    except Exception as e:
        logging.error(f"Ошибка при получении статистики: {e}")
        await message.answer("Произошла ошибка при получении статистики.")
    finally:
        session.close()

# -------------------------------------------------------------------
# Автоматическая рассылка утром для всех зарегистрированных
# -------------------------------------------------------------------
async def morning_job():
    """
    Каждый день обходим всех пользователей и автоматически запускаем им FSM-опрос (на сегодня).
    """
    session = get_session()
    try:
        users = session.query(User).all()
        for user in users:
            # Программно запускаем сбор данных (сегодня)
            state = dp.current_state(chat=user.telegram_id, user=user.telegram_id)
            await state.set_state(GatherDataState.bedtime_before_midnight.state)
            await bot.send_message(
                user.telegram_id,
                "Доброе утро! Самое время внести данные за сегодня.\n"
                "Легли ли вы вчера до 00:00? (да/нет)",
                reply_markup=yes_no_kb
            )
    finally:
        session.close()

# -------------------------------------------------------------------
# on_startup: инициализация БД + запуск APScheduler
# -------------------------------------------------------------------
async def on_startup(dp):
    init_db()
    logging.info("База данных инициализирована.")

    scheduler = AsyncIOScheduler(timezone="Europe/Moscow")  # поменяйте при желании
    # Пример: запускать каждый день в 08:00
    scheduler.add_job(morning_job, 'cron', hour=8, minute=0)
    scheduler.start()
    logging.info("Scheduler (APS) запущен.")

# -------------------------------------------------------------------
# Точка входа
# -------------------------------------------------------------------
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)