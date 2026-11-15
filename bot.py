import os
import uuid
import asyncio
from telebot.async_telebot import AsyncTeleBot
from shazamio import Shazam

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = AsyncTeleBot(BOT_TOKEN)
shazam = Shazam()

TEMP_DIR = "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)


@bot.message_handler(commands=["start", "help"])
async def send_welcome(message):
    text = (
        "Salom! Men musiqani topuvchi botman.\n\n"
        "Menga quyidagilardan birini yuboring:\n"
        "• Ovozli xabar (golos)\n"
        "• Qisqa video yoki dumaloq video\n"
        "• Audio fayl"
    )
    await bot.reply_to(message, text)


@bot.message_handler(content_types=["audio", "voice", "video", "video_note"])
async def handle_media(message):
    status_msg = await bot.reply_to(message, "Musiqa qidirilmoqda, biroz kuting...")
    file_path = None

    try:
        if message.audio:
            file_id = message.audio.file_id
        elif message.voice:
            file_id = message.voice.file_id
        elif message.video:
            file_id = message.video.file_id
        else:
            file_id = message.video_note.file_id

        file_info = await bot.get_file(file_id)
        ext = os.path.splitext(file_info.file_path)[1] or ".mp4"
        file_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}{ext}")

        downloaded_bytes = await bot.download_file(file_info.file_path)
        with open(file_path, "wb") as f:
            f.write(downloaded_bytes)

        result = await shazam.recognize(file_path)
        track = result.get("track")

        if track:
            title = track.get("title", "Noma'lum qo'shiq")
            artist = track.get("subtitle", "Noma'lum ijrochi")
            url = track.get("url", "")
            reply_text = (
                f"🎵 **Qo'shiq:** {title}\n"
                f"👤 **Ijrochi:** {artist}\n"
                f"🔗 [Shazam'da tinglash]({url})"
            )
            await bot.edit_message_text(
                reply_text,
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="Markdown",
            )
        else:
            await bot.edit_message_text(
                "Afsuski, bu fayldan musiqani aniqlab bo'lmadi.",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
            )

    except Exception:
        await bot.edit_message_text(
            "Xatolik yuz berdi. Qisqaroq audio yoki video yuborib ko'ring.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
        )
    finally:
        if file_path and os.path.exists(file_path):
            os.remove(file_path)


if __name__ == "__main__":
    print("Bot ishga tushdi...")
    asyncio.run(bot.polling(non_stop=True))
