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

PHOTOS, WORK_TYPE, SUBJECT, TEACHER, PREVIEW, EDIT_MENU, EDIT_WORK_TYPE, ADD_PHOTOS, DELETE_PHOTOS = range(9)

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
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def subject_keyboard(show_edit_back=False):
    buttons = [
        [InlineKeyboardButton(subject, callback_data=f"subject:{index}")]
        for index, subject in enumerate(TEACHERS_BY_SUBJECT)
    ]
    if show_edit_back:
        buttons.append(
            [InlineKeyboardButton("⬅️ Вернуться к редактированию", callback_data="subject:edit_back")]
        )
    return InlineKeyboardMarkup(buttons)


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


def preview_keyboard():
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("✅ Опубликовать", callback_data="preview:publish"),
            InlineKeyboardButton("✏️ Изменить данные", callback_data="preview:edit"),
        ]]
    )


def edit_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Изменить тип работы", callback_data="edit:type")],
        [InlineKeyboardButton("Изменить предмет", callback_data="edit:subject")],
        [InlineKeyboardButton("Изменить учителя", callback_data="edit:teacher")],
        [InlineKeyboardButton("Добавить фотографии", callback_data="edit:add_photos")],
        [InlineKeyboardButton("Удалить фотографии", callback_data="edit:delete_photos")],
        [InlineKeyboardButton("Вернуться к предпросмотру", callback_data="edit:preview")],
    ])


def photo_delete_keyboard(index: int, count: int):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("◀️", callback_data="photo:prev"),
            InlineKeyboardButton("▶️", callback_data="photo:next"),
        ],
        [InlineKeyboardButton("🗑 Удалить это фото", callback_data="photo:delete")],
        [InlineKeyboardButton("Готово", callback_data="photo:done")],
    ])


def publication_caption(context: ContextTypes.DEFAULT_TYPE):
    return (
        "📄 Новая работа\n\n"
        f"Тип: {context.user_data['work_type']}\n"
        f"Предмет: {context.user_data['subject']}\n"
        f"Учитель: {context.user_data['teacher']}"
    )


def preview_text(context: ContextTypes.DEFAULT_TYPE):
    return (
        "📄 Проверьте данные перед публикацией\n\n"
        f"Фотографий: {len(context.user_data['photos'])}\n\n"
        f"Тип: {context.user_data['work_type']}\n"
        f"Предмет: {context.user_data['subject']}\n"
        f"Учитель: {context.user_data['teacher']}\n\n"
        "Предпросмотр сообщения для группы — первая фотография и подпись ниже."
    )


async def show_preview(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.user_data["chat_id"]
    photos = context.user_data["photos"]
    caption = publication_caption(context)
    first_photo = photos[0]
    photo_message_id = context.user_data.get("preview_photo_message_id")
    photo_mode = context.user_data.get("photo_preview_mode", "preview")

    if photo_message_id is None:
        photo_message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=first_photo,
            caption=caption,
        )
        context.user_data["preview_photo_message_id"] = photo_message.message_id
    elif photo_mode == "delete":
        await context.bot.edit_message_media(
            chat_id=chat_id,
            message_id=photo_message_id,
            media=InputMediaPhoto(media=first_photo, caption=caption),
            reply_markup=None,
        )
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=photo_message_id,
            reply_markup=None,
        )
    else:
        previous_photo = context.user_data.get("preview_photo_file_id")
        previous_caption = context.user_data.get("preview_photo_caption")
        if previous_photo != first_photo:
            await context.bot.edit_message_media(
                chat_id=chat_id,
                message_id=photo_message_id,
                media=InputMediaPhoto(media=first_photo, caption=caption),
                reply_markup=None,
            )
        elif previous_caption != caption:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=photo_message_id,
                caption=caption,
                reply_markup=None,
            )

    context.user_data["preview_photo_file_id"] = first_photo
    context.user_data["preview_photo_caption"] = caption
    context.user_data["photo_preview_mode"] = "preview"

    text = preview_text(context)
    preview_message_id = context.user_data.get("preview_message_id")
    summary_is_preview = context.user_data.get("summary_is_preview", False)
    previous_text = context.user_data.get("preview_summary_text")

    if preview_message_id is None:
        message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=preview_keyboard(),
        )
        context.user_data["preview_message_id"] = message.message_id
    elif not summary_is_preview or previous_text != text:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=preview_message_id,
            text=text,
            reply_markup=preview_keyboard(),
        )
    else:
        await context.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=preview_message_id,
            reply_markup=preview_keyboard(),
        )

    context.user_data["preview_summary_text"] = text
    context.user_data["summary_is_preview"] = True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["photos"] = []
    context.user_data["chat_id"] = update.effective_chat.id

    keyboard = ReplyKeyboardMarkup([["Готово"]], resize_keyboard=True)
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Отправь фотографии своей работы.\n"
        "Количество фотографий не ограничено.\n"
        "Когда закончишь, нажми «Готово».",
        reply_markup=keyboard,
    )
    return PHOTOS


