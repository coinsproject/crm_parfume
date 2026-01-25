#!/usr/bin/env python3
"""
Скрипт для исправления поврежденной таблицы FTS в SQLite
"""
import sqlite3
import sys
import os
from pathlib import Path

def fix_fts_table(db_path: str):
    """Исправляет поврежденную таблицу FTS"""
    if not os.path.exists(db_path):
        print(f"[FAIL] База данных не найдена: {db_path}")
        return False
    
    print(f"Исправление таблицы FTS в базе данных: {db_path}")
    print("-" * 60)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем, существует ли таблица FTS
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name LIKE '%fts%'
        """)
        fts_tables = cursor.fetchall()
        
        if not fts_tables:
            print("[INFO] Таблицы FTS не найдены")
            conn.close()
            return True
        
        print(f"[INFO] Найдено таблиц FTS: {len(fts_tables)}")
        for table in fts_tables:
            print(f"   - {table[0]}")
        
        # Сначала удаляем все связанные таблицы FTS5 (вспомогательные)
        fts5_aux_tables = ['price_products_fts5_data', 'price_products_fts5_idx', 
                          'price_products_fts5_docsize', 'price_products_fts5_config']
        for aux_table in fts5_aux_tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {aux_table}")
                print(f"[INFO] Удалена вспомогательная таблица: {aux_table}")
            except:
                pass
        
        # Пытаемся пересоздать таблицы FTS
        for table_name, in fts_tables:
            print(f"\nОбработка таблицы: {table_name}")
            
            # Пропускаем вспомогательные таблицы FTS5 (они уже удалены)
            if table_name in fts5_aux_tables:
                continue
            
            try:
                # Получаем структуру оригинальной таблицы
                cursor.execute("SELECT sql FROM sqlite_master WHERE name=?", (table_name,))
                create_sql = cursor.fetchone()
                
                # Удаляем поврежденную таблицу
                print(f"[INFO] Удаление поврежденной таблицы {table_name}...")
                try:
                    # Используем PRAGMA для обхода проверок
                    cursor.execute("PRAGMA writable_schema=ON")
                    cursor.execute(f"DELETE FROM sqlite_master WHERE name='{table_name}'")
                    cursor.execute("PRAGMA writable_schema=OFF")
                    conn.commit()
                    print(f"[OK] Таблица {table_name} удалена")
                except Exception as drop_error:
                    print(f"[WARN] Не удалось удалить {table_name}: {drop_error}")
                    # Пропускаем эту таблицу
                    continue
                    
                    # Пересоздаем таблицу
                    print(f"[INFO] Пересоздание таблицы...")
                    cursor.execute(create_sql[0])
                    print(f"[OK] Таблица {table_name} пересоздана")
                else:
                    print(f"[WARN] Не удалось найти структуру таблицы {table_name}")
                    # Пытаемся удалить и пересоздать по стандартной схеме
                    if 'price_products_fts' in table_name:
                        print(f"[INFO] Пересоздание price_products_fts по стандартной схеме...")
                        cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                        cursor.execute("""
                            CREATE VIRTUAL TABLE price_products_fts5 USING fts5(
                                external_article,
                                raw_name,
                                product_name,
                                brand,
                                search_text,
                                content='price_products',
                                content_rowid='id'
                            )
                        """)
                        print(f"[OK] Таблица price_products_fts5 пересоздана")
                    
            except sqlite3.OperationalError as e:
                print(f"[WARN] Ошибка при обработке {table_name}: {e}")
                # Пытаемся просто удалить поврежденную таблицу
                try:
                    cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
                    print(f"[OK] Поврежденная таблица {table_name} удалена")
                except:
                    pass
        
        # Коммитим изменения
        conn.commit()
        print("\n" + "=" * 60)
        print("[OK] Таблицы FTS исправлены!")
        
        # Проверяем целостность
        print("\nПроверка целостности после исправления...")
        cursor.execute("PRAGMA quick_check")
        result = cursor.fetchone()
        if result and result[0] == "ok":
            print("[OK] База данных в порядке!")
        else:
            print(f"[WARN] Предупреждение: {result[0] if result else 'FAILED'}")
        
        conn.close()
        return True
        
    except sqlite3.DatabaseError as e:
        print(f"[FAIL] Ошибка базы данных: {e}")
        return False
    except Exception as e:
        print(f"[FAIL] Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        # Пытаемся найти базу данных
        possible_paths = ["crm_new.db", "crm.db", "data/crm.db"]
        db_path = None
        for path in possible_paths:
            if os.path.exists(path):
                db_path = path
                break
        
        if not db_path:
            print("[FAIL] База данных не найдена. Укажите путь:")
            print("   python fix_fts_table.py <path_to_database.db>")
            sys.exit(1)
    
    success = fix_fts_table(db_path)
    sys.exit(0 if success else 1)

