import sqlite3
from datetime import datetime, timedelta
import pytz

def init_db():
    conn = sqlite3.connect("sales.db")
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT,
            date TEXT,
            user_tag TEXT,
            time TEXT,
            amount TEXT,
            user_id INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def convert_to_msk(time_str):
    """Конвертирует время в московское (MSK, UTC+3)"""
    try:
        # Парсим входящее время (предполагаем формат HH:MM)
        time_obj = datetime.strptime(time_str, "%H:%M")
        
        # Создаем datetime с текущей датой и указанным временем в UTC
        utc_now = datetime.now(pytz.utc)
        utc_time = utc_now.replace(
            hour=time_obj.hour, 
            minute=time_obj.minute, 
            second=0, 
            microsecond=0
        )
        
        # Конвертируем в московское время
        msk_tz = pytz.timezone('Europe/Moscow')
        msk_time = utc_time.astimezone(msk_tz)
        
        # Возвращаем только время в формате HH:MM
        return msk_time.strftime("%H:%M")
    except ValueError:
        # Если формат времени некорректный, возвращаем исходное значение
        return time_str

def add_sale(sale_type, date, user_tag, time, amount, user_id):
    if sale_type.lower() not in ('продажа', 'закупка'): 
        print("Неправильный тип")
        return None
    
    # Конвертируем время в MSK
    msk_time = convert_to_msk(time)
    
    conn = sqlite3.connect("sales.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sales (type, date, user_tag, time, amount, user_id)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (sale_type.lower(), date, user_tag, msk_time, amount, user_id))
    conn.commit()
    conn.close()
    
def get_sales_by_date(date, sale_type):
    """Получает все продажи/закупки за указанную дату"""
    conn = sqlite3.connect("sales.db")
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT type, date, user_tag, time, amount, user_id 
        FROM sales 
        WHERE date = ? AND type = ?
        ORDER BY time
    ''', (date, sale_type.lower()))
    
    sales = cursor.fetchall()
    conn.close()
    return sales