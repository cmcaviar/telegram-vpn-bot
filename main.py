import json
import string
import subprocess
import pytz
from datetime import datetime, timedelta
import time

import asyncpg
import docker

import buttons
import dbworker

from telebot import asyncio_filters
from telebot.async_telebot import AsyncTeleBot
import emoji as e
import asyncio
from telebot import types
from telebot.asyncio_storage import StateMemoryStorage
from telebot.asyncio_handler_backends import State, StatesGroup
from yoyo import get_backend, read_migrations

from logger import logger
from buttons import main_buttons
from dbworker import User

with open("config.json", encoding="utf-8") as file_handler:
    CONFIG = json.load(file_handler)
    dbworker.CONFIG = CONFIG
    buttons.CONFIG = CONFIG
with open("texts.json", encoding="utf-8") as file_handler:
    text_mess = json.load(file_handler)
    texts_for_bot = text_mess

BOTAPIKEY = CONFIG["tg_token"]

bot = AsyncTeleBot(CONFIG["tg_token"], state_storage=StateMemoryStorage())
# Часовой пояс UTC+3
MOSCOW_TZ = pytz.timezone("Europe/Moscow")


class MyStates(StatesGroup):
    findUserViaId = State()
    editUser = State()
    editUserResetTime = State()

    UserAddTimeDays = State()
    UserAddTimeHours = State()
    UserAddTimeMinutes = State()
    UserAddTimeApprove = State()

    waiting_for_message = State()
    confirm_send = State()

    AdminNewUser = State()

    checkSubscription = State()

    AddChannelName = State()
    AddChannelID = State()
    AddChannelLink = State()
    ConfirmAddChannel = State()
    DeleteChannels = State()
    DeleteChannelByName = State()


def start_postgres_container():
    client = docker.from_env()

    # Проверяем, запущен ли контейнер
    containers = client.containers.list(filters={"name": "my_postgres"})
    if containers:
        logger.info("PostgreSQL контейнер уже запущен.")
        return

    # Запускаем контейнер с помощью docker-compose
    logger.info("Запуск PostgreSQL контейнера...")
    subprocess.run(["docker-compose", "up", "-d"], check=True)

    # Ждем, пока PostgreSQL станет доступным
    logger.info("Ожидание готовности PostgreSQL...")
    time.sleep(5)  # Можно заменить на более сложную проверку


async def create_db_pool():
    return await asyncpg.create_pool(
        user="user",
        password="1231234",
        database="vpn-bot",
        host="localhost",
        port=5432,
        min_size=2,
        max_size=10
    )


async def run_migrations():
    db_url = "postgresql://user:1231234@localhost:5432/vpn-bot"
    backend = get_backend(db_url)
    migrations = read_migrations("my_migrations")

    with backend.lock():
        backend.apply_migrations(backend.to_apply(migrations))

    logger.info("Все миграции успешно применены")


async def main():
    # Запускаем контейнер при старте приложения
    start_postgres_container()
    global pool
    # Создаем пул соединений
    pool = await create_db_pool()
    logger.info("Пул соединений создан.")
    await run_migrations()


    asyncio.create_task(subscription_checker())
    asyncio.create_task(checkTime())
    logger.info("Subscription checker started")

    # Запускаем бота
    await bot.polling(non_stop=True, interval=0, request_timeout=60, timeout=60)



@bot.message_handler(commands=['start'])
async def start(message: types.Message):
    global pool
    if message.chat.type == "private":
        await bot.delete_state(message.from_user.id)
        user_dat = await User.GetInfo(pool=pool, tgid=message.chat.id)
        if user_dat.registered:
            await bot.send_message(message.chat.id, "Информация о подписке", parse_mode="HTML",
                                   reply_markup=await main_buttons(user_dat))
        else:
            try:
                username = "@" + str(message.from_user.username)
            except:

                username = str(message.from_user.id)

            await user_dat.Adduser(username=username, full_name=message.from_user.full_name, pool=pool)
            user_dat = await User.GetInfo(pool, message.chat.id)
            await bot.send_message(message.chat.id, e.emojize(texts_for_bot["hello_message"]), parse_mode="HTML",
                                   reply_markup=await main_buttons(user_dat))
            await bot.send_message(message.chat.id, e.emojize(texts_for_bot["hello_message2"]), parse_mode="HTML")



@bot.message_handler(state=MyStates.editUser, content_types=["text"])
async def Work_with_Message(m: types.Message):
    global pool
    async with bot.retrieve_data(m.from_user.id) as data:
        tgid = data['usertgid']
    user_dat = await User.GetInfo(pool=pool, tgid=tgid)
    if e.demojize(m.text) == "Назад :right_arrow_curving_left:":
        await bot.reset_data(m.from_user.id)
        await bot.delete_state(m.from_user.id)
        await bot.send_message(m.from_user.id, "Вернул вас назад!", reply_markup=await buttons.admin_buttons())
        return
    if e.demojize(m.text) == "Добавить время":
        await bot.set_state(m.from_user.id, MyStates.UserAddTimeDays)
        Butt_skip = types.ReplyKeyboardMarkup(resize_keyboard=True)
        Butt_skip.add(types.KeyboardButton(e.emojize(f"Пропустить :next_track_button:")))
        await bot.send_message(m.from_user.id, "Введите сколько дней хотите добавить:", reply_markup=Butt_skip)
        return
    if e.demojize(m.text) == "Обнулить время":
        await bot.set_state(m.from_user.id, MyStates.editUserResetTime)
        Butt_skip = types.ReplyKeyboardMarkup(resize_keyboard=True)
        Butt_skip.add(types.KeyboardButton(e.emojize(f"Да")))
        Butt_skip.add(types.KeyboardButton(e.emojize(f"Нет")))
        await bot.send_message(m.from_user.id, "Вы уверены что хотите сбросить время для этого пользователя ?",
                               reply_markup=Butt_skip)
        return


