from flask import Flask, request, jsonify
import psycopg2
from psycopg2 import sql
import os

app = Flask(__name__)

# Настройки подключения к PostgreSQL из переменных окружения
DB_CONFIG = {
    "host": os.getenv('DB_HOST'),
    "database": os.getenv('DB_NAME'),
    "user": os.getenv('DB_USER'),
    "password": os.getenv('DB_PASSWORD')
}

def get_db_connection():
    return psycopg2.connect(**DB_CONFIG)

@app.route('/load', methods=['POST'])
def load_currency():
    data = request.json
    currency_name = data.get('currency_name')
    rate = data.get('rate')

    if not currency_name or not rate:
        return jsonify({"error": "Не указаны название валюты или курс"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Проверка существования валюты
        cursor.execute("SELECT * FROM currencies WHERE currency_name = %s", (currency_name,))
        if cursor.fetchone():
            return jsonify({"error": "Валюта уже существует"}), 400

        # Добавление валюты
        cursor.execute(
            "INSERT INTO currencies (currency_name, rate) VALUES (%s, %s)",
            (currency_name, rate)
        )
        conn.commit()
        return jsonify({"message": f"Валюта {currency_name} успешно добавлена"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/update_currency', methods=['POST'])
def update_currency():
    data = request.json
    currency_name = data.get('currency_name')
    new_rate = data.get('rate')

    if not currency_name or not new_rate:
        return jsonify({"error": "Не указаны название валюты или новый курс"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Проверка существования валюты
        cursor.execute("SELECT * FROM currencies WHERE currency_name = %s", (currency_name,))
        if not cursor.fetchone():
            return jsonify({"error": "Валюта не найдена"}), 404

        # Обновление курса
        cursor.execute(
            "UPDATE currencies SET rate = %s WHERE currency_name = %s",
            (new_rate, currency_name)
        )
        conn.commit()
        return jsonify({"message": f"Курс валюты {currency_name} обновлен"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

@app.route('/delete', methods=['POST'])
def delete_currency():
    data = request.json
    currency_name = data.get('currency_name')

    if not currency_name:
        return jsonify({"error": "Не указано название валюты"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Проверка существования валюты
        cursor.execute("SELECT * FROM currencies WHERE currency_name = %s", (currency_name,))
        if not cursor.fetchone():
            return jsonify({"error": "Валюта не найдена"}), 404

        # Удаление валюты
        cursor.execute("DELETE FROM currencies WHERE currency_name = %s", (currency_name,))
        conn.commit()
        return jsonify({"message": f"Валюта {currency_name} удалена"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)