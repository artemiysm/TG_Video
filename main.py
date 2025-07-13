import glob
import os
from telebot import TeleBot, types
import yt_dlp
from dotenv import load_dotenv
import shutil

load_dotenv()
bot = TeleBot(os.getenv("BOT_TOKEN"))

def get_download_options(url, user_path):
    base_options = {
        'outtmpl': os.path.join(user_path, '%(title)s.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
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
        })
    else:
        base_options['format'] = 'best[ext=mp4]/best'

    return base_options

@bot.message_handler(commands=['start'])
def start(message):
    text = (
        "Приветствую вас!\n"
        "Это бот для скачивания видео по ссылке\n"
        "Вам достаточно вставить ссылку\n"
        "и бот начнёт скачивание\n"
        "А когда скачает - тут же отправит вам!"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(commands=['download'])
def download_command(message):
    msg = bot.send_message(message.chat.id, "Введите ссылку на видео:")
    bot.register_next_step_handler(msg, process_url)

def process_url(message):
    chat_id = message.chat.id
    url = message.text

    if not url.startswith(('http://', 'https://')):
        bot.send_message(chat_id, " Это не похоже на ссылку. Попробуйте ещё раз.")
        return

    user_path = os.path.join("downloads", str(message.from_user.id))
    os.makedirs(user_path, exist_ok=True)

    try:
        options = get_download_options(url, user_path)
        bot.send_message(chat_id, " Видео скачивается. Пожалуйста, подождите...")

        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Проверка размера файла
            file_size = os.path.getsize(filename) / (1024 * 1024)  # в MB
            if file_size > 50:
                os.remove(filename)
                bot.send_message(chat_id, " Видео слишком большое (>50MB). Telegram не позволяет отправить его.")
                return

            with open(filename, 'rb') as video:
                if 'tiktok.com' in url:
                    bot.send_video(chat_id, video, timeout=120)
                else:
                    bot.send_document(chat_id, video, timeout=120)

            os.remove(filename)

    except yt_dlp.utils.DownloadError as e:
        if "Requested format is not available" in str(e):
            try:
                options['format'] = 'best'
                with yt_dlp.YoutubeDL(options) as ydl:
                    ydl.download([url])
            except Exception as fallback_e:
                bot.send_message(chat_id, f"Ошибка при скачивании: {str(fallback_e)}")
        else:
            bot.send_message(chat_id, f"Ошибка загрузки: {str(e)}")
    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка: {str(e)}")
    finally:
        # Очистка временных файлов
        for f in glob.glob(os.path.join(user_path, '*')):
            try:
                os.remove(f)
            except:
                pass

bot.polling(none_stop=True)