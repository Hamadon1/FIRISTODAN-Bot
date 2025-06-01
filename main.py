#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Боти Telegram барои интишори ҳаррӯзаи филмҳо дар канал
Эҷодкунанда: Claude
Таърих: 2025
"""

import telebot
import json
import logging
import schedule
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ==================== ТАНЗИМОТ (КОНФИГУРАТСИЯ) ====================
BOT_TOKEN = "7007180291:AAGA9O0UCbs6gB2SAme4h2FCOKD9GovagP0"  # Token-и ботатонро дар ин ҷо ворид кунед
ADMIN_USER_ID = 6862331593  # ID-и Telegram-и администратор (танҳо рақам)
CHANNEL_ID = "@kinohoijazob"  # ID-и канал ё username (масалан @mychannel ё -100xxxxxxxxxx)
DATA_FILE = "bot_data.json"  # Номи файли JSON барои захираи маълумот
MAX_QUEUE_SIZE = 10  # Шумораи максималии филмҳо дар навбат
DEFAULT_POST_TIME = "10:00"  # Вақти пешфарз барои интишор

# ==================== ТАНЗИМИ LOGGING ====================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ==================== ИНИТСИАЛИЗАТСИЯИ БОТ ====================
bot = telebot.TeleBot(BOT_TOKEN)

# ==================== СТРУКТУРАИ МАЪЛУМОТ ====================
class BotData:
    def __init__(self):
        self.movie_queue: List[Dict] = []  # Навбати филмҳо
        self.post_time: str = DEFAULT_POST_TIME  # Вақти интишор
        self.last_post_date: str = ""  # Таърихи охирин интишор
    
    def to_dict(self) -> Dict:
        """Табдил додани маълумот ба dict барои JSON"""
        return {
            'movie_queue': self.movie_queue,
            'post_time': self.post_time,
            'last_post_date': self.last_post_date
        }
    
    def from_dict(self, data: Dict):
        """Бор кардани маълумот аз dict"""
        self.movie_queue = data.get('movie_queue', [])
        self.post_time = data.get('post_time', DEFAULT_POST_TIME)
        self.last_post_date = data.get('last_post_date', "")

# ==================== ГЛОБАЛИИ МАЪЛУМОТ ====================
bot_data = BotData()

# ==================== ФУНКСИЯҲОИ КУМАКӢ ====================
def save_data():
    """Захираи маълумот ба файли JSON"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(bot_data.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("Маълумот бомуваффақият захира шуд")
    except Exception as e:
        logger.error(f"Хатогӣ ҳангоми захираи маълумот: {e}")

