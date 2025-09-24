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

# --- الإعدادات الأساسية ---
TOKEN = os.environ.get("TELEGRAM_TOKEN")

# إعداد سجلات الأخطاء (للتشخيص)
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# تعريف "الحالات" للمحادثة
SELECTING_FORMAT, AWAITING_TRIM_TIMES = range(2)

# --- دوال مساعدة ---
def format_duration(duration_iso):
    """تحويل مدة الفيديو من صيغة ISO 8601 إلى HH:MM:SS"""
    if not duration_iso:
        return "غير معروف"
    duration = isodate.parse_duration(duration_iso)
    total_seconds = int(duration.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    else:
        return f"{minutes:02}:{seconds:02}"

def format_bytes(size):
    """تحويل حجم الملف من بايت إلى صيغة مقروءة (MB, GB)"""
    if size is None:
        return "غير معروف"
    power = 1024
    n = 0
    power_labels = {0: '', 1: 'K', 2: 'M', 3: 'G', 4: 'T'}
    while size > power and n < len(power_labels):
        size /= power
        n += 1
    return f"{size:.1f} {power_labels[n]}B"

# --- دوال المحادثة ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """دالة البداية والرد على /start"""
    await update.message.reply_text(
        "أهلاً بك في بوت NAQRA 🤖\n\n"
        "أرسل لي أي رابط من منصات التواصل الاجتماعي وسأقوم بتحليله لك."
    )
    return SELECTING_FORMAT

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة الرابط المرسل واستخراج معلوماته"""
    url = update.message.text
    if not url.startswith('http'):
        await update.message.reply_text("الرجاء إرسال رابط صالح.")
        return SELECTING_FORMAT

    processing_message = await update.message.reply_text("جاري تحليل الرابط... ⏳")

    try:
        ydl_opts = {'noplaylist': True, 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        context.user_data['info'] = info
        title = info.get('title', 'بدون عنوان')
        thumbnail = info.get('thumbnail')
        duration = format_duration(info.get('duration_string'))
        
        caption = f"🎬 **العنوان:** {title}\n"
        caption += f"⏳ **المدة:** {duration}"

        keyboard = []
        # إضافة أزرار الجودة
        for f in info.get('formats', []):
            if f.get('vcodec') != 'none' and f.get('acodec') != 'none' and f.get('ext') == 'mp4':
                quality = f.get('height')
                filesize = format_bytes(f.get('filesize') or f.get('filesize_approx'))
                if quality and quality >= 360:
                     # منع تكرار نفس الجودة
                    if not any(f"quality_{quality}" in row[0].callback_data for row in keyboard):
                        keyboard.append([InlineKeyboardButton(
                            f"فيديو 🎥 {quality}p ({filesize})",
                            callback_data=f"quality_{quality}"
                        )])
        
        # إضافة زر الصوت
        keyboard.append([InlineKeyboardButton("صوت 🎵 (MP3)", callback_data="audio")])
        # إضافة زر القص
        keyboard.append([InlineKeyboardButton("قص المقطع ✂️", callback_data="trim")])
        
        # زر قائمة التشغيل
        if 'entries' in info:
            keyboard.append([InlineKeyboardButton("تنزيل أول 5 من القائمة 📂", callback_data="playlist_5")])

        reply_markup = InlineKeyboardMarkup(keyboard)

        if thumbnail:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=thumbnail,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(caption, reply_markup=reply_markup, parse_mode='Markdown')
        
        await processing_message.delete()
        return SELECTING_FORMAT

    except Exception as e:
        logger.error(f"Error processing link {url}: {e}")
        await processing_message.edit_text("فشل تحليل الرابط. قد يكون خاصًا أو غير مدعوم.")
        return SELECTING_FORMAT

async def handle_format_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """معالجة اختيار المستخدم (جودة، صوت، قص)"""
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
    """معالجة وقت القص المرسل من المستخدم"""
    trim_times = update.message.text
    # يمكنك إضافة تحقق أكثر دقة من صيغة الوقت هنا
    context.user_data['trim_times'] = trim_times
    await update.message.reply_text("تم استلام وقت القص. جاري التنزيل والمعالجة...")
    await download_and_send(context, update.message.chat_id)
    return ConversationHandler.END

async def download_and_send(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """الدالة الرئيسية للتنزيل، القص، والإرسال"""
    info = context.user_data.get('info')
    choice = context.user_data.get('choice')
    trim_times = context.user_data.get('trim_times')
    
    url = info.get('webpage_url')
    output_template = f"downloads/%(id)s.%(ext)s"
    ydl_opts = {'outtmpl': output_template}

    try:
        if choice == "audio":
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
            })
        elif "quality_" in choice:
            quality = choice.split('_')[1]
            ydl_opts['format'] = f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        # يمكنك إضافة منطق playlist هنا
        
        # --- منطق القص ---
        if trim_times:
            start_time, end_time = trim_times.split('-')
            postprocessor_args = f"-ss {start_time} -to {end_time}"
            ydl_opts['postprocessor_args'] = postprocessor_args


        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await context.bot.send_message(chat_id, "بدء عملية التنزيل من المصدر...")
            download_info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(download_info)
            
            if choice == "audio":
                # إذا كان هناك قص، قد لا يتم تغيير الامتداد تلقائيا
                if trim_times:
                     base, _ = os.path.splitext(file_path)
                     file_path = base + ".mp3"
                else:
                    file_path = os.path.splitext(file_path)[0] + '.mp3'

        await context.bot.send_message(chat_id, "اكتمل التنزيل. جاري الرفع إليك...")
        
        # إرسال الملف
        if choice == "audio":
            await context.bot.send_audio(chat_id=chat_id, audio=open(file_path, 'rb'), write_timeout=180)
        else:
            await context.bot.send_video(chat_id=chat_id, video=open(file_path, 'rb'), write_timeout=180)

        os.remove(file_path) # حذف الملف بعد الإرسال

    except Exception as e:
        logger.error(f"Error during download/send: {e}")
        await context.bot.send_message(chat_id, f"حدث خطأ فادح أثناء المعالجة: {e}")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """إلغاء المحادثة الحالية"""
    await update.message.reply_text("تم إلغاء العملية الحالية.")
    return ConversationHandler.END

# --- تجميع البوت وتشغيله ---
def main() -> None:
    if not TOKEN:
        raise ValueError("لم يتم العثور على TELEGRAM_TOKEN!")

    app = Application.builder().token(TOKEN).build()

    # إنشاء مجلد التنزيلات
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)],
        states={
            SELECTING_FORMAT: [CallbackQueryHandler(handle_format_choice)],
            AWAITING_TRIM_TIMES: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_trim_times)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    
    print("البوت بدأ التشغيل بالنسخة المطورة...")
    app.run_polling()

if __name__ == "__main__":
    main()
