import os
import logging

from telegram import (
    Update,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

PHOTOS, WORK_TYPE, SUBJECT, TEACHER = range(4)

TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "0"))

TEACHERS_BY_SUBJECT = {
    "Алгебра": [
        "Городнов Артем Михайлович",
        "Любецкая Елена Васильевна",
        "Неустроев Глеб Александрович",
        "Петров Алексей Владимирович",
    ],
    "Биология": ["Майчак Вера Валерьевна"],
    "География": ["Степаньков Дмитрий Викторович"],
    "Геометрия": [
        "Городнов Артем Михайлович",
        "Любецкая Елена Васильевна",
        "Неустроев Глеб Александрович",
        "Петров Алексей Владимирович",
    ],
    "Информатика": [
        "Большакова Екатерина Игоревна",
        "Панфилова Дарья Александровна",
    ],
    "История": [
        "Кадыков Александр Николаевич",
        "Цветкова Ангелина Филипповна",
    ],
    "Литература": [
        "Гаранина Екатерина Владимировна",
        "Ишутин Юрий Юрьевич",
    ],
    "Обществознание": ["Егорова Айгюль Николаевна"],
    "Право": [
        "Степанова Софья Алексеевна",
        "Юсупов Андрей Витальевич",
    ],
    "Русский язык": [
        "Борисова Елена Олеговна",
        "Гаранина Екатерина Владимировна",
    ],
    "Теория познания": ["Курилович Иван Сергеевич"],
    "Физика": [
        "Белянин Василий Николаевич",
        "Кочегаров Александр Александрович",
    ],
    "Химия": ["Кивгазова Полина Владимировна"],
    "Экономика": ["Нимерницкая Ирина Андреевна"],
}

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def subject_keyboard():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton(subject, callback_data=f"subject:{index}")]
            for index, subject in enumerate(TEACHERS_BY_SUBJECT)
        ]
    )


def teacher_keyboard(subject: str):
    teachers = TEACHERS_BY_SUBJECT[subject]
    buttons = [
        [InlineKeyboardButton(teacher, callback_data=f"teacher:{index}")]
        for index, teacher in enumerate(teachers)
    ]
    buttons.append(
        [InlineKeyboardButton("⬅️ Другой предмет", callback_data="subject:back")]
    )
    return InlineKeyboardMarkup(buttons)


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
    await update.message.reply_text(
        "Выбери предмет работы. 📚",
        reply_markup=subject_keyboard()
    )
    return SUBJECT


async def receive_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    subject_index = int(query.data.split(":", 1)[1])
    subjects = list(TEACHERS_BY_SUBJECT)

    if subject_index >= len(subjects):
        await query.answer("Список предметов обновился. Начни заново: /start", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    subject = subjects[subject_index]
    context.user_data["subject"] = subject

    await query.edit_message_text(
        f"Предмет: {subject}\nВыбери преподавателя:",
        reply_markup=teacher_keyboard(subject)
    )
    return TEACHER


async def back_to_subjects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "Выбери предмет работы. 📚",
        reply_markup=subject_keyboard()
    )
    return SUBJECT


async def remind_choose_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери предмет кнопкой выше.")
    return SUBJECT


async def remind_choose_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери преподавателя кнопкой выше.")
    return TEACHER


async def receive_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    subject = context.user_data.get("subject")
    teachers = TEACHERS_BY_SUBJECT.get(subject, [])
    teacher_index = int(query.data.split(":", 1)[1])

    if teacher_index >= len(teachers):
        await query.answer("Список преподавателей обновился. Начни заново: /start", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    teacher = teachers[teacher_index]
    context.user_data["teacher"] = teacher
    photos = context.user_data["photos"]

    await query.edit_message_text(
        f"Выбран преподаватель: {teacher}\nОтправляю работу…"
    )

    caption = (
        "📄 Новая работа\n\n"
        f"Тип: {context.user_data['work_type']}\n"
        f"Предмет: {subject}\n"
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
        await query.message.reply_text(
            "Не удалось опубликовать работу. Обратись к администратору."
        )
        return ConversationHandler.END

    await query.message.reply_text("Спасибо, работа отправлена! 🌸")
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
                CallbackQueryHandler(receive_subject, pattern=r"^subject:\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_choose_subject),
            ],
            TEACHER: [
                CallbackQueryHandler(back_to_subjects, pattern=r"^subject:back$"),
                CallbackQueryHandler(receive_teacher, pattern=r"^teacher:\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_choose_teacher),
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