async def receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.setdefault("photos", []).append(update.message.photo[-1].file_id)
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
        reply_markup=ReplyKeyboardRemove(),
    )
    return WORK_TYPE


async def receive_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    work_type = update.message.text.strip()
    if not work_type:
        await update.message.reply_text("Напиши тип работы.")
        return WORK_TYPE

    context.user_data["work_type"] = work_type
    await update.message.reply_text(
        "Выбери предмет работы. 📚",
        reply_markup=subject_keyboard(),
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
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text(
        f"Предмет: {subject}\nВыбери преподавателя:",
        reply_markup=teacher_keyboard(subject),
    )
    return TEACHER


async def back_to_subjects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text(
        "Выбери предмет работы. 📚",
        reply_markup=subject_keyboard(
            show_edit_back=bool(context.user_data.get("preview_message_id"))
        ),
    )
    return SUBJECT


async def remind_choose_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери предмет кнопкой выше.")
    return SUBJECT


async def remind_choose_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери преподавателя кнопкой выше.")
    return TEACHER


async def back_to_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    previous_subject = context.user_data.pop("subject_before_edit", None)
    previous_teacher = context.user_data.pop("teacher_before_edit", None)
    if previous_subject is not None:
        context.user_data["subject"] = previous_subject
        context.user_data["teacher"] = previous_teacher
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text(
        "Что изменить?",
        reply_markup=edit_keyboard(),
    )
    return EDIT_MENU


async def receive_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    subject = context.user_data.get("subject")
    teachers = TEACHERS_BY_SUBJECT.get(subject, [])
    teacher_index = int(query.data.split(":", 1)[1])

    if teacher_index >= len(teachers):
        await query.answer("Список преподавателей обновился. Начни заново: /start", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    context.user_data["teacher"] = teachers[teacher_index]
    context.user_data["chat_id"] = query.message.chat_id
    if not context.user_data.get("preview_message_id"):
        context.user_data["preview_message_id"] = query.message.message_id
    context.user_data["summary_is_preview"] = False
    context.user_data.pop("subject_before_edit", None)
    context.user_data.pop("teacher_before_edit", None)
    await query.edit_message_text("Готовлю предпросмотр…", reply_markup=None)
    await show_preview(context)
    return PREVIEW


async def show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text("Что изменить?", reply_markup=edit_keyboard())
    return EDIT_MENU


async def edit_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text("Напиши новый тип работы:", reply_markup=None)
    return EDIT_WORK_TYPE


async def receive_edited_work_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    work_type = update.message.text.strip()
    if not work_type:
        await update.message.reply_text("Напиши новый тип работы.")
        return EDIT_WORK_TYPE

    context.user_data["work_type"] = work_type
    context.user_data["summary_is_preview"] = False
    await show_preview(context)
    return PREVIEW


async def edit_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["subject_before_edit"] = context.user_data["subject"]
    context.user_data["teacher_before_edit"] = context.user_data["teacher"]
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text(
        "Выбери новый предмет:",
        reply_markup=subject_keyboard(show_edit_back=True),
    )
    return SUBJECT


async def edit_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    subject = context.user_data["subject"]
    await query.answer()
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text(
        f"Выбери нового преподавателя по предмету «{subject}»:",
        reply_markup=teacher_keyboard(subject),
    )
    return TEACHER


async def add_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["photos_before_add"] = len(context.user_data["photos"])
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text(
        "Отправь дополнительные фотографии и нажми «Готово».",
        reply_markup=None,
    )
    await query.message.reply_text(
        "Жду фотографии. Когда закончишь, нажми «Готово».",
        reply_markup=ReplyKeyboardMarkup([["Готово"]], resize_keyboard=True),
    )
    return ADD_PHOTOS


async def receive_additional_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["photos"].append(update.message.photo[-1].file_id)
    count = len(context.user_data["photos"])
    await update.message.reply_text(
        f"Фото добавлено! 📸 Всего фотографий: {count}.\n"
        "Можешь отправить ещё или нажать «Готово».",
        reply_markup=ReplyKeyboardMarkup([["Готово"]], resize_keyboard=True),
    )
    return ADD_PHOTOS


async def finish_additional_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    added = len(context.user_data["photos"]) - context.user_data.get("photos_before_add", 0)
    message = (
        "Новые фотографии добавлены. Возвращаю предпросмотр."
        if added
        else "Новых фотографий не добавлено. Возвращаю предпросмотр."
    )
    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())
    context.user_data["summary_is_preview"] = False
    await show_preview(context)
    return PREVIEW


async def remind_add_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отправь фото или нажми «Готово».")
    return ADD_PHOTOS


async def delete_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    photos = context.user_data["photos"]
    if len(photos) <= 1:
        await query.answer(
            "Нужно оставить хотя бы одну фотографию. Сначала добавь другую, если хочешь заменить эту.",
            show_alert=True,
        )
        return EDIT_MENU

    await query.answer()
    context.user_data["photo_delete_index"] = 0
    context.user_data["photo_preview_mode"] = "delete"
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text(
        "Просматривай фотографии ниже. Выбранную можно удалить.",
        reply_markup=None,
    )
    await show_photo_for_deletion(context)
    return DELETE_PHOTOS


async def show_photo_for_deletion(context: ContextTypes.DEFAULT_TYPE):
    photos = context.user_data["photos"]
    index = context.user_data["photo_delete_index"]
    await context.bot.edit_message_media(
        chat_id=context.user_data["chat_id"],
        message_id=context.user_data["preview_photo_message_id"],
        media=InputMediaPhoto(
            media=photos[index],
            caption=f"Фото {index + 1} из {len(photos)}",
        ),
        reply_markup=photo_delete_keyboard(index, len(photos)),
    )


async def handle_photo_deletion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    action = query.data.split(":", 1)[1]
    photos = context.user_data["photos"]
    index = context.user_data["photo_delete_index"]

    if action == "done":
        await query.answer()
        context.user_data["summary_is_preview"] = False
        await show_preview(context)
        return PREVIEW

    if action == "delete" and len(photos) <= 1:
        await query.answer(
            "Нужно оставить хотя бы одну фотографию. Сначала добавь другую.",
            show_alert=True,
        )
        return DELETE_PHOTOS

    await query.answer()
    if action == "prev":
        index = (index - 1) % len(photos)
    elif action == "next":
        index = (index + 1) % len(photos)
    elif action == "delete":
        photos.pop(index)
        index = min(index, len(photos) - 1)

    context.user_data["photo_delete_index"] = index
    await show_photo_for_deletion(context)
    return DELETE_PHOTOS


async def return_to_preview(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["summary_is_preview"] = False
    await show_preview(context)
    return PREVIEW


async def remind_preview_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Нажми кнопку «Опубликовать» или «Изменить данные» под предпросмотром.")
    return PREVIEW


async def remind_edit_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Выбери действие кнопкой под меню редактирования.")
    return EDIT_MENU


async def remind_delete_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Используй кнопки под фотографией.")
    return DELETE_PHOTOS


async def publish_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    photos = context.user_data.get("photos", [])
    if not photos:
        await query.edit_message_text("Добавь хотя бы одну фотографию перед публикацией.")
        return ConversationHandler.END

    caption = publication_caption(context)
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text("Публикую работу…", reply_markup=None)

    try:
        if len(photos) == 1:
            await context.bot.send_photo(
                chat_id=TARGET_CHAT_ID,
                photo=photos[0],
                caption=caption,
            )
        else:
            for start_index in range(0, len(photos), 10):
                batch = photos[start_index:start_index + 10]
                media = [
                    InputMediaPhoto(
                        media=photo,
                        caption=caption if index == 0 else None,
                    )
                    for index, photo in enumerate(batch)
                ]
                await context.bot.send_media_group(
                    chat_id=TARGET_CHAT_ID,
                    media=media,
                )
    except Exception as error:
        logger.error("Ошибка публикации (%s)", type(error).__name__)
        await query.message.reply_text(
            "Не удалось опубликовать работу. Данные сохранены — попробуй ещё раз."
        )
        context.user_data["summary_is_preview"] = False
        await show_preview(context)
        return PREVIEW

    await query.edit_message_text(
        "Спасибо! Работа успешно отправлена 🌸",
        reply_markup=None,
    )
    context.user_data.clear()
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "Отправка отменена. Чтобы начать заново, напиши /start.",
        reply_markup=ReplyKeyboardRemove(),
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
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_work_type),
            ],
            SUBJECT: [
                CallbackQueryHandler(receive_subject, pattern=r"^subject:\d+$"),
                CallbackQueryHandler(back_to_edit_menu, pattern=r"^subject:edit_back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_choose_subject),
            ],
            TEACHER: [
                CallbackQueryHandler(back_to_subjects, pattern=r"^subject:back$"),
                CallbackQueryHandler(receive_teacher, pattern=r"^teacher:\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_choose_teacher),
            ],
            PREVIEW: [
                CallbackQueryHandler(publish_submission, pattern=r"^preview:publish$"),
                CallbackQueryHandler(show_edit_menu, pattern=r"^preview:edit$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_preview_button),
            ],
            EDIT_MENU: [
                CallbackQueryHandler(edit_work_type, pattern=r"^edit:type$"),
                CallbackQueryHandler(edit_subject, pattern=r"^edit:subject$"),
                CallbackQueryHandler(edit_teacher, pattern=r"^edit:teacher$"),
                CallbackQueryHandler(add_photos, pattern=r"^edit:add_photos$"),
                CallbackQueryHandler(delete_photos, pattern=r"^edit:delete_photos$"),
                CallbackQueryHandler(return_to_preview, pattern=r"^edit:preview$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_edit_button),
            ],
            EDIT_WORK_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_edited_work_type),
            ],
            ADD_PHOTOS: [
                MessageHandler(filters.PHOTO, receive_additional_photo),
                MessageHandler(filters.Regex(r"^Готово$"), finish_additional_photos),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_add_photos),
            ],
            DELETE_PHOTOS: [
                CallbackQueryHandler(handle_photo_deletion, pattern=r"^photo:(prev|next|delete|done)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_delete_button),
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

