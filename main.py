import logging
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from datetime import datetime, timedelta
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import CommandObject

from database import init_db, add_sale, get_sales_by_date, delete_sale, update_sale, get_sale_by_id, sum_sales_for_period
import re
from config import BOT_TOKEN
import os
from pathlib import Path

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Состояния для FSM
class Form(StatesGroup):
    waiting_for_date = State()
    waiting_for_record_selection = State()
    waiting_for_edit_choice = State()
    waiting_for_edit_amount = State()
    waiting_for_edit_time = State()
    waiting_for_edit_sales = State()
    waiting_for_edit_purchases = State()
    waiting_for_edit_admin = State()
    waiting_for_edit_card = State()
    waiting_for_edit_user_tag = State()
    waiting_for_delete_confirmation = State()

# Функция для создания инлайн-календаря
def create_calendar(year=None, month=None, selected_date=None):
    if year is None or month is None:
        today = datetime.now()
        year, month = today.year, today.month

    keyboard = InlineKeyboardBuilder()

    month_name = datetime(year, month, 1).strftime('%B %Y')
    keyboard.row(InlineKeyboardButton(text=month_name, callback_data="ignore"))

    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.row(*[InlineKeyboardButton(text=day, callback_data="ignore") for day in week_days])

    first_day = datetime(year, month, 1)
    last_day = (datetime(year, month + 1, 1) - timedelta(days=1)) if month < 12 else (datetime(year + 1, 1, 1) - timedelta(days=1))

    buttons = []

    for _ in range((first_day.weekday() + 1) % 7):
        buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))

    for day in range(1, last_day.day + 1):
        date_obj = datetime(year, month, day).date()
        date_str = date_obj.strftime('%Y-%m-%d')

        text = f"{day}"
        if selected_date and date_obj == selected_date:
            text = f"✅ {day}"

        buttons.append(InlineKeyboardButton(text=text, callback_data=f"calendar_day_{date_str}"))

    while len(buttons) % 7 != 0:
        buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))

    for i in range(0, len(buttons), 7):
        keyboard.row(*buttons[i:i+7])

    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1

    keyboard.row(
        InlineKeyboardButton(text="⬅️", callback_data=f"calendar_prev_{prev_year}_{prev_month}"),
        InlineKeyboardButton(text="Сегодня", callback_data="calendar_today"),
        InlineKeyboardButton(text="➡️", callback_data=f"calendar_next_{next_year}_{next_month}")
    )
    
    # Добавляем кнопку отчетности за месяц
    keyboard.row(
        InlineKeyboardButton(text="📊 Отчет за месяц", callback_data=f"month_report:{year}:{month}"),
        InlineKeyboardButton(text="🔄 Перезагрузить", callback_data="reload")
    )
    
    keyboard.row(
        InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")
    )

    return keyboard.as_markup()

# Добавляем обработчик для отчетности за месяц
@dp.callback_query(lambda c: c.data.startswith('month_report:'))
async def handle_month_report(callback_query: types.CallbackQuery):
    _, year, month = callback_query.data.split(':')
    year, month = int(year), int(month)
    
    # Получаем все записи за месяц
    start_date = datetime(year, month, 1).strftime('%d.%m.%y')
    end_date = (datetime(year, month + 1, 1) - timedelta(days=1)).strftime('%d.%m.%y') if month < 12 else (datetime(year + 1, 1, 1) - timedelta(days=1)).strftime('%d.%m.%y')
    
    # Здесь нужно реализовать получение данных за месяц из вашей БД
    # Это примерная реализация - адаптируйте под свою структуру БД
    monthly_sales = sum_sales_for_period(start_date, end_date, 'продажа')
    monthly_purchases = sum_sales_for_period(start_date, end_date, 'закупка')
    
    admin_percent = round(monthly_sales * 0.15)
    card_fee = 100 * (datetime(year, month + 1, 1) - datetime(year, month, 1)).days if month < 12 else (datetime(year + 1, 1, 1) - datetime(year, month, 1)).days
    month_total = int(monthly_sales - monthly_purchases - admin_percent - card_fee)
    
    month_name = datetime(year, month, 1).strftime('%B %Y')
    report = (
        f"<b>Отчетность за {month_name}</b>\n\n"
        f"Продажи: {int(monthly_sales)}р\n"
        f"Закупки: {int(monthly_purchases)}р\n"
        f"Процент админа: {admin_percent}р\n"
        f"Комиссия карты: {card_fee}р\n\n"
        f"<b>ИТОГО: {month_total}р</b>"
    )
    
    await callback_query.message.answer(report)
    await callback_query.answer()


