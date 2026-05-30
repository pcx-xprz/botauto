"""
EXEGroup CEX Listing Airdrop — Auto Bot
Menggunakan Telethon untuk mengotomasi semua task Telegram.
"""

import asyncio
import re
import sys
import logging
from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
from telethon.errors import (
    UserAlreadyParticipantError,
    FloodWaitError,
    SessionPasswordNeededError,
)

logging.basicConfig(
    format="[%(asctime)s] %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
log = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
#  Import config                                                       #
# ------------------------------------------------------------------ #
try:
    import config
except ImportError:
    log.error("config.py tidak ditemukan! Salin config.py dan isi dulu.")
    sys.exit(1)


# ------------------------------------------------------------------ #
#  Helper                                                             #
# ------------------------------------------------------------------ #

def solve_math(text: str) -> str | None:
    """
    Deteksi soal matematika sederhana dari teks bot dan kembalikan jawabannya.
    Contoh: '75 - 14 =' → '61'
    """
    match = re.search(r"(\d+)\s*([\+\-\*\/])\s*(\d+)\s*=", text)
    if not match:
        return None
    a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
    ops = {"+": a + b, "-": a - b, "*": a * b, "/": a // b}
    answer = ops.get(op)
    log.info(f"🔢 Deteksi soal: {a} {op} {b} = {answer}")
    return str(answer)


async def click_button(client: TelegramClient, message, label_keywords: list[str]) -> bool:
    """
    Cari dan klik inline button berdasarkan keyword label (case-insensitive).
    Kembalikan True jika berhasil diklik.
    """
    if not message.buttons:
        return False
    for row in message.buttons:
        for btn in row:
            btn_text = btn.text.lower()
            if any(kw.lower() in btn_text for kw in label_keywords):
                log.info(f"🖱️  Klik tombol: '{btn.text}'")
                await btn.click()
                return True
    return False


async def find_button(message, label_keywords: list[str]):
    """Kembalikan objek button pertama yang cocok dengan keyword."""
    if not message.buttons:
        return None
    for row in message.buttons:
        for btn in row:
            if any(kw.lower() in btn.text.lower() for kw in label_keywords):
                return btn
    return None


# ------------------------------------------------------------------ #
#  Core automation per akun                                           #
# ------------------------------------------------------------------ #

async def run_account(session: str, api_id: int, api_hash: str, wallet: str):
    log.info(f"\n{'='*55}")
    log.info(f"🚀 Memulai akun: {session}")
    log.info(f"{'='*55}")

    client = TelegramClient(session, api_id, api_hash)
    await client.start()

    # Pastikan sudah terautentikasi
    if not await client.is_user_authorized():
        log.error(f"❌ Session '{session}' belum login. Jalankan login_helper.py terlebih dulu.")
        await client.disconnect()
        return

    me = await client.get_me()
    log.info(f"✅ Login sebagai: @{me.username or me.first_name} (ID: {me.id})")

    bot = config.BOT_USERNAME
    delay = config.DELAY_BETWEEN_STEPS

    # -------------------------------------------------------------- #
    #  LANGKAH 1 — /start dengan referral code                        #
    # -------------------------------------------------------------- #
    log.info("📨 Mengirim /start ke bot...")
    await client.send_message(bot, f"/start {config.REFERRAL_CODE}")
    await asyncio.sleep(delay)

    # Ambil pesan terbaru dari bot
    messages = await client.get_messages(bot, limit=5)
    last_msg = messages[0] if messages else None

    # -------------------------------------------------------------- #
    #  LANGKAH 2 — Selesaikan math captcha                            #
    # -------------------------------------------------------------- #
    captcha_solved = False
    for msg in messages:
        if not msg.text:
            continue
        answer = solve_math(msg.text)
        if answer:
            # Cari & klik tombol "Continue" dulu jika ada
            cont_btn = await find_button(msg, ["continue", "lanjut"])
            if cont_btn:
                log.info("🖱️  Klik 'Continue'...")
                await cont_btn.click()
                await asyncio.sleep(delay)

            log.info(f"📝 Mengirim jawaban captcha: {answer}")
            await client.send_message(bot, answer)
            await asyncio.sleep(delay)
            captcha_solved = True
            break

    if not captcha_solved:
        log.warning("⚠️  Captcha tidak ditemukan — mungkin sudah diselesaikan sebelumnya.")

    # Refresh pesan setelah captcha
    await asyncio.sleep(delay)
    messages = await client.get_messages(bot, limit=5)

    # -------------------------------------------------------------- #
    #  LANGKAH 3 — Join Telegram Group                                #
    # -------------------------------------------------------------- #
    log.info(f"👥 Join grup: @{config.GROUP_TO_JOIN}")
    try:
        entity = await client.get_entity(config.GROUP_TO_JOIN)
        await client(JoinChannelRequest(entity))
        log.info("✅ Berhasil join grup!")
    except UserAlreadyParticipantError:
        log.info("ℹ️  Sudah menjadi anggota grup.")
    except FloodWaitError as e:
        log.warning(f"⏳ FloodWait: tunggu {e.seconds} detik...")
        await asyncio.sleep(e.seconds)
    except Exception as e:
        log.error(f"❌ Gagal join grup: {e}")

    await asyncio.sleep(delay)

    # -------------------------------------------------------------- #
    #  LANGKAH 4 — Klik tombol "Done" di bot                          #
    # -------------------------------------------------------------- #
    log.info("🔘 Mencari dan klik tombol 'Done'...")
    messages = await client.get_messages(bot, limit=10)
    done_clicked = False
    for msg in messages:
        if await click_button(client, msg, ["done", "selesai", "✅"]):
            done_clicked = True
            await asyncio.sleep(delay)
            break

    if not done_clicked:
        log.warning("⚠️  Tombol 'Done' tidak ditemukan, mencoba kirim teks 'Done'...")
        await client.send_message(bot, "Done")
        await asyncio.sleep(delay)

    # -------------------------------------------------------------- #
    #  LANGKAH 5 — Submit wallet address                              #
    # -------------------------------------------------------------- #
    log.info(f"💳 Submit wallet: {wallet}")
    await asyncio.sleep(delay)

    # Ambil pesan terbaru, cek apakah bot meminta wallet
    messages = await client.get_messages(bot, limit=5)
    wallet_sent = False
    for msg in messages:
        if msg.text and any(kw in msg.text.lower() for kw in ["wallet", "address", "submit", "eth", "base"]):
            log.info("📬 Bot meminta wallet, mengirim sekarang...")
            await client.send_message(bot, wallet)
            wallet_sent = True
            await asyncio.sleep(delay)
            break

    if not wallet_sent:
        # Kirim langsung jika tidak ada prompt spesifik
        log.info("📬 Mengirim wallet address langsung...")
        await client.send_message(bot, wallet)
        await asyncio.sleep(delay)

    # -------------------------------------------------------------- #
    #  LANGKAH 6 — Cek status akhir                                   #
    # -------------------------------------------------------------- #
    await asyncio.sleep(delay)
    messages = await client.get_messages(bot, limit=3)
    log.info("\n📊 Pesan terakhir dari bot:")
    for msg in messages:
        if msg.text:
            # Tampilkan 300 karakter pertama
            preview = msg.text[:300].replace("\n", " | ")
            log.info(f"   └─ {preview}")

    log.info(f"\n✅ Selesai untuk akun: {session}")
    log.info("⚠️  INGAT: Follow Twitter @PegaBankEXE dan Retweet pinned post secara manual!")

    await client.disconnect()


# ------------------------------------------------------------------ #
#  Entry point                                                        #
# ------------------------------------------------------------------ #

async def main():
    # Tentukan mode: multi-account atau single-account
    if config.ACCOUNTS:
        log.info(f"🔄 Mode MULTI-ACCOUNT — {len(config.ACCOUNTS)} akun terdeteksi")
        for idx, acc in enumerate(config.ACCOUNTS):
            session, api_id, api_hash, wallet = acc
            await run_account(session, api_id, api_hash, wallet)
            if idx < len(config.ACCOUNTS) - 1:
                wait = config.DELAY_BETWEEN_ACCOUNTS
                log.info(f"⏳ Jeda {wait} detik sebelum akun berikutnya...")
                await asyncio.sleep(wait)
    else:
        log.info("👤 Mode SINGLE-ACCOUNT")
        await run_account(
            config.SESSION_NAME,
            config.API_ID,
            config.API_HASH,
            config.WALLET_ADDRESS,
        )

    log.info("\n🎉 Semua akun selesai diproses!")


if __name__ == "__main__":
    asyncio.run(main())
