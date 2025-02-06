import json
import string
import subprocess
from datetime import datetime, timedelta
import time

import asyncpg
import docker

import buttons
import dbworker

from telebot import TeleBot
from telebot import asyncio_filters
from telebot.async_telebot import AsyncTeleBot
import emoji as e
import asyncio
import threading
from telebot import types
from telebot.asyncio_storage import StateMemoryStorage
from telebot.asyncio_handler_backends import State, StatesGroup
from yoyo import get_backend, read_migrations

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


class MyStates(StatesGroup):
    findUserViaId = State()
    editUser = State()
    editUserResetTime = State()

    UserAddTimeDays = State()
    UserAddTimeHours = State()
    UserAddTimeMinutes = State()
    UserAddTimeApprove = State()

    AdminNewUser = State()

    checkSubscription = State()


def start_postgres_container():
    client = docker.from_env()

    # Проверяем, запущен ли контейнер
    containers = client.containers.list(filters={"name": "my_postgres"})
    if containers:
        print("PostgreSQL контейнер уже запущен.")
        return

    # Запускаем контейнер с помощью docker-compose
    print("Запуск PostgreSQL контейнера...")
    subprocess.run(["docker-compose", "up", "-d"], check=True)

    # Ждем, пока PostgreSQL станет доступным
    print("Ожидание готовности PostgreSQL...")
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

    print("Все миграции успешно применены")


async def main():
    # Запускаем контейнер при старте приложения
    start_postgres_container()
    global pool
    # Создаем пул соединений
    pool = await create_db_pool()
    print("Пул соединений создан.")
    await run_migrations()

    # Запускаем поток для checkTime
    threadcheckTime = threading.Thread(target=checkTime, name="checkTime1")
    threadcheckTime.start()

    # Запускаем бота
    await bot.polling(non_stop=True, interval=0, request_timeout=60, timeout=60)

async def on_startup():
    asyncio.create_task(subscription_checker())
    print("Subscription checker started")
bot.add_custom_filter(asyncio_filters.StateFilter(bot))

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
            await bot.send_message(message.chat.id, e.emojize(texts_for_bot["trial_message"]))


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
        now = datetime.now()
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
        readymes += f"Подписка: до <b>{(user_dat.subscription + timedelta(hours=CONFIG['UTC_time'])).strftime('%d.%m.%Y %H:%M')}</b> ✅"
    else:
        readymes += f"Подписка: закончилась <b>{(user_dat.subscription + timedelta(hours=CONFIG['UTC_time'])).strftime('%d.%m.%Y %H:%M')}</b> ❌"

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
        readymes += f"Подписка: до <b>{(user_dat.subscription + timedelta(hours=CONFIG['UTC_time'])).strftime('%d.%m.%Y %H:%M')}</b> ✅"
    else:
        readymes += f"Подписка: закончилась <b>{(user_dat.subscription + timedelta(hours=CONFIG['UTC_time'])).strftime('%d.%m.%Y %H:%M')}</b> ❌"

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

    if user_dat.subscription > datetime.now():
        readymes += f"Подписка: до <b>{(user_dat.subscription + timedelta(hours=CONFIG['UTC_time'])).strftime('%d.%m.%Y %H:%M')}</b> ✅"
    else:
        readymes += f"Подписка: закончилась <b>{(user_dat.subscription + timedelta(hours=CONFIG['UTC_time'])).strftime('%d.%m.%Y %H:%M')}</b> ❌"

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


