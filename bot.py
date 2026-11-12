import os
import logging

from telegram import Update, InputMediaPhoto, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters
)

PHOTOS, WORK_TYPE, SUBJECT, TEACHER = range(4)

TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "0"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["photos"] = []

    keyboard = ReplyKeyboardMarkup(
        [["Готово"]],
        resize_keyboard=True
    )

    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Отправь фотографии своей работы.\n"
        "Количество фотографий не ограничено.\n"
        "Когда закончишь, нажми «Готово».",
        reply_markup=keyboard
    )
    return PHOTOS


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault("photos", []).append(
        update.message.photo[-1].file_id
    )

    count = len(context.user_data["photos"])

    await update.message.reply_text(
        f"Фото добавлено! 📸 Всего фотографий: {count}.\n"
        "Можешь отправить ещё или нажать «Готово»."
    )
    return PHOTOS


async def finish_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("photos"):
        await update.message.reply_text("Сначала отправь фотографию.")
        return PHOTOS

    await update.message.reply_text(
        "Что это за работа?",
        reply_markup=ReplyKeyboardRemove()
    )
    return WORK_TYPE


async def receive_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["work_type"] = update.message.text.strip()
    await update.message.reply_text("По какому предмету эта работа? 📚")
    return SUBJECT


async def receive_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["subject"] = update.message.text.strip()
    await update.message.reply_text("Назови учителя по этому предмету. 👩‍🏫")
    return TEACHER


async def receive_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teacher = update.message.text.strip()
    photos = context.user_data["photos"]

    caption = (
        "📄 Новая работа\n\n"
        f"Тип: {context.user_data['work_type']}\n"
        f"Предмет: {context.user_data['subject']}\n"
        f"Учитель: {teacher}"
    )

    try:
        if len(photos) == 1:
            await context.bot.send_photo(
                chat_id=TARGET_CHAT_ID,
                photo=photos[0],
                caption=caption
            )
        else:
            for start_index in range(0, len(photos), 10):
                batch = photos[start_index:start_index + 10]

                media = [
                    InputMediaPhoto(
                        media=photo,
                        caption=caption if i == 0 else None
                    )
                    for i, photo in enumerate(batch)
                ]

                await context.bot.send_media_group(
                    chat_id=TARGET_CHAT_ID,
                    media=media
                )

    except Exception:
        logger.exception("Ошибка публикации")
        await update.message.reply_text(
            "Не удалось опубликовать работу. Обратись к администратору."
        )
        return ConversationHandler.END

    await update.message.reply_text("Спасибо, работа отправлена! 🌸")
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Отправка отменена. Чтобы начать заново, напиши /start.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


def main():
    if not TOKEN or not TARGET_CHAT_ID:
        raise RuntimeError("Не заданы настройки бота")

    app = Application.builder().token(TOKEN).build()

    conversation = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            PHOTOS: [
                MessageHandler(filters.PHOTO, receive_photo),
                MessageHandler(filters.Regex(r"^Готово$"), finish_photos),
            ],
            WORK_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_work_type)
            ],
            SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_subject)
            ],
            TEACHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_teacher)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conversation)

    print("Photo Publisher запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()
