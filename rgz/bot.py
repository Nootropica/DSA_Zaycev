import asyncio
import logging
import os
from datetime import datetime
from typing import Optional
import aiohttp
import psycopg2
import psycopg2.extras
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Настройки БД из переменных окружения
db_host = os.getenv('DB_HOST', 'localhost')
db_name = os.getenv('DB_NAME', 'finance_bot')
db_user = os.getenv('DB_USER', 'postgres')
db_password = os.getenv('DB_PASSWORD')

DB_CONFIG = {
    'host': db_host,
    'port': 5432,
    'user': db_user,
    'password': db_password,
    'database': db_name
}

# URL внешнего сервиса для курсов валют
CURRENCY_SERVICE_URL = f"http://{os.getenv('CURRENCY_SERVICE_HOST', '127.0.0.1')}:{os.getenv('CURRENCY_SERVICE_PORT', '5000')}/rate"

# Создание бота и диспетчера
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Состояния для FSM
class RegistrationStates(StatesGroup):
    waiting_for_username = State()


class OperationStates(StatesGroup):
    waiting_for_amount = State()
    waiting_for_date = State()


# Подключение к БД
def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


# Инициализация БД
def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Создание таблиц
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            chat_id BIGINT UNIQUE NOT NULL,
            date DATE NOT NULL DEFAULT CURRENT_DATE
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS operations (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            sum DECIMAL(10, 2) NOT NULL,
            chat_id BIGINT NOT NULL,
            type_operation VARCHAR(10) NOT NULL CHECK (type_operation IN ('ДОХОД', 'РАСХОД')),
            FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
        )
    ''')

    conn.commit()
    cursor.close()
    conn.close()


# Проверка регистрации пользователя
def is_user_registered(chat_id: int) -> bool:
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT EXISTS(SELECT 1 FROM users WHERE chat_id = %s)",
        (chat_id,)
    )
    result = cursor.fetchone()[0]

    cursor.close()
    conn.close()
    return result


# Получение курса валюты
async def get_currency_rate(currency: str) -> Optional[float]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{CURRENCY_SERVICE_URL}?currency={currency}") as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('rate')
                return None
    except Exception as e:
        logging.error(f"Ошибка получения курса валюты: {e}")
        return None


# Конвертация суммы в другую валюту
def convert_amount(amount: float, rate: float) -> float:
    return round(amount / rate, 2)


# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Добро пожаловать в бот учета финансов!\n\n"
        "Доступные команды:\n"
        "/reg - Регистрация\n"
        "/add_operation - Добавить операцию\n"
        "/operations - Просмотр операций\n"
        "/lk - Личный кабинет"
    )


# Обработчик команды /reg (2.1.2 Регистрация)
@dp.message(Command("reg"))
async def cmd_register(message: Message, state: FSMContext):
    chat_id = message.chat.id

    # Проверяем, что пользователь не зарегистрирован
    if is_user_registered(chat_id):
        await message.answer("Вы уже зарегистрированы!")
        return

    # Предлагаем ввести логин
    await message.answer("Введите ваш логин:")
    await state.set_state(RegistrationStates.waiting_for_username)


@dp.message(RegistrationStates.waiting_for_username)
async def process_registration(message: Message, state: FSMContext):
    username = message.text.strip()
    chat_id = message.chat.id
    registration_date = datetime.now().date()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Сохраняем логин, chat_id и дату регистрации в БД
        cursor.execute(
            "INSERT INTO users (name, chat_id, date) VALUES (%s, %s, %s)",
            (username, chat_id, registration_date)
        )
        conn.commit()

        cursor.close()
        conn.close()

        await message.answer("Вы успешно зарегистрированы!")
        await state.clear()

    except Exception as e:
        logging.error(f"Ошибка регистрации: {e}")
        await message.answer("Произошла ошибка при регистрации. Попробуйте еще раз.")
        await state.clear()


# Обработчик команды /add_operation (2.1.3 Добавление новой операции)
@dp.message(Command("add_operation"))
async def cmd_add_operation(message: Message, state: FSMContext):
    chat_id = message.chat.id

    # Проверяем регистрацию
    if not is_user_registered(chat_id):
        await message.answer("Сначала необходимо зарегистрироваться. Используйте команду /reg")
        return

    # Создаем кнопки для выбора типа операции
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="РАСХОД", callback_data="operation_expense"),
            InlineKeyboardButton(text="ДОХОД", callback_data="operation_income")
        ]
    ])

    await message.answer("Выберите тип операции:", reply_markup=keyboard)

# Обработчик выбора типа операции
@dp.callback_query(F.data.in_(["operation_expense", "operation_income"]))
async def process_operation_type(callback: CallbackQuery, state: FSMContext):
    operation_type = "РАСХОД" if callback.data == "operation_expense" else "ДОХОД"

    # Сохраняем тип операции в состоянии
    await state.update_data(operation_type=operation_type)

    await callback.message.edit_text("Введите сумму операции в рублях:")
    await state.set_state(OperationStates.waiting_for_amount)
    await callback.answer()

# обработчик ввода суммы
@dp.message(OperationStates.waiting_for_amount) # Ловит сообщения только в состоянии waiting_for_amount
async def process_operation_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        if amount <= 0:
            await message.answer("Сумма должна быть положительной. Введите сумму заново:")
            return

        # Сохраняем сумму в состоянии
        await state.update_data(amount=amount)

        await message.answer("Введите дату операции в формате ДД.ММ.ГГГГ (например, 15.11.2024):")
        await state.set_state(OperationStates.waiting_for_date)

    except ValueError:
        await message.answer("Неверный формат суммы. Введите числовое значение:")


@dp.message(OperationStates.waiting_for_date) # Обработчик ввода даты
async def process_operation_date(message: Message, state: FSMContext):
    try:
        # Парсим дату
        date_str = message.text.strip()
        operation_date = datetime.strptime(date_str, "%d.%m.%Y").date()

        # Получаем данные из состояния
        data = await state.get_data()
        operation_type = data['operation_type']
        amount = data['amount']
        chat_id = message.chat.id

        # Сохраняем операцию в БД
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO operations (date, sum, chat_id, type_operation) VALUES (%s, %s, %s, %s)",
            (operation_date, amount, chat_id, operation_type)
        )
        conn.commit()

        cursor.close()
        conn.close()

        await message.answer("Операция успешно добавлена!")
        await state.clear()

    except ValueError:
        await message.answer("Неверный формат даты. Используйте формат ДД.ММ.ГГГГ:")
    except Exception as e:
        logging.error(f"Ошибка добавления операции: {e}")
        await message.answer("Произошла ошибка при добавлении операции.")
        await state.clear()


# Обработчик команды /operations (2.1.4 Просмотр операций пользователя)
@dp.message(Command("operations"))
async def cmd_operations(message: Message, state: FSMContext):
    chat_id = message.chat.id

    # Проверяем регистрацию
    if not is_user_registered(chat_id):
        await message.answer("Сначала необходимо зарегистрироваться. Используйте команду /reg")
        return

    # Создаем кнопки для выбора валюты
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="RUB", callback_data="currency_RUB"),
            InlineKeyboardButton(text="EUR", callback_data="currency_EUR"),
            InlineKeyboardButton(text="USD", callback_data="currency_USD")
        ]
    ])

    await message.answer("Выберите валюту для отображения операций:", reply_markup=keyboard)


@dp.callback_query(F.data.in_(["currency_RUB", "currency_EUR", "currency_USD"]))
async def process_currency_selection(callback: CallbackQuery):
    currency = callback.data.split("_")[1] # разделяет callback_data и берет второй элемент
    chat_id = callback.message.chat.id

    try:
        # Получаем курс валюты, если не RUB
        rate = 1.0 # для RUB
        if currency in ["EUR", "USD"]:
            rate = await get_currency_rate(currency)
            if rate is None:
                await callback.message.edit_text("Ошибка получения курса валюты. Попробуйте позже.")
                await callback.answer()
                return

        # Получаем операции пользователя
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cursor.execute(
            "SELECT id, date, sum, type_operation FROM operations WHERE chat_id = %s ORDER BY date DESC",
            (chat_id,)
        )
        operations = cursor.fetchall()

        cursor.close()
        conn.close()

        if not operations:
            await callback.message.edit_text("У вас пока нет операций.")
            await callback.answer()
            return

        # Формируем сообщение с операциями
        response = f"Ваши операции (в {currency}):\n\n"

        for operation in operations:
            converted_amount = convert_amount(float(operation['sum']), rate) if currency != "RUB" else float(
                operation['sum'])
            response += f"📅 {operation['date'].strftime('%d.%m.%Y')}\n"
            response += f"💰 {converted_amount:.2f} {currency}\n"
            response += f"📊 {operation['type_operation']}\n"
            response += f"🆔 ID: {operation['id']}\n\n"

        # Ограничиваем длину сообщения
        if len(response) > 4000:
            response = response[:4000] + "\n... (показаны последние операции)"

        await callback.message.edit_text(response)
        await callback.answer()

    except Exception as e:
        logging.error(f"Ошибка получения операций: {e}")
        await callback.message.edit_text("Произошла ошибка при получении операций.")
        await callback.answer()


# Обработчик команды /lk (Личный кабинет - Вариант 11)
@dp.message(Command("lk"))
async def cmd_personal_cabinet(message: Message):
    chat_id = message.chat.id

    # Проверяем регистрацию
    if not is_user_registered(chat_id):
        await message.answer("Сначала необходимо зарегистрироваться. Используйте команду /reg")
        return

    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Получаем информацию о пользователе
        cursor.execute(
            "SELECT name, date FROM users WHERE chat_id = %s",
            (chat_id,)
        )
        user_info = cursor.fetchone()

        # Получаем количество операций пользователя
        cursor.execute(
            "SELECT COUNT(*) FROM operations WHERE chat_id = %s",
            (chat_id,)
        )
        operations_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        if user_info:
            username = user_info['name']
            registration_date = user_info['date'].strftime('%d.%m.%Y')

            # Формируем сообщение с информацией личного кабинета
            response = (
                f"👤 **Личный кабинет**\n\n"
                f"📛 **Логин:** {username}\n"
                f"📅 **Дата регистрации:** {registration_date}\n"
                f"📊 **Количество операций:** {operations_count}\n"
            )

            await message.answer(response, parse_mode="Markdown")
        else:
            await message.answer("Ошибка получения информации о пользователе.")

    except Exception as e:
        logging.error(f"Ошибка получения информации личного кабинета: {e}")
        await message.answer("Произошла ошибка при получении информации.")


# Главная функция
async def main():
    # Проверка наличия обязательных переменных окружения
    if not BOT_TOKEN:
        raise ValueError("Не установлена переменная окружения TELEGRAM_BOT_TOKEN")

    if not db_password:
        raise ValueError("Не установлена переменная окружения DB_PASSWORD")

    # Инициализация БД
    try:
        init_db()
        logging.info("База данных успешно инициализирована")
    except Exception as e:
        logging.error(f"Ошибка инициализации БД: {e}")
        return

    # Запуск бота
    logging.info("Запуск бота...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())