# Обнуление времени пользователю
@bot.message_handler(state=MyStates.editUserResetTime, content_types=["text"])
async def Work_with_Message(m: types.Message):
    global pool
    async with bot.retrieve_data(m.from_user.id) as data:
        tgid = data['usertgid']

    if e.demojize(m.text) == "Да":
        now = datetime.now(pytz.utc).astimezone(MOSCOW_TZ).replace(tzinfo=None)
        async with pool.acquire() as conn:  # Получаем соединение из пула
            await conn.execute(
                "UPDATE userss SET subscription = $1, banned = false, notion_oneday = true WHERE tgid = $2",
                now,  # Время в формате timestamp
                tgid  # Идентификатор пользователя
            )
            await bot.send_message(m.from_user.id, "Время сброшено!")

    async with bot.retrieve_data(m.from_user.id) as data:
        usertgid = data['usertgid']
    user_dat = await User.GetInfo(pool=pool, tgid=tgid)

    readymes = f"Пользователь: <b>{str(user_dat.fullname)}</b> ({str(user_dat.username)})\nTG-id: <code>{str(user_dat.tgid)}</code>\n\n"

    if user_dat.subscription > datetime.now():
        readymes += f"Подписка: до <b>{user_dat.subscription.strftime('%d.%m.%Y %H:%M')}</b> ✅"
    else:
        readymes += f"Подписка: закончилась <b>{user_dat.subscription.strftime('%d.%m.%Y %H:%M')}</b> ❌"

    await bot.set_state(m.from_user.id, MyStates.editUser)

    await bot.send_message(
        m.from_user.id, e.emojize(readymes),
        reply_markup=await buttons.admin_buttons_edit_user(user_dat),
        parse_mode="HTML"
    )


@bot.message_handler(state=MyStates.UserAddTimeDays, content_types=["text"])
async def Work_with_Message(m: types.Message):
    if e.demojize(m.text) == "Пропустить :next_track_button:":
        days = 0
    else:
        try:
            days = int(m.text)
        except:
            await bot.send_message(m.from_user.id, "Должно быть число!\nПопробуйте еще раз.")
            return
        if days < 0:
            await bot.send_message(m.from_user.id, "Не должно быть отрицательным числом!\nПопробуйте еще раз.")
            return

    async with bot.retrieve_data(m.from_user.id) as data:
        data['days'] = days
    await bot.set_state(m.from_user.id, MyStates.UserAddTimeHours)
    Butt_skip = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Butt_skip.add(types.KeyboardButton(e.emojize(f"Пропустить :next_track_button:")))
    await bot.send_message(m.from_user.id, "Введите сколько часов хотите добавить:", reply_markup=Butt_skip)


@bot.message_handler(state=MyStates.UserAddTimeHours, content_types=["text"])
async def Work_with_Message(m: types.Message):
    if e.demojize(m.text) == "Пропустить :next_track_button:":
        hours = 0
    else:
        try:
            hours = int(m.text)
        except:
            await bot.send_message(m.from_user.id, "Должно быть число!\nПопробуйте еще раз.")
            return
        if hours < 0:
            await bot.send_message(m.from_user.id, "Не должно быть отрицательным числом!\nПопробуйте еще раз.")
            return

    async with bot.retrieve_data(m.from_user.id) as data:
        data['hours'] = hours
    await bot.set_state(m.from_user.id, MyStates.UserAddTimeMinutes)
    Butt_skip = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Butt_skip.add(types.KeyboardButton(e.emojize(f"Пропустить :next_track_button:")))
    await bot.send_message(m.from_user.id, "Введите сколько минут хотите добавить:", reply_markup=Butt_skip)


@bot.message_handler(state=MyStates.UserAddTimeMinutes, content_types=["text"])
async def Work_with_Message(m: types.Message):
    if e.demojize(m.text) == "Пропустить :next_track_button:":
        minutes = 0
    else:
        try:
            minutes = int(m.text)
        except:
            await bot.send_message(m.from_user.id, "Должно быть число!\nПопробуйте еще раз.")
            return
        if minutes < 0:
            await bot.send_message(m.from_user.id, "Не должно быть отрицательным числом!\nПопробуйте еще раз.")
            return

    async with bot.retrieve_data(m.from_user.id) as data:
        data['minutes'] = minutes
        hours = data['hours']
        days = data['days']
        tgid = data['usertgid']

    await bot.set_state(m.from_user.id, MyStates.UserAddTimeApprove)
    Butt_skip = types.ReplyKeyboardMarkup(resize_keyboard=True)
    Butt_skip.add(types.KeyboardButton(e.emojize(f"Да")))
    Butt_skip.add(types.KeyboardButton(e.emojize(f"Нет")))
    await bot.send_message(m.from_user.id,
                           f"Пользователю {str(tgid)} добавится:\n\nДни: {str(days)}\nЧасы: {str(hours)}\nМинуты: {str(minutes)}\n\nВсе верно ?",
                           reply_markup=Butt_skip)


@bot.message_handler(state=MyStates.UserAddTimeApprove, content_types=["text"])
async def Work_with_Message(m: types.Message):
    all_time = 0
    if e.demojize(m.text) == "Да":
        async with bot.retrieve_data(m.from_user.id) as data:
            minutes = data['minutes']
            hours = data['hours']
            days = data['days']
            tgid = data['usertgid']
        all_time += minutes * 60
        all_time += hours * 60 * 60
        all_time += days * 60 * 60 * 24
        await AddTimeToUser(tgid, all_time)
        await bot.send_message(m.from_user.id, e.emojize("Время добавлено пользователю!"), parse_mode="HTML")

    async with bot.retrieve_data(m.from_user.id) as data:
        usertgid = data['usertgid']
    user_dat = await User.GetInfo(pool=pool, tgid=tgid)
    readymes = f"Пользователь: <b>{str(user_dat.fullname)}</b> ({str(user_dat.username)})\nTG-id: <code>{str(user_dat.tgid)}</code>\n\n"

    if user_dat.subscription > datetime.now():
        readymes += f"Подписка: до <b>{user_dat.subscription.strftime('%d.%m.%Y %H:%M')}</b> ✅"
    else:
        readymes += f"Подписка: закончилась <b>{user_dat.subscription.strftime('%d.%m.%Y %H:%M')}</b> ❌"

    await bot.set_state(m.from_user.id, MyStates.editUser)

    await bot.send_message(
        m.from_user.id, e.emojize(readymes),
        reply_markup=await buttons.admin_buttons_edit_user(user_dat),
        parse_mode="HTML"
    )


@bot.message_handler(state=MyStates.findUserViaId, content_types=["text"])
async def Work_with_Message(m: types.Message):
    global pool
    await bot.delete_state(m.from_user.id)
    try:
        user_id = int(m.text)
    except:
        await bot.send_message(m.from_user.id, "Неверный Id!", reply_markup=await buttons.admin_buttons())
        return
    user_dat = await User.GetInfo(pool=pool, tgid=user_id)
    if not user_dat.registered:
        await bot.send_message(m.from_user.id, "Такого пользователя не существует!",
                               reply_markup=await buttons.admin_buttons())
        return

    readymes = f"Пользователь: <b>{str(user_dat.fullname)}</b> ({str(user_dat.username)})\nTG-id: <code>{str(user_dat.tgid)}</code>\n\n"

    sub_trial = user_dat.sub_trial
    sub_end_paid = user_dat.subscription

    # Определяем, какая дата позже
    latest_sub_end = max(filter(None, [sub_trial, sub_end_paid]), default=None)

    if latest_sub_end:
        if latest_sub_end.replace(tzinfo=MOSCOW_TZ) > datetime.now(MOSCOW_TZ).astimezone(MOSCOW_TZ):
            readymes += f"Подписка: до <b>{latest_sub_end.strftime('%d.%m.%Y %H:%M')}</b> ✅"
        else:
            readymes += f"Подписка: закончилась <b>{latest_sub_end.strftime('%d.%m.%Y %H:%M')}</b>❌"
    else: readymes += f"Подписки пока нет"


    await bot.set_state(m.from_user.id, MyStates.editUser)
    async with bot.retrieve_data(m.from_user.id) as data:
        data['usertgid'] = user_dat.tgid

    await bot.send_message(
        m.from_user.id, e.emojize(readymes),
        reply_markup=await buttons.admin_buttons_edit_user(user_dat),
        parse_mode="HTML"
    )


