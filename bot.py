import os
import uuid
import asyncio
from aiohttp import web
from telebot.async_telebot import AsyncTeleBot
from shazamio import Shazam
import yt_dlp

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = AsyncTeleBot(BOT_TOKEN)
shazam = Shazam()

TEMP_DIR = "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)


def download_mp3(query: str, output_base: str) -> str:
    """Qo'shiq nomi bo'yicha audio qidiradi. Avval YouTube, keyin SoundCloud sinab ko'radi."""
    # 1. YouTube’da qidirish
    ydl_opts_yt = {
        "format": "bestaudio/best",
        "outtmpl": f"{output_base}.%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "ytsearch1",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    try:
        print(f"YouTube orqali qidirilmoqda: {query}")
        with yt_dlp.YoutubeDL(ydl_opts_yt) as ydl:
            ydl.download([query])
        if os.path.exists(f"{output_base}.mp3"):
            return f"{output_base}.mp3"
    except Exception as e:
        print(f"YouTube search error: {e}")

    # 2. SoundCloud’da qidirish (Zaxira yo'li - bu yerda bloklanish deyarli bo'lmaydi)
    ydl_opts_sc = {
        "format": "bestaudio/best",
        "outtmpl": f"{output_base}.%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "default_search": "scsearch1",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }
    try:
        print(f"SoundCloud orqali zaxira qidiruvi: {query}")
        with yt_dlp.YoutubeDL(ydl_opts_sc) as ydl:
            ydl.download([query])
        if os.path.exists(f"{output_base}.mp3"):
            return f"{output_base}.mp3"
    except Exception as e:
        print(f"SoundCloud search error: {e}")

    raise Exception("Hech bir manbadan audio topilmadi.")


@bot.message_handler(commands=["start", "help"])
async def send_welcome(message):
    text = (
        "Salom! Men musiqani topuvchi va MP3 yuklab beruvchi botman.\n\n"
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
    mp3_path = None

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
            caption_text = (
                f"🎵 **Qo'shiq:** {title}\n"
                f"👤 **Ijrochi:** {artist}\n"
                f"🔗 [Shazam'da tinglash]({url})"
            )

            await bot.edit_message_text(
                f"✅ Topildi: **{artist} - {title}**\n📥 Serverdan MP3 fayli yuklanmoqda...",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
                parse_mode="Markdown",
            )

            try:
                mp3_base = os.path.join(TEMP_DIR, str(uuid.uuid4()))
                mp3_path = await asyncio.to_thread(
                    download_mp3, f"{artist} - {title}", mp3_base
                )
                
                # Agar fayl yuklangan bo'lsa, uni yuboramiz
                if mp3_path and os.path.exists(mp3_path):
                    with open(mp3_path, "rb") as audio_file:
                        await bot.send_audio(
                            message.chat.id,
                            audio_file,
                            title=title,
                            performer=artist,
                            caption=caption_text,
                            parse_mode="Markdown",
                        )
                    await bot.delete_message(message.chat.id, status_msg.message_id)
                else:
                    raise Exception("Fayl yaratilmadi")

            except Exception as download_error:
                # Agar barcha qidiruvlar muvaffaqiyatsiz bo'lsa, ushbu ma'lumotni beradi
                print(f"Download to'liq muvaffaqiyatsiz tugadi: {download_error}")
                fallback_text = (
                    f"✅ Topildi: **{artist} - {title}**\n\n"
                    f"⚠ Afsuski, server cheklovlari tufayli bu safar MP3 faylini internetdan yuklab berolmadim. "
                    f"Uni quyidagi havola orqali tinglashingiz mumkin:\n"
                    f"🔗 [Shazam'da tinglash]({url})"
                )
                await bot.edit_message_text(
                    fallback_text,
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

    except Exception as e:
        print(f"Xatolik: {e}")
        await bot.edit_message_text(
            "Xatolik yuz berdi. Qisqaroq audio yoki video yuborib ko'ring.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
        )
    finally:
        for path in (file_path, mp3_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass


async def handle_web(request):
    return web.Response(text="Bot ishlamoqda!")


async def main():
    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print("Bot ishga tushdi...")
    await bot.polling(non_stop=True)


if __name__ == "__main__":
    asyncio.run(main())



