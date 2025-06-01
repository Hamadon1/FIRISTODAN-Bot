import telebot
from telebot import types
import sqlite3
import schedule
import time
import threading
from datetime import datetime, timedelta
import os

# Танзимоти бот
BOT_TOKEN = "7268398403:AAGsmC5e19hOexTV8nSaKUwbaq5wbjYKUg8"  # Токени ботатонро дар ин ҷо гузоред
ADMIN_ID = 6862331593  # ID админро дар ин ҷо гузоред
CHANNEL_USERNAME = "@kinohoijazob"  # Номи канал (бо @)
DB_NAME = 'movies_v2.db' # Номи файли базаи додаҳо

# Ҳолатҳои корбар барои идоракунии ҷараён
USER_STATE_NONE = 0
USER_STATE_WAITING_MOVIE_FILE = 1
USER_STATE_WAITING_MOVIE_TITLE = 2
USER_STATE_WAITING_MOVIE_DESCRIPTION = 3
USER_STATE_WAITING_DELETE_MOVIE_ID = 4
USER_STATE_WAITING_PUBLISH_NOW_MOVIE_ID = 5

user_data = {} # Барои нигоҳ доштани маълумоти муваққатии корбар ҳангоми иловаи филм

bot = telebot.TeleBot(BOT_TOKEN)

# --- Функсияҳои базаи додаҳо ---
def init_database():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS movies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            file_id TEXT NOT NULL,
            file_type TEXT NOT NULL,
            is_published BOOLEAN DEFAULT FALSE,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS publish_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            movie_id INTEGER UNIQUE,
            publish_date DATE NOT NULL,
            is_published BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (movie_id) REFERENCES movies (id) ON DELETE CASCADE
        )
    ''')
    conn.commit()
    conn.close()

def save_movie_to_db(title, description, file_id, file_type):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO movies (title, description, file_id, file_type)
        VALUES (?, ?, ?, ?)
    ''', (title, description, file_id, file_type))
    movie_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return movie_id