@dp.inline_query()
async def handle_inline_sales(query: types.InlineQuery):
    # Строгое регулярное выражение
    pattern = r"#?(продажа|закупка)/(\d{2}\.\d{2}\.\d{2})/(@\w+)/(\d{2}:\d{2})/([\d,.]+)(р)?$"
    match = re.fullmatch(pattern, query.query.strip())
    
    if not match:
        await query.answer(
            results=[],
            switch_pm_text="Неверный формат. Пример: #продажа/10.04.25/@username/10:00/7000р",
            switch_pm_parameter="help"
        )
        return

    sale_type, date, user_tag, time, amount, _ = match.groups()
    amount = amount.replace(',', '').replace('.', '').strip()
    
    # Проверка на дубликаты
    existing = get_sales_by_date(date, sale_type)
    duplicate = any(
        sale[2] == user_tag and sale[3] == time and sale[4] == amount
        for sale in existing
    )
    
    if duplicate:
        result = types.InlineQueryResultArticle(
            id="1",
            title="Такая запись уже существует",
            input_message_content=types.InputTextMessageContent(
                message_text="Эта запись уже была добавлена ранее",
                parse_mode=ParseMode.HTML
            )
        )
    else:
        # Создаем клавиатуру с кнопкой подтверждения
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Подтвердить добавление",
                        callback_data=f"confirm_add:{sale_type}:{date}:{user_tag}:{time}:{amount}"
                    )
                ]
            ]
        )
        
        result = types.InlineQueryResultArticle(
            id="1",
            title=f"{sale_type.capitalize()}: {amount}р",
            input_message_content=types.InputTextMessageContent(
                message_text=(
                    f"<b>Добавлено:</b>\n"
                    f"Тип: {sale_type}\n"
                    f"Дата: {date}\n"
                    f"Пользователь: {user_tag}\n"
                    f"Время: {time}\n"
                    f"Сумма: {amount}р\n"
                    f"Добавил: {query.from_user.full_name}"
                ),
                parse_mode=ParseMode.HTML
            ),
            description=f"{sale_type} {date} {user_tag} {time}",
            reply_markup=keyboard
        )

    await query.answer(results=[result], cache_time=0)

@dp.callback_query(lambda c: c.data.startswith('confirm_add:'))
async def process_confirmation(callback_query: types.CallbackQuery):
    try:
        # Разбиваем данные callback, но берем только первые 6 элементов
        parts = callback_query.data.split(':')
        if len(parts) < 6:
            await callback_query.answer("Ошибка: неверный формат данных", show_alert=True)
            return
            
        _, sale_type, date, user_tag, time, amount = parts[:6]
        


        add_sale(
            sale_type=sale_type,
            date=date,
            user_tag=user_tag,
            time=time,
            amount=amount,
            user_id=callback_query.from_user.id
        )
        await callback_query.answer("✅ Запись успешно добавлена", show_alert=True)
        
        # Убираем кнопку после нажатия
        await callback_query.message.edit_reply_markup(reply_markup=None)
        
    except Exception as e:
        await callback_query.answer(f"Ошибка: {str(e)}", show_alert=True)
        print(f"Error in process_confirmation: {e}")

