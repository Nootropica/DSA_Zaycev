from flask import Flask, request, jsonify
import psycopg2
from psycopg2 import sql
import os

app = Flask(__name__)

# Настройки подключения к PostgreSQL
DB_CONFIG = {
    "host": os.getenv('DB_HOST'),
    "database": os.getenv('DB_NAME'),
    "user": os.getenv('DB_USER'),
    "password": os.getenv('DB_PASSWORD'),
    "port": os.getenv('DB_PORT', '5432')
}


def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)


@app.route('/convert', methods=['GET'])
def convert_currency():
    currency_name = request.args.get('currency')
    amount = request.args.get('amount')

    if not currency_name or not amount:
        return jsonify({"error": "Не указаны валюта или сумма"}), 400

    try:
        amount = float(amount)
    except ValueError:
        return jsonify({"error": "Сумма должна быть числом"}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT rate FROM currencies WHERE currency_name = %s",
                (currency_name,)
            )
            result = cursor.fetchone()

            if not result:
                return jsonify({"error": "Валюта не найдена"}), 404

            # Преобразуем Decimal к float
            rate = float(result[0])
            converted_amount = amount * rate

            return jsonify({
                "original_amount": amount,
                "currency": currency_name,
                "rate": rate,
                "converted_amount": round(converted_amount, 2),
                "target_currency": "RUB"
            }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


@app.route('/currencies', methods=['GET'])
def get_all_currencies():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT currency_name, rate FROM currencies ORDER BY currency_name"
            )
            currencies = cursor.fetchall()

            result = [
                {"currency": curr[0], "rate": curr[1], "to_currency": "RUB"}
                for curr in currencies
            ]

            return jsonify({"currencies": result}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002)