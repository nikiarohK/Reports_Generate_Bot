import sqlite3
from typing import List, Tuple, Optional

DATABASE_NAME = 'sales.db'

def init_db():
    """Инициализирует базу данных и создает таблицу, если она не существует"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_type TEXT NOT NULL,
        user_tag TEXT NOT NULL,
        time TEXT NOT NULL,
        amount TEXT NOT NULL,
        date TEXT NOT NULL,
        user_id INTEGER NOT NULL
    )
    ''')
    
    conn.commit()
    conn.close()

def add_sale(sale_type: str, date: str, user_tag: str, time: str, amount: str, user_id: int):
    """Добавляет новую запись о продаже/закупке в базу данных"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    INSERT INTO sales (sale_type, user_tag, time, amount, date, user_id)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (sale_type, user_tag, time, amount, date, user_id))
    
    conn.commit()
    conn.close()

def get_sales_by_date(date: str, sale_type: str) -> List[Tuple]:
    """Возвращает все записи о продажах/закупках за указанную дату"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT id, sale_type, user_tag, time, amount, date, user_id
    FROM sales
    WHERE date = ? AND sale_type = ?
    ORDER BY time
    ''', (date, sale_type))
    
    sales = cursor.fetchall()
    conn.close()
    return sales

def delete_sale(sale_id: int):
    """Удаляет запись о продаже/закупке по ID"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    DELETE FROM sales
    WHERE id = ?
    ''', (sale_id,))
    
    conn.commit()
    conn.close()

def update_sale(
    sale_id: int,
    sale_type: str = None,
    user_tag: str = None,
    time: str = None,
    amount: str = None,
    date: str = None
):
    """Обновляет запись о продаже/закупке"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    updates = []
    params = []
    
    if sale_type is not None:
        updates.append("sale_type = ?")
        params.append(sale_type)
    if user_tag is not None:
        updates.append("user_tag = ?")
        params.append(user_tag)
    if time is not None:
        updates.append("time = ?")
        params.append(time)
    if amount is not None:
        updates.append("amount = ?")
        params.append(amount)
    if date is not None:
        updates.append("date = ?")
        params.append(date)
    
    if updates:
        query = "UPDATE sales SET " + ", ".join(updates) + " WHERE id = ?"
        params.append(sale_id)
        
        cursor.execute(query, tuple(params))
        conn.commit()
    
    conn.close()

def get_sale_by_id(sale_id: int) -> Optional[Tuple]:
    """Возвращает запись о продаже/закупке по ID или None, если не найдена"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
    SELECT id, sale_type, user_tag, time, amount, date, user_id
    FROM sales
    WHERE id = ?
    ''', (sale_id,))
    
    sale = cursor.fetchone()
    conn.close()
    return sale

def sum_sales_for_period(start_date, end_date, sale_type):
    """Суммирует продажи/закупки за указанный период"""
    # Пример реализации - замените на реальный запрос к вашей БД
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT SUM(amount) 
        FROM sales 
        WHERE sale_type = ? AND date BETWEEN ? AND ?
    """, (sale_type, start_date, end_date))
    
    result = cursor.fetchone()[0] or 0
    conn.close()
    return float(result) if result else 0