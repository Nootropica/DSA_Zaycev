import os
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# Конфигурация
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CURRENCY_SERVICE_URL = os.getenv('CURRENCY_SERVICE_URL', "http://localhost:5001")
DATA_SERVICE_URL = os.getenv('DATA_SERVICE_URL', "http://localhost:5002")
ROLE_SERVICE_URL = os.getenv('ROLE_SERVICE_URL', "http://localhost:5003")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Состояния FSM
class CurrencyStates(StatesGroup):
    waiting_for_currency_name = State()
    waiting_for_currency_rate = State()
    waiting_for_currency_to_delete = State()
    waiting_for_currency_to_update = State()
    waiting_for_new_rate = State()

class ConvertStates(StatesGroup):
    waiting_for_currency_to_convert = State()
    waiting_for_amount_to_convert = State()

async def check_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором"""
    try:
        response = requests.get(
            f"{ROLE_SERVICE_URL}/check_role",
            params={"user_id": user_id},
            timeout=3
        )
        return response.status_code == 200 and response.json().get('role') == 'admin'
    except requests.exceptions.RequestException:
        return False

# Обработчик /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    menu_commands = [
        ("/start", "Главное меню"),
        ("/get_currencies", "Список валют"),
        ("/convert", "Конвертация"),
    ]

    # Добавляем команду manage_currency только для администраторов
    if await check_admin(message.from_user.id):
        menu_commands.append(("/manage_currency", "Управление валютами"))

    builder = ReplyKeyboardBuilder()
    for cmd, desc in menu_commands:
        builder.add(KeyboardButton(text=cmd))

    await message.answer(
        f"👋 Привет, {message.from_user.first_name}! Я бот для работы с валютами.",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# Обработчик /manage_currency
@dp.message(Command("manage_currency"))
async def cmd_manage_currency(message: types.Message):
    if not await check_admin(message.from_user.id):
        await message.answer("❌ Эта команда доступна только администраторам")
        return

    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="Добавить валюту"),
        KeyboardButton(text="Удалить валюту"),
        KeyboardButton(text="Изменить курс")
    )
    builder.row(KeyboardButton(text="Отмена"))

    await message.answer(
        "Выберите действие:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )

# Обработчик /set_role (только для администраторов)
@dp.message(Command("set_role"))
async def cmd_set_role(message: types.Message, state: FSMContext):
    if not await check_admin(message.from_user.id):
        await message.answer("❌ Эта команда доступна только администраторам")
        return

    args = message.text.split()
    if len(args) != 3 or args[2].lower() not in ['admin', 'user']:
        await message.answer("Использование: /set_role <user_id> <admin|user>")
        return

    user_id = args[1]
    role = args[2].lower()

    try:
        response = requests.post(
            f"{ROLE_SERVICE_URL}/set_role",
            json={"user_id": user_id, "role": role},
            timeout=3
        )

        if response.status_code == 200:
            await message.answer(f"✅ Роль пользователя {user_id} установлена как {role}")
        else:
            error = response.json().get('error', 'Неизвестная ошибка')
            await message.answer(f"❌ Ошибка: {error}")
    except requests.exceptions.RequestException:
        await message.answer("❌ Сервис ролей недоступен")

# Добавление валюты
@dp.message(lambda message: message.text == "Добавить валюту")
async def add_currency_start(message: types.Message, state: FSMContext):
    if not await check_admin(message.from_user.id):
        await message.answer("❌ Эта команда доступна только администраторам")
        return

    await message.answer("Введите название валюты (например, USD, EUR):",
                         reply_markup=types.ReplyKeyboardRemove())
    await state.set_state(CurrencyStates.waiting_for_currency_name)

@dp.message(CurrencyStates.waiting_for_currency_name)
async def process_currency_name(message: types.Message, state: FSMContext):
    currency = message.text.upper()

    response = requests.get(f"{DATA_SERVICE_URL}/currencies")
    if response.status_code == 200:
        currencies = [c['currency'] for c in response.json().get('currencies', [])]
        if currency in currencies:
            await message.answer(f"❌ Валюта {currency} уже существует")
            await state.clear()
            return

    await state.update_data(currency_name=currency)
    await message.answer(f"Введите курс {currency} к рублю:")
    await state.set_state(CurrencyStates.waiting_for_currency_rate)

@dp.message(CurrencyStates.waiting_for_currency_rate)
async def process_currency_rate(message: types.Message, state: FSMContext):
    try:
        rate = float(message.text.replace(',', '.'))
        data = await state.get_data()

        response = requests.post(
            f"{CURRENCY_SERVICE_URL}/load",
            json={"currency_name": data['currency_name'], "rate": rate},
            timeout=3
        )

        if response.status_code == 200:
            await message.answer(f"✅ Валюта {data['currency_name']} успешно добавлена")
        else:
            error = response.json().get('error', 'Неизвестная ошибка')
            await message.answer(f"❌ Ошибка: {error}")

    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите корректное число")
        return
    except requests.exceptions.RequestException:
        await message.answer("❌ Сервис валют недоступен")
        return

    await state.clear()

# Удаление валюты
@dp.message(lambda message: message.text == "Удалить валюту")
async def delete_currency_start(message: types.Message, state: FSMContext):
    if not await check_admin(message.from_user.id):
        await message.answer("❌ Эта команда доступна только администраторам")
        return

    response = requests.get(f"{DATA_SERVICE_URL}/currencies")
    if response.status_code != 200:
        await message.answer("❌ Не удалось получить список валют")
        return

    currencies = [c['currency'] for c in response.json().get('currencies', [])]
    if not currencies:
        await message.answer("ℹ️ Нет доступных валют для удаления")
        return

    await message.answer(
        f"Введите название валюты для удаления ({', '.join(currencies)}):",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(CurrencyStates.waiting_for_currency_to_delete)

@dp.message(CurrencyStates.waiting_for_currency_to_delete)
async def process_delete_currency(message: types.Message, state: FSMContext):
    currency = message.text.upper()

    try:
        response = requests.post(
            f"{CURRENCY_SERVICE_URL}/delete",
            json={"currency_name": currency},
            timeout=3
        )

        if response.status_code == 200:
            await message.answer(f"✅ Валюта {currency} успешно удалена")
        elif response.status_code == 404:
            await message.answer(f"❌ Валюта {currency} не найдена")
        else:
            await message.answer("❌ Произошла ошибка при удалении")
    except requests.exceptions.RequestException:
        await message.answer("❌ Сервис валют недоступен")

    await state.clear()

# Изменение курса
@dp.message(lambda message: message.text == "Изменить курс")
async def update_currency_start(message: types.Message, state: FSMContext):
    if not await check_admin(message.from_user.id):
        await message.answer("❌ Эта команда доступна только администраторам")
        return

    response = requests.get(f"{DATA_SERVICE_URL}/currencies")
    if response.status_code != 200:
        await message.answer("❌ Не удалось получить список валют")
        return

    currencies = [c['currency'] for c in response.json().get('currencies', [])]
    if not currencies:
        await message.answer("ℹ️ Нет доступных валют для изменения")
        return

    await message.answer(
        f"Введите название валюты для изменения ({', '.join(currencies)}):",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await state.set_state(CurrencyStates.waiting_for_currency_to_update)

@dp.message(CurrencyStates.waiting_for_currency_to_update)
async def process_currency_to_update(message: types.Message, state: FSMContext):
    currency = message.text.upper()
    await state.update_data(currency_name=currency)
    await message.answer(f"Введите новый курс для {currency}:")
    await state.set_state(CurrencyStates.waiting_for_new_rate)

@dp.message(CurrencyStates.waiting_for_new_rate)
async def process_new_rate(message: types.Message, state: FSMContext):
    try:
        new_rate = float(message.text.replace(',', '.'))
        data = await state.get_data()

        response = requests.post(
            f"{CURRENCY_SERVICE_URL}/update_currency",
            json={"currency_name": data['currency_name'], "rate": new_rate},
            timeout=3
        )

        if response.status_code == 200:
            await message.answer(f"✅ Курс {data['currency_name']} обновлен: 1 {data['currency_name']} = {new_rate} RUB")
        else:
            error = response.json().get('error', 'Неизвестная ошибка')
            await message.answer(f"❌ Ошибка: {error}")

    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите корректное число")
        return
    except requests.exceptions.RequestException:
        await message.answer("❌ Сервис валют недоступен")
        return

    await state.clear()

# Получение списка валют
@dp.message(Command("get_currencies"))
async def cmd_get_currencies(message: types.Message):
    try:
        response = requests.get(f"{DATA_SERVICE_URL}/currencies", timeout=3)

        if response.status_code == 200:
            currencies = response.json().get('currencies', [])
            if currencies:
                text = "📊 Текущие курсы валют:\n" + "\n".join(
                    [f"{c['currency']}: {c['rate']} RUB" for c in currencies]
                )
            else:
                text = "ℹ️ Нет доступных валют"
        else:
            text = "❌ Не удалось получить курсы валют"

        await message.answer(text)
    except requests.exceptions.RequestException:
        await message.answer("❌ Сервис данных недоступен")

# Конвертация валюты
@dp.message(Command("convert"))
async def cmd_convert(message: types.Message, state: FSMContext):
    try:
        response = requests.get(f"{DATA_SERVICE_URL}/currencies", timeout=3)
        if response.status_code != 200:
            await message.answer("❌ Не удалось получить список валют")
            return

        currencies = [c['currency'] for c in response.json().get('currencies', [])]
        if not currencies:
            await message.answer("ℹ️ Нет доступных валют для конвертации")
            return

        await message.answer(
            f"Введите название валюты ({', '.join(currencies)}):",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(ConvertStates.waiting_for_currency_to_convert)
    except requests.exceptions.RequestException:
        await message.answer("❌ Сервис данных недоступен")

@dp.message(ConvertStates.waiting_for_currency_to_convert)
async def process_currency_to_convert(message: types.Message, state: FSMContext):
    currency = message.text.upper()
    await state.update_data(currency=currency)
    await message.answer("Введите сумму для конвертации:")
    await state.set_state(ConvertStates.waiting_for_amount_to_convert)

@dp.message(ConvertStates.waiting_for_amount_to_convert)
async def process_amount_to_convert(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        data = await state.get_data()

        response = requests.get(
            f"{DATA_SERVICE_URL}/convert",
            params={"currency": data['currency'], "amount": amount},
            timeout=3
        )

        if response.status_code == 200:
            result = response.json()
            await message.answer(
                f"🔢 Результат конвертации:\n"
                f"{amount} {data['currency']} = {result['converted_amount']:.2f} RUB\n"
                f"Курс: 1 {data['currency']} = {result['rate']} RUB"
            )
        else:
            error = response.json().get('error', 'Неизвестная ошибка')
            await message.answer(f"❌ Ошибка: {error}")

    except ValueError:
        await message.answer("⚠️ Пожалуйста, введите корректное число")
        return
    except requests.exceptions.RequestException:
        await message.answer("❌ Сервис данных недоступен")
        return

    await state.clear()

# Отмена действий
@dp.message(lambda message: message.text == "Отмена")
async def cancel_action(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Действие отменено", reply_markup=types.ReplyKeyboardRemove())

# Запуск бота
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())