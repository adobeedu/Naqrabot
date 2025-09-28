import os
import logging
import yt_dlp
import isodate
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)
from telegram.error import BadRequest
# --- إضافات جديدة لخادم الويب الوهمي ---
from flask import Flask
import threading
# -----------------------------------------

# --- الإعدادات الأساسية ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHANNEL_ID = -1002627341759
CHANNEL_USERNAME = "mukhtaredu"

# إعداد سجلات الأخطاء
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# تعريف "الحالات" للمحادثة
SELECTING_FORMAT, AWAITING_TRIM_TIMES = range(2)

# --- دوال مساعدة ---

async def is_user_subscribed(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception:
        return False

def format_duration(duration_iso):
    if not duration_iso: return "غير معروف"
    try:
        duration = isodate.parse_duration(duration_iso)
        total_seconds = int(duration.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0: return f"{hours:02}:{minutes:02}:{seconds:02}"
        else: return f"{minutes:02}:{seconds:02}"
    except:
        return duration_iso # Fallback to original string if parsing fails

def format_bytes(size):
    if size is None: return "غير معروف"
    power = 1024; n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size >= power and n < len(power_labels):
        size /= power; n += 1
    return f"{size:.1f} {power_labels[n]}B"

# --- دوال المحادثة (منطق البوت الرئيسي) ---
# ... (هنا كل دوال البوت مثل start, handle_link, etc. لم تتغير)
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not await is_user_subscribed(context, user_id):
        keyboard = [[InlineKeyboardButton("✅ اشتراك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "عذرًا، يجب عليك الاشتراك في قناة البوت أولاً للاستفادة من خدماته.  চ্যানেলটিতে যোগ দিন 👇",
            reply_markup=reply_markup
        )
        return ConversationHandler.END
        
    await update.message.reply_text(
        "أهلاً بك في بوت NAQRA 🤖\n\nأرسل لي أي رابط من منصات التواصل الاجتماعي وسأقوم بتحليله لك."
    )
    return SELECTING_FORMAT

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    if not await is_user_subscribed(context, user_id):
        keyboard = [[InlineKeyboardButton("✅ اشتراك في القناة", url=f"https://t.me/{CHANNEL_USERNAME}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "عذرًا، يجب عليك الاشتراك في قناة البوت أولاً للاستفادة من خدماته. চ্যানেলটিতে যোগ দিন 👇",
            reply_markup=reply_markup
        )
        return ConversationHandler.END

    url = update.message.text
    if not url or not url.startswith('http'):
        await update.message.reply_text("الرجاء إرسال رابط صالح.")
        return SELECTING_FORMAT

    processing_message = await update.message.reply_text("جاري تحليل الرابط... ⏳")
        
    try:
        ydl_opts = {'noplaylist': True, 'quiet': True, 'extract_flat': 'in_playlist'}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if not info:
            raise yt_dlp.utils.DownloadError("لم يتم العثور على معلومات من الرابط.")

        context.user_data['info'] = info
        title = info.get('title', 'بدون عنوان')
        thumbnail = info.get('thumbnail')
        duration = format_duration(info.get('duration_string') or info.get('duration'))
            
        caption = f"🎬 **العنوان:** {title}\n⏳ **المدة:** {duration}"
        keyboard = []
            
        video_formats = [f for f in info.get('formats', []) if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4']
        added_qualities = set()
        for f in sorted(video_formats, key=lambda x: x.get('height', 0), reverse=True):
            quality = f.get('height')
            if quality and quality >= 360 and quality not in added_qualities:
                filesize = format_bytes(f.get('filesize') or f.get('filesize_approx'))
                keyboard.append([InlineKeyboardButton(f"فيديو 🎥 {quality}p ({filesize})", callback_data=f"quality_{quality}")])
                added_qualities.add(quality)
            
        if not added_qualities: # If no video found, still add audio button
             keyboard.append([InlineKeyboardButton("صوت 🎵 (MP3)", callback_data="audio")])
        else:
             keyboard.insert(len(added_qualities), [InlineKeyboardButton("صوت 🎵 (MP3)", callback_data="audio")])

        keyboard.append([InlineKeyboardButton("قص المقطع ✂️", callback_data="trim")])
            
        reply_markup = InlineKeyboardMarkup(keyboard)
        if thumbnail:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=thumbnail, caption=caption, reply_markup=reply_markup, parse_mode='Markdown')
        else:
            await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode='Markdown')
            
        await processing_message.delete()
        return SELECTING_FORMAT

    except Exception as e:
        logger.error(f"Error processing link {url}: {e}")
        await processing_message.edit_text("فشل تحليل الرابط. قد يكون الرابط خاصًا، غير مدعوم، أو أن هناك مشكلة في الاتصال.")
        return ConversationHandler.END

async def handle_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data
    context.user_data['choice'] = choice

    if choice == "trim":
        await query.edit_message_text("✂️ **قص المقطع**\n\nأرسل الآن وقت البداية والنهاية بالصيغة التالية:\n`MM:SS-MM:SS`\n\nمثال: `0:30-1:45`")
        return AWAITING_TRIM_TIMES
    else:
        await query.edit_message_text("تم اختيار الصيغة. جاري التنزيل والمعالجة...")
        await download_and_send(context, query.message.chat_id)
        return ConversationHandler.END

async def handle_trim_times(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    trim_times = update.message.text
    context.user_data['trim_times'] = trim_times
    await update.message.reply_text("تم استلام وقت القص. جاري التنزيل والمعالجة...")
    await download_and_send(context, update.message.chat_id)
    return ConversationHandler.END

async def download_and_send(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    info = context.user_data.get('info')
    choice = context.user_data.get('choice')
    trim_times = context.user_data.get('trim_times')
    url = info.get('webpage_url')
    output_template = f"downloads/%(id)s.%(ext)s"
    ydl_opts = {'outtmpl': output_template}

    try:
        if choice == "audio":
            ydl_opts.update({'format': 'bestaudio/best', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}]})
        elif "quality_" in choice:
            quality = choice.split('_')[1]
            ydl_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            
        if trim_times:
            try:
                start_time, end_time = trim_times.replace(" ", "").split('-')
                postprocessor_args = f"-ss {start_time} -to {end_time}"
                ydl_opts.setdefault('postprocessor_args', {}).setdefault('ffmpeg', []).extend(postprocessor_args.split())
            except ValueError:
                await context.bot.send_message(chat_id, "صيغة وقت القص غير صحيحة. تم تجاهل القص.")

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await context.bot.send_message(chat_id, "بدء عملية التنزيل من المصدر...")
            download_info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(download_info)
                
            if choice == "audio":
                base, _ = os.path.splitext(file_path)
                final_path = base + ".mp3"
                if not os.path.exists(final_path): final_path = file_path
                file_path = final_path

        await context.bot.send_message(chat_id, "اكتمل التنزيل. جاري الرفع إليك...")
            
        if choice == "audio":
            await context.bot.send_audio(chat_id=chat_id, audio=open(file_path, 'rb'), write_timeout=300)
        else:
            await context.bot.send_video(chat_id=chat_id, video=open(file_path, 'rb'), write_timeout=300)

        os.remove(file_path)
    except Exception as e:
        logger.error(f"Error during download/send: {e}")
        await context.bot.send_message(chat_id, f"حدث خطأ فادح أثناء المعالجة. قد يكون الفيديو طويلاً جداً أو أن هناك مشكلة فنية.\nالخطأ: {type(e).__name__}")
    finally:
        context.user_data.clear()

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("تم إلغاء العملية الحالية.")
    context.user_data.clear()
    return ConversationHandler.END

def main_bot_logic():
    """الدالة التي تحتوي على منطق البوت الرئيسي"""
    if not TOKEN: raise ValueError("لم يتم العثور على TELEGRAM_TOKEN!")
    app = Application.builder().token(TOKEN).build()
    if not os.path.exists('downloads'): os.makedirs('downloads')

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)],
        states={
            SELECTING_FORMAT: [CallbackQueryHandler(handle_format_choice)],
            AWAITING_TRIM_TIMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trim_times)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        conversation_timeout=300
    )
    app.add_handler(conv_handler)
        
    print("بوت تيليغرام بدأ التشغيل...")
    app.run_polling()

# --- كود تشغيل الخادم الوهمي لإبقاء Render نشطًا ---
app_flask = Flask(__name__)

@app_flask.route('/')
def index():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host='0.0.0.0', port=port)
# ----------------------------------------------------

if __name__ == "__main__":
    # تشغيل خادم فلاسك في خيط منفصل
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
        
    # تشغيل البوت
    main_bot_logic()