@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Продажа", callback_data="sales"),
        InlineKeyboardButton(text="Закупка", callback_data="purchase")
    )
    builder.row(InlineKeyboardButton(text="Отчетность", callback_data="report"))

    try:
        photo_path = Path("hello_photo.jpg").absolute()
        await message.reply_photo(
            photo=types.FSInputFile(photo_path),
            caption="Всю информацию по отчетности канала можно глянуть по кнопкам ниже👇",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке фото: {str(e)}")
        await message.answer(
            "Привет!\n\nВсю информацию по отчетности канала можно глянуть по кнопкам ниже👇",
            reply_markup=builder.as_markup()
        )

@dp.callback_query(lambda c: c.data.startswith(('calendar_prev_', 'calendar_next_', 'calendar_today')))
async def process_calendar_navigation(callback_query: types.CallbackQuery):
    if callback_query.data.startswith('calendar_prev_'):
        _, _, year, month = callback_query.data.split('_')
        year, month = int(year), int(month)
    elif callback_query.data.startswith('calendar_next_'):
        _, _, year, month = callback_query.data.split('_')
        year, month = int(year), int(month)
    else:
        today = datetime.now()
        year, month = today.year, today.month

    await callback_query.message.edit_reply_markup(
        reply_markup=create_calendar(year=year, month=month)
    )
    await callback_query.answer()

async def show_records(date_str: str, records: list, message: types.Message, record_type: str):
    report = f"{'Закупки' if record_type == 'закупка' else 'Продажи'} за {date_str}\n\n"
    total = 0
    
    for record in records:
        record_id, user_tag, time, amount = record[0], record[2], record[3], record[4]
        report += f"{record_id}. {user_tag}/{time}/{amount}\n"
        try:
            total += float(amount.replace('р', '').replace(',', '').strip())
        except:
            pass
    
    report += f"\nОбщая сумма: {int(total)}р"
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit_records:{date_str}:{record_type}"),
        InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete_records:{date_str}:{record_type}")
    )
    
    await message.answer(report, reply_markup=keyboard.as_markup())

@dp.callback_query(lambda c: c.data in ['sales', 'purchase', 'report'])
async def process_callback_button(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.update_data(action=callback_query.data)
    
    today = datetime.now().date()
    formatted_today = today.strftime('%d.%m.%y')

    if callback_query.data == 'sales':
        sales = get_sales_by_date(formatted_today, 'продажа')
        if sales:
            await show_records(formatted_today, sales, callback_query.message, 'продажа')
        else:
            await callback_query.message.answer("Сегодня пока нет данных о продажах.")

    elif callback_query.data == 'purchase':
        purchases = get_sales_by_date(formatted_today, 'закупка')
        if purchases:
            await show_records(formatted_today, purchases, callback_query.message, 'закупка')
        else:
            await callback_query.message.answer("Сегодня пока нет данных о закупках.")

    elif callback_query.data == 'report':
        await generate_report(callback_query.message, formatted_today, state)

    await callback_query.message.answer(
        "Выберите дату для просмотра:",
        reply_markup=create_calendar()
    )

@dp.callback_query(lambda c: c.data.startswith('edit_records:'))
async def handle_edit_records(callback_query: types.CallbackQuery, state: FSMContext):
    _, date_str, record_type = callback_query.data.split(':')
    records = get_sales_by_date(date_str, record_type)
    
    keyboard = InlineKeyboardBuilder()
    for record in records:
        record_id, user_tag, time, amount = record[0], record[2], record[3], record[4]
        keyboard.row(InlineKeyboardButton(
            text=f"{record_id}. {user_tag}/{time}/{amount}",
            callback_data=f"select_record:{record_id}"
        ))
    
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_{record_type}"))
    
    await state.set_state(Form.waiting_for_record_selection)
    await state.update_data(record_type=record_type, date_str=date_str)
    
    await callback_query.message.edit_text(
        "Выберите запись для редактирования:",
        reply_markup=keyboard.as_markup()
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('select_record:'))
async def handle_select_record(callback_query: types.CallbackQuery, state: FSMContext):
    record_id = int(callback_query.data.split(':')[1])
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✏️ Сумму", callback_data=f"edit_amount:{record_id}"),
        InlineKeyboardButton(text="✏️ Время", callback_data=f"edit_time:{record_id}"),
        InlineKeyboardButton(text="✏️ Username", callback_data=f"edit_user_tag:{record_id}"),
    )
    keyboard.row(
        InlineKeyboardButton(text="❌ Удалить запись", callback_data=f"confirm_delete:{record_id}"),
    )
    keyboard.row(
        InlineKeyboardButton(text="🔙 Назад", callback_data="cancel_edit")
    )
    
    await state.set_state(Form.waiting_for_edit_choice)
    await state.update_data(record_id=record_id)
    
    await callback_query.message.edit_text(
        "Что вы хотите изменить?",
        reply_markup=keyboard.as_markup()
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('confirm_delete:'))
async def handle_confirm_delete(callback_query: types.CallbackQuery, state: FSMContext):
    record_id = int(callback_query.data.split(':')[1])
    record = get_sale_by_id(record_id)
    
    if not record:
        await callback_query.answer("Запись не найдена")
        return
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_record:{record_id}"),
        InlineKeyboardButton(text="❌ Нет, отмена", callback_data="cancel_delete")
    )
    
    await state.set_state(Form.waiting_for_delete_confirmation)
    await state.update_data(record_id=record_id)
    
    await callback_query.message.edit_text(
        f"Вы уверены, что хотите удалить запись?\n\n"
        f"ID: {record_id}\n"
        f"Тип: {record[1]}\n"
        f"Дата: {record[5]}\n"
        f"Пользователь: {record[2]}\n"
        f"Время: {record[3]}\n"
        f"Сумма: {record[4]}",
        reply_markup=keyboard.as_markup()
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('delete_record:'))
async def handle_delete_record(callback_query: types.CallbackQuery, state: FSMContext):
    record_id = int(callback_query.data.split(':')[1])
    record = get_sale_by_id(record_id)
    
    if record:
        delete_sale(record_id)
        await callback_query.message.edit_text(f"Запись {record_id} успешно удалена")
    else:
        await callback_query.message.edit_text("Ошибка: запись не найдена")
    
    await state.clear()
    await callback_query.answer()