@bot.message_handler(state=MyStates.AdminNewUser, content_types=["text"])
async def Work_with_Message(m: types.Message):
    if e.demojize(m.text) == "Назад :right_arrow_curving_left:":
        await bot.delete_state(m.from_user.id)
        await bot.send_message(m.from_user.id, "Вернул вас назад!", reply_markup=await buttons.admin_buttons())
        return

    if set(m.text) <= set(string.ascii_letters + string.digits):
        async with pool.acquire() as conn:
            await conn.execute(f"INSERT INTO static_profiles (name) values (?)", (m.text,))
        check = subprocess.call(f'./addusertovpn.sh {str(m.text)}', shell=True)
        await bot.delete_state(m.from_user.id)
        await bot.send_message(m.from_user.id,
                               "Пользователь добавлен!", reply_markup=await buttons.admin_buttons_static_users())
    else:
        await bot.send_message(m.from_user.id,
                               "Можно использовать только латинские символы и арабские цифры!\nПопробуйте заново.")
        return


@bot.message_handler(state=MyStates.AddChannelName, content_types=["text"])
async def add_channel_name(m: types.Message):
    async with bot.retrieve_data(m.from_user.id) as data:
        data['channel_name'] = m.text

    await bot.set_state(m.from_user.id, MyStates.AddChannelID)
    await bot.send_message(m.from_user.id, "Введите ID канала (отрицательное число):")


@bot.message_handler(state=MyStates.AddChannelID, content_types=["text"])
async def add_channel_id(m: types.Message):
    try:
        channel_id = int(m.text)
    except ValueError:
        await bot.send_message(m.from_user.id, "ID должен быть числом! Попробуйте еще раз.")
        return

    async with bot.retrieve_data(m.from_user.id) as data:
        data['channel_id'] = channel_id

    await bot.set_state(m.from_user.id, MyStates.AddChannelLink)
    await bot.send_message(m.from_user.id, "Введите ссылку на канал (например, https://t.me/mychannel):")


@bot.message_handler(state=MyStates.AddChannelLink, content_types=["text"])
async def add_channel_link(m: types.Message):
    channel_link = m.text

    async with bot.retrieve_data(m.from_user.id) as data:
        data['channel_link'] = channel_link
        channel_name = data['channel_name']
        channel_id = data['channel_id']

    # Подтверждение перед добавлением
    await bot.set_state(m.from_user.id, MyStates.ConfirmAddChannel)
    confirm_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    confirm_markup.add(types.KeyboardButton("✅ Подтвердить"))
    confirm_markup.add(types.KeyboardButton("❌ Отмена"))

    await bot.send_message(m.from_user.id,
                           f"Вы хотите добавить канал:\n\n"
                           f"📢 Название: <b>{channel_name}</b>\n"
                           f"🆔 ID: <code>{channel_id}</code>\n"
                           f"🔗 Ссылка: {channel_link}\n\n"
                           f"Все верно?",
                           reply_markup=confirm_markup, parse_mode="HTML")


@bot.message_handler(state=MyStates.ConfirmAddChannel, content_types=["text"])
async def confirm_add_channel(m: types.Message):
    global pool
    if m.text == "✅ Подтвердить":
        async with bot.retrieve_data(m.from_user.id) as data:
            channel_name = data['channel_name']
            channel_id = data['channel_id']
            channel_link = data['channel_link']

        # Добавляем в базу данных
        await User.AddChannels(pool, channel_id, channel_name, channel_link)

        channels = await User.get_subscription_channels(pool=pool)
        if channels:
            channels_list = "\n".join([f"🔹 {channel['name']} | {channel['invite_link']}" for channel in channels])
        await bot.send_message(m.from_user.id, "✅ Канал успешно добавлен! Активные каналы: \n" + channels_list,
                               parse_mode="HTML", reply_markup=await buttons.admin_buttons())

    else:
        await bot.send_message(m.from_user.id, "❌ Добавление канала отменено.",
                               reply_markup=await buttons.admin_buttons_channels())

    await bot.delete_state(m.from_user.id)
    return

@bot.message_handler(state=MyStates.DeleteChannels, content_types=["text"])
async def delete_channels(m: types.Message):
    global pool
    if m.text == "Отмена":
            await bot.send_message(m.from_user.id, "Админ панель", reply_markup=await buttons.admin_buttons())
            return
    if m.text == "Удалить все каналы ❌":
        await User.DeleteChannels(pool=pool)
        await bot.send_message(m.from_user.id, "Каналы удалены!", reply_markup=await buttons.admin_buttons())
        return
    else:
        channels = await User.get_subscription_channels(pool=pool)

        if channels:
            channels_list = "\n".join(
                [f"🔹 <code>{channel['name']}</code> | {channel['invite_link']}" for channel in channels])
            await bot.send_message(m.from_user.id,
                                   f"Введите название канала, который хотите удалить:\n\n{channels_list}",
                                   reply_markup=types.ReplyKeyboardRemove(), parse_mode="HTML")
            await bot.set_state(m.from_user.id, MyStates.DeleteChannelByName)
        else:
            await bot.send_message(m.from_user.id, "❌ У вас нет добавленных каналов.",
                                   reply_markup=types.ReplyKeyboardRemove())
        return

@bot.message_handler(state=MyStates.waiting_for_message, content_types=["text"])
async def confirm_notification(m: types.Message):
    async with bot.retrieve_data(m.from_user.id) as data:
        data['notification_text'] = m.text

    confirm_markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    confirm_markup.add(types.KeyboardButton("✅ Подтвердить"))
    confirm_markup.add(types.KeyboardButton("❌ Отмена"))

    await bot.set_state(m.from_user.id, MyStates.confirm_send)
    await bot.send_message(m.from_user.id,
                           f"Вы уверены, что хотите отправить это сообщение?\n\n"
                           f"<b>{m.text}</b>",
                           parse_mode="HTML",
                           reply_markup=confirm_markup)

