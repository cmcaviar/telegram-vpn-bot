import datetime
import pytz


CONFIG = {}

class User:
    def __init__(self):
        self.id = None
        self.tgid = None
        self.subscription = None
        self.sub_trial = None
        self.checked_sub = None
        self.registered = False
        self.username = None
        self.fullname = None

    @classmethod
    async def GetInfo(cls, pool, tgid):
        """Получает информацию о пользователе по Telegram ID."""
        self = User()
        self.tgid = tgid
        async with pool.acquire() as conn:
            log = await conn.fetchrow("SELECT * FROM userss WHERE tgid=$1", tgid)

        if log:
            self.id = log["id"]
            self.subscription = log["subscription"]
            self.sub_trial = log["sub_trial"]
            self.promo_flag = log["promo_flag"]
            self.checked_sub = log["checked_sub"]
            self.registered = True
            self.username = log["username"]
            self.fullname = log["fullname"]
        else:
            self.registered = False

        return self

    async def PaymentInfo(self, pool):
        """Получает информацию о платеже пользователя."""
        async with pool.acquire() as conn:
            log = await conn.fetchrow("SELECT * FROM payments WHERE tgid=$1", self.tgid)
            return log

    async def CancelPayment(self, pool):
        """Удаляет платеж пользователя."""
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM payments WHERE tgid=$1", self.tgid)

    async def NewPay(self, pool, bill_id, summ, time_to_add, mesid):
        """Создаёт новую запись о платеже, если её нет."""
        pay_info = await self.PaymentInfo(pool)
        if pay_info is None:
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO payments (tgid, bill_id, amount, time_to_add, mesid) 
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (tgid) DO NOTHING;""",
                    self.tgid, str(bill_id), summ, int(time_to_add), str(mesid)
                )

    async def GetAllPaymentsInWork(self, pool):
        """Получает все активные платежи."""
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM payments")

    async def Adduser(self, pool, username, full_name):
        """Добавляет нового пользователя в базу данных."""

        print(f"🆕 Добавление пользователя {self.tgid}")
        print(f"👤 Логин: {username}, Имя: {full_name}")

        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO userss (tgid, username, fullname) 
                VALUES ($1, $2, $3)
                ON CONFLICT (tgid) DO NOTHING;""",
                self.tgid, username, full_name
            )

        print(f"✅ Пользователь {self.tgid} успешно добавлен в базу!")

        self.registered = True

    async def GetAllUsers(self, pool):
        """Получает всех пользователей."""
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM userss")

    async def GetAllUsersWithSub(self, pool):
        MOSCOW_TZ = pytz.timezone("Europe/Moscow")
        now_moscow = datetime.datetime.now(pytz.utc).astimezone(MOSCOW_TZ).replace(tzinfo=None)
        async with pool.acquire() as conn:
            return await conn.fetch(
                "SELECT * FROM userss WHERE subscription > $1",
                now_moscow  # ✅ Теперь формат полностью соответствует БД
            )

    async def GetAllUsersWithoutSub(self, pool):
        """Получает пользователей без подписки."""
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM userss WHERE banned = TRUE AND username <> '@None'")


    async def grant_vpn_access(self, pool, tgid: int, days: int):
        MOSCOW_TZ = pytz.timezone("Europe/Moscow")
        """Выдает доступ к VPN на указанное количество дней."""
        print(f"🆕 Добавление пользователя {self.tgid}")

        now_moscow = datetime.datetime.now(pytz.utc).astimezone(MOSCOW_TZ)
        sub_trial = (now_moscow + datetime.timedelta(days=days)).replace(tzinfo=None)

        print(f"✅ Выдача VPN-доступа пользователю {tgid}")
        print(f"📅 Доступ до: {sub_trial.strftime('%d.%m.%Y %H:%M')} МСК")

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE userss SET sub_trial = $1 WHERE tgid = $2",
                sub_trial, tgid
            )

        print(f"🎉 Пользователь {tgid} теперь имеет trial-доступ до {sub_trial.strftime('%d.%m.%Y %H:%M')} МСК")

    async def revoke_vpn_access(self, pool, tgid: int):
        MOSCOW_TZ = pytz.timezone("Europe/Moscow")
        """Отзывает доступ к VPN немедленно."""
        self = User()
        self.tgid = tgid

        now_moscow = datetime.datetime.now(pytz.utc).astimezone(MOSCOW_TZ)

        print(f"❌ Отзыв VPN-доступа у пользователя {tgid}")
        print(f"⏳ Доступ прекращен в: {now_moscow.strftime('%d.%m.%Y %H:%M')} МСК")

        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE userss SET sub_trial = $1 WHERE tgid = $2",
                now_moscow, tgid
            )

        print(f"🔒 Доступ у пользователя {tgid} успешно отозван!")

    async def get_subscription_channels(pool):
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM channels")

    async def AddChannels(pool, channel_id, name, invite_link):
        """Добавляет новый канал в базу данных."""
        async with pool.acquire() as conn:
            await conn.execute(
               """INSERT INTO channels (channel_id, name, invite_link) 
                    VALUES ($1, $2, $3)
                    ON CONFLICT (channel_id) DO NOTHING;""",
                    channel_id, name, invite_link
                )

    async def DeleteChannels(pool):
        async with pool.acquire() as conn:
            await conn.execute(
               "DELETE FROM channels;")

    async def GetChannelByName(pool, name):
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM channels WHERE name = $1", name)

    async def DeleteChannelByName(pool, name):
        async with pool.acquire() as conn:
            return await conn.execute("DELETE FROM channels WHERE name = $1", name)

    async def CheckNewNickname(self, pool, message):
        """Проверяет изменение никнейма и имени у пользователя."""
        try:
            username = "@" + str(message.from_user.username)
        except:
            username = str(message.from_user.id)

        if message.from_user.full_name != self.fullname or username != self.username:
            async with pool.acquire() as conn:
                await conn.execute(
                    "UPDATE userss SET username = $1, fullname = $2 WHERE id = $3",
                    username, message.from_user.full_name, self.id
                )