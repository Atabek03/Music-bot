import os
import re
import uuid
import asyncio
import subprocess
from aiohttp import web
from telebot.async_telebot import AsyncTeleBot
from shazamio import Shazam
import yt_dlp

BOT_TOKEN = os.environ.get("BOT_TOKEN")
bot = AsyncTeleBot(BOT_TOKEN)
shazam = Shazam()

TEMP_DIR = "downloads"
os.makedirs(TEMP_DIR, exist_ok=True)

BOT_USERNAME = ""


def extract_sample_for_shazam(media_path: str, sample_output_path: str) -> str:
    """Shazam aniq tanishi uchun fayldan 25 soniyalik toza audio namuna oladi."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        media_path,
        "-t",
        "25",
        "-vn",
        "-acodec",
        "libmp3lame",
        "-ab",
        "128k",
        "-ar",
        "44100",
        sample_output_path,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return sample_output_path


def download_video_from_url(url: str, output_base: str) -> str:
    """Havoladagi videoni MP4 formatda yuklab oladi (45 MB gacha)."""
    ydl_opts = {
        "format": "best[ext=mp4][filesize<45M]/bestvideo[ext=mp4][filesize<40M]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": f"{output_base}.%(ext)s",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": 45 * 1024 * 1024,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        base, _ = os.path.splitext(filename)
        mp4_file = f"{base}.mp4"
        if os.path.exists(mp4_file):
            return mp4_file
        return filename


def full_track_filter(info, *, incomplete):
    """60 soniyadan qisqa parchalarni o'tkazib yuboradi."""
    duration = info.get("duration")
    if duration and duration < 60:
        return "Qisqa parcha, keyingisi tekshiriladi"
    return None


def download_full_mp3(artist: str, title: str, output_base: str) -> str:
    """Bloklangan yoki qisqa parchalarni chetlab o'tib, to'liq MP3 faylni yuklaydi."""
    search_queries = [
        f"scsearch5:{artist} - {title}",
        f"scsearch5:{title} {artist}",
        f"ytsearch5:{artist} - {title} official audio",
    ]

    mp3_file = f"{output_base}.mp3"

    for query in search_queries:
        if os.path.exists(mp3_file):
            os.remove(mp3_file)

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"{output_base}.%(ext)s",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "max_downloads": 1,
            "match_filter": full_track_filter,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([query])
        except Exception as e:
            print(f"Qidiruv jarayoni ({query}): {e}")

        if os.path.exists(mp3_file):
            if os.path.getsize(mp3_file) > 700 * 1024:
                return mp3_file
            else:
                os.remove(mp3_file)

    raise Exception("To'liq MP3 fayl topilmadi.")


def get_promo_line() -> str:
    """Botning o'z manzilini chiroyli reklama ko'rinishida qaytaradi."""
    if BOT_USERNAME:
        return f"\n\n🤖 @{BOT_USERNAME} orqali yuklandi"
    return ""


async def recognize_and_send_full_music(chat_id: int, status_msg_id: int, sample_path: str):
    """Shazam orqali qo'shiqni aniqlaydi va to'liq MP3 faylini reklama matni bilan yuboradi."""
    full_mp3_path = None
    promo = get_promo_line()
    try:
        result = await shazam.recognize(sample_path)
        track = result.get("track")

        if not track:
            await bot.edit_message_text(
                "❌ Musiqa Shazam bazasidan topilmadi.",
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
            f"{promo}"
        )

        await bot.edit_message_text(
            f"✅ Topildi: **{artist} - {title}**\n📥 To'liq MP3 yuklanmoqda...",
            chat_id=chat_id,
            message_id=status_msg_id,
            parse_mode="Markdown",
        )

        try:
            mp3_base = os.path.join(TEMP_DIR, str(uuid.uuid4()))
            full_mp3_path = await asyncio.to_thread(
                download_full_mp3, artist, title, mp3_base
            )

            if full_mp3_path and os.path.exists(full_mp3_path):
                with open(full_mp3_path, "rb") as audio_file:
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
                raise Exception("Fayl yaratilmadi")

        except Exception as download_error:
            print(f"To'liq MP3 yuklashda xatolik: {download_error}")
            await bot.edit_message_text(
                f"✅ Topildi: **{artist} - {title}**\n\n"
                f"⚠ Afsuski, bu qo'shiqning to'liq MP3 fayli ochiq manbalardan topilmadi:\n"
                f"🔗 [Shazam'da tinglash]({url})"
                f"{promo}",
                chat_id=chat_id,
                message_id=status_msg_id,
                parse_mode="Markdown",
            )
    finally:
        if full_mp3_path and os.path.exists(full_mp3_path):
            try:
                os.remove(full_mp3_path)
            except OSError:
                pass