@bot.message_handler(state=MyStates.confirm_send, content_types=["text"])
async def process_notification_decision(m: types.Message):
    global pool
    if m.text == "✅ Подтвердить":
        async with bot.retrieve_data(m.from_user.id) as data:
            notification_text = data['notification_text']

        # Получаем список пользователей из базы
        async with pool.acquire() as conn:
            users = await conn.fetch("SELECT tgid FROM userss WHERE banned = FALSE")

        sent_count = 0
        for user in users:
            try:
                await bot.send_message(user["tgid"], notification_text)
                sent_count += 1
            except Exception as e:
                logger.info(f"Ошибка отправки {user['tgid']}: {e}")

        await bot.send_message(m.from_user.id, f"✅ Сообщение успешно отправлено {sent_count} пользователям.",
                               reply_markup=await buttons.admin_buttons())

    else:
        await bot.send_message(m.from_user.id, "❌ Рассылка отменена.",
                               reply_markup=await buttons.admin_buttons())

    await bot.delete_state(m.from_user.id)
    return

@bot.message_handler(state=MyStates.DeleteChannelByName, content_types=["text"])
async def Work_with_Message(m: types.Message):
    global pool
    await bot.delete_state(m.from_user.id)
    channel_name = m.text
    if len(channel_name) < 1:
        await bot.send_message(m.from_user.id, "Некорректное имя", reply_markup=await buttons.admin_buttons())
        return
    channel = await User.GetChannelByName(pool, channel_name)
    if not channel:
        await bot.send_message(m.from_user.id, "Такого канала не существует!",
                               reply_markup=await buttons.admin_buttons())
        return
    await User.DeleteChannelByName(pool, channel_name)
    await bot.send_message(
        m.from_user.id, e.emojize(f"Канал {channel_name} удален"),
        reply_markup=await buttons.admin_buttons_channels(),
        parse_mode="HTML"
    )


