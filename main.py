import glob
import os
from telebot import TeleBot, types
import yt_dlp
from dotenv import load_dotenv
import shutil
import time

load_dotenv()
bot = TeleBot(os.getenv("BOT_TOKEN"))

# Глобальные переменные для отслеживания прогресса
progress_message = None
last_update_time = 0

def progress_hook(d, chat_id):
    """Функция для отображения прогресса загрузки"""
    global progress_message, last_update_time
    
    if d['status'] == 'downloading':
        # Очищаем строку процентов от ANSI-кодов
        percent_str = d.get('_percent_str', '0%')
        clean_percent = ''.join(c for c in percent_str if c.isdigit() or c in ('.', '%'))
        
        try:
            percent = float(clean_percent.strip('%'))
        except ValueError:
            percent = 0.0
            
        speed = d.get('_speed_str', 'N/A')
        eta = d.get('_eta_str', 'N/A')
        
        # Создаем текстовый прогресс-бар
        def make_progress_bar(p):
            bars = 10
            filled = int(round(bars * p / 100))
            return '[' + '█' * filled + ' ' * (bars - filled) + ']'
        
        progress_bar = make_progress_bar(percent)
        
        # Формируем сообщение
        text = (
            f" Загрузка видео...\n"
            f"{progress_bar} {percent:.1f}%\n"
            f" Скорость: {speed}\n"
            f" Осталось: {eta}"
        )
        
        # Обновляем сообщение не чаще чем раз в 2 секунды
        current_time = time.time()
        if current_time - last_update_time > 2:
            try:
                if progress_message:
                    bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=progress_message.message_id,
                        text=text
                    )
                else:
                    progress_message = bot.send_message(chat_id, text)
                last_update_time = current_time
            except Exception as e:
                print(f"Ошибка обновления прогресса: {e}")

def get_download_options(url, user_path, chat_id):
    """Возвращает параметры скачивания с хуком прогресса"""
    base_options = {
        'outtmpl': os.path.join(user_path, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'progress_hooks': [lambda d: progress_hook(d, chat_id)],
    }

    # Специальные настройки для TikTok
    if 'tiktok.com' in url:
        base_options.update({
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.tiktok.com/',
            },
            'extractor_args': {'tiktok': {'region': 'US'}}
        })

    # Настройки формата
    if shutil.which("ffmpeg"):
        base_options.update({
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'merge_output_format': 'mp4',
            'cookies': 'cookies.txt',
        })
    else:
        base_options['format'] = 'best[ext=mp4]/best'

    return base_options

@bot.message_handler(commands=['start'])
def handle_start(message):
    keyboard = types.ReplyKeyboardMarkup(row_width=1)
    button1 = types.KeyboardButton('Скачать видео')
    keyboard.add(button1)
    bot.reply_to(message, 'Привет! Я бот для скачивания видео.', reply_markup=keyboard)

@bot.message_handler(func=lambda message: message.text == 'Скачать видео')
def download_command(message):
    msg = bot.send_message(message.chat.id, "Введите ссылку на видео:")
    bot.register_next_step_handler(msg, process_url)

def process_url(message):
    global progress_message
    
    chat_id = message.chat.id
    url = message.text

    if not url.startswith(('http://', 'https://')):
        bot.send_message(chat_id, " Это не похоже на ссылку. Попробуйте ещё раз.")
        return

    user_path = os.path.join("downloads", str(message.from_user.id))
    os.makedirs(user_path, exist_ok=True)

    try:
        # Отправляем начальное сообщение о начале загрузки
        progress_message = bot.send_message(chat_id, " Подготовка к загрузке...")
        
        options = get_download_options(url, user_path, chat_id)
        
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Проверка размера файла
            file_size = os.path.getsize(filename) / (1024 * 1024)
            if file_size > 50:
                os.remove(filename)
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_message.message_id,
                    text=" Видео слишком большое (>50MB). Telegram не позволяет отправить его."
                )
                return

            # Отправка файла
            with open(filename, 'rb') as video:
                bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=progress_message.message_id,
                    text=" Видео успешно скачано! Отправляю..."
                )
                if 'tiktok.com' in url:
                    bot.send_video(chat_id, video, timeout=120)
                else:
                    bot.send_document(chat_id, video, timeout=120)

            # Удаляем временный файл
            os.remove(filename)
            
            # Удаляем сообщение о прогрессе
            bot.delete_message(chat_id, progress_message.message_id)
            progress_message = None

    except yt_dlp.utils.DownloadError as e:
        error_msg = f" Ошибка загрузки: {str(e)}"
        if progress_message:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_message.message_id,
                text=error_msg
            )
        else:
            bot.send_message(chat_id, error_msg)
    except Exception as e:
        error_msg = f" Неожиданная ошибка: {str(e)}"
        if progress_message:
            bot.edit_message_text(
                chat_id=chat_id,
                message_id=progress_message.message_id,
                text=error_msg
            )
        else:
            bot.send_message(chat_id, error_msg)
    finally:
        # Очистка временных файлов
        for f in glob.glob(os.path.join(user_path, '*')):
            try:
                os.remove(f)
            except:
                pass

if __name__ == '__main__':
    os.makedirs("downloads", exist_ok=True)
    bot.polling(none_stop=True)