@bot.message_handler(state="*", content_types=["text"])
async def Work_with_Message(m: types.Message):
    global pool
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

        if e.demojize(m.text) == "Назад :right_arrow_curving_left:":
            await bot.send_message(m.from_user.id, "Админ панель", reply_markup=await buttons.admin_buttons())
            return

        if e.demojize(m.text) == "Всех пользователей":
            allusers = await user_dat.GetAllUsers(pool=pool)
            readymass = []
            readymes = ""

            for user in allusers:

                sub_end_promo = user.get('sub_promo_end')
                sub_end_paid = user.get('subscription')

                if sub_end_promo:
                    sub_end_promo += timedelta(hours=CONFIG['UTC_time'])
                if sub_end_paid:
                    sub_end_paid += timedelta(hours=CONFIG['UTC_time'])

                # Определяем, какая дата позже
                latest_sub_end = max(filter(None, [sub_end_promo, sub_end_paid]), default=None)

                if user[2] > datetime.utcnow():  # Сравниваем как datetime
                    user_info = f"{user[7]} (<code>{str(user[1])}</code>) ✅ до {latest_sub_end}\n"
                else:
                    user_info = f"{user[7]} (<code>{str(user[1])}</code>) ❌ закончилась {latest_sub_end}\n"

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

        if e.demojize(m.text) == "Продлить пробный период":
            async with pool.acquire() as conn:
                log = await conn.fetch("SELECT * FROM userss WHERE banned = TRUE AND username <> '@None'")

            timetoadd = timedelta(days=1)  # 3 дня
            countSended = 0
            countBlocked = 0
            BotChecking = TeleBot(BOTAPIKEY)

            for user in log:
                try:
                    countSended += 1
                    async with pool.acquire() as conn:
                        await conn.execute(
                            """
                            UPDATE userss 
                            SET subscription = NOW() + $1, banned = FALSE, notion_oneday = FALSE 
                            WHERE tgid = $2
                            """,
                            timetoadd,
                            user["tgid"]
                        )
                    subprocess.call(f'./addusertovpn.sh {user["tgid"]}', shell=True)

                    Butt_main = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    Butt_main.add(
                        types.KeyboardButton(e.emojize("Продлить :money_bag:")),
                        types.KeyboardButton(e.emojize("Как подключить :gear:"))
                    )
                    Butt_main.add(
                        types.KeyboardButton(e.emojize(f"Получить бесплатный ВПН"))
                    )

                    # Отправляем сообщение пользователю
                    await asyncio.to_thread(bot.send_message, user["tgid"],
                                            texts_for_bot["alert_to_extend_sub"],
                                            reply_markup=Butt_main, parse_mode="HTML")
                except Exception as ex:
                    countSended -= 1
                    countBlocked += 1
                    print(f"Ошибка у пользователя {user['tgid']}: {ex}")
                    pass

            BotChecking.send_message(
                CONFIG['admin_tg_id'],
                f"Добавлен пробный период {countSended} пользователям. {countBlocked} пользователей заблокировало бота",
                parse_mode="HTML"
            )
        if e.demojize(m.text) == "Уведомление об обновлении":
            async with pool.acquire() as conn:
                log = await conn.fetch("SELECT * FROM userss WHERE username <> '@None'")
            BotChecking = TeleBot(BOTAPIKEY)
            countSended = 0
            countBlocked = 0
            for user in log:
                try:
                    countSended += 1

                    Butt_main = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    Butt_main.add(types.KeyboardButton(e.emojize(f"Продлить :money_bag:")),
                                  types.KeyboardButton(e.emojize(f"Как подключить :gear:")))
                    Butt_main.add(
                        types.KeyboardButton(e.emojize(f"Получить бесплатный ВПН"))
                    )
                    BotChecking.send_message(user['tgid'],
                                             texts_for_bot["alert_to_update"],
                                             reply_markup=Butt_main, parse_mode="HTML")
                except:
                    countSended -= 1
                    countBlocked += 1
                    pass

            BotChecking.send_message(CONFIG['admin_tg_id'],
                                     f"Сообщение отправлено {countSended} пользователям. {countBlocked} пользователей заблокировало бота",
                                     parse_mode="HTML")

        if e.demojize(m.text) == "Пользователей с подпиской":
            allusers = await user_dat.GetAllUsersWithSub(pool=pool)
            readymass = []
            readymes = ""
            if len(allusers) == 0:
                await bot.send_message(m.from_user.id, e.emojize("Нету пользователей с подпиской!"),
                                       reply_markup=await buttons.admin_buttons(), parse_mode="HTML")
                return
            for user in allusers:
                sub_end_promo = user.get('sub_promo_end')
                sub_end_paid = user.get('subscription')

                if sub_end_promo:
                    sub_end_promo += timedelta(hours=CONFIG['UTC_time'])
                if sub_end_paid:
                    sub_end_paid += timedelta(hours=CONFIG['UTC_time'])

                # Определяем, какая дата позже
                latest_sub_end = max(filter(None, [sub_end_promo, sub_end_paid]), default=None)
                if latest_sub_end > datetime.utcnow():  # Сравниваем корректно с datetime.utcnow()

                    user_info = f"{user[7]} (<code>{str(user[1])}</code>) - {latest_sub_end}\n\n"

                    if len(readymes) + len(user_info) > 4090:
                        readymass.append(readymes)
                        readymes = ""

                    readymes += user_info

            readymass.append(readymes)
            for user in readymass:
                await bot.send_message(m.from_user.id, e.emojize(user), parse_mode="HTML")
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

    if e.demojize(m.text) == "Продлить :money_bag:":
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
        if user_dat.trial_subscription == False:
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

    if e.demojize(m.text) == "Получить бесплатный ВПН":
        now = datetime.now()

        async with pool.acquire() as conn:

            # Получаем данные о подписке
            user_dat = await conn.fetchrow(
                "SELECT sub_promo_end, subscription FROM userss WHERE tgid = $1",
                user_dat.tgid
            )

        # Проверяем активную подписку
        if user_dat:
            sub_end_promo = user_dat.get('sub_promo_end')
            sub_end_paid = user_dat.get('subscription')

            if sub_end_promo:
                sub_end_promo += timedelta(hours=CONFIG['UTC_time'])
            if sub_end_paid:
                sub_end_paid += timedelta(hours=CONFIG['UTC_time'])

            # Определяем, какая дата позже
            latest_sub_end = max(filter(None, [sub_end_promo, sub_end_paid]), default=None)

            if latest_sub_end and latest_sub_end > now:
                readymes = (
                    f"У вас активирован доступ к ВПН до "
                    f"<b>{latest_sub_end.strftime('%d.%m.%Y %H:%M')}</b> ✅"
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
            await bot.send_message(user_dat.tgid, "Пока нет промо-предложений")
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
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE userss SET sub_promo_end = NOW() + INTERVAL '1 day' * $1 WHERE tgid = $2",
                3, user_id
            )

        await bot.send_message(chat_id, "✅ Доступ к VPN активирован на 3 дня!")
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
        # Проверяем, истекла ли подписка
        if userdat.subscription < datetime.now():
            passdat = datetime.now() + timedelta(seconds=timetoadd)
            await conn.execute(
                """
                UPDATE userss 
                SET subscription = $1, banned = FALSE, notion_oneday = FALSE 
                WHERE tgid = $2
                """,
                passdat, userdat.tgid
            )
            subprocess.call(f'./addusertovpn.sh {userdat.tgid}', shell=True)

            # Отправляем сообщение пользователю
            await asyncio.to_thread(bot.send_message, userdat.tgid, e.emojize(
                'Данные для входа были обновлены, скачайте новый файл авторизации через раздел "Как подключить :gear:"'
            ))
        else:
            passdat = userdat.subscription + timedelta(seconds=timetoadd)
            await conn.execute(
                """
                UPDATE userss 
                SET subscription = $1, notion_oneday = FALSE 
                WHERE tgid = $2
                """,
                passdat, userdat.tgid
            )

    Butt_main = types.ReplyKeyboardMarkup(resize_keyboard=True)
    dateto = passdat.strftime('%d.%m.%Y %H:%M')

    if passdat >= datetime.now():
        Butt_main.add(
            types.KeyboardButton(e.emojize(f":green_circle: До: {dateto} МСК :green_circle:"))
        )

    Butt_main.add(
        types.KeyboardButton(e.emojize("Продлить :money_bag:")),
        types.KeyboardButton(e.emojize("Как подключить :gear:"))

    )
    Butt_main.add(
        types.KeyboardButton(e.emojize(f"Получить бесплатный ВПН"))
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
    while True:
        try:
            time.sleep(15)
            async with pool.acquire() as conn:
                log = await conn.fetch("SELECT * FROM userss")
            for i in log:
                time_now = int(time.time())
                remained_time = int(i[2]) - time_now
                if remained_time <= 0 and i[3] == False:
                    async with pool.acquire() as conn:
                        await conn.execute("UPDATE userss SET banned = TRUE WHERE tgid = $1", i[1])
                    subprocess.call(f'sudo ./deleteuserfromvpn.sh {str(i[1])}', shell=True)

                    dateto = datetime.utcfromtimestamp(int(i[2]) + CONFIG['UTC_time'] * 3600).strftime(
                        '%d.%m.%Y %H:%M')
                    Butt_main = types.ReplyKeyboardMarkup(resize_keyboard=True)
                    Butt_main.add(
                        types.KeyboardButton(e.emojize(f":red_circle: Закончилась: {dateto} МСК:red_circle:")))
                    Butt_main.add(types.KeyboardButton(e.emojize(f"Продлить :money_bag:")),
                                  types.KeyboardButton(e.emojize(f"Как подключить :gear:")))
                    Butt_main.add(
                        types.KeyboardButton(e.emojize(f"Получить бесплатный ВПН"))
                    )
                    BotChecking = TeleBot(BOTAPIKEY)
                    BotChecking.send_message(i['tgid'],
                                             texts_for_bot["ended_sub_message"],
                                             reply_markup=Butt_main, parse_mode="HTML")

                if remained_time <= 86400 and i[4] == False:
                    async with pool.acquire() as conn:
                        await conn.execute(f"UPDATE userss SET notion_oneday=true where tgid=?", (i[1],))
                    BotChecking = TeleBot(BOTAPIKEY)
                    BotChecking.send_message(i['tgid'], texts_for_bot["alert_to_renew_sub"], parse_mode="HTML")

                # Дарим бесплатную подписку на 7 дней если он висит 3 дня как неактивный и не ливнул
                # if remained_time <= 259200 and i['trial_continue'] == 0:
                #     BotChecking = TeleBot(BOTAPIKEY)
                #     timetoadd = 7 * 60 * 60 * 24
                #     db = sqlite3.connect(DBCONNECT)
                #     db.execute(f"UPDATE userss SET trial_continue=1 where tgid=?", (i[1],))
                #     db.execute(
                #         f"Update userss set subscription = ?, banned=false, notion_oneday=false where tgid=?",
                #         (str(int(time.time()) + timetoadd), i[1]))
                #     db.commit()
                #     db.close()
                #     subprocess.call(f'./addusertovpn.sh {str(i[1])}', shell=True)

                #     Butt_main = types.ReplyKeyboardMarkup(resize_keyboard=True)
                #     Butt_main.add(types.KeyboardButton(e.emojize(f"Продлить :money_bag:")),
                #                   types.KeyboardButton(e.emojize(f"Как подключить :gear:")))
                #     BotChecking.send_message(i['tgid'],
                #                              e.emojize(texts_for_bot["alert_to_extend_sub"]),
                #                              reply_markup=Butt_main, parse_mode="HTML")

        except Exception as err:
            print(err)
            pass


async def subscription_checker():
    global pool
    while True:
        await asyncio.sleep(6 * 3600)  # Проверка каждые 24 часа

        async with pool.acquire() as conn:
            # Получаем всех активных пользователей
            active_users = await conn.fetch(
                "SELECT tgid FROM userss WHERE sub_promo_end > NOW()"
            )

            # Получаем список каналов для проверки
            channels = await conn.fetch("SELECT * FROM channels")

            for user in active_users:
                try:
                    should_revoke = False
                    user_id = user['tgid']

                    # Проверяем подписки на все каналы
                    for channel in channels:
                        try:
                            member = await bot.get_chat_member(
                                chat_id=channel['channel_id'],
                                user_id=user_id
                            )
                            if member.status not in ['member', 'administrator', 'creator']:
                                should_revoke = True
                                break
                        except Exception as err:
                            print(f"Ошибка проверки канала: {err}")
                            continue

                    # Если не подписан на какой-то канал
                    if should_revoke:
                        now = datetime.now()
                        await conn.execute(
                            "UPDATE userss SET sub_promo_end = $1 WHERE tgid = $2",
                            now,
                            user_id
                        )

                        # Форматируем сообщение
                        mes = e.emojize(
                            "❌ *Доступ к VPN отозван!*\n"
                            "Причина: отписка от обязательных каналов\n\n"
                            "Чтобы восстановить доступ, используйте /getvpn"
                        )

                        await bot.send_message(
                            user_id,
                            mes,
                            parse_mode="Markdown"
                        )

                except Exception as err:
                    print(f"Ошибка обработки пользователя {user_id}: {err}")


if __name__ == '__main__':
    asyncio.run(main())
