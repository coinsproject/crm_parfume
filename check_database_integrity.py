#!/usr/bin/env python3
"""
Скрипт для проверки целостности базы данных SQLite
"""
import sqlite3
import sys
import os
from pathlib import Path

def check_database_integrity(db_path: str):
    """Проверяет целостность базы данных SQLite"""
    if not os.path.exists(db_path):
        print(f"[FAIL] База данных не найдена: {db_path}")
        return False
    
    print(f"Проверка базы данных: {db_path}")
    print("-" * 60)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Быстрая проверка целостности
        print("Выполняется быстрая проверка целостности...")
        cursor.execute("PRAGMA quick_check")
        result = cursor.fetchone()
        
        if result and result[0] == "ok":
            print("[OK] Быстрая проверка: OK")
        else:
            print(f"[FAIL] Быстрая проверка: {result[0] if result else 'FAILED'}")
            conn.close()
            return False
        
        # Полная проверка целостности
        print("Выполняется полная проверка целостности...")
        cursor.execute("PRAGMA integrity_check")
        result = cursor.fetchone()
        
        if result and result[0] == "ok":
            print("[OK] Полная проверка: OK")
        else:
            print(f"[FAIL] Полная проверка: {result[0] if result else 'FAILED'}")
            conn.close()
            return False
        
        # Проверка внешних ключей
        print("Проверка внешних ключей...")
        cursor.execute("PRAGMA foreign_key_check")
        fk_errors = cursor.fetchall()
        
        if fk_errors:
            print(f"[WARN] Найдено {len(fk_errors)} ошибок внешних ключей:")
            for error in fk_errors[:10]:  # Показываем первые 10
                print(f"   - {error}")
            if len(fk_errors) > 10:
                print(f"   ... и ещё {len(fk_errors) - 10} ошибок")
        else:
            print("[OK] Внешние ключи: OK")
        
        # Статистика базы данных
        print("\nСтатистика базы данных:")
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]
        print(f"   Таблиц: {table_count}")
        
        # Проверка размера файла
        db_size = os.path.getsize(db_path)
        print(f"   Размер файла: {db_size / 1024 / 1024:.2f} MB")
        
        conn.close()
        print("\n" + "=" * 60)
        print("[OK] База данных в порядке!")
        return True
        
    except sqlite3.DatabaseError as e:
        print(f"[FAIL] Ошибка базы данных: {e}")
        print("\nРекомендации:")
        print("1. Восстановите базу данных из резервной копии")
        print("2. Выполните: sqlite3 database.db '.recover' | sqlite3 recovered.db")
        print("3. Проверьте логи приложения для дополнительной информации")
        return False
    except Exception as e:
        print(f"[FAIL] Неожиданная ошибка: {e}")
        return False


def recover_database(db_path: str, backup_path: str = None):
    """Пытается восстановить базу данных"""
    if backup_path is None:
        backup_path = f"{db_path}.backup"
    
    print(f"\nПопытка восстановления базы данных...")
    print(f"Исходный файл: {db_path}")
    print(f"Резервная копия: {backup_path}")
    
    try:
        import shutil
        # Создаем резервную копию поврежденного файла
        damaged_backup = f"{db_path}.damaged"
        shutil.copy2(db_path, damaged_backup)
        print(f"Создана резервная копия поврежденного файла: {damaged_backup}")
        
        # Пытаемся восстановить
        recovered_path = f"{db_path}.recovered"
        os.system(f'sqlite3 "{damaged_backup}" ".recover" | sqlite3 "{recovered_path}"')
        
        if os.path.exists(recovered_path):
            print(f"[OK] Восстановленный файл создан: {recovered_path}")
            print("Проверьте восстановленный файл перед заменой оригинала!")
            return recovered_path
        else:
            print("[FAIL] Не удалось восстановить базу данных")
            return None
    except Exception as e:
        print(f"[FAIL] Ошибка при восстановлении: {e}")
        return None


if __name__ == "__main__":
    # Определяем путь к базе данных
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Пытаемся найти базу данных в текущей директории
        possible_paths = [
            "crm.db",
            "crm_new.db",
            "db/crm.db",
            "../crm.db",
        ]
        db_path = None
        for path in possible_paths:
            if os.path.exists(path):
                db_path = path
                break
        
        if not db_path:
            print("[FAIL] База данных не найдена. Укажите путь к базе данных:")
            print("   python check_database_integrity.py <path_to_database.db>")
            sys.exit(1)
    
    # Проверяем целостность
    is_ok = check_database_integrity(db_path)
    
    if not is_ok:
        print("\n[WARN] База данных повреждена!")
        response = input("Попытаться восстановить? (y/n): ")
        if response.lower() == 'y':
            recover_database(db_path)
    
    sys.exit(0 if is_ok else 1)

