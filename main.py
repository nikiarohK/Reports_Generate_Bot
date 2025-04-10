import logging
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputFile, InlineQueryResultArticle, InputTextMessageContent
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from datetime import datetime, timedelta
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import init_db, add_sale
import re
from config import BOT_TOKEN
from database import get_sales_by_date  

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота с настройками по умолчанию
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Состояния для FSM
class Form(StatesGroup):
    waiting_for_date = State()

# Функция для создания инлайн-календаря
def create_calendar(year=None, month=None):
    if year is None or month is None:
        today = datetime.now()
        year, month = today.year, today.month
    
    # Создаем клавиатуру
    keyboard = InlineKeyboardBuilder()
    
    # Заголовок с месяцем и годом
    month_name = datetime(year, month, 1).strftime('%B %Y')
    keyboard.row(InlineKeyboardButton(text=month_name, callback_data="ignore"))
    
    # Дни недели
    week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    buttons = []
    for day in week_days:
        buttons.append(InlineKeyboardButton(text=day, callback_data="ignore"))
    keyboard.row(*buttons)
    
    # Дни месяца
    first_day = datetime(year, month, 1)
    last_day = datetime(year, month + 1, 1) - timedelta(days=1) if month < 12 else datetime(year + 1, 1, 1) - timedelta(days=1)
    
    # Пустые кнопки для дней предыдущего месяца
    for _ in range((first_day.weekday() + 1) % 7):
        buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
    
    # Кнопки с днями текущего месяца
    for day in range(1, last_day.day + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        buttons.append(InlineKeyboardButton(text=str(day), callback_data=f"calendar_day_{date_str}"))
    
    # Пустые кнопки для оставшихся дней
    while len(buttons) % 7 != 0:
        buttons.append(InlineKeyboardButton(text=" ", callback_data="ignore"))
    
    # Добавляем дни в клавиатуру по 7 в ряд
    for i in range(0, len(buttons), 7):
        keyboard.row(*buttons[i:i+7])
    
    # Кнопки навигации
    prev_month = month - 1 if month > 1 else 12
    prev_year = year if month > 1 else year - 1
    next_month = month + 1 if month < 12 else 1
    next_year = year if month < 12 else year + 1
    
    keyboard.row(
        InlineKeyboardButton(text="⬅️", callback_data=f"calendar_prev_{prev_year}_{prev_month}"),
        InlineKeyboardButton(text="Сегодня", callback_data="calendar_today"),
        InlineKeyboardButton(text="➡️", callback_data=f"calendar_next_{next_year}_{next_month}")
    )
    
    # Добавляем кнопку "Вернуться в меню"
    keyboard.row(
        InlineKeyboardButton(text="🔙 Вернуться в меню", callback_data="back_to_menu")
    )
    
    return keyboard.as_markup()

@dp.inline_query()
async def handle_inline_sales(query: types.InlineQuery):
    # Пример: #продажа/10.04.25/@Verona/10:00/7000р
    pattern = r"#(\w+)/(\d{2}\.\d{2}\.\d{2})/(@\w+)/(\d{2}:\d{2})/([\d.,]+р?)"
    match = re.search(pattern, query.query)
    
    if not match:
        # Используем answer для inline-запросов вместо reply
        await query.answer(
            results=[],
            switch_pm_text="Неверный формат. Пример: #продажа/10.04.25/@username/10:00/7000р",
            switch_pm_parameter="help"
        )
        return

    sale_type, date, user_tag, time, amount = match.groups()

    # Добавляем в базу данных
    add_sale(
        sale_type=sale_type,
        date=date,
        user_tag=user_tag,
        time=time,
        amount=amount,
        user_id=query.from_user.id
    )

    # Создаем результат для inline-запроса
    result = types.InlineQueryResultArticle(
        id="1",
        title=f"Продажа: {amount}",
        input_message_content=types.InputTextMessageContent(
            message_text=(
                f"<b>Добавлено:</b>\n"
                f"Тип: {sale_type}\n"
                f"Дата: {date}\n"
                f"Пользователь: {user_tag}\n"
                f"Время: {time}\n"
                f"Сумма: {amount}\n"
                f"Добавил: {query.from_user.full_name}"
            ),
            parse_mode=ParseMode.HTML
        ),
        description=f"{sale_type} {date} {user_tag} {time}"
    )

    await query.answer(
        results=[result],
        cache_time=0
    )


# Обработчик команды /start
@dp.message(Command("start"))
async def send_welcome(message: types.Message):
    # Создаем инлайн-кнопки с нужным расположением
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки "Продажа" и "Закупка" в один ряд
    builder.row(
        InlineKeyboardButton(text="Продажа", callback_data="sales"),
        InlineKeyboardButton(text="Закупка", callback_data="purchase")
    )
    
    # Добавляем кнопку "Отчетность" в отдельный ряд
    builder.row(
        InlineKeyboardButton(text="Отчетность", callback_data="report")
    )

    # Отправляем сообщение с фото и кнопками
    try:
        photo = InputFile("hello_photo.jpg")
        await message.reply_photo(
            photo=photo,
            caption="Всю информацию по отчетности канала можно глянуть по кнопкам ниже👇",
            reply_markup=builder.as_markup()
        )
    except FileNotFoundError:
        await message.answer(
            "Привет\n\n"
            "Всю информацию по отчетности канала можно глянуть по кнопкам ниже👇",
            reply_markup=builder.as_markup()
        )
    except Exception as e:
        logging.error(f"Ошибка при отправке фото: {e}")
        await message.answer(
            "Привет\n\n"
            "Всю информацию по отчетности канала можно глянуть по кнопкам ниже👇",
            reply_markup=builder.as_markup()
        )

# Обработчик нажатий на инлайн-кнопки (выбор действия)
@dp.callback_query(lambda c: c.data in ['sales', 'purchase', 'report'])
async def process_callback_button(callback_query: types.CallbackQuery, state: FSMContext):
    await callback_query.answer()
    
    await state.update_data(action=callback_query.data)
    
    today = datetime.now().date()
    formatted_today = today.strftime('%d.%m.%y')

    if callback_query.data == 'sales':
        sales = get_sales_by_date(formatted_today, 'продажа')
        if sales:
            report = f"Продажи за {formatted_today}\n\n"
            total = 0
            for sale in sales:
                user_tag = sale[2]
                time = sale[3]
                amount = sale[4]
                report += f"{user_tag}/{time}/{amount}\n"
                try:
                    total += float(amount.replace('р', '').replace(',', '').strip())
                except:
                    pass
            report += f"\nСумма продаж: {int(total)}р"
            await callback_query.message.answer(report)
        else:
            await callback_query.message.answer("Сегодня пока нет данных о продажах.")

    elif callback_query.data == 'purchase':
        purchases = get_sales_by_date(formatted_today, 'закупка')
        if purchases:
            report = f"Покупка рекламы за {formatted_today}\n\n"
            total = 0
            for purchase in purchases:
                user_tag = purchase[2]
                time = purchase[3]
                amount = purchase[4]
                report += f"{user_tag}/{time}/{amount}\n"
                try:
                    total += float(amount.replace('р', '').replace(',', '').strip())
                except:
                    pass
            report += f"\nСумма покупки рекламы: {int(total)}р"
            await callback_query.message.answer(report)
        else:
            await callback_query.message.answer("Сегодня пока нет данных о закупках.")

    elif callback_query.data == 'report':
        sales = get_sales_by_date(formatted_today, 'продажа')
        purchases = get_sales_by_date(formatted_today, 'закупка')

        total_sales = sum([
            float(sale[4].replace('р', '').replace(',', '').strip())
            for sale in sales
            if sale[4]
        ]) if sales else 0

        total_purchases = sum([
            float(purchase[4].replace('р', '').replace(',', '').strip())
            for purchase in purchases
            if purchase[4]
        ]) if purchases else 0

        admin_percent = round(total_sales * 0.15)
        content_creator = 0  # пока пусто
        card_fee = 100

        day_total = int(total_sales - total_purchases - admin_percent - content_creator - card_fee)

        # подсчет баланса по предыдущим дням
        balance = 0
        for day_offset in range(1, today.day):
            prev_date = today.replace(day=day_offset)
            prev_fmt = prev_date.strftime('%d.%m.%y')
            prev_sales = get_sales_by_date(prev_fmt, 'продажа') or []
            prev_purchases = get_sales_by_date(prev_fmt, 'закупка') or []

            psum = sum([float(s[4].replace('р', '').replace(',', '').strip()) for s in prev_sales if s[4]])
            bsum = sum([float(p[4].replace('р', '').replace(',', '').strip()) for p in prev_purchases if p[4]])
            admin_cut = round(psum * 0.15)
            prev_day_total = psum - bsum - admin_cut - 0 - 100  # контентщик = 0, карта = 100
            balance += int(prev_day_total)

        report = (
            f"<b>Отчетность за {formatted_today}г</b>\n"
            f"Сумма продаж : {int(total_sales)}р\n"
            f"Покупка рекламы : {int(total_purchases)}р\n"
            f"Процент админа : {admin_percent}р\n"
            f"Контенщик : - \n"
            f"Карта : - {card_fee}р\n\n"
            f"<b>ИТОГ ДНЯ : {day_total}р</b>\n"
            f"<b>Баланс: {balance}р</b>"
        )

        await callback_query.message.answer(report)

    await callback_query.message.answer(
        "Выберите дату для просмотра:",
        reply_markup=create_calendar()
    )


# Обработчик взаимодействий с календарем
@dp.callback_query(lambda c: c.data.startswith('calendar_day_'))
async def process_calendar(callback_query: types.CallbackQuery, state: FSMContext):
    data = callback_query.data
    
    if data.startswith('calendar_day_'):
        # Пользователь выбрал дату
        date_str = data.split('_')[2]
        selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        formatted_date = selected_date.strftime('%d.%m.%y')  # Формат 10.04.25
        
        # Получаем сохраненное действие
        state_data = await state.get_data()
        action = state_data.get('action')
        
        if action == 'sales':
            # Получаем данные о продажах за выбранную дату
            sales = get_sales_by_date(formatted_date, 'продажа')
            
            if not sales:
                await callback_query.message.answer(
                    f"Нет данных о продажах за {formatted_date}"
                )
            else:
                # Формируем отчет
                report = f"Продажи за {formatted_date}г\n\n"
                total = 0
                
                for sale in sales:
                    user_tag = sale[2]  # user_tag
                    time = sale[3]     # time
                    amount = sale[4]    # amount
                    report += f"{user_tag}/{time}/{amount}\n"
                    
                    # Суммируем продажи
                    try:
                        amount_num = float(amount.replace('р', '').replace(',', '').strip())
                        total += amount_num
                    except:
                        pass
                
                report += f"\nСумма продаж: {int(total)}р"
                
                await callback_query.message.answer(report)
        
        elif action == 'purchase':
            # Получаем данные о закупках за выбранную дату
            purchases = get_sales_by_date(formatted_date, 'закупка')
            
            if not purchases:
                await callback_query.message.answer(
                    f"Нет данных о закупках за {formatted_date}"
                )
            else:
                # Формируем отчет
                report = f"Покупка рекламы за {formatted_date}г\n\n"
                total = 0
                
                for purchase in purchases:
                    user_tag = purchase[2]  # user_tag
                    time = purchase[3]     # time
                    amount = purchase[4]    # amount
                    report += f"{user_tag}/{time}/{amount}\n"
                    
                    # Суммируем закупки
                    try:
                        amount_num = float(amount.replace('р', '').replace(',', '').strip())
                        total += amount_num
                    except:
                        pass
                
                report += f"\nСумма покупки рекламы: {int(total)}р"
                
                await callback_query.message.answer(report)
        
        elif action == 'report':
            # Получаем данные о всех операциях за выбранную дату
            sales = get_sales_by_date(formatted_date, 'продажа')
            purchases = get_sales_by_date(formatted_date, 'закупка')
            
            total_sales = sum([
                float(sale[4].replace('р', '').replace(',', '').strip())
                for sale in sales if sale[4]
            ]) if sales else 0

            total_purchases = sum([
                float(purchase[4].replace('р', '').replace(',', '').strip())
                for purchase in purchases if purchase[4]
            ]) if purchases else 0

            admin_percent = round(total_sales * 0.15)
            content_creator = 0  # Пока не задан
            card_fee = 100

            day_total = int(total_sales - total_purchases - admin_percent - content_creator - card_fee)

            # Подсчет баланса за все предыдущие дни месяца
            balance = 0
            selected_day = selected_date.day
            for day_offset in range(1, selected_day):
                prev_date = selected_date.replace(day=day_offset)
                prev_fmt = prev_date.strftime('%d.%m.%y')
                prev_sales = get_sales_by_date(prev_fmt, 'продажа') or []
                prev_purchases = get_sales_by_date(prev_fmt, 'закупка') or []

                psum = sum([float(s[4].replace('р', '').replace(',', '').strip()) for s in prev_sales if s[4]])
                bsum = sum([float(p[4].replace('р', '').replace(',', '').strip()) for p in prev_purchases if p[4]])
                admin_cut = round(psum * 0.15)
                prev_day_total = psum - bsum - admin_cut - 0 - 100
                balance += int(prev_day_total)

            balance += day_total

            report = (
                f"<b>Отчетность за {formatted_date}г</b>\n"
                f"Сумма продаж : {int(total_sales)}р\n"
                f"Покупка рекламы : {int(total_purchases)}р\n"
                f"Процент админа : {admin_percent}р\n"
                f"Контенщик : - \n"
                f"Карта : - {card_fee}р\n\n"
                f"<b>ИТОГ ДНЯ : {day_total}р</b>\n"
                f"<b>Баланс: {balance}р</b>"
            )

            await callback_query.message.answer(report)
        

# Обработчик кнопки "Вернуться в меню"
@dp.callback_query(lambda c: c.data == 'back_to_menu')
async def back_to_menu_handler(callback_query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    
    # Создаем инлайн-кнопки с нужным расположением
    builder = InlineKeyboardBuilder()
    
    # Добавляем кнопки "Продажа" и "Закупка" в один ряд
    builder.row(
        InlineKeyboardButton(text="Продажа", callback_data="sales"),
        InlineKeyboardButton(text="Закупка", callback_data="purchase")
    )
    
    # Добавляем кнопку "Отчетность" в отдельный ряд
    builder.row(
        InlineKeyboardButton(text="Отчетность", callback_data="report")
    )
    
    # Редактируем сообщение с календарем, возвращая меню
    await callback_query.message.edit_text(
        "Всю информацию по отчетности канала можно глянуть по кнопкам ниже👇",
        reply_markup=builder.as_markup()
    )
    await callback_query.answer()

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    import asyncio
    init_db()
    asyncio.run(main())