@bot.message_handler(commands=["start", "help"])
async def send_welcome(message):
    text = (
        "Salom! Men video va to'liq musiqani yuklab beruvchi botman.\n\n"
        "Menga quyidagilardan birini yuboring:\n"
        "• Instagram Reels, TikTok yoki YouTube havolasi (tepada video, tagida to'liq MP3 yuboraman)\n"
        "• Ovozli xabar (golos)\n"
        "• Qisqa video yoki dumaloq video\n"
        "• Audio fayl"
    )
    await bot.reply_to(message, text)


@bot.message_handler(content_types=["audio", "voice", "video", "video_note"])
async def handle_media(message):
    status_msg = await bot.reply_to(message, "Musiqa qidirilmoqda, biroz kuting...")
    raw_path = None
    sample_mp3 = None

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
        raw_path = os.path.join(TEMP_DIR, f"{uuid.uuid4()}{ext}")

        downloaded_bytes = await bot.download_file(file_info.file_path)
        with open(raw_path, "wb") as f:
            f.write(downloaded_bytes)

        sample_mp3 = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.mp3")
        await asyncio.to_thread(extract_sample_for_shazam, raw_path, sample_mp3)

        await recognize_and_send_full_music(
            message.chat.id, status_msg.message_id, sample_mp3
        )

    except Exception as e:
        print(f"Media xatosi: {e}")
        await bot.edit_message_text(
            "Xatolik yuz berdi. Qisqaroq audio yoki video yuborib ko'ring.",
            chat_id=message.chat.id,
            message_id=status_msg.message_id,
        )
    finally:
        for path in (raw_path, sample_mp3):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


@bot.message_handler(func=lambda m: m.text and re.search(r"https?://\S+", m.text))
async def handle_link(message):
    match = re.search(r"https?://\S+", message.text)
    url = match.group(0)
    status_msg = await bot.reply_to(message, "📥 Havoladan video yuklanmoqda, biroz kuting...")
    video_path = None
    sample_mp3 = None
    promo = get_promo_line()

    try:
        base_path = os.path.join(TEMP_DIR, str(uuid.uuid4()))
        video_path = await asyncio.to_thread(download_video_from_url, url, base_path)

        if video_path and os.path.exists(video_path):
            with open(video_path, "rb") as video_file:
                await bot.send_video(
                    message.chat.id,
                    video_file,
                    caption=f"🎬 Videongiz tayyor!{promo}",
                    supports_streaming=True,
                )

            await bot.edit_message_text(
                "🎵 Videodagi musiqa aniqlanmoqda...",
                chat_id=message.chat.id,
                message_id=status_msg.message_id,
            )
            sample_mp3 = os.path.join(TEMP_DIR, f"{uuid.uuid4()}.mp3")
            await asyncio.to_thread(extract_sample_for_shazam, video_path, sample_mp3)

            await recognize_and_send_full_music(
                message.chat.id, status_msg.message_id, sample_mp3
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
        for path in (video_path, sample_mp3):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


async def handle_web(request):
    return web.Response(text="Bot ishlamoqda!")


async def main():
    global BOT_USERNAME
    me = await bot.get_me()
    BOT_USERNAME = me.username or ""

    app = web.Application()
    app.router.add_get("/", handle_web)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    print(f"Bot @{BOT_USERNAME} ishga tushdi...")
    await bot.polling(non_stop=True)


if __name__ == "__main__":
    asyncio.run(main())

