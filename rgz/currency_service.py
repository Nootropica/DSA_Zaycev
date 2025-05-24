import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# Статические курсы валют
CURRENCY_RATES = {
    'USD': 79.60,
    'EUR': 89.71
}


@app.route('/rate', methods=['GET'])
def get_currency_rate():
    """
    Получение курса валюты

    Параметры:
    - currency: валюта (USD или EUR)

    Возвращает:
    - 200: {"rate": курс}
    - 400: {"message": "UNKNOWN CURRENCY"}
    - 500: {"message": "UNEXPECTED ERROR"}
    """

    try:
        # Получаем параметр currency из query string
        currency = request.args.get('currency')

        # Проверяем, что параметр передан
        if not currency:
            return jsonify({"message": "UNKNOWN CURRENCY"}), 400

        # Приводим к верхнему регистру
        currency = currency.upper()

        # Проверяем, что валюта поддерживается
        if currency not in CURRENCY_RATES:
            return jsonify({"message": "UNKNOWN CURRENCY"}), 400

        # Возвращаем курс валюты
        rate = CURRENCY_RATES[currency]
        return jsonify({"rate": rate}), 200

    except Exception as e:
        # Логируем ошибку (в продакшене нужно использовать proper logging)
        print(f"Ошибка в сервисе курсов валют: {e}")
        return jsonify({"message": "UNEXPECTED ERROR"}), 500


@app.route('/health', methods=['GET'])
def health_check():
    """Проверка работоспособности сервиса"""
    return jsonify({"status": "OK", "service": "Currency Rate Service"}), 200


@app.route('/', methods=['GET'])
def index():
    """Главная страница с документацией"""
    return jsonify({
        "service": "Currency Rate Service",
        "version": "1.0.0",
        "endpoints": {
            "/rate": {
                "method": "GET",
                "parameters": {
                    "currency": "USD или EUR"
                },
                "example": "/rate?currency=USD",
                "responses": {
                    "200": {"rate": "число"},
                    "400": {"message": "UNKNOWN CURRENCY"},
                    "500": {"message": "UNEXPECTED ERROR"}
                }
            },
            "/health": {
                "method": "GET",
                "description": "Проверка работоспособности сервиса"
            }
        },
        "supported_currencies": list(CURRENCY_RATES.keys()),
        "current_rates": CURRENCY_RATES
    }), 200


@app.errorhandler(404)
def not_found(error):
    """Обработчик 404 ошибки"""
    return jsonify({"message": "Endpoint not found"}), 404


@app.errorhandler(405)
def method_not_allowed(error):
    """Обработчик 405 ошибки"""
    return jsonify({"message": "Method not allowed"}), 405


if __name__ == '__main__':
    # Получаем порт из переменных окружения или используем 5000 по умолчанию
    port = int(os.getenv('CURRENCY_SERVICE_PORT', 5000))
    host = os.getenv('CURRENCY_SERVICE_HOST', '127.0.0.1')
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'

    print(f"🚀 Запуск сервиса курсов валют на {host}:{port}")
    print(f"📊 Доступные валюты: {', '.join(CURRENCY_RATES.keys())}")
    print(f"🔗 Пример запроса: http://{host}:{port}/rate?currency=USD")

    app.run(host=host, port=port, debug=debug)