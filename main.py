import os
import sys
import json
import asyncio
import aiohttp
import telebot
import re
from datetime import datetime, timedelta
from telebot import apihelper
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# Подключаем инструмент для срезания окончаний слов, чтобы бот понимал любые падежи
try:
    from nltk.stem.snowball import SnowballStemmer
    stemmer = SnowballStemmer("russian")
except ImportError:
    print("Библиотека NLTK не установлена")
    sys.exit(1)

# Настройка для стабильной работы asyncio на Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# =====================================================================
# 1. КОНФИГУРАЦИЯ БОТА И ПРОКСИ
# =====================================================================
TOKEN = '8901416081:AAF8rAZEXXp5sSkK3u6ylZlczHEMV0hGxQY'
bot = telebot.TeleBot(TOKEN)

# Список прокси на случай, если Telegram заблокирован
PROXY_POOL = [
    "http://54.38.139.182:3128", "http://132.243.234.171:9443", "http://144.31.73.173:3128",
    "http://144.178.199.118:8443", "http://176.12.65.24:443", "http://45.153.4.154:3128",
    "http://185.181.209.34:8080", "http://51.178.253.98:80", "http://49.51.228.35:81"
]

# =====================================================================
# 2. NLP-МАТРИЦА КЛЮЧЕВЫХ СЛОВ (5 НАДЕЖНЫХ СЦЕНАРИЕВ)
# =====================================================================
# Словари с основами слов для определения темы сообщения пользователя
SCENARIO_KEYWORDS = {
    'greeting': ['привет', 'здравств', 'добр'],
    'location_contacts': ['адрес', 'где', 'доеха', 'телеф', 'контак', 'находи', 'располож', 'найт'],
    'schedule': ['режим', 'график', 'врем', 'час', 'работ'],
    'rent_spaces': ['аренд', 'снят', 'офис', 'цена', 'стоимост', 'помещен', 'свобод', 'склад', 'торгов'],
    'feedback_request': ['посмотрет', 'просмотр', 'связа', 'свяж', 'перезвон', 'заявк', 'менеджер']
}


def analyze_text(text):
    """ Очищает текст от знаков препинания, приводит к корням и определяет тему запроса """
    # Выделяем из текста только буквы и цифры, переводя их в нижний регистр
    words = re.findall(r'[а-яА-ЯёЁa-zA-Z0-9]+', text.lower())
    # Приводим каждое слово к его базовой основе (стемминг)
    stems = [stemmer.stem(word) for word in words]

    matched_scenarios = {}
    # Считаем количество совпадений ключевых слов для каждого сценария
    for scenario, keywords in SCENARIO_KEYWORDS.items():
        matches = sum(1 for stem in stems for kw in keywords if kw in stem)
        if matches > 0:
            matched_scenarios[scenario] = matches

    # Возвращаем сценарий с наибольшим количеством совпадений
    if matched_scenarios:
        return max(matched_scenarios, key=matched_scenarios.get), stems
    return None, stems