@bot.message_handler(state="*", content_types=["text"])
async def Work_with_Message(m: types.Message):
    global pool
    global MOSCOW_TZ
    user_dat = await User.GetInfo(pool=pool, tgid=m.chat.id)

    if user_dat.registered == False:
        try:
            username = "@" + str(m.from_user.username)
        except:

            username = str(m.from_user.id)

        await user_dat.Adduser(username=username, full_name=m.from_user.full_name, pool=pool)
        await bot.send_message(m.chat.id,
                               texts_for_bot["hello_message"],
                               parse_mode="HTML", reply_markup=await main_buttons(user_dat))
        return
    await user_dat.CheckNewNickname(pool=pool, message=m)

    if m.from_user.id == CONFIG["admin_tg_id"]:
        if e.demojize(m.text) == "Админ-панель :smiling_face_with_sunglasses:":
            await bot.send_message(m.from_user.id, "Админ панель", reply_markup=await buttons.admin_buttons())
            return

        if e.demojize(m.text) == "Главное меню :right_arrow_curving_left:":
            await bot.send_message(m.from_user.id, e.emojize("Админ-панель :smiling_face_with_sunglasses:"),
                                   reply_markup=await main_buttons(user_dat))
            return

        if e.demojize(m.text) == "Вывести пользователей :bust_in_silhouette:":
            await bot.send_message(m.from_user.id, e.emojize("Выберите каких пользователей хотите вывести."),
                                   reply_markup=await buttons.admin_buttons_output_users())
            return

        if e.demojize(m.text) == "Редактировать каналы":
            # Получаем список каналов из базы данных
            channels = await User.get_subscription_channels(pool=pool)

            if channels:
                channels_list = "\n".join([f"🔹 {channel['name']} | {channel['invite_link']}" for channel in channels])
                message_text = f"📢 Ваши каналы:\n\n{channels_list}"
            else:
                message_text = "❌ У вас нет добавленных каналов."

            await bot.send_message(m.from_user.id, e.emojize(message_text),
                                   reply_markup=await buttons.admin_buttons_channels())
            return

        if e.demojize(m.text) == "Добавить канал":
            await bot.set_state(m.from_user.id, MyStates.AddChannelName)
            Butt_skip = types.ReplyKeyboardMarkup(resize_keyboard=True)
            Butt_skip.add(types.KeyboardButton(e.emojize(f"Пропустить :next_track_button:")))
            await bot.send_message(m.from_user.id, "Введите название канала:", reply_markup=Butt_skip)
            return

        if e.demojize(m.text) == "Удалить канал":
            await bot.set_state(m.from_user.id, MyStates.DeleteChannels)
            Butt_main = types.ReplyKeyboardMarkup(resize_keyboard=True)
            Butt_main.add(
                types.KeyboardButton(e.emojize("Удалить все каналы ❌")),
                types.KeyboardButton(e.emojize("Удалить 1 канал")),
                types.KeyboardButton(e.emojize("Отмена"))
            )
            await bot.send_message(m.from_user.id, "Хотите удалить каналы?", reply_markup=Butt_main)
            return
        if e.demojize(m.text) == "Отчет по подпискам":
            async with pool.acquire() as conn:
                # Получаем данные о подписках
                records = await conn.fetch("""
                    SELECT 
                        c.name AS channel_name,
                        c.channel_id,
                        u.username,
                        u.tgid AS user_id
                    FROM channels c
                    LEFT JOIN channel_subscriptions cs ON c.channel_id = cs.channel_id
                    LEFT JOIN userss u ON cs.user_id = u.tgid
                    ORDER BY c.channel_id
                """)

            if not records:
                await bot.send_message(m.chat.id, "Нет данных о подписках")
                return

            # Группируем подписчиков по каналам
            from collections import defaultdict
            import io
            import csv

            subscriptions = defaultdict(list)
            for row in records:
                channel_info = f"{row['channel_name']} ({row['channel_id']})"
                user_info = f"{row['username'] or 'user_' + str(row['user_id'])} ({row['user_id']})"
                subscriptions[channel_info].append(user_info)

            # Создаем CSV
            output = io.StringIO()
            writer = csv.writer(output, delimiter=';')

            # Заголовок с именами каналов
            writer.writerow(subscriptions.keys())

            # Количество подписчиков под каждым каналом
            writer.writerow([len(subscriptions[channel]) for channel in subscriptions])

            # Формируем строки с подписчиками
            max_subs = max(len(users) for users in
                           subscriptions.values())  # Находим максимальное кол-во подписчиков у одного канала
            for i in range(max_subs):
                row = [subscriptions[channel][i] if i < len(subscriptions[channel]) else "" for channel in
                       subscriptions]
                writer.writerow(row)

            # Преобразуем в байты и отправляем
            output.seek(0)
            csv_data = io.BytesIO(output.getvalue().encode())
            csv_data.name = 'subscriptions_report.csv'

            await bot.send_document(
                chat_id=m.chat.id,
                document=csv_data,
                caption="Отчет по подпискам"
            )
        if e.demojize(m.text) == "Назад :right_arrow_curving_left:":
            await bot.send_message(m.from_user.id, "Админ панель", reply_markup=await buttons.admin_buttons())
            return

        if e.demojize(m.text, language='alias') == ":loudspeaker: Уведомление пользователей":
            await bot.set_state(m.from_user.id, MyStates.waiting_for_message)
            await bot.send_message(m.from_user.id, "✍ Введите сообщение для рассылки:")

        if e.demojize(m.text) == "Всех пользователей":
            allusers = await user_dat.GetAllUsers(pool=pool)
            await showUsers(user_dat, allusers, m)
            return

        if e.demojize(m.text) == "Пользователей с подпиской":
            allusers = await user_dat.GetAllUsersWithSub(pool=pool)
            if len(allusers) == 0:
                await bot.send_message(m.from_user.id, e.emojize("Нету пользователей с подпиской!"),
                                       reply_markup=await buttons.admin_buttons(), parse_mode="HTML")
                return
            await showUsers(user_dat, allusers, m)
            return

        if e.demojize(m.text) == "Вывести статичных пользователей":
            async with pool.acquire() as conn:
                all_staticusers = await conn.fetch("SELECT * FROM static_profiles")
            if len(all_staticusers) == 0:
                await bot.send_message(m.from_user.id, "Статичных пользователей нету!")
                return
            for user in all_staticusers:
                Butt_delete_account = types.InlineKeyboardMarkup()
                Butt_delete_account.add(types.InlineKeyboardButton(e.emojize("Удалить пользователя :cross_mark:"),
                                                                   callback_data=f'DELETE:{str(user[0])}'))

                config = open(f'/root/wg0-client-{str(str(user[1]))}.conf', 'rb')
                await bot.send_document(chat_id=m.chat.id, document=config,
                                        visible_file_name=f"{str(str(user[1]))}.conf",
                                        caption=f"Пользователь: <code>{str(user[1])}</code>", parse_mode="HTML",
                                        reply_markup=Butt_delete_account)

            return

        if e.demojize(m.text) == "Редактировать пользователя по id :pencil:":
            await bot.send_message(m.from_user.id, "Введите Telegram Id пользователя:",
                                   reply_markup=types.ReplyKeyboardRemove())
            await bot.set_state(m.from_user.id, MyStates.findUserViaId)
            return

        if e.demojize(m.text) == "Статичные пользователи":
            await bot.send_message(m.from_user.id, "Выберите пункт меню:",
                                   reply_markup=await buttons.admin_buttons_static_users())
            return

        if e.demojize(m.text) == "Добавить пользователя :plus:":
            await bot.send_message(m.from_user.id,
                                   "Введите имя для нового пользователя!\nМожно использовать только латинские символы и арабские цифры.",
                                   reply_markup=await buttons.admin_buttons_back())
            await bot.set_state(m.from_user.id, MyStates.AdminNewUser)
            return
    if e.demojize(m.text) == "/trial":
        user_dat = await User.GetInfo(tgid=m.from_user.id, pool=pool)
        if user_dat.sub_trial is None:

            await user_dat.grant_vpn_access(
            pool = pool,
            tgid = m.from_user.id,
            days = 1
            )
            subprocess.call(f'./addusertovpn.sh {m.from_user.id}', shell=True)

            tomorrow = datetime.now(pytz.utc).astimezone(MOSCOW_TZ) + timedelta(days=1)
            await bot.send_message(m.chat.id,
                                   f"🎉 Выдан пробный доступ до {tomorrow.strftime('%d.%m.%Y %H:%M')} МСК \n Жми 'Как подключить' 👇👇 ",
                                   reply_markup=await main_buttons(user_dat), parse_mode="HTML")
        else:
            await bot.send_message(m.chat.id,
                                   "Триал уже был активирован!",
                                   reply_markup=await main_buttons(user_dat), parse_mode="HTML")

    if e.demojize(m.text) == "Приобрести доступ :money_bag:":
        payment_info = await user_dat.PaymentInfo(pool=pool)
        if True:
            Butt_payment = types.InlineKeyboardMarkup()
            Butt_payment.add(
                types.InlineKeyboardButton(e.emojize(
                    f"1 мес. 📅 - {str(round(CONFIG['perc_1'] * CONFIG['one_month_cost']))} руб. Выгода {round(((1 - CONFIG['perc_1']) / 1) * 100)}%"),
                    callback_data="BuyMonth:1"))
            Butt_payment.add(
                types.InlineKeyboardButton(e.emojize(
                    f"3 мес. 📅 - {str(round(CONFIG['perc_3'] * CONFIG['one_month_cost']))} руб. Выгода {round(((3 - CONFIG['perc_3']) / 3) * 100)}%"),
                    callback_data="BuyMonth:3"))
            Butt_payment.add(
                types.InlineKeyboardButton(e.emojize(
                    f"6 мес. 📅 - {str(round(CONFIG['perc_6'] * CONFIG['one_month_cost']))} руб. Выгода {round(((6 - CONFIG['perc_6']) / 6) * 100)}%"),
                    callback_data="BuyMonth:6"))
            await bot.send_message(m.chat.id,
                                   "<b>Оплатить можно с помощью Банковской карты!</b>\n\nВыберите на сколько месяцев хотите приобрести подписку:",
                                   reply_markup=Butt_payment, parse_mode="HTML")

    if e.demojize(m.text) == "Как подключить :gear:":
        sub_trial = user_dat.sub_trial
        sub_end_paid = user_dat.subscription

        # Приводим даты к часовому поясу UTC+3
        if sub_trial:
            sub_trial = sub_trial.replace(tzinfo=MOSCOW_TZ).astimezone(MOSCOW_TZ)
        if sub_end_paid:
            sub_end_paid = sub_end_paid.replace(tzinfo=MOSCOW_TZ).astimezone(MOSCOW_TZ)
        # Определяем, какая дата позже
        latest_sub_end = max(filter(None, [sub_trial, sub_end_paid]), default=None)
        if latest_sub_end and latest_sub_end > datetime.now(MOSCOW_TZ).replace(tzinfo=MOSCOW_TZ):
            Butt_how_to = types.InlineKeyboardMarkup()
            Butt_how_to.add(
                types.InlineKeyboardButton(e.emojize("Подробнее как подключить"),
                                           url="https://telegra.ph/Gajd-na-ustanovku-11-27"))
            Butt_how_to.add(
                types.InlineKeyboardButton(e.emojize("Проверить VPN"),
                                           url="https://2ip.ru/"))
            config = open(f'/root/wg0-client-{str(user_dat.tgid)}.conf', 'rb')
            await bot.send_document(chat_id=m.chat.id, document=config, visible_file_name=f"{str(user_dat.tgid)}.conf",
                                    caption=texts_for_bot["how_to_connect_info"], parse_mode="HTML",
                                    reply_markup=Butt_how_to)
        else:
            await bot.send_message(chat_id=m.chat.id, text="Сначала нужно купить подписку!")

    if e.demojize(m.text, language='alias') == ":small_blue_diamond: :calendar: Информация о подписке :calendar: :small_blue_diamond:":
        sub_trial = user_dat.sub_trial
        sub_end_paid = user_dat.subscription

        # Приводим даты к часовому поясу UTC+3
        if sub_trial:
            sub_trial = sub_trial.replace(tzinfo=MOSCOW_TZ).astimezone(MOSCOW_TZ)
        if sub_end_paid:
            sub_end_paid = sub_end_paid.replace(tzinfo=MOSCOW_TZ).astimezone(MOSCOW_TZ)

        # Определяем, какая дата позже
        latest_sub_end = max(filter(None, [sub_trial, sub_end_paid]), default=None)

        if latest_sub_end:
            if latest_sub_end > datetime.now(MOSCOW_TZ).replace(tzinfo=MOSCOW_TZ):
                message = f"✅ Подписка активна до <b>{latest_sub_end.strftime('%d.%m.%Y %H:%M')} МСК</b>"
            else:
                message = f"❌ Подписка закончилась <b>{latest_sub_end.strftime('%d.%m.%Y %H:%M')} МСК</b>"
        else:
            message = "Нет активных подписок"

        await bot.send_message(m.chat.id, message, parse_mode="HTML")

    if e.demojize(m.text, language='alias') == ":gift: Хочу бесплатный VPN! :gift:":
        if user_dat:
            sub_end_paid = user_dat.subscription
            promo_flag = user_dat.promo_flag

            # Приводим к UTC+3, если дата существует
            if sub_end_paid:
                sub_end_paid = sub_end_paid.replace(tzinfo=MOSCOW_TZ)

            if sub_end_paid and promo_flag and sub_end_paid > datetime.now(MOSCOW_TZ).replace(tzinfo=MOSCOW_TZ):  # Сравниваем корректно в UTC+3
                readymes = (
                    f"У вас активирован доступ к ВПН до "
                    f"<b>{sub_end_paid.strftime('%d.%m.%Y %H:%M')}</b> ✅\n"
                    f"\n Жми 'Как подключить' 👇👇" 
                    f"⚠️ ВНИМАНИЕ! НЕ ОТПИСЫВАЙСЯ ИЛИ ВСЁ ПОЙДЕТ ПО ПИЗДЕ!"
                )
                await bot.send_message(
                    m.chat.id,
                    e.emojize(readymes),
                    parse_mode="HTML"
                )
                return

        # Если подписки нет - показываем каналы
        async with pool.acquire() as conn:
            channels = await conn.fetch("SELECT * FROM channels")

        if not channels:
            await bot.send_message(m.chat.id, "Пока нет промо-предложений")
            return

        channels_text = "\n".join(
            f"➡️ {channel['name']} - {channel['invite_link']}"
            for channel in channels
        )

        await bot.send_message(
            m.chat.id,
            e.emojize(
                f"📢 Для доступа к VPN подпишитесь на каналы:\n{channels_text}\n"
                "После подписки нажмите кнопку ниже 👇"
            ),
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton(
                    "✅ Я подписался",
                    callback_data="checkSubscription"
                )
            )
        )

        await bot.set_state(m.from_user.id, MyStates.checkSubscription)
        async with bot.retrieve_data(m.from_user.id) as data:
            data['channels'] = [dict(channel) for channel in channels]


