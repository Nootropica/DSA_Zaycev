import os
import psycopg2
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Получаем токен бота и данные для подключения к БД из переменных окружения
bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
db_host = os.getenv('DB_HOST')
db_name = os.getenv('DB_NAME')
db_user = os.getenv('DB_USER')
db_password = os.getenv('DB_PASSWORD')

# Инициализация бота и диспетчера
bot = Bot(token=bot_token)
dp = Dispatcher()


# Определение состояний для FSM
class CurrencyStates(StatesGroup):
    waiting_for_currency_name = State()
    waiting_for_currency_rate = State()
    waiting_for_currency_to_delete = State()
    waiting_for_currency_to_update = State()
    waiting_for_new_rate = State()


class ConvertStates(StatesGroup):
    waiting_for_currency_to_convert = State()
    waiting_for_amount_to_convert = State()


# Функция для подключения к базе данных
def get_db_connection():
    try:
        conn = psycopg2.connect(
            host=db_host,
            database=db_name,
            user=db_user,
            password=db_password
        )
        return conn
    except Exception as e:
        print(f"Ошибка при подключении к PostgreSQL: {e}")
        return None


# Функция для создания таблиц (выполняется при старте бота)
def create_tables():
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS currencies (
                        id SERIAL PRIMARY KEY,
                        currency_name VARCHAR(10) UNIQUE NOT NULL,
                        rate NUMERIC(10, 2) NOT NULL
                    )
                ''')

                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS admins (
                        id SERIAL PRIMARY KEY,
                        chat_id VARCHAR(50) UNIQUE NOT NULL
                    )
                ''')
                conn.commit()
            print("Таблицы успешно созданы")
        except Exception as e:
            print(f"Ошибка при создании таблиц: {e}")
            conn.rollback()
        finally:
            conn.close()


# Проверка, является ли пользователь администратором
def is_admin(chat_id: str) -> bool:
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM admins WHERE chat_id = %s",
                    (chat_id,)
                )
                admin = cursor.fetchone()
                return admin is not None
        finally:
            conn.close()
    return False


# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}! Я бот для работы с валютами.\n\n"
        "Доступные команды:\n"
        "/start - показать это сообщение\n"
        "/get_currencies - показать все курсы валют\n"
        "/convert - конвертировать валюту в рубли\n"
    )

    # Добавляем команды для администраторов
    if is_admin(str(message.chat.id)):
        await message.answer(
            "Команды администратора:\n"
            "/start - меню\n"
            "/manage_currency - управление валютами\n"
            "/get_currencies - сохраненные валюты\n"
            "/convert - конвертация валют\n"
        )


