from flask import Flask, request, jsonify
import psycopg2
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


@app.route('/check_role', methods=['GET'])
def check_role():
    user_id = request.args.get('user_id')

    if not user_id:
        return jsonify({"error": "Не указан user_id"}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Проверяем существование пользователя и его роль
            cursor.execute(
                "SELECT role FROM user_roles WHERE user_id = %s",
                (user_id,)
            )
            result = cursor.fetchone()

            if not result:
                # Если пользователь не найден, считаем его обычным пользователем
                return jsonify({"role": "user"}), 200

            return jsonify({"role": result[0]}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


@app.route('/set_role', methods=['POST'])
def set_role():
    data = request.json
    user_id = data.get('user_id')
    role = data.get('role')

    if not user_id or not role or role not in ['admin', 'user']:
        return jsonify({"error": "Неверные параметры"}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # Проверяем существование пользователя
            cursor.execute(
                "SELECT 1 FROM user_roles WHERE user_id = %s",
                (user_id,)
            )

            if cursor.fetchone():
                # Обновляем роль, если пользователь существует
                cursor.execute(
                    "UPDATE user_roles SET role = %s WHERE user_id = %s",
                    (role, user_id)
                )
            else:
                # Добавляем нового пользователя с ролью
                cursor.execute(
                    "INSERT INTO user_roles (user_id, role) VALUES (%s, %s)",
                    (user_id, role)
                )

            conn.commit()
            return jsonify({"message": f"Роль пользователя {user_id} установлена как {role}"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5003)