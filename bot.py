import asyncio
import json
import logging
import os
from pathlib import Path

from telegram import (
    Update,
    InputMediaPhoto,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.error import Forbidden, RetryAfter, TelegramError
from telegram.ext import (
    Application,
    ApplicationHandlerStop,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    ConversationHandler,
    filters,
)

PHOTOS, WORK_TYPE, SUBJECT, TEACHER, PREVIEW, EDIT_MENU, EDIT_WORK_TYPE, ADD_PHOTOS, DELETE_PHOTOS, CUSTOM_SUBJECT, CUSTOM_TEACHER, CONTACT_ADMIN = range(12)

TOKEN = os.getenv("BOT_TOKEN")
TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "0"))
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "").strip()
CONTACT_ADMIN_TEXT = "👤 Связаться с админом"
END_CONTACT_TEXT = "Закончить связь"

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

DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data"))
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"
SUPPORT_ROUTES_FILE = DATA_DIR / "support_routes.json"


def load_support_routes():
    try:
        data = json.loads(SUPPORT_ROUTES_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    routes = {}
    for message_id, user_chat_id in data.items():
        try:
            routes[str(int(message_id))] = int(user_chat_id)
        except (TypeError, ValueError):
            continue
    return routes


SUPPORT_ROUTES = load_support_routes()


def save_support_routes():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temporary_file = SUPPORT_ROUTES_FILE.with_suffix(".tmp")
        temporary_file.write_text(json.dumps(SUPPORT_ROUTES), encoding="utf-8")
        os.chmod(temporary_file, 0o600)
        os.replace(temporary_file, SUPPORT_ROUTES_FILE)
    except OSError as error:
        logger.error("Could not save support routes (%s)", type(error).__name__)


def load_subscriber_state():
    try:
        data = json.loads(SUBSCRIBERS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set(), set()
    except (OSError, json.JSONDecodeError) as error:
        logger.error("Could not read subscriber list (%s)", type(error).__name__)
        return set(), set()

    if not isinstance(data, dict):
        return set(), set()

    def parse_ids(key):
        ids = set()
        for value in data.get(key, []):
            try:
                ids.add(int(value))
            except (TypeError, ValueError):
                continue
        return ids

    return parse_ids("chat_ids"), parse_ids("unsubscribed_chat_ids")


SUBSCRIBERS, UNSUBSCRIBED_CHAT_IDS = load_subscriber_state()


def save_subscriber_state():
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        temporary_file = SUBSCRIBERS_FILE.with_suffix(".tmp")
        temporary_file.write_text(
            json.dumps({
                "chat_ids": sorted(SUBSCRIBERS),
                "unsubscribed_chat_ids": sorted(UNSUBSCRIBED_CHAT_IDS),
            }),
            encoding="utf-8",
        )
        os.chmod(temporary_file, 0o600)
        os.replace(temporary_file, SUBSCRIBERS_FILE)
    except OSError as error:
        logger.error("Could not save subscriber list (%s)", type(error).__name__)


def subscribe_chat(chat_id):
    changed = chat_id in UNSUBSCRIBED_CHAT_IDS or chat_id not in SUBSCRIBERS
    UNSUBSCRIBED_CHAT_IDS.discard(chat_id)
    SUBSCRIBERS.add(chat_id)
    if changed:
        save_subscriber_state()


def unsubscribe_chat(chat_id):
    changed = chat_id not in UNSUBSCRIBED_CHAT_IDS or chat_id in SUBSCRIBERS
    SUBSCRIBERS.discard(chat_id)
    UNSUBSCRIBED_CHAT_IDS.add(chat_id)
    if changed:
        save_subscriber_state()


def photo_collection_keyboard():
    return ReplyKeyboardMarkup(
        [["Готово", CONTACT_ADMIN_TEXT]],
        resize_keyboard=True,
    )


def end_contact_keyboard():
    return ReplyKeyboardMarkup([[END_CONTACT_TEXT]], resize_keyboard=True)


async def remember_private_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if (
        chat
        and chat.type == "private"
        and chat.id not in UNSUBSCRIBED_CHAT_IDS
        and chat.id not in SUBSCRIBERS
    ):
        subscribe_chat(chat.id)


def subject_keyboard(show_edit_back=False):
    buttons = [
        [InlineKeyboardButton(subject, callback_data=f"subject:{index}")]
        for index, subject in enumerate(TEACHERS_BY_SUBJECT)
    ]
    buttons.append([InlineKeyboardButton("Другое", callback_data="subject:other")])
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
    if update.effective_chat and update.effective_chat.type == "private":
        subscribe_chat(update.effective_chat.id)
    context.user_data.clear()
    context.user_data["photos"] = []
    context.user_data["chat_id"] = update.effective_chat.id

    keyboard = photo_collection_keyboard()
    await update.message.reply_text(
        "Привет! 👋\n\n"
        "Отправь фотографии своей работы.\n"
        "Количество фотографий не ограничено.\n"
        "Когда закончишь, нажми «Готово».\n"
        "Чтобы задать вопрос, нажми «Связаться с админом».\n\n"
        "Отказаться от объявлений можно командой /stop.",
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


async def open_admin_contact(update: Update, context: ContextTypes.DEFAULT_TYPE, return_state: int):
    try:
        admin_chat_id = int(ADMIN_USER_ID)
    except (TypeError, ValueError):
        await update.message.reply_text(
            "Связь с администратором пока не настроена. Попробуй позже.",
            reply_markup=photo_collection_keyboard(),
        )
        return return_state

    if update.effective_chat.id == admin_chat_id:
        await update.message.reply_text(
            "Эта кнопка предназначена для вопросов администратору.",
            reply_markup=photo_collection_keyboard(),
        )
        return return_state

    context.user_data["support_return_state"] = return_state
    await update.message.reply_text(
        "Напиши сообщение администратору. Текст, фото и файлы будут переданы ему. "
        "Когда закончишь, нажми «Закончить связь».",
        reply_markup=end_contact_keyboard(),
    )
    return CONTACT_ADMIN


async def open_admin_contact_from_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await open_admin_contact(update, context, PHOTOS)


async def open_admin_contact_from_additional_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await open_admin_contact(update, context, ADD_PHOTOS)


async def finish_admin_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return_state = context.user_data.pop("support_return_state", PHOTOS)
    await update.message.reply_text(
        "Связь с администратором завершена. Можешь продолжить отправку фотографий.",
        reply_markup=photo_collection_keyboard(),
    )
    return return_state


async def send_support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    try:
        admin_chat_id = int(ADMIN_USER_ID)
    except (TypeError, ValueError):
        await message.reply_text(
            "Связь с администратором пока не настроена.",
            reply_markup=end_contact_keyboard(),
        )
        return CONTACT_ADMIN

    name = user.full_name if user else "Пользователь"
    if user and user.username:
        name += f" (@{user.username})"
    if user:
        name += f"\nTelegram ID: {user.id}"

    try:
        await context.bot.send_message(
            chat_id=admin_chat_id,
            text=(
                f"✉️ Сообщение от {name}\n"
                "Ответь на сообщение ниже — бот передаст ответ ученику."
            ),
        )
        copied = await context.bot.copy_message(
            chat_id=admin_chat_id,
            from_chat_id=chat.id,
            message_id=message.message_id,
        )
    except TelegramError as error:
        logger.warning("Could not deliver support message (%s)", type(error).__name__)
        await message.reply_text(
            "Не получилось передать сообщение. Попробуй ещё раз чуть позже.",
            reply_markup=end_contact_keyboard(),
        )
        return CONTACT_ADMIN

    SUPPORT_ROUTES[str(copied.message_id)] = chat.id
    save_support_routes()
    await message.reply_text(
        "Сообщение передано администратору. Можешь написать ещё или закончить связь.",
        reply_markup=end_contact_keyboard(),
    )
    return CONTACT_ADMIN


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


async def start_custom_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("preview_message_id"):
        context.user_data["preview_message_id"] = query.message.message_id
    context.user_data["summary_is_preview"] = False
    await query.edit_message_text("Напиши название предмета:")
    return CUSTOM_SUBJECT


async def receive_custom_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subject = update.message.text.strip()
    if not subject:
        await update.message.reply_text("Напиши название предмета.")
        return CUSTOM_SUBJECT

    context.user_data["subject"] = subject
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id,
        message_id=context.user_data["preview_message_id"],
        text="Теперь напиши имя преподавателя:",
    )
    return CUSTOM_TEACHER


async def receive_custom_teacher(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teacher = update.message.text.strip()
    if not teacher:
        await update.message.reply_text("Напиши имя преподавателя.")
        return CUSTOM_TEACHER

    context.user_data["teacher"] = teacher
    context.user_data["chat_id"] = update.effective_chat.id
    context.user_data["summary_is_preview"] = False
    context.user_data.pop("subject_before_edit", None)
    context.user_data.pop("teacher_before_edit", None)
    await context.bot.edit_message_text(
        chat_id=context.user_data["chat_id"],
        message_id=context.user_data["preview_message_id"],
        text="Готовлю предпросмотр…",
    )
    await show_preview(context)
    return PREVIEW


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
    if subject not in TEACHERS_BY_SUBJECT:
        await query.edit_message_text("Напиши имя нового преподавателя:")
        return CUSTOM_TEACHER

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
        reply_markup=photo_collection_keyboard(),
    )
    return ADD_PHOTOS


async def receive_additional_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["photos"].append(update.message.photo[-1].file_id)
    count = len(context.user_data["photos"])
    await update.message.reply_text(
        f"Фото добавлено! 📸 Всего фотографий: {count}.\n"
        "Можешь отправить ещё или нажать «Готово».",
        reply_markup=photo_collection_keyboard(),
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


async def show_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user or not update.effective_chat:
        return
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text("Напиши /myid в личном чате с ботом.")
        return
    await update.effective_message.reply_text(
        f"Твой Telegram ID: {update.effective_user.id}"
    )


async def stop_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat and update.effective_chat.type == "private":
        unsubscribe_chat(update.effective_chat.id)
        await update.effective_message.reply_text(
            "Рассылки отключены. Чтобы снова подписаться, отправь /start."
        )
    else:
        await update.effective_message.reply_text(
            "Отключить рассылки можно в личном чате с ботом."
        )


async def route_admin_support_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if (
        not message
        or not user
        or not chat
        or not ADMIN_USER_ID
        or str(user.id) != ADMIN_USER_ID
        or not message.reply_to_message
        or (message.text or "").startswith("/")
    ):
        return

    target_chat_id = SUPPORT_ROUTES.get(str(message.reply_to_message.message_id))
    if not target_chat_id:
        return

    try:
        await context.bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=chat.id,
            message_id=message.message_id,
        )
    except TelegramError as error:
        logger.warning("Could not deliver admin reply (%s)", type(error).__name__)
        await message.reply_text("Не удалось передать ответ ученику.")
    else:
        await message.reply_text("Ответ отправлен ученику.")
    raise ApplicationHandlerStop


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user
    chat = update.effective_chat
    if not message or not user or not chat or chat.type != "private":
        if message:
            await message.reply_text("Команду /broadcast используй в личном чате с ботом.")
        return

    if not ADMIN_USER_ID or str(user.id) != ADMIN_USER_ID:
        await message.reply_text("Эта команда доступна только администратору.")
        return

    parts = (message.text or "").split(maxsplit=1)
    text = parts[1].strip() if len(parts) > 1 else ""
    if not text:
        await message.reply_text("Формат команды: /broadcast текст сообщения")
        return
    if len(text) > 4096:
        await message.reply_text("Сообщение слишком длинное — максимум 4096 символов.")
        return

    recipients = sorted(SUBSCRIBERS - {chat.id})
    if not recipients:
        await message.reply_text(
            "Пока некому отправить сообщение. Пользователям нужно открыть бота и отправить /start."
        )
        return

    sent = 0
    failed = 0
    blocked = 0
    await message.reply_text(f"Начинаю рассылку: {len(recipients)} получателей.")

    for chat_id in recipients:
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            sent += 1
        except RetryAfter as error:
            retry_after = error.retry_after
            if hasattr(retry_after, "total_seconds"):
                retry_after = retry_after.total_seconds()
            await asyncio.sleep(float(retry_after) + 0.1)
            try:
                await context.bot.send_message(chat_id=chat_id, text=text)
                sent += 1
            except Forbidden:
                SUBSCRIBERS.discard(chat_id)
                blocked += 1
            except TelegramError as retry_error:
                logger.warning(
                    "Broadcast delivery failed (%s)",
                    type(retry_error).__name__,
                )
                failed += 1
        except Forbidden:
            SUBSCRIBERS.discard(chat_id)
            blocked += 1
        except TelegramError as error:
            logger.warning("Broadcast delivery failed (%s)", type(error).__name__)
            failed += 1
        await asyncio.sleep(0.05)

    if blocked:
        save_subscriber_state()
    await message.reply_text(
        f"Рассылка завершена. Доставлено: {sent}; не доставлено: {failed + blocked}."
    )


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
                MessageHandler(filters.Regex(r"^👤 Связаться с админом$"), open_admin_contact_from_photos),
            ],
            CONTACT_ADMIN: [
                MessageHandler(filters.Regex(r"^Закончить связь$"), finish_admin_contact),
                MessageHandler(filters.ALL & ~filters.COMMAND, send_support_message),
            ],
            WORK_TYPE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_work_type),
            ],
            SUBJECT: [
                CallbackQueryHandler(receive_subject, pattern=r"^subject:\d+$"),
                CallbackQueryHandler(start_custom_subject, pattern=r"^subject:other$"),
                CallbackQueryHandler(back_to_edit_menu, pattern=r"^subject:edit_back$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_choose_subject),
            ],
            TEACHER: [
                CallbackQueryHandler(back_to_subjects, pattern=r"^subject:back$"),
                CallbackQueryHandler(receive_teacher, pattern=r"^teacher:\d+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, remind_choose_teacher),
            ],
            CUSTOM_SUBJECT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_subject),
            ],
            CUSTOM_TEACHER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_teacher),
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
                MessageHandler(filters.Regex(r"^👤 Связаться с админом$"), open_admin_contact_from_additional_photos),
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

    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.REPLY,
            route_admin_support_reply,
        ),
        group=-2,
    )
    app.add_handler(conversation)
    app.add_handler(
        MessageHandler(filters.ALL, remember_private_user),
        group=-1,
    )
    app.add_handler(CommandHandler("myid", show_my_id), group=1)
    app.add_handler(CommandHandler("stop", stop_notifications), group=1)
    app.add_handler(CommandHandler("broadcast", broadcast_message), group=1)

    print("Photo Publisher запущен!")
    app.run_polling()


if __name__ == "__main__":
    main()