@dp.callback_query(lambda c: c.data == 'cancel_delete')
async def handle_cancel_delete(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    record_id = data.get('record_id')
    
    if record_id:
        keyboard = InlineKeyboardBuilder()
        keyboard.row(
            InlineKeyboardButton(text="✏️ Сумму", callback_data=f"edit_amount:{record_id}"),
            InlineKeyboardButton(text="✏️ Время", callback_data=f"edit_time:{record_id}"),
            InlineKeyboardButton(text="✏️ Username", callback_data=f"edit_user_tag:{record_id}"),
        )
        keyboard.row(
            InlineKeyboardButton(text="❌ Удалить запись", callback_data=f"confirm_delete:{record_id}"),
        )
        keyboard.row(
            InlineKeyboardButton(text="🔙 Назад", callback_data="cancel_edit")
        )
        
        await callback_query.message.edit_text(
            "Что вы хотите изменить?",
            reply_markup=keyboard.as_markup()
        )
    
    await state.set_state(Form.waiting_for_edit_choice)
    await callback_query.answer("Удаление отменено")

@dp.callback_query(lambda c: c.data.startswith('edit_user_tag:'))
async def handle_edit_user_tag_choice(callback_query: types.CallbackQuery, state: FSMContext):
    _, record_id = callback_query.data.split(':')
    record_id = int(record_id)
    
    await state.set_state(Form.waiting_for_edit_user_tag)
    await state.update_data(record_id=record_id)
    await callback_query.message.answer("Введите новый username (начинается с @):")
    await callback_query.answer()

@dp.message(Form.waiting_for_edit_user_tag)
async def process_new_user_tag(message: types.Message, state: FSMContext):
    data = await state.get_data()
    record_id = data['record_id']
    
    if message.text.startswith('@') and len(message.text) > 1:
        update_sale(record_id, user_tag=message.text)
        await message.answer("Username успешно обновлен")
        await state.clear()
    else:
        await message.answer("Неверный формат username. Должен начинаться с @ и содержать имя пользователя. Попробуйте еще раз.")
        
@dp.callback_query(lambda c: c.data.startswith(('edit_amount:', 'edit_time:')))
async def handle_edit_choice(callback_query: types.CallbackQuery, state: FSMContext):
    action, record_id = callback_query.data.split(':')
    record_id = int(record_id)
    
    if action == 'edit_amount':
        await state.set_state(Form.waiting_for_edit_amount)
        await state.update_data(record_id=record_id)
        await callback_query.message.answer("Введите новую сумму:")
    elif action == 'edit_time':
        await state.set_state(Form.waiting_for_edit_time)
        await state.update_data(record_id=record_id)
        await callback_query.message.answer("Введите новое время (формат ЧЧ:ММ):")
    
    await callback_query.answer()

@dp.message(Form.waiting_for_edit_amount)
async def process_new_amount(message: types.Message, state: FSMContext):
    data = await state.get_data()
    record_id = data['record_id']
    
    try:
        new_amount = message.text.replace('р', '').replace(',', '').strip()
        float(new_amount)
        update_sale(record_id, amount=new_amount)
        await message.answer("Сумма успешно обновлена")
        await state.clear()
    except ValueError:
        await message.answer("Неверный формат суммы. Попробуйте еще раз.")

@dp.message(Form.waiting_for_edit_time)
async def process_new_time(message: types.Message, state: FSMContext):
    data = await state.get_data()
    record_id = data['record_id']
    
    if re.match(r'^\d{2}:\d{2}$', message.text):
        update_sale(record_id, time=message.text)
        await message.answer("Время успешно обновлено")
        await state.clear()
    else:
        await message.answer("Неверный формат времени. Используйте ЧЧ:ММ (например, 14:30)")

async def generate_report(message: types.Message, date_str: str, state: FSMContext):
    sales = get_sales_by_date(date_str, 'продажа')
    purchases = get_sales_by_date(date_str, 'закупка')

    total_sales = sum([float(s[4].replace('р', '').replace(',', '').strip()) for s in sales if s[4]]) if sales else 0
    total_purchases = sum([float(p[4].replace('р', '').replace(',', '').strip()) for p in purchases if p[4]]) if purchases else 0

    admin_percent = round(total_sales * 0.15)
    card_fee = 100
    day_total = int(total_sales - total_purchases - admin_percent - card_fee)

    report = (
        f"<b>Отчетность за {date_str}г</b>\n"
        f"1. Сумма продаж : {int(total_sales)}р\n"
        f"2. Покупка рекламы : {int(total_purchases)}р\n"
        f"3. Процент админа : {admin_percent}р\n"
        f"4. Контенщик : - \n"
        f"5. Карта : - {card_fee}р\n\n"
        f"<b>ИТОГ ДНЯ : {day_total}р</b>"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✏️ Продажи", callback_data="edit_report_sales"),
        InlineKeyboardButton(text="✏️ Закупки", callback_data="edit_report_purchases")
    )
    keyboard.row(
        InlineKeyboardButton(text="✏️ % Админа", callback_data="edit_report_admin"),
        InlineKeyboardButton(text="✏️ Карта", callback_data="edit_report_card")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="update_report"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
    )

    await state.update_data(
        current_sales=total_sales,
        current_purchases=total_purchases,
        current_admin=admin_percent,
        current_card=card_fee,
        report_date=date_str
    )

    await message.answer(report, reply_markup=keyboard.as_markup())

@dp.callback_query(lambda c: c.data.startswith('calendar_day_'))
async def process_calendar(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        date_str = callback_query.data.split('_')[2]
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        formatted_date = selected_date.strftime('%d.%m.%y')
        
        data = await state.get_data()
        action = data.get('action')
        
        if action == 'sales':
            sales = get_sales_by_date(formatted_date, 'продажа')
            if sales:
                await show_records(formatted_date, sales, callback_query.message, 'продажа')
            else:
                await callback_query.message.answer(f"Нет данных о продажах за {formatted_date}")

        elif action == 'purchase':
            purchases = get_sales_by_date(formatted_date, 'закупка')
            if purchases:
                await show_records(formatted_date, purchases, callback_query.message, 'закупка')
            else:
                await callback_query.message.answer(f"Нет данных о закупках за {formatted_date}")

        elif action == 'report':
            await generate_report(callback_query.message, formatted_date, state)

        try:
            await callback_query.message.edit_reply_markup(
                reply_markup=create_calendar(
                    year=selected_date.year,
                    month=selected_date.month,
                    selected_date=selected_date
                )
            )
        except Exception as e:
            logging.error(f"Не удалось обновить календарь: {e}")
        
        await callback_query.answer()
    except Exception as e:
        logging.error(f"Ошибка при обработке календаря: {e}")
        await callback_query.answer("Произошла ошибка, попробуйте еще раз")

@dp.callback_query(lambda c: c.data == 'cancel_edit')
async def handle_cancel_edit(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback_query.message.delete()
    await callback_query.answer("Редактирование отменено")

@dp.callback_query(lambda c: c.data.startswith('back_to_'))
async def handle_back_to_records(callback_query: types.CallbackQuery, state: FSMContext):
    record_type = callback_query.data.split('_')[-1]
    today = datetime.now().date()
    formatted_today = today.strftime('%d.%m.%y')
    
    if record_type == 'sales':
        sales = get_sales_by_date(formatted_today, 'продажа')
        if sales:
            await show_records(formatted_today, sales, callback_query.message, 'продажа')
        else:
            await callback_query.message.answer("Сегодня пока нет данных о продажах.")
    elif record_type == 'purchase':
        purchases = get_sales_by_date(formatted_today, 'закупка')
        if purchases:
            await show_records(formatted_today, purchases, callback_query.message, 'закупка')
        else:
            await callback_query.message.answer("Сегодня пока нет данных о закупках.")
    
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('edit_report_'))
async def handle_edit_report(callback_query: types.CallbackQuery, state: FSMContext):
    action = callback_query.data.split('_')[-1]
    
    if action == 'sales':
        await state.set_state(Form.waiting_for_edit_sales)
        await callback_query.message.answer("Введите новую сумму продаж:")
    elif action == 'purchases':
        await state.set_state(Form.waiting_for_edit_purchases)
        await callback_query.message.answer("Введите новую сумму закупок:")
    elif action == 'admin':
        await state.set_state(Form.waiting_for_edit_admin)
        await callback_query.message.answer("Введите новый процент админа:")
    elif action == 'card':
        await state.set_state(Form.waiting_for_edit_card)
        await callback_query.message.answer("Введите новую комиссию карты:")
    
    await callback_query.answer()

@dp.message(Form.waiting_for_edit_sales)
async def process_new_sales(message: types.Message, state: FSMContext):
    try:
        new_sales = float(message.text.replace('р', '').replace(',', '').strip())
        await state.update_data(current_sales=new_sales)
        await message.answer(f"Сумма продаж обновлена: {int(new_sales)}р")
        await show_updated_report(message, state)
    except ValueError:
        await message.answer("Неверный формат суммы. Попробуйте еще раз.")

@dp.message(Form.waiting_for_edit_purchases)
async def process_new_purchases(message: types.Message, state: FSMContext):
    try:
        new_purchases = float(message.text.replace('р', '').replace(',', '').strip())
        await state.update_data(current_purchases=new_purchases)
        await message.answer(f"Сумма закупок обновлена: {int(new_purchases)}р")
        await show_updated_report(message, state)
    except ValueError:
        await message.answer("Неверный формат суммы. Попробуйте еще раз.")

@dp.message(Form.waiting_for_edit_admin)
async def process_new_admin(message: types.Message, state: FSMContext):
    try:
        new_admin = float(message.text.replace('р', '').replace(',', '').strip())
        await state.update_data(current_admin=new_admin)
        await message.answer(f"Процент админа обновлен: {int(new_admin)}р")
        await show_updated_report(message, state)
    except ValueError:
        await message.answer("Неверный формат суммы. Попробуйте еще раз.")

@dp.message(Form.waiting_for_edit_card)
async def process_new_card(message: types.Message, state: FSMContext):
    try:
        new_card = float(message.text.replace('р', '').replace(',', '').strip())
        await state.update_data(current_card=new_card)
        await message.answer(f"Комиссия карты обновлена: {int(new_card)}р")
        await show_updated_report(message, state)
    except ValueError:
        await message.answer("Неверный формат суммы. Попробуйте еще раз.")

async def show_updated_report(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    total_sales = data.get('current_sales', 0)
    total_purchases = data.get('current_purchases', 0)
    admin_percent = data.get('current_admin', round(total_sales * 0.15))
    card_fee = data.get('current_card', 100)
    date_str = data.get('report_date', datetime.now().strftime('%d.%m.%y'))
    day_total = int(total_sales - total_purchases - admin_percent - card_fee)

    report = (
        f"<b>Отчетность за {date_str}г</b>\n"
        f"1. Сумма продаж : {int(total_sales)}р\n"
        f"2. Покупка рекламы : {int(total_purchases)}р\n"
        f"3. Процент админа : {admin_percent}р\n"
        f"4. Контенщик : - \n"
        f"5. Карта : - {card_fee}р\n\n"
        f"<b>ИТОГ ДНЯ : {day_total}р</b>"
    )

    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✏️ Продажи", callback_data="edit_report_sales"),
        InlineKeyboardButton(text="✏️ Закупки", callback_data="edit_report_purchases")
    )
    keyboard.row(
        InlineKeyboardButton(text="✏️ % Админа", callback_data="edit_report_admin"),
        InlineKeyboardButton(text="✏️ Карта", callback_data="edit_report_card")
    )
    keyboard.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="update_report"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_menu")
    )

    await message.answer(report, reply_markup=keyboard.as_markup())

@dp.callback_query(lambda c: c.data == 'update_report')
async def handle_update_report(callback_query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    date_str = data.get('report_date', datetime.now().strftime('%d.%m.%y'))
    await generate_report(callback_query.message, date_str, state)
    await callback_query.answer("Отчет обновлен")

@dp.callback_query(lambda c: c.data == 'reload')
async def reload_handler(callback_query: types.CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Продажа", callback_data="sales"),
        InlineKeyboardButton(text="Закупка", callback_data="purchase")
    )
    builder.row(InlineKeyboardButton(text="Отчетность", callback_data="report"))
    
    try:
        await callback_query.message.delete()
        await callback_query.message.answer(
            "Всю информацию по отчетности канала можно глянуть по кнопкам ниже👇",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка при перезагрузке: {str(e)}")
        await callback_query.answer("Произошла ошибка, попробуйте еще раз")

@dp.callback_query(lambda c: c.data == 'back_to_menu')
async def back_to_menu_handler(callback_query: types.CallbackQuery, state: FSMContext):
    try:
        await state.clear()
        
        builder = InlineKeyboardBuilder()
        builder.row(
            InlineKeyboardButton(text="Продажа", callback_data="sales"),
            InlineKeyboardButton(text="Закупка", callback_data="purchase")
        )
        builder.row(InlineKeyboardButton(text="Отчетность", callback_data="report"))
        
        # Пытаемся отредактировать сообщение, если это возможно
        try:
            await callback_query.message.edit_text(
                "Всю информацию по отчетности канала можно глянуть по кнопкам ниже👇",
                reply_markup=builder.as_markup()
            )
        except:
            # Если не удалось отредактировать (например, если это было фото), отправляем новое сообщение
            await callback_query.message.answer(
                "Всю информацию по отчетности канала можно глянуть по кнопкам ниже👇",
                reply_markup=builder.as_markup()
            )
        
        await callback_query.answer()
    except Exception as e:
        logging.error(f"Ошибка в back_to_menu_handler: {e}")
        await callback_query.answer("Произошла ошибка, попробуйте еще раз")

@dp.callback_query(lambda c: c.data.startswith('delete_records:'))
async def handle_delete_records(callback_query: types.CallbackQuery, state: FSMContext):
    _, date_str, record_type = callback_query.data.split(':')
    records = get_sales_by_date(date_str, record_type)
    
    keyboard = InlineKeyboardBuilder()
    for record in records:
        record_id, user_tag, time, amount = record[0], record[2], record[3], record[4]
        keyboard.row(InlineKeyboardButton(
            text=f"{record_id}. {user_tag}/{time}/{amount}",
            callback_data=f"select_delete:{record_id}"
        ))
    
    keyboard.row(InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_to_{record_type}"))
    
    await state.set_state(Form.waiting_for_record_selection)
    await state.update_data(record_type=record_type, date_str=date_str)
    
    await callback_query.message.edit_text(
        "Выберите запись для удаления:",
        reply_markup=keyboard.as_markup()
    )
    await callback_query.answer()

@dp.callback_query(lambda c: c.data.startswith('select_delete:'))
async def handle_select_delete(callback_query: types.CallbackQuery, state: FSMContext):
    record_id = int(callback_query.data.split(':')[1])
    record = get_sale_by_id(record_id)
    
    if not record:
        await callback_query.answer("Запись не найдена")
        return
    
    keyboard = InlineKeyboardBuilder()
    keyboard.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"delete_record:{record_id}"),
        InlineKeyboardButton(text="❌ Нет, отмена", callback_data="cancel_delete")
    )
    
    await state.set_state(Form.waiting_for_delete_confirmation)
    await state.update_data(record_id=record_id)
    
    await callback_query.message.edit_text(
        f"Вы уверены, что хотите удалить запись?\n\n"
        f"ID: {record_id}\n"
        f"Тип: {record[1]}\n"
        f"Дата: {record[5]}\n"
        f"Пользователь: {record[2]}\n"
        f"Время: {record[3]}\n"
        f"Сумма: {record[4]}",
        reply_markup=keyboard.as_markup()
    )
    await callback_query.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    init_db()
    asyncio.run(main())