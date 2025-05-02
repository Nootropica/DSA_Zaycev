import os
from aiogram import Bot, Dispatcher
from aiogram.filters.command import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

# Получаем токен бота из переменных окружения
bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
bot = Bot(token=bot_token)
dp = Dispatcher()

# Словарь для хранения курсов валют
currency_rates = {}


# Определяем состояния для FSM (сохранение валюты)
class CurrencyStates(StatesGroup):
    waiting_for_currency_name = State()
    waiting_for_currency_rate = State()


# Определяем состояния для FSM (конвертация валюты)
class ConvertStates(StatesGroup):
    waiting_for_currency_to_convert = State()
    waiting_for_amount_to_convert = State()


# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        f"👋 Привет, {message.from_user.first_name}! Я бот для работы с валютами.\n\n"
        "Доступные команды:\n"
        "/start - показать это сообщение\n"
        "/save_currency - сохранить курс валюты\n"
        "/convert - конвертировать валюту в рубли\n\n"
        "Просто введите нужную команду!"
    )


# Обработчик команды /save_currency
@dp.message(Command("save_currency"))
async def cmd_save_currency(message: Message, state: FSMContext):
    await message.answer("Введите название валюты (например, USD, EUR):")
    await state.set_state(CurrencyStates.waiting_for_currency_name)


# Обработчик ввода названия валюты
@dp.message(CurrencyStates.waiting_for_currency_name)
async def process_currency_name(message: Message, state: FSMContext):
    await state.update_data(currency_name=message.text.upper())
    await message.answer(f"Введите курс валюты {message.text.upper()} к рублю:")
    await state.set_state(CurrencyStates.waiting_for_currency_rate)


# Обработчик ввода курса валюты
@dp.message(CurrencyStates.waiting_for_currency_rate)
async def process_currency_rate(message: Message, state: FSMContext):
    try:
        rate = float(message.text.replace(',', '.'))
        data = await state.get_data()
        currency_name = data['currency_name']
        currency_rates[currency_name] = rate
        await message.answer(
            f"Курс {currency_name} сохранен: 1 {currency_name} = {rate} RUB"
        )
        await state.clear()
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для курса валюты.")


# Обработчик команды /convert
@dp.message(Command("convert"))
async def cmd_convert(message: Message, state: FSMContext):
    if not currency_rates:
        await message.answer("Нет сохранённых курсов валют. Сначала добавьте курс через /save_currency.")
        return

    await message.answer(
        "Введите название валюты для конвертации (доступные: "
        + ", ".join(currency_rates.keys())
        + "):"
    )
    await state.set_state(ConvertStates.waiting_for_currency_to_convert)


# Обработчик ввода названия валюты для конвертации
@dp.message(ConvertStates.waiting_for_currency_to_convert)
async def process_currency_to_convert(message: Message, state: FSMContext):
    currency = message.text.upper()

    if currency not in currency_rates:
        await message.answer(
            f"Валюта {currency} не найдена. Доступные: "
            + ", ".join(currency_rates.keys())
            + "\nПопробуйте ещё раз:"
        )
        return

    await state.update_data(currency_to_convert=currency)
    await message.answer(f"Введите сумму в {currency} для конвертации в рубли:")
    await state.set_state(ConvertStates.waiting_for_amount_to_convert)


# Обработчик ввода суммы для конвертации
@dp.message(ConvertStates.waiting_for_amount_to_convert)
async def process_amount_to_convert(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(',', '.'))
        data = await state.get_data()
        currency = data['currency_to_convert']
        rate = currency_rates[currency]
        converted_amount = amount * rate

        await message.answer(
            f"{amount} {currency} = {converted_amount:.2f} RUB\n"
            f"Курс: 1 {currency} = {rate} RUB"
        )
        await state.clear()

    except ValueError:
        await message.answer("Пожалуйста, введите корректное число для суммы.")


# Запуск бота
async def main():
    await dp.start_polling(bot)


if __name__ == '__main__':
    import asyncio

    asyncio.run(main())