@bot.callback_query_handler(func=lambda call: 'checkSubscription' in call.data)
async def check_subscription_handler(call: types.CallbackQuery):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    global pool
    async with bot.retrieve_data(user_id, chat_id) as data:
        channels = data['channels']

    unsubscribed = []
    for channel in channels:
        try:
            member = await bot.get_chat_member(chat_id=channel['channel_id'], user_id=user_id)
            if member.status not in ['member', 'administrator', 'creator']:
                unsubscribed.append(channel)
        except Exception as e:
            await bot.answer_callback_query(call.id, "❌ Ошибка проверки подписки!")
            return

    if unsubscribed:
        text = "Вы не подписаны на:\n" + "\n".join(
            [f"• {channel['name']}" for channel in unsubscribed]
        )
        await bot.answer_callback_query(call.id, "Подпишитесь на все каналы!")
        await bot.send_message(chat_id, text)
    else:
        now = datetime.now(pytz.utc).astimezone(MOSCOW_TZ).replace(tzinfo=None) + timedelta(days=3)
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE userss SET promo_flag = TRUE, checked_sub = FALSE, subscription = $1 WHERE tgid = $2",
                now, user_id
            )
            # Добавляем подписки
            for channel in channels:
                await conn.execute(
                    "INSERT INTO channel_subscriptions (user_id, channel_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    user_id, channel['channel_id']
                )
        subprocess.call(f'./addusertovpn.sh {user_id}', shell=True)
        await bot.send_message(chat_id, "✅ Доступ к VPN активирован на 3 дня! \n Жми 'Как подключить' 👇👇")
        await bot.delete_state(user_id, chat_id)


@bot.callback_query_handler(func=lambda c: 'BuyMonth:' in c.data)
async def Buy_month(call: types.CallbackQuery):
    global pool
    user_dat = await User.GetInfo(pool=pool, tgid=call.from_user.id)

    payment_info = await user_dat.PaymentInfo(pool=pool)
    if payment_info is None:
        Month_count = int(str(call.data).split(":")[1])
        await bot.delete_message(call.message.chat.id, call.message.id)
        if (Month_count == 1):
            count = CONFIG['perc_1']
        if (Month_count == 3):
            count = CONFIG['perc_3']
        if (Month_count == 6):
            count = CONFIG['perc_6']
        bill = await bot.send_invoice(call.message.chat.id, f"Оплата VPN",
                                      f"VPN на {str(Month_count)} мес. Выгода {round(((Month_count - count) / Month_count) * 100)}%",
                                      call.data,
                                      currency="RUB", prices=[
                types.LabeledPrice(
                    f"VPN на {str(Month_count)} мес.  Выгода {round(((Month_count - count) / Month_count) * 100)}%",
                    round(count * CONFIG['one_month_cost'] * 100))],
                                      provider_token=CONFIG["tg_shop_token"])
    await bot.answer_callback_query(call.id)




