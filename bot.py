import os
import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

# --- الإعدادات ---
# سيتم قراءة التوكن من متغيرات البيئة بدلاً من كتابته هنا مباشرة
TOKEN = os.environ.get("TELEGRAM_TOKEN")
    
# --- دوال البوت ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("أهلاً بك في بوت نقرة (NAQRA) 🤖\n\nأرسل لي أي رابط من منصات التواصل الاجتماعي وسأقوم بتنزيله لك.")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    url = message.text
    if not url or not url.startswith('http'):
        await message.reply_text("عفواً، لم أفهم طلبك. الرجاء إرسال رابط صالح.")
        return

    keyboard = [
        [
            InlineKeyboardButton("فيديو 🎬", callback_data=f"video_{url}"),
            InlineKeyboardButton("صوت 🎵", callback_data=f"audio_{url}"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("اختر الصيغة التي تريدها:", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
        
    try:
        data = query.data
        download_type, url = data.split('_', 1)
    except (ValueError, IndexError):
        await query.edit_message_text(text="حدث خطأ في معالجة طلبك. حاول مرة أخرى.")
        return

    await query.edit_message_text(text=f"جاري معالجة الرابط... ⏳")

    try:
        output_template = f"downloads/%(id)s.%(ext)s"
        ydl_opts = {'outtmpl': output_template, 'noplaylist': True}

        if download_type == 'audio':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3'}],
            })
        else:
            ydl_opts.update({'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'})

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            if download_type == 'audio':
                file_path = os.path.splitext(file_path)[0] + '.mp3'

        await query.message.reply_text("تم التنزيل! جاري رفع الملف لك...")
            
        chat_id = query.message.chat_id
        if download_type == 'audio':
            await context.bot.send_audio(chat_id=chat_id, audio=open(file_path, 'rb'), write_timeout=120)
        else:
            await context.bot.send_video(chat_id=chat_id, video=open(file_path, 'rb'), write_timeout=120)
            
        os.remove(file_path)
        await query.edit_message_text(text="اكتمل ✅")

    except Exception as e:
        print(f"Error: {e}")
        await query.edit_message_text(text=f"فشل التنزيل. قد يكون الرابط خاصًا أو غير مدعوم.\nالخطأ: {type(e).__name__}")

if __name__ == '__main__':
    if not os.path.exists('downloads'):
        os.makedirs('downloads')

    if not TOKEN:
        raise ValueError("لم يتم العثور على TELEGRAM_TOKEN! تأكد من إعداده.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(button_handler))
        
    print("البوت بدأ التشغيل...")
    app.run_polling()
