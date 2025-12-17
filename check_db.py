import sqlite3

def check_users_table():
    try:
        conn = sqlite3.connect('crm.db')
        cursor = conn.cursor()

        # Получаем список таблиц
        cursor.execute('SELECT name FROM sqlite_master WHERE type="table";')
        tables = cursor.fetchall()
        print('Таблицы в базе данных:')
        for table in tables:
            print(f'  - {table[0]}')

        # Проверяем структуру таблицы users
        cursor.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="users";')
        table_info = cursor.fetchone()
        if table_info:
            print(f'\nСтруктура таблицы users:\n{table_info[0]}')
            
            # Проверим, есть ли колонка pending_activation
            cursor.execute('PRAGMA table_info(users);')
            columns = cursor.fetchall()
            print('\nКолонки в таблице users:')
            for col in columns:
                print(f'  - {col[1]}: {col[2]} (NOT NULL: {col[3]}, DEFAULT: {col[4]})')
                
            # Проверим, есть ли колонка pending_activation
            column_names = [col[1] for col in columns]
            if 'pending_activation' in column_names:
                print('\n✓ Колонка pending_activation успешно добавлена в таблицу users')
            else:
                print('\n✗ Колонка pending_activation НЕ НАЙДЕНА в таблице users')
        else:
            print('\nТаблица users не найдена')

        conn.close()
    except Exception as e:
        print(f'Ошибка при работе с базой данных: {e}')

if __name__ == "__main__":
    check_users_table()