async def AddTimeToUser(tgid, timetoadd):
    global pool
    userdat = await User.GetInfo(pool=pool, tgid=tgid)

    async with pool.acquire() as conn:
        now_moscow = datetime.now(MOSCOW_TZ).astimezone(MOSCOW_TZ)  # Текущее время в UTC+3

        # Приводим подписку пользователя к UTC+3 (если есть)
        if userdat.subscription:
            user_subscription = userdat.subscription.replace(tzinfo=MOSCOW_TZ)
        else:
            user_subscription = now_moscow - timedelta(seconds=10000)  # Если подписки нет, считаем ее истекшей

        # Если подписка уже истекла, начинаем отсчет с текущего момента
        if user_subscription < now_moscow:
            new_subscription = now_moscow.replace(tzinfo=None) + timedelta(seconds=timetoadd)
        else:
            new_subscription = user_subscription.replace(tzinfo=None) + timedelta(seconds=timetoadd)

        # Записываем новое время подписки в БД
        await conn.execute(
            """
            UPDATE userss 
            SET subscription = $1, banned = FALSE, notion_oneday = FALSE 
            WHERE tgid = $2
            """,
            new_subscription, userdat.tgid
        )

        # Если подписка была истекшей, добавляем пользователя в VPN
        if user_subscription < now_moscow:

            subprocess.call(f'./addusertovpn.sh {userdat.tgid}', shell=True)

            # Уведомляем пользователя
            await bot.send_message(userdat.tgid, e.emojize(
                '✅ Данные для входа обновлены! Скачайте новый файл авторизации в разделе "Как подключить :gear:"'
            ))

    # Формируем кнопки
    Butt_main = types.ReplyKeyboardMarkup(resize_keyboard=True)
    formatted_date = new_subscription.strftime('%d.%m.%Y %H:%M')

    Butt_main.add(
        types.KeyboardButton(e.emojize("Приобрести доступ :money_bag:")),
        types.KeyboardButton(e.emojize("Как подключить :gear:"))
    )
    Butt_main.add(
        types.KeyboardButton(e.emojize(f":gift: Хочу бесплатный VPN! :gift:", language='alias'))
    )


@bot.callback_query_handler(func=lambda c: 'DELETE:' in c.data or 'DELETYES:' in c.data or 'DELETNO:' in c.data)
async def DeleteUserYesOrNo(call: types.CallbackQuery):
    idstatic = str(call.data).split(":")[1]
    async with pool.acquire() as conn:
        staticuser = await conn.fetchrow("SELECT * FROM static_profiles WHERE id = $1", int(idstatic))
    if staticuser[0] != int(idstatic):
        await bot.answer_callback_query(call.id, "Пользователь уже удален!")
        return

    if "DELETE:" in call.data:
        Butt_delete_account = types.InlineKeyboardMarkup()
        Butt_delete_account.add(
            types.InlineKeyboardButton(e.emojize("Удалить!"), callback_data=f'DELETYES:{str(staticuser[0])}'),
            types.InlineKeyboardButton(e.emojize("Нет"), callback_data=f'DELETNO:{str(staticuser[0])}'))
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=Butt_delete_account)
        await bot.answer_callback_query(call.id)
        return
    if "DELETYES:" in call.data:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM static_profiles WHERE id = $1", int(idstatic))
        await bot.delete_message(call.message.chat.id, call.message.id)
        check = subprocess.call(f'./deleteuserfromvpn.sh {str(staticuser[1])}', shell=True)
        await bot.answer_callback_query(call.id, "Пользователь удален!")
        return
    if "DELETNO:" in call.data:
        Butt_delete_account = types.InlineKeyboardMarkup()
        Butt_delete_account.add(types.InlineKeyboardButton(e.emojize("Удалить пользователя :cross_mark:"),
                                                           callback_data=f'DELETE:{str(idstatic)}'))
        await bot.edit_message_reply_markup(call.message.chat.id, call.message.id, reply_markup=Butt_delete_account)
        await bot.answer_callback_query(call.id)
        return


@bot.pre_checkout_query_handler(func=lambda query: True)
async def checkout(pre_checkout_query):
    month = int(str(pre_checkout_query.invoice_payload).split(":")[1])
    if (month == 1):
        count = CONFIG['perc_1']
    if (month == 3):
        count = CONFIG['perc_3']
    if (month == 6):
        count = CONFIG['perc_6']
    if count * 100 * CONFIG['one_month_cost'] != pre_checkout_query.total_amount:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=False,
                                            error_message="Нельзя купить по старой цене!")
        await bot.send_message(pre_checkout_query.from_user.id,
                               "<b>Цена изменилась! Нельзя приобрести по старой цене!</b>", parse_mode="HTML")
    else:
        await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True,
                                            error_message="Оплата не прошла, попробуйте еще раз!")


@bot.message_handler(content_types=['successful_payment'])
async def got_payment(m):
    payment: types.SuccessfulPayment = m.successful_payment
    month = int(str(payment.invoice_payload).split(":")[1])

    user_dat = await User.GetInfo(pool=pool, tgid=m.from_user.id)
    await bot.send_message(m.from_user.id, texts_for_bot["success_pay_message"],
                           reply_markup=await buttons.main_buttons(user_dat), parse_mode="HTML")
    await AddTimeToUser(m.from_user.id, month * 30 * 24 * 60 * 60)
    if (month == 1):
        count = CONFIG['perc_1']
    if (month == 3):
        count = CONFIG['perc_3']
    if (month == 6):
        count = CONFIG['perc_6']
    await bot.send_message(CONFIG["admin_tg_id"],
                           f"Новая оплата подписки на <b>{month}</b> мес. <b>{round(count * CONFIG['one_month_cost'])}</b> руб.",
                           parse_mode="HTML")


bot.add_custom_filter(asyncio_filters.StateFilter(bot))


