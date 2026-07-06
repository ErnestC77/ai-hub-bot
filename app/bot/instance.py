from app.bot.setup import create_bot

# Единый экземпляр Bot, используемый и в aiogram-диспетчере (app.main),
# и в сервисах, которым нужно звать Bot API напрямую (payments.stars_service).
bot = create_bot()
