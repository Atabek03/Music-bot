import os
import re
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


def download_video_from_url(url: str, output_base: str) -> str:
    """Havoladagi videoni MP4 formatda yuklab oladi (Telegram 50 MB limitiga moslab)."""
    ydl_opts = {
        "format": "best[ext=mp4][filesize<45M]/bestvideo[ext=mp4][filesize<40M]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": f"{output_base}.%(ext)s",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": 45 * 1024 * 1024,  # Maksimal 45 MB
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        base, _ = os.path.splitext(filename)
        mp4_file = f"{base}.mp4"
        if os.path.exists(mp4_file):
            return mp4_file
        return filename


def download_mp3(query: str, output_base: str) -> str:
    """Qo'shiq nomi bo'yicha to'liq MP3 fayl qidiradi (YouTube -> SoundCloud)."""
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
        with yt_dlp.YoutubeDL(ydl_opts_yt) as ydl:
            ydl.download([query])
        if os.path.exists(f"{output_base}.mp3"):
            return f"{output_base}.mp3"
    except Exception as e:
        print(f"YouTube search error: {e}")

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
        with yt_dlp.YoutubeDL(ydl_opts_sc) as ydl:
            ydl.download([query])
        if os.path.exists(f"{output_base}.mp3"):
            return f"{output_base}.mp3"
    except Exception as e:
        print(f"SoundCloud search error: {e}")

    raise Exception("Hech bir manbadan audio topilmadi.")


async def process_and_send_song(chat_id: int, status_msg_id: int, source_path: str):
    """Video yoki audiodan musiqani aniqlaydi va topilgan qo'shiqning MP3 faylini yuboradi."""
    mp3_path = None
    try:
        result = await shazam.recognize(source_path)
        track = result.get("track")

        if not track:
            await bot.edit_message_text(
                "Videoda musiqa aniqlanmadi (yoki oddiy suhbat videosi).",
                chat_id=chat_id,
                message_id=status_msg_id,
            )
            return

        title = track.get("title", "Noma'lum qo'shiq")
        artist = track.get("subtitle", "Noma'lum ijrochi")
        url = track.get("url", "")
        caption_text = (
            f"🎵 **Qo'shiq:** {title}\n"
            f"👤 **Ijrochi:** {artist}\n"
            f"🔗 [Shazam'da tinglash]({url})"
        )

        await bot.edit_message_text(
            f"✅ Musiqa topildi: **{artist} - {title}**\n📥 MP3 fayli yuklanmoqda...",
            chat_id=chat_id,
            message_id=status_msg_id,
            parse_mode="Markdown",
        )

        try:
            mp3_base = os.path.join(TEMP_DIR, str(uuid.uuid4()))
            mp3_path = await asyncio.to_thread(
                download_mp3, f"{artist} - {title}", mp3_base
            )

            if mp3_path and os.path.exists(mp3_path):
                with open(mp3_path, "rb") as audio_file:
                    await bot.send_audio(
                        chat_id,
                        audio_file,
                        title=title,
                        performer=artist,
                        caption=caption_text,
                        parse_mode="Markdown",
                    )
                await bot.delete_message(chat_id, status_msg_id)
            else:
                raise Exception("MP3 fayl yaratilmadi")

        except Exception as download_error:
            print(f"MP3 yuklashda xatolik: {download_error}")
            fallback_text = (
                f"✅ Topildi: **{artist} - {title}**\n\n"
                f"⚠ MP3 faylini yuklab bo'lmadi. Quyidagi havola orqali tinglashingiz mumkin:\n"
                f"🔗 [Shazam'da tinglash]({url})"
            )
            await bot.edit_message_text(
                fallback_text,
                chat_id=chat_id,
                message_id=status_msg_id,
                parse_mode="Markdown",
            )
    finally:
        if mp3_path and os.path.exists(mp3_path):
            try:
                os.remove(mp3_path)
            except OSError:
                pass


@bot.message_handler(commands=["start", "help"])
async def send_welcome(message):
    text = (
        "Salom! Men video va musiqani yuklab beruvchi botman.\n\n"
        "Menga quyidagilardan birini yuboring:\n"
        "• Instagram Reels, TikTok yoki YouTube havolasi (ham videosini, ham musiqasini tashlab beraman)\n"
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

        await process_and_send_song(message.chat.id, status_msg.message_id, file_path)

    except Exception as e:
        print(f"Media xatosi: {e}")
        await bot.edit_message_text(
            "Xatolik yuz berdi. Qisqaroq audio yoki video yuborib ko'ring.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
        )
    finally:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass


@bot.message_handler(func=lambda m: m.text and re.search(r"https?://\S+", m.text))
async def handle_link(message):
    match = re.search(r"https?://\S+", message.text)
    url = match.group(0)
    status_msg = await bot.reply_to(message, "📥 Havoladan video yuklanmoqda, biroz kuting...")
    video_path = None

    try:
        base_path = os.path.join(TEMP_DIR, str(uuid.uuid4()))
        video_path = await asyncio.to_thread(
            download_video_from_url, url, base_path
        )

        # 1. Yuklangan videoning o'zini foydalanuvchiga yuboramiz
        if video_path and os.path.exists(video_path):
            with open(video_path, "rb") as video_file:
                await bot.send_video(
                    message.chat.id,
                    video_file,
                    caption="🎬 Videongiz tayyor!",
                    supports_streaming=True,
                )

            # 2. Endi shu videoning ichidagi musiqani qidiramiz
            await bot.edit_message_text(
                "🎵 Video ichidagi musiqa aniqlanmoqda...",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
            )
            await process_and_send_song(
                message.chat.id, status_msg.message_id, video_path
            )
        else:
            raise Exception("Video fayl saqlanmadi")

    except Exception as e:
        print(f"Havola xatosi: {e}")
        await bot.edit_message_text(
            "Havoladagi videoni yuklab bo'lmadi. Video hajmi 45 MB dan katta, profil yopiq (Private) yoki platforma cheklov qo'ygan bo'lishi mumkin.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
        )
    finally:
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except OSError:
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