def load_data():
    """Бор кардани маълумот аз файли JSON"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        bot_data.from_dict(data)
        logger.info("Маълумот бомуваффақият бор карда шуд")
    except FileNotFoundError:
        logger.info("Файли маълумот ёфт нашуд, маълумоти нав эҷод мешавад")
        save_data()
    except Exception as e:
        logger.error(f"Хатогӣ ҳангоми бор кардани маълумот: {e}")

def is_admin(user_id: int) -> bool:
    """Санҷиши ҳуқуқи администратор"""
    return user_id == ADMIN_USER_ID

def get_next_post_time() -> str:
    """Гирифтани вақти интишори навбатӣ"""
    try:
        now = datetime.now()
        post_hour, post_minute = map(int, bot_data.post_time.split(':'))
        
        # Муайян кардани таърихи интишори навбатӣ
        next_post = now.replace(hour=post_hour, minute=post_minute, second=0, microsecond=0)
        
        # Агар вақт гузашта бошад, барои фардо муайян мекунем
        if next_post <= now:
            next_post += timedelta(days=1)
        
        return next_post.strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        logger.error(f"Хатогӣ ҳангоми ҳисоби вақти навбатӣ: {e}")
        return "Номуайян"

def post_movie():
    """Интишори филми навбатӣ дар канал"""
    try:
        if not bot_data.movie_queue:
            logger.info("Навбати филмҳо холӣ аст")
            return
        
        # Гирифтани филми аввал аз навбат
        movie = bot_data.movie_queue.pop(0)
        
        # Интишори филм дар канал
        bot.send_video(
            chat_id=CHANNEL_ID,
            video=movie['file_id'],
            caption=movie.get('caption', ''),
            parse_mode='HTML'
        )
        
        # Навсозии таърихи охирин интишор
        bot_data.last_post_date = datetime.now().strftime("%Y-%m-%d")
        
        # Захираи маълумот
        save_data()
        
        logger.info(f"Филм бомуваффақият интишор шуд: {movie.get('caption', 'Бе сарлавҳа')}")
        
        # Огоҳ кардани администратор
        try:
            bot.send_message(
                ADMIN_USER_ID,
                f"✅ Филм бомуваффақият интишор шуд!\n\n"
                f"📝 Сарлавҳа: {movie.get('caption', 'Бе сарлавҳа')}\n"
                f"⏰ Вақт: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"📊 Филмҳои боқимонда дар навбат: {len(bot_data.movie_queue)}"
            )
        except Exception as e:
            logger.error(f"Хатогӣ ҳангоми огоҳкунии администратор: {e}")
            
    except Exception as e:
        logger.error(f"Хатогӣ ҳангоми интишори филм: {e}")
        try:
            bot.send_message(
                ADMIN_USER_ID,
                f"❌ Хатогӣ ҳангоми интишори филм: {str(e)}"
            )
        except:
            pass

def setup_scheduler():
    """Танзими ҷадвали интишор"""
    schedule.clear()  # Пок кардани ҷадвали қаблӣ
    schedule.every().day.at(bot_data.post_time).do(post_movie)
    logger.info(f"Ҷадвали интишор танзим шуд барои соати {bot_data.post_time}")

def scheduler_thread():
    """Thread барои кори ҷадвал"""
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)  # Санҷиш ҳар дақиқа
        except Exception as e:
            logger.error(f"Хатогӣ дар scheduler thread: {e}")
            time.sleep(60)

# ==================== ФАРМОНҲОИ БОТ ====================

@bot.message_handler(commands=['start', 'help'])
def handle_start_help(message):
    """Коркарди фармони /start ва /help"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Шумо ҳуқуқи истифодаи ин ботро надоред.")
        return
    
    help_text = """
🎬 **Боти интишори филмҳо**

**Фармонҳои дастрас:**

🎯 **Асосӣ:**
• Барои илова кардани филм - танҳо файли видеоро фиристед
• `/status` - Вазъи кунунӣ
• `/listmovies` - Рӯйхати филмҳо дар навбат

⚙️ **Идоракунӣ:**
• `/remove <рақам>` - Нест кардани филм аз навбат
• `/settime HH:MM` - Тағири вақти интишор
• `/forcepost` - Интишори форӣ

❓ `/help` - Ин паём

**Маълумот:**
• Ҳадди аксари навбат: {max_queue} филм
• Вақти кунунии интишор: {post_time}
• Филмҳо ҳар рӯз ба таври худкор интишор мешаванд
    """.format(
        max_queue=MAX_QUEUE_SIZE,
        post_time=bot_data.post_time
    )
    
    bot.reply_to(message, help_text, parse_mode='Markdown')
    logger.info(f"Администратор фармони help-ро дархост кард")

@bot.message_handler(commands=['status'])
def handle_status(message):
    """Коркарди фармони /status"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Шумо ҳуқуқи истифодаи ин ботро надоред.")
        return
    
    queue_count = len(bot_data.movie_queue)
    next_movie = bot_data.movie_queue[0]['caption'] if bot_data.movie_queue else "Ҳеҷ филм дар навбат нест"
    next_post_time = get_next_post_time()
    
    status_text = f"""
📊 **Вазъи кунунӣ:**

