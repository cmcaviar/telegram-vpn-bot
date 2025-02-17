import logging
import sys

# Создаем логгер
logger = logging.getLogger("bot_logger")
logger.setLevel(logging.INFO)  # Можно менять на INFO, WARNING, ERROR

# Формат логов
log_format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

# Логирование в файл
file_handler = logging.FileHandler("bot.log", encoding="utf-8")
file_handler.setFormatter(log_format)
file_handler.setLevel(logging.INFO)  # Только INFO и выше идут в файл

# Логирование в консоль (для systemd)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_format)
console_handler.setLevel(logging.INFO)  # Всё от DEBUG и выше идёт в консоль

# Добавляем обработчики в логгер
logger.addHandler(file_handler)
logger.addHandler(console_handler)