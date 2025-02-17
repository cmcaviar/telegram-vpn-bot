import pytz

from dbworker import User
from telebot import types
import emoji as e
from datetime import datetime, timezone


CONFIG={}
UTC_PLUS_3 = pytz.timezone('Europe/Moscow')  # Москва в UTC+3

async def main_buttons(user: User):
    Butt_main = types.ReplyKeyboardMarkup(resize_keyboard=True)


    if CONFIG["admin_tg_id"] == user.tgid:
        Butt_main.add(types.KeyboardButton(e.emojize(f"Админ-панель :smiling_face_with_sunglasses:")))

    Butt_main.add(
        types.KeyboardButton(e.emojize(f":small_blue_diamond: :calendar: Информация о подписке :calendar: :small_blue_diamond:", language='alias'))
    )
    Butt_main.add(
        types.KeyboardButton(e.emojize(f"Приобрести доступ :money_bag:")),
        types.KeyboardButton(e.emojize(f"Как подключить :gear:"))
    )
    Butt_main.add(
        types.KeyboardButton(e.emojize(f":gift: Хочу бесплатный VPN! :gift:", language='alias'))
    )

    return Butt_main




async def admin_buttons():
    Butt_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Butt_admin.add(types.KeyboardButton(e.emojize(f":loudspeaker: Уведомление пользователей")))
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Вывести пользователей :bust_in_silhouette:")))
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Редактировать пользователя по id :pencil:")))
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Статичные пользователи")))
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Редактировать каналы")))
    Butt_admin.add(types.KeyboardButton(e.emojize("Главное меню :right_arrow_curving_left:")))
    return Butt_admin

async def admin_buttons_output_users():
    Butt_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Пользователей с подпиской")))
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Всех пользователей")))
    Butt_admin.add(types.KeyboardButton(e.emojize("Назад :right_arrow_curving_left:")))
    return Butt_admin

async def admin_buttons_channels():
    Butt_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Добавить канал")))
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Удалить канал")))
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Отчет по подпискам")))
    Butt_admin.add(types.KeyboardButton(e.emojize("Назад :right_arrow_curving_left:")))
    return Butt_admin


async def admin_buttons_static_users():
    Butt_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Добавить пользователя :plus:")))
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Вывести статичных пользователей")))
    Butt_admin.add(types.KeyboardButton(e.emojize("Назад :right_arrow_curving_left:")))
    return Butt_admin

async def admin_buttons_edit_user(user: User):
    Butt_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Butt_admin.add(types.KeyboardButton(e.emojize(f"Добавить время")))
    if ((user.subscription and user.subscription.replace(tzinfo=timezone.utc) > datetime.now(pytz.utc).astimezone(UTC_PLUS_3))
            or (user.sub_trial and user.sub_trial.replace(tzinfo=timezone.utc) > datetime.now(pytz.utc).astimezone(UTC_PLUS_3))):
        Butt_admin.add(types.KeyboardButton(e.emojize(f"Обнулить время")))
    Butt_admin.add(types.KeyboardButton(e.emojize("Назад :right_arrow_curving_left:")))
    return Butt_admin

async def admin_buttons_back():
    Butt_admin = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Butt_admin.add(types.KeyboardButton(e.emojize("Назад :right_arrow_curving_left:")))
    return Butt_admin