🎬 Филмҳо дар навбат: {queue_count}/{MAX_QUEUE_SIZE}
⏰ Вақти интишор: {bot_data.post_time}
🕐 Интишори навбатӣ: {next_post_time}
🎭 Филми навбатӣ: {next_movie}
📅 Охирин интишор: {bot_data.last_post_date if bot_data.last_post_date else 'Ҳанӯз интишор нашудааст'}
    """
    
    bot.reply_to(message, status_text, parse_mode='Markdown')
    logger.info("Администратор маълумоти status-ро дархост кард")

@bot.message_handler(commands=['listmovies'])
def handle_list_movies(message):
    """Коркарди фармони /listmovies"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Шумо ҳуқуқи истифодаи ин ботро надоред.")
        return
    
    if not bot_data.movie_queue:
        bot.reply_to(message, "📝 Навбати филмҳо холӣ аст.")
        return
    
    movies_text = "📝 **Рӯйхати филмҳо дар навбат:**\n\n"
    for i, movie in enumerate(bot_data.movie_queue, 1):
        caption = movie.get('caption', 'Бе сарлавҳа')
        movies_text += f"{i}. {caption}\n"
    
    bot.reply_to(message, movies_text, parse_mode='Markdown')
    logger.info("Администратор рӯйхати филмҳоро дархост кард")

@bot.message_handler(commands=['remove'])
def handle_remove_movie(message):
    """Коркарди фармони /remove"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Шумо ҳуқуқи истифодаи ин ботро надоред.")
        return
    
    try:
        # Гирифтани рақами филм аз фармон
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "❌ Истифодаи дуруст: /remove <рақам>\nМисол: /remove 2")
            return
        
        movie_index = int(args[1]) - 1  # Табдил ба index (аз 0 шурӯъ мешавад)
        
        if movie_index < 0 or movie_index >= len(bot_data.movie_queue):
            bot.reply_to(message, f"❌ Рақами нодуруст. Рақам бояд аз 1 то {len(bot_data.movie_queue)} бошад.")
            return
        
        # Нест кардани филм
        removed_movie = bot_data.movie_queue.pop(movie_index)
        save_data()
        
        bot.reply_to(
            message, 
            f"✅ Филм аз навбат нест карда шуд:\n📝 {removed_movie.get('caption', 'Бе сарлавҳа')}"
        )
        logger.info(f"Филм аз навбат нест карда шуд: {removed_movie.get('caption', 'Бе сарлавҳа')}")
        
    except ValueError:
        bot.reply_to(message, "❌ Рақами нодуруст. Лутфан рақами дуруст ворид кунед.")
    except Exception as e:
        bot.reply_to(message, f"❌ Хатогӣ: {str(e)}")
        logger.error(f"Хатогӣ ҳангоми нест кардани филм: {e}")

@bot.message_handler(commands=['settime'])
def handle_set_time(message):
    """Коркарди фармони /settime"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Шумо ҳуқуқи истифодаи ин ботро надоред.")
        return
    
    try:
        # Гирифтани вақт аз фармон
        args = message.text.split()
        if len(args) != 2:
            bot.reply_to(message, "❌ Истифодаи дуруст: /settime HH:MM\nМисол: /settime 14:30")
            return
        
        new_time = args[1]
        
        # Санҷиши формати вақт
        time_parts = new_time.split(':')
        if len(time_parts) != 2:
            raise ValueError("Формати нодуруст")
        
        hour, minute = int(time_parts[0]), int(time_parts[1])
        
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            raise ValueError("Вақти нодуруст")
        
        # Танзими вақти нав
        bot_data.post_time = new_time
        setup_scheduler()  # Навсозии ҷадвал
        save_data()
        
        bot.reply_to(
            message, 
            f"✅ Вақти интишор тағир дода шуд ба: {new_time}\n"
            f"⏰ Интишори навбатӣ: {get_next_post_time()}"
        )
        logger.info(f"Вақти интишор тағир дода шуд ба: {new_time}")
        
    except ValueError:
        bot.reply_to(message, "❌ Формати вақт нодуруст. Истифода баред: HH:MM (масалан, 14:30)")
    except Exception as e:
        bot.reply_to(message, f"❌ Хатогӣ: {str(e)}")
        logger.error(f"Хатогӣ ҳангоми тағири вақт: {e}")

