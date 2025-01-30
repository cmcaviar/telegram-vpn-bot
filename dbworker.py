import asyncpg
import time
import subprocess

CONFIG = {}

class User:
    def __init__(self):
        self.id = None
        self.tgid = None
        self.subscription = None
        self.trial_subscription = True
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
            self.trial_subscription = log["banned"]
            self.registered = True
            self.username = log["username"]
            self.fullname = log["fullname"]
        else:
            self.registered = False

        return self

    async def PaymentInfo(self, pool):
        """Получает информацию о платеже пользователя."""
        async with pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM payments WHERE tgid=$1", self.tgid)

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
                    VALUES ($1, $2, $3, $4, $5)""",
                    self.tgid, str(bill_id), summ, int(time_to_add), str(mesid)
                )

    async def GetAllPaymentsInWork(self, pool):
        """Получает все активные платежи."""
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM payments")

    async def Adduser(self, pool, username, full_name):
        """Добавляет нового пользователя в базу данных."""
        if not self.registered:
            async with pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO userss (tgid, subscription, username, fullname) 
                    VALUES ($1, $2, $3, $4)""",
                    self.tgid, str(int(time.time()) + int(CONFIG['trial_period']) * 86400), username, full_name
                )
            subprocess.call(f'./addusertovpn.sh {str(self.tgid)}', shell=True)
            self.registered = True

    async def GetAllUsers(self, pool):
        """Получает всех пользователей."""
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM userss")

    async def GetAllUsersWithSub(self, pool):
        """Получает пользователей с активной подпиской."""
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM userss WHERE subscription > $1", str(int(time.time())))

    async def GetAllUsersWithoutSub(self, pool):
        """Получает пользователей без подписки."""
        async with pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM userss WHERE banned = TRUE AND username <> '@None'")

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