async def checkTime():
    MOSCOW_TZ = pytz.timezone("Europe/Moscow")

    while True:
        try:
            logger.info("[INFO] Ожидание час перед следующей проверкой...")
            await asyncio.sleep(3600)  # ✅ Правильный async sleep

            logger.info("[INFO] Проверка истекших доступов...")
            async with pool.acquire() as conn:
                log = await conn.fetch("SELECT * FROM userss")
            logger.info(f"[INFO] Получено {len(log)} пользователей из БД")

            time_now = int(datetime.now(MOSCOW_TZ).timestamp())  # Текущее время в UTC+3
            logger.info(f"[DEBUG] Текущее время (UTC+3): {time_now}")

            for user in log:
                tgid = user["tgid"]
                sub_end_paid = user["subscription"]  # Может быть `None`
                sub_trial = user["sub_trial"]  # Может быть `None`
                is_banned = user["banned"]
                notion_oneday = user["notion_oneday"]

                # Преобразуем timestamp в datetime
                if sub_trial:
                    sub_trial = sub_trial.replace(tzinfo=pytz.utc).astimezone(MOSCOW_TZ)
                if sub_end_paid:
                    sub_end_paid = sub_end_paid.replace(tzinfo=pytz.utc).astimezone(MOSCOW_TZ)

                # Определяем, какая дата позже
                latest_sub_end = max(filter(None, [sub_trial, sub_end_paid]), default=0)
                if latest_sub_end:
                    latest_sub_end = int(latest_sub_end.timestamp())

                # Вычисляем оставшееся время в секундах
                remained_time = (latest_sub_end - time_now) if latest_sub_end else None

                # 🔴 Если подписка истекла и пользователь не заблокирован
                if remained_time is not None and remained_time <= 0 and not is_banned:
                    logger.info(f"[WARNING] Подписка истекла у {tgid}, блокируем...")
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE userss SET banned = TRUE WHERE tgid = $1", tgid)

                    logger.info(f"[INFO] Выполняем скрипт: sudo ./deleteuserfromvpn.sh {tgid}")
                    subprocess.call(f'sudo ./deleteuserfromvpn.sh {tgid}', shell=True)

                    # ✅ Преобразуем время подписки в UTC+3
                    sub_end_moscow = datetime.utcfromtimestamp(latest_sub_end).replace(tzinfo=MOSCOW_TZ).astimezone(
                        MOSCOW_TZ)
                    formatted_date = sub_end_moscow.strftime('%d.%m.%Y %H:%M')

                    logger.info(f"[INFO] Отправляем уведомление о блокировке {tgid}: подписка истекла {formatted_date}")

                    # ✅ Отправляем уведомление
                    await bot.send_message(
                        tgid, texts_for_bot["ended_sub_message"],
                        reply_markup=await main_buttons(user), parse_mode="HTML"
                    )

                # 🟡 Если осталось меньше 24 часов и уведомление еще не отправлялось
                if remained_time is not None and remained_time <= 86400 and not notion_oneday:
                    logger.info(f"[INFO] Уведомляем {tgid} о скором окончании подписки (осталось {remained_time} сек)")
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE userss SET notion_oneday = TRUE WHERE tgid = $1", tgid)

                    await bot.send_message(
                        tgid, texts_for_bot["alert_to_renew_sub"],
                        parse_mode="HTML"
                    )

        except Exception as ex:
            logger.info(f"[ERROR] Ошибка в checkTime: {ex}")
            pass



async def subscription_checker():
    MOSCOW_TZ = pytz.timezone("Europe/Moscow")

    global pool
    while True:
        logger.info("🔄 Начало проверки подписок...")
        await asyncio.sleep(3600 * 4)  # Проверка каждые 4 часа

        async with pool.acquire() as conn:
            # Получаем всех активных пользователей с промо-флагом
            active_users = await conn.fetch(
                "SELECT tgid, subscription FROM userss WHERE subscription > NOW() AND promo_flag = TRUE AND checked_sub = FALSE"
            )

            # Получаем список каналов для проверки
            channels = await conn.fetch("SELECT channel_id, name FROM channels")

            logger.info(f"📊 Найдено {len(active_users)} пользователей для проверки.")
            logger.info(f"📡 Проверяем подписку на {len(channels)} каналов.")
            now = datetime.now(pytz.utc).astimezone(MOSCOW_TZ).replace(tzinfo=None)

            for user in active_users:
                try:
                    should_revoke = False
                    user_id = user["tgid"]
                    sub_end_time = user["subscription"].astimezone(MOSCOW_TZ)  # Переводим в UTC+3

                    logger.info(f"🔍 Проверяем пользователя {user_id} (подписка до {sub_end_time.strftime('%d.%m.%Y %H:%M')} МСК)")

                    # Проверяем подписки на все каналы
                    for channel in channels:
                        channel_name = channel["name"]
                        channel_id = channel["channel_id"]
                        logger.info(f"  🔎 Проверяем подписку на канал {channel_name}...")

                        try:
                            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                            if member.status not in ["member", "administrator", "creator"]:
                                should_revoke = True
                                logger.info(f"  ❌ Пользователь {user_id} не подписан на {channel_name}")
                                break
                        except Exception as err:
                            logger.info(f"  ⚠️ Ошибка проверки канала {channel_name} для {user_id}: {err}")
                            continue

                    # Если не подписан на какой-то канал
                    if should_revoke:

                        await conn.execute(
                            "UPDATE userss SET promo_flag = FALSE,subscription = $1, checked_sub = TRUE WHERE tgid = $2",
                            now, user_id
                        )
                        subprocess.call(f'sudo ./deleteuserfromvpn.sh {user_id}', shell=True)

                        # Отправляем сообщение пользователю
                        mes = e.emojize(
                            "❌ *Доступ к VPN отозван!*\n"
                            "Причина: отписка от обязательных каналов\n\n"
                            "Чтобы восстановить доступ, подпишитесь на каналы и запустите проверку!"
                        )

                        await bot.send_message(user_id, mes, parse_mode="Markdown")

                        logger.info(f"🚫 Доступ пользователя {user_id} отозван из-за отписки от каналов!")

                except Exception as err:
                    logger.info(f"🔥 Ошибка обработки пользователя {user_id}: {err}")

        logger.info("✅ Проверка подписок завершена.")

async def showUsers(user_dat, allusers, m: types.Message):
    readymass = []
    readymes = ""

    for user in allusers:
        sub_trial = user_dat.sub_trial
        sub_end_paid = user_dat.subscription

        # Определяем, какая дата позже
        latest_sub_end = max(filter(None, [sub_trial, sub_end_paid]), default=None)

        now_utc3 = datetime.now(pytz.utc).astimezone(MOSCOW_TZ).replace(tzinfo=None)  # Текущее время в UTC+3

        if latest_sub_end and latest_sub_end > now_utc3:
            user_info = f"{user[7]} (<code>{str(user[1])}</code>) ✅ до {latest_sub_end.strftime('%d.%m.%Y %H:%M')}\n"
        else:
            user_info = f"{user[7]} (<code>{str(user[1])}</code>) ❌ закончилась {latest_sub_end.strftime('%d.%m.%Y %H:%M') if latest_sub_end else '—'}\n"

        if len(readymes) + len(user_info) > 4090:
            readymass.append(readymes)
            readymes = ""

        readymes += user_info

    readymass.append(readymes)

    for user in readymass:
        await bot.send_message(
            m.from_user.id,
            e.emojize(user),
            reply_markup=await buttons.admin_buttons(),
            parse_mode="HTML"
        )
    return

if __name__ == '__main__':
    asyncio.run(main())