@bot.message_handler(commands=['forcepost'])
def handle_force_post(message):
    """Коркарди фармони /forcepost"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Шумо ҳуқуқи истифодаи ин ботро надоред.")
        return
    
    if not bot_data.movie_queue:
        bot.reply_to(message, "❌ Навбати филмҳо холӣ аст.")
        return
    
    bot.reply_to(message, "⏳ Интишори филм...")
    post_movie()
    
    logger.info("Администратор интишори форӣ дархост кард")

@bot.message_handler(content_types=['video'])
def handle_video(message):
    """Коркарди файлҳои видеоӣ"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Шумо ҳуқуқи истифодаи ин ботро надоред.")
        return
    
    try:
        # Санҷиши ҷои холӣ дар навбат
        if len(bot_data.movie_queue) >= MAX_QUEUE_SIZE:
            bot.reply_to(
                message, 
                f"❌ Навбат пур аст! (Ҳадди аксар: {MAX_QUEUE_SIZE})\n"
                f"Лутфан якчанд филмро нест кунед ё интизор шавед."
            )
            return
        
        # Илова кардани филм ба навбат
        movie_data = {
            'file_id': message.video.file_id,
            'caption': message.caption or f"Филм #{len(bot_data.movie_queue) + 1}",
            'added_date': datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        
        bot_data.movie_queue.append(movie_data)
        save_data()
        
        bot.reply_to(
            message,
            f"✅ Филм ба навбат илова карда шуд!\n\n"
            f"📝 Сарлавҳа: {movie_data['caption']}\n"
            f"🔢 Ҷойи дар навбат: {len(bot_data.movie_queue)}\n"
            f"⏰ Интишори тахминӣ: {get_next_post_time()}"
        )
        
        logger.info(f"Филми нав илова карда шуд: {movie_data['caption']}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Хатогӣ ҳангоми илова кардани филм: {str(e)}")
        logger.error(f"Хатогӣ ҳангоми коркарди видео: {e}")

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    """Коркарди дигар паёмҳо"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Шумо ҳуқуқи истифодаи ин ботро надоред.")
        return
    
    bot.reply_to(
        message, 
        "❓ Фармони номаълум. Барои дидани фармонҳои дастрас /help-ро истифода баред."
    )

# ==================== ФУНКСИЯИ АСОСӢ ====================
def main():
    """Функсияи асосии барнома"""
    logger.info("Оғози кори бот...")
    
    try:
        # Бор кардани маълумот
        load_data()
        
        # Танзими ҷадвал
        setup_scheduler()
        
        # Оғози thread барои ҷадвал
        scheduler_thread_obj = threading.Thread(target=scheduler_thread, daemon=True)
        scheduler_thread_obj.start()
        
        logger.info("Бот омода аст!")
        
        # Огоҳ кардани администратор дар бораи оғози кор
        try:
            bot.send_message(
                ADMIN_USER_ID,
                f"🚀 Бот оғоз ёфт!\n\n"
                f"📊 Филмҳо дар навбат: {len(bot_data.movie_queue)}\n"
                f"⏰ Вақти интишор: {bot_data.post_time}\n"
                f"🕐 Интишори навбатӣ: {get_next_post_time()}"
            )
        except Exception as e:
            logger.error(f"Наметавонад ба администратор паём фиристад: {e}")
        
        # Оғози polling
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
        
    except KeyboardInterrupt:
        logger.info("Бот аз ҷониби корбар қатъ карда шуд")
    except Exception as e:
        logger.error(f"Хатогии умумӣ: {e}")
    finally:
        logger.info("Бот қатъ карда шуд")

if __name__ == "__main__":
    main()