# =====================================================================
# 3. ВСПОМОГАТЕЛЬНЫЕ КОМПОНЕНТЫ
# =====================================================================
def load_data():
    """ Чтение и загрузка базы данных из локального файла data.json """
    if not os.path.exists('data.json'):
        return None
    try:
        with open('data.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return None


def get_base_keyboard():
    """ Создание кнопок в интерфейсе бота """
    keyboard = InlineKeyboardMarkup()
    btn1 = InlineKeyboardButton(text="📞 Связаться с менеджером", callback_data="contact_manager")
    btn2 = InlineKeyboardButton(text="🏢 Свободные помещения", callback_data="show_all_spaces")
    keyboard.add(btn1, btn2)
    return keyboard


# =====================================================================
# 4. ОБРАБОТЧИКИ (ХЕНДЛЕРЫ) СООБЩЕНИЙ
# =====================================================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """ Выводит приветственное сообщение и краткую инструкцию по работе с ботом """
    welcome_text = (
        "👋 Здравствуйте! Вас приветствует бот-помощник компании «Черник-В».\n\n"
        "Я помогу вам подобрать коммерческую недвижимость в аренду и отвечу на базовые вопросы. "
        "Через меня вы можете:\n"
        "• Узнать актуальный график работы\n"
        "• Посмотреть полный список всех свободных помещений\n"
        "• Уточнить наш адрес и контактные данные\n"
        "• Оставить заявку на просмотр объекта, чтобы с вами связался менеджер\n\n"
        "Просто напишите ваш вопрос ниже или воспользуйтесь кнопками 👇"
    )
    bot.reply_to(message, welcome_text, parse_mode="Markdown", reply_markup=get_base_keyboard())


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """ Главный диспетчер: распределяет сообщения пользователя по сценариям на основе анализа текста """
    data = load_data()
    if not data:
        bot.reply_to(message, "⚠️ Ошибка: база данных `data.json` не найдена.")
        return

    # Анализируем входящий текст
    scenario, user_stems = analyze_text(message.text)
    company_info = data.get('company_info', {})

    # Сценарий 1: Обработка приветствия
    if scenario == 'greeting':
        send_welcome(message)
        return

    # Сценарий 2: Вывод адреса и контактных данных компании
    elif scenario == 'location_contacts':
        res = (f"🏢 *Наш адрес:* {company_info.get('address')}\n"
               f"📞 *Контакты:* {company_info.get('contacts')}")
        bot.reply_to(message, res, parse_mode="Markdown", reply_markup=get_base_keyboard())

    # Сценарий 3: Вывод режима работы организации
    elif scenario == 'schedule':
        res = f"🕒 *График работы ООО «ЧЕРНИК-В»*:{company_info.get('schedule')}"
        bot.reply_to(message, res, parse_mode="Markdown")

    # Сценарий 4: Запрос номера телефона для обратной связи (пошаговый сценарий)
    elif scenario == 'feedback_request':
        msg = bot.reply_to(message, "📝 Отлично! Введите ваш номер телефона, чтобы наш менеджер связался с вами:",
                           parse_mode="Markdown")
        # Передаем управление следующему шагу (ожидаем номер телефона от юзера)
        bot.register_next_step_handler(msg, process_phone_step)

    # Сценарий 5: Поиск недвижимости (выводит только свободные объекты из общей базы)
    elif scenario == 'rent_spaces':
        spaces = data.get('commercial_spaces', [])

        # Фильтруем объекты, оставляя строго со статусом "свободен"
        free_spaces = [s for s in spaces if s.get('status') == 'свободен']

        if not free_spaces:
            bot.reply_to(message, "📋 К сожалению, на текущий момент все помещения заняты.")
            return

        res = "📋 *Список всех доступных для аренды объектов:*\n\n"
        for idx, s in enumerate(free_spaces, 1):
            # Проверяем тип этажа (например, цоколь или мансарда), если указан в JSON
            f_type = f" ({s.get('floor_type')})" if s.get('floor_type') else ""
            res += (f"{idx}. *{s.get('type').capitalize()}* — {s.get('area')}\n"
                    f"   Этаж: {s.get('floor')}{f_type} | Цена: {s.get('price')}\n"
                    f"   Описание: {s.get('description')}\n\n")

        # Прикрепляем инлайн-кнопку для записи на просмотр под списком объектов
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="📅 Записаться на просмотр", callback_data="book_viewing"))
        bot.reply_to(message, res, parse_mode="Markdown", reply_markup=kb)

    # Заглушка, если бот не смог распознать тему сообщения
    else:
        fallback = (
            "🤖 Я не до конца понял суть вопроса.\n"
            "Через меня вы можете:\n"
            "• Узнать актуальный график работы\n"
            "• Посмотреть полный список всех свободных помещений\n"
            "• Уточнить наш адрес и контактные данные\n"
            "• Оставить заявку на просмотр объекта, чтобы с вами связался менеджер\n\n"
            "Просто напишите ваш вопрос ниже или воспользуйтесь кнопками 👇"
        )
        bot.reply_to(message, fallback, reply_markup=get_base_keyboard())


# =====================================================================
# 5. МЕХАНИЗМ ЗАПИСИ ДАННЫХ И КОЛБЭКИ
# =====================================================================
def process_phone_step(message):
    """ Проверяет корректность ввода телефона, обрабатывает отмену и фиксирует заявку """
    user_text = message.text.strip()

    # Инлайн-кнопка для отмены ввода номера телефона
    cancel_kb = InlineKeyboardMarkup()
    cancel_kb.add(InlineKeyboardButton(text="❌ Отменить ввод", callback_data="cancel_phone_input"))

    # Проверка, если пользователь вручную написал команду отмены
    if user_text.lower() in ['назад', 'отмена', '/start', '/help']:
        bot.reply_to(message, "Вы вернулись в главное меню. Ввод телефона отменен.", reply_markup=get_base_keyboard())
        return

    # Валидация номера телефона через регулярное выражение (+7 и 10 цифр)
    phone_pattern = r'^\+7\d{10}$'
    if not re.match(phone_pattern, user_text):
        # Если формат неверный, возвращаем на этот же шаг ввода
        msg = bot.reply_to(
            message,
            "⚠️ *Ошибка в формате номера!*\n\n"
            "Номер должен начинаться с `+7` и содержать ровно 11 цифр.\n"
            "Пример корректного ввода: `+79325907864`\n\n"
            "Пожалуйста, попробуйте ввести номер еще раз или нажмите кнопку ниже:",
            parse_mode="Markdown",
            reply_markup=cancel_kb
        )
        bot.register_next_step_handler(msg, process_phone_step)
        return

    # Получаем текущее время и пересчитываем в часовой пояс пользователя (UTC+5)
    utc_time = datetime.utcnow()
    local_time = utc_time + timedelta(hours=5)
    time_str = local_time.strftime("%d.%m.%Y в %H:%M (UTC+5)")

    # Отправляем успешное получение контакта в консоль
    print(f"🔔 [Новый клиент] Пользователь {message.from_user.first_name} оставил телефон: {user_text} в {time_str}")

    confirm = (
        f"✅ Заявка принята в *{time_str}*!\n"
        f"Номер `{user_text}` успешно проверен. Наш специалист коммерческого отдела свяжется с вами."
    )
    bot.reply_to(message, confirm, parse_mode="Markdown")