# Обработчик команды /manage_currency (только для администраторов)
@dp.message(Command("manage_currency"))
async def cmd_manage_currency(message: types.Message):
    if not is_admin(str(message.chat.id)):
        await message.answer("Нет доступа к команде")
        return

    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="Добавить валюту"),
        KeyboardButton(text="Удалить валюту"),
        KeyboardButton(text="Изменить курс валюты")
    )
    builder.row(KeyboardButton(text="Отмена"))

    await message.answer(
        "Выберите действие:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )


# Обработчик кнопки "Добавить валюту"
@dp.message(lambda message: message.text == "Добавить валюту")
async def add_currency_start(message: types.Message, state: FSMContext):
    await message.answer(
        "Введите название валюты (например, USD, EUR):",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(CurrencyStates.waiting_for_currency_name)


# Обработчик ввода названия валюты для добавления
@dp.message(CurrencyStates.waiting_for_currency_name)
async def process_currency_name(message: types.Message, state: FSMContext):
    currency_name = message.text.upper()

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                # Проверяем, существует ли уже такая валюта
                cursor.execute(
                    "SELECT id FROM currencies WHERE currency_name = %s",
                    (currency_name,)
                )
                existing = cursor.fetchone()

                if existing:
                    await message.answer(f"Валюта {currency_name} уже существует")
                    await state.clear()
                    return

                await state.update_data(currency_name=currency_name)
                await message.answer(f"Введите курс валюты {currency_name} к рублю:")
                await state.set_state(CurrencyStates.waiting_for_currency_rate)
        finally:
            conn.close()
    else:
        await message.answer("Ошибка подключения к базе данных")
        await state.clear()


# Обработчик ввода курса валюты
@dp.message(CurrencyStates.waiting_for_currency_rate)
async def process_currency_rate(message: types.Message, state: FSMContext):
    try:
        rate = float(message.text.replace(',', '.'))
        data = await state.get_data()
        currency_name = data['currency_name']

        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "INSERT INTO currencies (currency_name, rate) VALUES (%s, %s)",
                        (currency_name, rate)
                    )
                    conn.commit()
                await message.answer(
                    f"Курс {currency_name} сохранен: 1 {currency_name} = {rate} RUB"
                )
            finally:
                conn.close()
        else:
            await message.answer("Ошибка подключения к базе данных")

        await state.clear()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для курса валюты")


# Обработчик кнопки "Удалить валюту"
@dp.message(lambda message: message.text == "Удалить валюту")
async def delete_currency_start(message: types.Message, state: FSMContext):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT currency_name FROM currencies")
                currencies = cursor.fetchall()
                if not currencies:
                    await message.answer("Нет сохранённых валют для удаления")
                    return

                await message.answer(
                    "Введите название валюты для удаления (доступные: " +
                    ", ".join([c[0] for c in currencies]) + "):",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                await state.set_state(CurrencyStates.waiting_for_currency_to_delete)
        finally:
            conn.close()
    else:
        await message.answer("Ошибка подключения к базе данных")


# Обработчик ввода названия валюты для удаления
@dp.message(CurrencyStates.waiting_for_currency_to_delete)
async def process_currency_to_delete(message: types.Message, state: FSMContext):
    currency_name = message.text.upper()

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM currencies WHERE currency_name = %s",
                    (currency_name,)
                )
                conn.commit()
                if cursor.rowcount == 0:
                    await message.answer(f"Валюта {currency_name} не найдена")
                else:
                    await message.answer(f"Валюта {currency_name} успешно удалена")
        finally:
            conn.close()
    else:
        await message.answer("Ошибка подключения к базе данных")

    await state.clear()


# Обработчик кнопки "Изменить курс валюты"
@dp.message(lambda message: message.text == "Изменить курс валюты")
async def update_currency_start(message: types.Message, state: FSMContext):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT currency_name FROM currencies")
                currencies = cursor.fetchall()
                if not currencies:
                    await message.answer("Нет сохранённых валют для изменения")
                    return

                await message.answer(
                    "Введите название валюты для изменения курса (доступные: " +
                    ", ".join([c[0] for c in currencies]) + "):",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                await state.set_state(CurrencyStates.waiting_for_currency_to_update)
        finally:
            conn.close()
    else:
        await message.answer("Ошибка подключения к базе данных")


# Обработчик ввода названия валюты для изменения
@dp.message(CurrencyStates.waiting_for_currency_to_update)
async def process_currency_to_update(message: types.Message, state: FSMContext):
    currency_name = message.text.upper()

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM currencies WHERE currency_name = %s",
                    (currency_name,)
                )
                existing = cursor.fetchone()

                if not existing:
                    await message.answer(f"Валюта {currency_name} не найдена")
                    await state.clear()
                    return

                await state.update_data(currency_name=currency_name)
                await message.answer(f"Введите новый курс для валюты {currency_name}:")
                await state.set_state(CurrencyStates.waiting_for_new_rate)
        finally:
            conn.close()
    else:
        await message.answer("Ошибка подключения к базе данных")
        await state.clear()


# Обработчик ввода нового курса валюты
@dp.message(CurrencyStates.waiting_for_new_rate)
async def process_new_rate(message: types.Message, state: FSMContext):
    try:
        new_rate = float(message.text.replace(',', '.'))
        data = await state.get_data()
        currency_name = data['currency_name']

        conn = get_db_connection()
        if conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(
                        "UPDATE currencies SET rate = %s WHERE currency_name = %s",
                        (new_rate, currency_name)
                    )
                    conn.commit()
                await message.answer(
                    f"Курс {currency_name} обновлен: 1 {currency_name} = {new_rate} RUB"
                )
            finally:
                conn.close()
        else:
            await message.answer("Ошибка подключения к базе данных")

        await state.clear()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для курса валюты")


# Обработчик команды /get_currencies
@dp.message(Command("get_currencies"))
async def cmd_get_currencies(message: types.Message):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT currency_name, rate FROM currencies ORDER BY currency_name")
                currencies = cursor.fetchall()
                if currencies:
                    response = "Текущие курсы валют:\n" + "\n".join(
                        [f"{c[0]}: {c[1]} RUB" for c in currencies]
                    )
                else:
                    response = "Нет сохранённых курсов валют"

                await message.answer(response)
        finally:
            conn.close()
    else:
        await message.answer("Ошибка подключения к базе данных")


# Обработчик команды /convert
@dp.message(Command("convert"))
async def cmd_convert(message: types.Message, state: FSMContext):
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT currency_name FROM currencies")
                currencies = cursor.fetchall()
                if not currencies:
                    await message.answer("Нет сохранённых курсов валют. Сначала добавьте курс через /manage_currency.")
                    return

                await message.answer(
                    "Введите название валюты для конвертации (доступные: " +
                    ", ".join([c[0] for c in currencies]) + "):"
                )
                await state.set_state(ConvertStates.waiting_for_currency_to_convert)
        finally:
            conn.close()
    else:
        await message.answer("Ошибка подключения к базе данных")


# Обработчик ввода названия валюты для конвертации
@dp.message(ConvertStates.waiting_for_currency_to_convert)
async def process_currency_to_convert(message: types.Message, state: FSMContext):
    currency = message.text.upper()

    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT rate::float FROM currencies WHERE currency_name = %s",
                    (currency,)
                )
                rate = cursor.fetchone()

                if not rate:
                    cursor.execute("SELECT currency_name FROM currencies")
                    currencies = cursor.fetchall()
                    await message.answer(
                        f"Валюта {currency} не найдена. Доступные: " +
                        ", ".join([c[0] for c in currencies]) +
                        "\nПопробуйте ещё раз:"
                    )
                    return

                await state.update_data(currency_to_convert=currency, rate=rate[0])
                await message.answer(f"Введите сумму в {currency} для конвертации в рубли:")
                await state.set_state(ConvertStates.waiting_for_amount_to_convert)
        finally:
            conn.close()
    else:
        await message.answer("Ошибка подключения к базе данных")


# Обработчик ввода суммы для конвертации
@dp.message(ConvertStates.waiting_for_amount_to_convert)
async def process_amount_to_convert(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        data = await state.get_data()
        currency = data['currency_to_convert']
        rate = data['rate']
        converted_amount = amount * rate

        await message.answer(
            f"{amount} {currency} = {converted_amount:.2f} RUB\n"
            f"Курс: 1 {currency} = {rate} RUB"
        )
        await state.clear()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для суммы.")


# Обработчик кнопки "Отмена"
@dp.message(lambda message: message.text == "Отмена")
async def cancel_action(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "Действие отменено",
        reply_markup=types.ReplyKeyboardRemove()
    )


# Запуск бота и создание таблиц
async def main():
    create_tables()  # Создаем таблицы при старте
    await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())