def schedule_movie(movie_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Санаи охирини нашрро ёфтан
    cursor.execute("SELECT MAX(publish_date) FROM publish_schedule")
    last_publish_date_str = cursor.fetchone()[0]
    
    next_publish_date = datetime.now().date() + timedelta(days=1) # Агар ҷадвал холӣ бошад
    if last_publish_date_str:
        last_publish_date = datetime.strptime(last_publish_date_str, '%Y-%m-%d').date()
        if last_publish_date >= next_publish_date: # Агар санаи охирин аз фардо дертар бошад
             next_publish_date = last_publish_date + timedelta(days=1)
        # Агар санаи охирин дар гузашта бошад, аз фардо сар мекунем
        elif last_publish_date < datetime.now().date():
             next_publish_date = datetime.now().date() + timedelta(days=1)


    cursor.execute('''
        INSERT INTO publish_schedule (movie_id, publish_date)
        VALUES (?, ?)
    ''', (movie_id, next_publish_date.strftime('%Y-%m-%d')))
    conn.commit()
    conn.close()
    return next_publish_date

def get_movie_by_id(movie_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, description, file_id, file_type FROM movies WHERE id = ?", (movie_id,))
    movie = cursor.fetchone()
    conn.close()
    return movie

def delete_movie_from_db(movie_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # ON DELETE CASCADE бояд филмро аз publish_schedule низ тоза кунад
    cursor.execute("DELETE FROM movies WHERE id = ?", (movie_id,))
    deleted_rows = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted_rows > 0

def get_pending_movies():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT m.id, m.title, ps.publish_date
        FROM movies m
        JOIN publish_schedule ps ON m.id = ps.movie_id
        WHERE ps.is_published = FALSE
        ORDER BY ps.publish_date ASC
    ''')
    movies = cursor.fetchall()
    conn.close()
    return movies

# --- Функсияҳои ёрирасон ---
def is_admin(user_id):
    return user_id == ADMIN_ID

def set_user_state(user_id, state):
    user_data.setdefault(user_id, {})['state'] = state

def get_user_state(user_id):
    return user_data.get(user_id, {}).get('state', USER_STATE_NONE)

def clear_user_data(user_id):
    if user_id in user_data:
        del user_data[user_id]

def create_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_add = types.KeyboardButton("➕ Иловаи филм")
    btn_pending = types.KeyboardButton("🗓 Рӯйхати интизорӣ")
    btn_publish_now = types.KeyboardButton("🚀 Нашри фаврӣ")
    btn_delete = types.KeyboardButton("🗑️ Тоза кардани филм")
    btn_status = types.KeyboardButton("📊 Ҳолати бот")
    btn_help = types.KeyboardButton("❓ Кӯмак")
    markup.add(btn_add, btn_pending, btn_publish_now, btn_delete, btn_status, btn_help)
    return markup

def create_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(types.KeyboardButton("↪️ Бекор кардан"))
    return markup

# --- Функсияҳои нашр ---
def publish_movie_to_channel(movie_id_to_publish=None, scheduled_publish=True):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    movie_to_post = None
    schedule_id_to_update = None

    if movie_id_to_publish: # Барои нашри фаврӣ
        cursor.execute('''
            SELECT m.id, m.title, m.description, m.file_id, m.file_type, ps.id 
            FROM movies m
            LEFT JOIN publish_schedule ps ON m.id = ps.movie_id
            WHERE m.id = ? AND m.is_published = FALSE
        ''', (movie_id_to_publish,))
        result = cursor.fetchone()
        if result:
            movie_id, title, description, file_id, file_type, schedule_id = result
            movie_to_post = (movie_id, title, description, file_id, file_type)
            schedule_id_to_update = schedule_id # Метавонад None бошад, агар филм ҳанӯз ба ҷадвал илова нашуда бошад
    
    elif scheduled_publish: # Барои нашри муқаррарӣ аз рӯи ҷадвал
        today = datetime.now().date().strftime('%Y-%m-%d')
        cursor.execute('''
            SELECT ps.id, m.title, m.description, m.file_id, m.file_type, ps.movie_id
            FROM publish_schedule ps
            JOIN movies m ON ps.movie_id = m.id
            WHERE ps.publish_date = ? AND ps.is_published = FALSE AND m.is_published = FALSE
            ORDER BY ps.id ASC LIMIT 1 
        ''', (today,)) # Танҳо якто дар як рӯз
        result = cursor.fetchone()
        if result:
            schedule_id, title, description, file_id, file_type, movie_id = result
            movie_to_post = (movie_id, title, description, file_id, file_type)
            schedule_id_to_update = schedule_id

    if movie_to_post:
        movie_id, title, description, file_id, file_type = movie_to_post
        caption = f"🎬 **{title}**\n\n{description if description else ''}\n\nКанали мо: {CHANNEL_USERNAME}"
        
        try:
            if file_type == 'video':
                bot.send_video(CHANNEL_USERNAME, file_id, caption=caption, parse_mode="Markdown")
            elif file_type == 'document':
                bot.send_document(CHANNEL_USERNAME, file_id, caption=caption, parse_mode="Markdown")
            
            # Нишондодани ҳамчун нашршуда
            cursor.execute("UPDATE movies SET is_published = TRUE WHERE id = ?", (movie_id,))
            if schedule_id_to_update: # Агар дар ҷадвал бошад
                 cursor.execute("UPDATE publish_schedule SET is_published = TRUE WHERE id = ?", (schedule_id_to_update,))
            elif not scheduled_publish and movie_id_to_publish: # Агар нашри фаврӣ ва дар ҷадвал набошад, онро ҳамчун нашршуда илова мекунем
                cursor.execute('''
                    INSERT OR IGNORE INTO publish_schedule (movie_id, publish_date, is_published)
                    VALUES (?, ?, TRUE)
                ''', (movie_id, datetime.now().date().strftime('%Y-%m-%d')))

            conn.commit()
            bot.send_message(ADMIN_ID, f"✅ Филми '{title}' (ID: {movie_id}) бомуваффақият дар канал нашр шуд!")

            if scheduled_publish: # Танҳо барои нашри муқаррарӣ
                cursor.execute('SELECT COUNT(*) FROM publish_schedule WHERE is_published = FALSE')
                remaining = cursor.fetchone()[0]
                if remaining == 0:
                    bot.send_message(ADMIN_ID, "🎉 Ҳамаи филмҳои ба нақша гирифташуда нашр шуданд!")
            
        except Exception as e:
            bot.send_message(ADMIN_ID, f"❌ Хатогӣ ҳангоми нашри филми '{title}' (ID: {movie_id}): {str(e)}")
    
    conn.close()

# --- Ҳендлерҳои Telegram ---
@bot.message_handler(commands=['start'])
def start_command(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Шумо иҷозати истифодаи ин ботро надоред.")
        return
    
    clear_user_data(message.from_user.id)
    set_user_state(message.from_user.id, USER_STATE_NONE)
    bot.send_message(message.chat.id, 
                     "👋 Салом, Администратор!\n\n"
                     "Интихоб кунед, ки чӣ кор кардан мехоҳед:",
                     reply_markup=create_main_menu())

@bot.message_handler(commands=['help'])
def help_command(message):
    if not is_admin(message.from_user.id): return
    help_text = (
        "📖 **Дастурамали кӯтоҳ:**\n\n"
        "🔹 **➕ Иловаи филм:** Барои илова кардани филми нав ба база ва ба нақша гирифтани он.\n"
        "🔹 **🗓 Рӯйхати интизорӣ:** Намоиши филмҳое, ки барои нашр дар навбатанд.\n"
        "🔹 **🚀 Нашри фаврӣ:** Интихоб ва нашри фаврии як филм.\n"
        "🔹 **🗑️ Тоза кардани филм:** Тоза кардани филм аз база ва ҷадвали нашр.\n"
        "🔹 **📊 Ҳолати бот:** Маълумот дар бораи филмҳои дар база буда.\n"
        "🔹 **↪️ Бекор кардан:** Барои бекор кардани амалиёти ҷорӣ.\n"
        "🔹 **❓ Кӯмак:** Намоиши ин дастурамал.\n\n"
        f"🕒 Филмҳо ҳар рӯз соати 12:00 ба таври худкор дар канали {CHANNEL_USERNAME} нашр мешаванд."
    )
    bot.send_message(message.chat.id, help_text, parse_mode="Markdown", reply_markup=create_main_menu())

# Ҳендлери умумӣ барои матн ва тугмаҳо
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "⛔ Шумо иҷозати истифодаи ин ботро надоред.")
        return

    user_id = message.from_user.id
    current_state = get_user_state(user_id)
    
    if message.text == "↪️ Бекор кардан":
        clear_user_data(user_id)
        set_user_state(user_id, USER_STATE_NONE)
        bot.send_message(user_id, "🔄 Амалиёт бекор карда шуд.", reply_markup=create_main_menu())
        return

    # --- Амалиётҳои асосӣ ---
    if message.text == "➕ Иловаи филм":
        set_user_state(user_id, USER_STATE_WAITING_MOVIE_FILE)
        user_data[user_id]['current_movie'] = {}
        bot.send_message(user_id, "🎬 Файли филмро (видео ё ҳуҷҷат) ирсол кунед:", reply_markup=create_cancel_keyboard())
    
    elif message.text == "🗓 Рӯйхати интизорӣ":
        pending_movies = get_pending_movies()
        if not pending_movies:
            bot.send_message(user_id, "📭 Ҳоло филмҳои дар навбатбуда мавҷуд нестанд.", reply_markup=create_main_menu())
            return
        
        response = "🗓 **Филмҳои дар навбати нашр:**\n\n"
        for i, (movie_id, title, publish_date) in enumerate(pending_movies):
            try:
                # Табдили сана ба формати хоно
                date_obj = datetime.strptime(publish_date, '%Y-%m-%d')
                formatted_date = date_obj.strftime('%d %B %Y')
            except ValueError:
                formatted_date = publish_date # Агар формат дигар бошад
            response += f"{i+1}. (ID: `{movie_id}`) **{title}** - {formatted_date}\n"
        
        # Агар рӯйхат хеле дароз бошад, онро тақсим кардан лозим меояд.
        # Ҳоло, агар аз 4096 аломат зиёд бошад, огоҳӣ медиҳем.
        if len(response) > 4096:
            bot.send_message(user_id, response[:4090] + "\n...", parse_mode="Markdown", reply_markup=create_main_menu())
            bot.send_message(user_id, "⚠️ Рӯйхат хеле дароз аст, танҳо қисме нишон дода шуд.", reply_markup=create_main_menu())
        else:
            bot.send_message(user_id, response, parse_mode="Markdown", reply_markup=create_main_menu())

    elif message.text == "🚀 Нашри фаврӣ":
        set_user_state(user_id, USER_STATE_WAITING_PUBLISH_NOW_MOVIE_ID)
        bot.send_message(user_id, "🆔 ID-и филмеро, ки мехоҳед ҳозир нашр кунед, ворид намоед (аз 'Рӯйхати интизорӣ' ёбед):", reply_markup=create_cancel_keyboard())

    elif message.text == "🗑️ Тоза кардани филм":
        set_user_state(user_id, USER_STATE_WAITING_DELETE_MOVIE_ID)
        bot.send_message(user_id, "🆔 ID-и филмеро, ки мехоҳед тоза кунед, ворид намоед (аз 'Рӯйхати интизорӣ' ёбед):", reply_markup=create_cancel_keyboard())
    
    elif message.text == "📊 Ҳолати бот":
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM movies')
        total_movies = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM movies WHERE is_published = TRUE')
        published_movies = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM publish_schedule WHERE is_published = FALSE')
        scheduled_movies = cursor.fetchone()[0]
        conn.close()
        status_text = (f"📊 **Ҳолати бот:**\n\n"
                       f"📹 Филмҳои умумӣ дар база: {total_movies}\n"
                       f"✅ Филмҳои нашршуда: {published_movies}\n"
                       f"⏳ Филмҳои дар навбати нашр: {scheduled_movies}\n")
        bot.send_message(user_id, status_text, parse_mode="Markdown", reply_markup=create_main_menu())

    elif message.text == "❓ Кӯмак":
        help_command(message)
        
    # --- Идоракунии ҳолатҳо ---
    elif current_state == USER_STATE_WAITING_MOVIE_TITLE:
        title = message.text.strip()
        if not title:
            bot.send_message(user_id, "⚠️ Номи филм наметавонад холӣ бошад. Лутфан дубора ворид кунед:", reply_markup=create_cancel_keyboard())
            return
        user_data[user_id]['current_movie']['title'] = title
        set_user_state(user_id, USER_STATE_WAITING_MOVIE_DESCRIPTION)
        bot.send_message(user_id, "📝 Тавсифи мухтасари филмро ирсол кунед (ё '-' барои тавсифи холӣ):", reply_markup=create_cancel_keyboard())

    elif current_state == USER_STATE_WAITING_MOVIE_DESCRIPTION:
        description = message.text.strip()
        if description == '-':
            description = ""
        
        movie_data = user_data[user_id]['current_movie']
        movie_id = save_movie_to_db(movie_data['title'], description, movie_data['file_id'], movie_data['file_type'])
        
        if movie_id:
            publish_date = schedule_movie(movie_id)
            bot.send_message(user_id, 
                             f"✅ Филми '{movie_data['title']}' бомуваффақият сабт шуд (ID: {movie_id}).\n"
                             f"📅 Барои нашр дар санаи {publish_date.strftime('%d %B %Y')} ба нақша гирифта шуд.", 
                             reply_markup=create_main_menu())
        else:
            bot.send_message(user_id, "❌ Хатогӣ ҳангоми сабти филм. Лутфан дубора кӯшиш кунед.", reply_markup=create_main_menu())
        
        clear_user_data(user_id)
        set_user_state(user_id, USER_STATE_NONE)

    elif current_state == USER_STATE_WAITING_DELETE_MOVIE_ID:
        try:
            movie_id_to_delete = int(message.text.strip())
            movie = get_movie_by_id(movie_id_to_delete)
            if movie:
                if delete_movie_from_db(movie_id_to_delete):
                    bot.send_message(user_id, f"🗑️ Филми '{movie[1]}' (ID: {movie_id_to_delete}) бомуваффақият тоза карда шуд.", reply_markup=create_main_menu())
                else:
                    bot.send_message(user_id, f"⚠️ Хатогӣ ҳангоми тоза кардани филм (ID: {movie_id_to_delete}).", reply_markup=create_main_menu())
            else:
                bot.send_message(user_id, f"🚫 Филм бо ID: {movie_id_to_delete} ёфт нашуд.", reply_markup=create_main_menu())
        except ValueError:
            bot.send_message(user_id, "⚠️ ID-и филм бояд рақам бошад. Лутфан дубора ворид кунед:", reply_markup=create_cancel_keyboard())
            return # Дар ҳамин ҳолат мемонем
        
        clear_user_data(user_id) # Барои ин амал user_data истифода намешавад, аммо барои унификатсия
        set_user_state(user_id, USER_STATE_NONE)

    elif current_state == USER_STATE_WAITING_PUBLISH_NOW_MOVIE_ID:
        try:
            movie_id_to_publish = int(message.text.strip())
            movie = get_movie_by_id(movie_id_to_publish)
            if movie:
                if movie[0] in [m[0] for m in get_pending_movies()]: # Агар дар рӯйхати интизорӣ бошад
                     bot.send_message(user_id, f"⏳ Омодагӣ ба нашри фаврии филми '{movie[1]}' (ID: {movie_id_to_publish})...", reply_markup=create_main_menu())
                     publish_movie_to_channel(movie_id_to_publish=movie_id_to_publish, scheduled_publish=False)
                else: # Агар аллакай нашр шудааст ё дар ҷадвал нест, аммо дар база ҳаст
                    conn = sqlite3.connect(DB_NAME)
                    cursor = conn.cursor()
                    cursor.execute("SELECT is_published FROM movies WHERE id = ?", (movie_id_to_publish,))
                    is_already_published = cursor.fetchone()
                    conn.close()
                    if is_already_published and is_already_published[0]:
                         bot.send_message(user_id, f"ℹ️ Филми '{movie[1]}' (ID: {movie_id_to_publish}) аллакай нашр шудааст.", reply_markup=create_main_menu())
                    else: # Дар база ҳаст, аммо дар ҷадвал нест ва нашр нашудааст (ҳолати нодир)
                        bot.send_message(user_id, f"⏳ Омодагӣ ба нашри фаврии филми '{movie[1]}' (ID: {movie_id_to_publish})...", reply_markup=create_main_menu())
                        publish_movie_to_channel(movie_id_to_publish=movie_id_to_publish, scheduled_publish=False)

            else:
                bot.send_message(user_id, f"🚫 Филм бо ID: {movie_id_to_publish} ёфт нашуд.", reply_markup=create_main_menu())
        except ValueError:
            bot.send_message(user_id, "⚠️ ID-и филм бояд рақам бошад. Лутфан дубора ворид кунед:", reply_markup=create_cancel_keyboard())
            return
        
        clear_user_data(user_id)
        set_user_state(user_id, USER_STATE_NONE)
        
    # Агар ягон тугмаи асосӣ пахш нашуда бошад ва ҳолати муайян набошад
    elif current_state == USER_STATE_NONE and message.text not in ["➕ Иловаи филм", "🗓 Рӯйхати интизорӣ", "🚀 Нашри фаврӣ", "🗑️ Тоза кардани филм", "📊 Ҳолати бот", "❓ Кӯмак"]:
        bot.send_message(user_id, "🤔 Фармони номаълум. Лутфан аз тугмаҳои меню истифода баред ё /help -ро пахш кунед.", reply_markup=create_main_menu())


@bot.message_handler(content_types=['video', 'document'])
def handle_media_files(message):
    if not is_admin(message.from_user.id): return
    user_id = message.from_user.id

    if get_user_state(user_id) == USER_STATE_WAITING_MOVIE_FILE:
        if message.content_type == 'video':
            file_id = message.video.file_id
            file_type = 'video'
        elif message.content_type == 'document':
            file_id = message.document.file_id
            file_type = 'document'
        else: # Набояд рӯй диҳад, зеро content_types филтр мекунад
            bot.send_message(user_id, "⚠️ Лутфан файли видео ё ҳуҷҷатро ирсол кунед.", reply_markup=create_cancel_keyboard())
            return

        user_data[user_id].setdefault('current_movie', {})['file_id'] = file_id
        user_data[user_id]['current_movie']['file_type'] = file_type
        
        set_user_state(user_id, USER_STATE_WAITING_MOVIE_TITLE)
        bot.send_message(user_id, "✅ Файл қабул шуд!\n\n🖋️ Акнун номи филмро ирсол кунед:", reply_markup=create_cancel_keyboard())
    else:
        # Агар корбар файлро дар ҳолати нодуруст фиристад
        bot.send_message(user_id, "⚠️ Ҳоло ман ин файлро интизор набудам. Агар филм илова карда истода бошед, лутфан аз аввал бо пахши '➕ Иловаи филм' оғоз кунед.", reply_markup=create_main_menu())


# --- Функсияи заминавӣ барои банақшагирӣ ---
def run_scheduler():
    schedule.every().day.at("12:00").do(publish_movie_to_channel, scheduled_publish=True) 
    # Шумо метавонед вақти дигарро муқаррар кунед, масалан: schedule.every().monday.at("10:30").do(job)
    
    bot.send_message(ADMIN_ID, f"⏰ Банақшагирандаи нашр фаъол шуд. Филмҳо ҳар рӯз соати 12:00 нашр мешаванд.")
    while True:
        schedule.run_pending()
        time.sleep(60) # Ҳар дақиқа санҷиш

# --- Оғози бот ---
if __name__ == "__main__":
    print("🤖 Бот бо функсияҳои ҷазобтар оғоз шуд...")
    bot.infinity_polling()