@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    """ Обработка нажатий на инлайн-кнопки (колбэки) """
    # Нажата кнопка прямой связи с менеджером
    if call.data == "contact_manager":
        bot.send_message(call.message.chat.id, "📞 Прямой номер коммерческого отдела: +79325907864")

    # Нажата кнопка просмотра всех помещений (имитируем текстовый запрос «аренда»)
    elif call.data == "show_all_spaces":
        call.message.text = "аренда"
        handle_all_messages(call.message)

    # Нажата кнопка записи на просмотр — запрашиваем телефон и добавляем инлайн-кнопку отмены
    elif call.data == "book_viewing":
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_phone_input"))
        msg = bot.send_message(call.message.chat.id, "📝 Напишите ваш телефон для связи в формате +7XXXXXXXXXX:",
                               reply_markup=kb)
        bot.register_next_step_handler(msg, process_phone_step)

    # Нажата инлайн-кнопка «Отменить ввод»
    elif call.data == "cancel_phone_input":
        # Сбрасываем ожидание ввода следующего шага для данного чата
        bot.clear_step_handler_by_chat_id(chat_id=call.message.chat.id)
        bot.send_message(call.message.chat.id, "Ввод отменен. Чем я могу еще помочь?", reply_markup=get_base_keyboard())

    # Уведомляем API Telegram об успешной обработке нажатия кнопки
    bot.answer_callback_query(call.id)


# =====================================================================
# 6. АСИНХРОННЫЙ ПОДБОР ПРОКСИ НА СТАРТЕ
# =====================================================================
async def check_single_proxy(session, proxy_url, url, success_event, result_container):
    """ Проверяет доступность одного конкретного прокси-сервера через запрос getMe """
    try:
        timeout = aiohttp.ClientTimeout(total=4)  # Лимит ожидания ответа — 4 секунды
        async with session.get(url, proxy=proxy_url, timeout=timeout, ssl=False) as response:
            if response.status == 200 and not success_event.is_set():
                success_event.set()  # Сигнал остальным задачам, что первый рабочий прокси найден
                result_container.append(proxy_url)
    except:
        pass


async def get_best_proxy():
    """ Запускает параллельный опрос всего пула прокси для поиска самого быстрого """
    url = f'https://api.telegram.org/bot{TOKEN}/getMe'
    success_event = asyncio.Event()
    result_container = []
    async with aiohttp.ClientSession() as session:
        # Формируем список асинхронных задач для каждого прокси из пула
        tasks = [check_single_proxy(session, p, url, success_event, result_container) for p in PROXY_POOL]
        # Запускаем одновременное выполнение всех проверок
        await asyncio.gather(*tasks)
    return result_container[0] if result_container else None


if __name__ == '__main__':
    print("🔄 Проверка прокси-серверов...")
    # Запуск асинхронного подбора прокси
    fastest_proxy = asyncio.run(get_best_proxy())

    if fastest_proxy:
        print(f"🟢 Подключаем быстрый прокси: {fastest_proxy}")
        # Записываем рабочий прокси в общие настройки библиотеки telebot
        apihelper.proxy = {'http': fastest_proxy, 'https': fastest_proxy}
    else:
        print("⚠️ Прокси не ответили, запускаемся напрямую.")

    try:
        bot.remove_webhook()
        print("🚀 Бот ООО «ЧЕРНИК-В» успешно слушает запросы!")
        # Запуск бесконечного цикла получения обновлений от серверов Telegram
        bot.infinity_polling(timeout=20, long_polling_timeout=10)
    except Exception as e:
        print(f"🔴 Критическая ошибка: {e}")
