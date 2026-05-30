"""
EXEGroup CEX Listing Airdrop — Auto Bot
Multi-account | Auto solve math captcha | Auto join grup | Auto submit wallet & twitter
"""

import asyncio
import os
import re
import sys

from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import (
    UserAlreadyParticipantError,
    FloodWaitError,
    SessionPasswordNeededError,
)

import config

# ── ANSI Colors ─────────────────────────────────────────────────────────────
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
WHITE   = "\033[97m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

def c(color, text): return f"{color}{text}{RESET}"
def info(msg):    print(f"   {c(CYAN,   '[*]')} {msg}")
def ok(msg):      print(f"   {c(GREEN,  '[+]')} {msg}")
def warn(msg):    print(f"   {c(YELLOW, '[!]')} {msg}")
def err(msg):     print(f"   {c(RED,    '[✗]')} {msg}")
def step(msg):    print(f"\n{c(MAGENTA, '──▶')} {msg}")
def banner(msg):  print(f"\n{c(CYAN, BOLD + msg + RESET)}")


# ── Loader helpers ───────────────────────────────────────────────────────────

def load_accounts() -> list[dict]:
    """
    Baca accounts.txt
    Format tiap baris: namasesi,api_id,api_hash
    Contoh         : ash,20189390,0f38d53f4fc26bc21496299718d9fa18
    """
    path = config.ACCOUNTS_FILE
    if not os.path.exists(path):
        err(f"File {path} tidak ditemukan!")
        sys.exit(1)

    accounts = []
    with open(path, "r") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                warn(f"accounts.txt baris {lineno} format salah, dilewati.")
                continue
            accounts.append({
                "session_name": parts[0],
                "api_id":       int(parts[1]),
                "api_hash":     parts[2],
            })
    return accounts


def load_lines(filepath: str) -> list[str]:
    """Baca file teks, kembalikan list baris non-kosong."""
    if not os.path.exists(filepath):
        warn(f"File {filepath} tidak ditemukan, nilai akan dikosongkan.")
        return []
    with open(filepath, "r") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


# ── Math captcha solver ──────────────────────────────────────────────────────

def solve_math(text: str) -> str | None:
    """
    Deteksi dan selesaikan soal matematika sederhana dari teks bot.
    Mendukung: +  -  *  /  x  ×  ÷
    Contoh   : '75 - 14 =' → '61'
    """
    # Normalisasi operator alternatif
    normalized = text.replace("×", "*").replace("x", "*").replace("÷", "/")

    pattern = r"(\d+)\s*([\+\-\*\/])\s*(\d+)\s*="
    match = re.search(pattern, normalized)
    if not match:
        return None

    a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
    if   op == "+": result = a + b
    elif op == "-": result = a - b
    elif op == "*": result = a * b
    elif op == "/": result = a // b
    else: return None

    info(f"Deteksi soal: {a} {op} {b} = {c(GREEN, str(result))}")
    return str(result)


# ── Button helpers ───────────────────────────────────────────────────────────

async def click_button(message, keywords: list[str]) -> bool:
    """Klik inline button pertama yang labelnya mengandung salah satu keyword."""
    if not message.buttons:
        return False
    for row in message.buttons:
        for btn in row:
            if any(kw.lower() in btn.text.lower() for kw in keywords):
                info(f"Klik tombol: '{c(WHITE, btn.text)}'")
                await btn.click()
                return True
    return False


async def get_button(message, keywords: list[str]):
    """Kembalikan objek button pertama yang cocok."""
    if not message.buttons:
        return None
    for row in message.buttons:
        for btn in row:
            if any(kw.lower() in btn.text.lower() for kw in keywords):
                return btn
    return None


def print_bot_messages(messages, limit: int = 3):
    """Tampilkan preview pesan terakhir dari bot."""
    for msg in messages[:limit]:
        if msg.text:
            preview = msg.text[:250].replace("\n", " │ ")
            print(f"      {c(WHITE, '└─')} {preview}")


# ── Join channel/grup ────────────────────────────────────────────────────────

async def join_channel(client: TelegramClient, target: str):
    """Join channel atau grup Telegram. Toleran terhadap sudah-jadi-anggota."""
    clean = target.replace("https://t.me/", "").replace("@", "").strip()
    info(f"Join: {c(WHITE, clean)}")
    try:
        entity = await client.get_entity(clean)
        await client(JoinChannelRequest(entity))
        ok("Berhasil bergabung!")
    except UserAlreadyParticipantError:
        ok("Sudah menjadi anggota.")
    except FloodWaitError as e:
        warn(f"FloodWait — tunggu {e.seconds} detik...")
        await asyncio.sleep(e.seconds + 2)
    except ValueError:
        err(f"Username/link tidak valid: {clean}")
    except Exception as e:
        if "already participant" in str(e).lower():
            ok("Sudah menjadi anggota.")
        else:
            err(f"Gagal join: {e}")


# ── Core per-account automation ──────────────────────────────────────────────

async def run_account(
    session_name: str,
    api_id: int,
    api_hash: str,
    wallet: str,
    twitter: str,
):
    banner(f"{'═'*52}")
    print(f"  {c(BOLD+CYAN, '🚀 AKUN')}: {c(WHITE, session_name)}")
    print(f"  {c(CYAN, 'Wallet')} : {c(WHITE, wallet or '(tidak ada)')}")
    print(f"  {c(CYAN, 'Twitter')}: {c(WHITE, twitter or '(tidak ada)')}")
    banner(f"{'═'*52}")

    session_path = os.path.join(config.SESSIONS_DIR, session_name.replace(".session", ""))

    if not os.path.exists(f"{session_path}.session"):
        err(f"File session tidak ditemukan: {session_path}.session — dilewati.")
        return

    client = TelegramClient(session_path, api_id, api_hash)

    try:
        await client.connect()
    except Exception as e:
        err(f"Gagal konek: {e}")
        return

    if not await client.is_user_authorized():
        err("Session belum login! Jalankan login_helper.py terlebih dulu.")
        await client.disconnect()
        return

    me = await client.get_me()
    ok(f"Login sebagai: {c(WHITE, me.first_name)} (ID: {me.id})")

    bot    = config.BOT_USERNAME
    delay  = config.DELAY_STEP

    # ── STEP 1: /start ───────────────────────────────────────────────────────
    step("STEP 1 — Kirim /start ke bot")
    await client.send_message(bot, f"/start {config.REFERRAL_CODE}")
    await asyncio.sleep(delay)

    messages = await client.get_messages(bot, limit=8)

    # ── STEP 2: Selesaikan math captcha ─────────────────────────────────────
    step("STEP 2 — Deteksi & selesaikan math captcha")
    captcha_done = False
    for msg in messages:
        if not msg.text:
            continue
        answer = solve_math(msg.text)
        if answer:
            # Klik 'Continue' jika ada (instruksi bot: "Click Continue before typing")
            cont_btn = await get_button(msg, ["continue", "lanjut", "next"])
            if cont_btn:
                info(f"Klik '{c(WHITE, cont_btn.text)}' sebelum jawab...")
                await cont_btn.click()
                await asyncio.sleep(delay)

            info(f"Kirim jawaban: {c(GREEN, answer)}")
            await client.send_message(bot, answer)
            await asyncio.sleep(delay)
            captcha_done = True
            break

    if not captcha_done:
        warn("Captcha tidak terdeteksi — mungkin sudah selesai sebelumnya.")

    # Refresh pesan
    await asyncio.sleep(delay)
    messages = await client.get_messages(bot, limit=8)

    # ── STEP 3: Join Telegram grup ──────────────────────────────────────────
    step(f"STEP 3 — Join grup @{config.GROUP_TO_JOIN}")
    await join_channel(client, config.GROUP_TO_JOIN)
    await asyncio.sleep(delay)

    # ── STEP 4: Klik tombol Done ─────────────────────────────────────────────
    step("STEP 4 — Klik tombol 'Done'")
    messages = await client.get_messages(bot, limit=10)
    done_clicked = False
    for msg in messages:
        if await click_button(msg, ["done", "selesai", "✅", "complete", "finished"]):
            done_clicked = True
            await asyncio.sleep(delay)
            break

    if not done_clicked:
        warn("Tombol 'Done' tidak ditemukan, kirim teks 'Done'...")
        await client.send_message(bot, "Done")
        await asyncio.sleep(delay)

    # ── STEP 5: Submit Twitter username ─────────────────────────────────────
    if twitter:
        step(f"STEP 5 — Submit Twitter: @{twitter}")
        await asyncio.sleep(delay)
        messages = await client.get_messages(bot, limit=5)
        twitter_sent = False
        for msg in messages:
            if msg.text and any(kw in msg.text.lower() for kw in ["twitter", "follow", "tweet", "retweet"]):
                await client.send_message(bot, f"@{twitter}")
                twitter_sent = True
                await asyncio.sleep(delay)
                break
        if not twitter_sent:
            # Coba klik tombol Twitter / Follow jika ada
            for msg in messages:
                if await click_button(msg, ["twitter", "follow", "tweet"]):
                    await asyncio.sleep(delay)
                    await client.send_message(bot, f"@{twitter}")
                    await asyncio.sleep(delay)
                    break
    else:
        warn("STEP 5 dilewati — tidak ada data twitter.txt")

    # ── STEP 6: Submit wallet address ────────────────────────────────────────
    if wallet:
        step(f"STEP 6 — Submit wallet address")
        await asyncio.sleep(delay)
        messages = await client.get_messages(bot, limit=5)
        wallet_sent = False
        for msg in messages:
            if msg.text and any(kw in msg.text.lower() for kw in
                                ["wallet", "address", "submit", "eth", "base", "0x"]):
                info(f"Bot meminta wallet, kirim sekarang...")
                await client.send_message(bot, wallet)
                wallet_sent = True
                await asyncio.sleep(delay)
                break

        if not wallet_sent:
            info(f"Kirim wallet langsung: {c(WHITE, wallet)}")
            await client.send_message(bot, wallet)
            await asyncio.sleep(delay)
    else:
        warn("STEP 6 dilewati — tidak ada data address.txt")

    # ── STEP 7: Status akhir ─────────────────────────────────────────────────
    step("STEP 7 — Status akhir dari bot")
    await asyncio.sleep(delay)
    final_msgs = await client.get_messages(bot, limit=3)
    print_bot_messages(final_msgs)

    ok(f"Akun {c(WHITE, session_name)} selesai!\n")
    if not twitter:
        warn("Jangan lupa Follow @PegaBankEXE & Retweet pinned post secara manual!")

    await client.disconnect()


# ── Entry point ──────────────────────────────────────────────────────────────

async def main():
    banner("╔══════════════════════════════════════════════╗")
    banner("║   EXEGroup Airdrop Auto Bot  — by botauto   ║")
    banner("╚══════════════════════════════════════════════╝")

    # Buat folder sessions jika belum ada
    os.makedirs(config.SESSIONS_DIR, exist_ok=True)

    # Load semua data
    accounts  = load_accounts()
    addresses = load_lines(config.ADDRESS_FILE)
    twitters  = load_lines(config.TWITTER_FILE)

    if not accounts:
        err("Tidak ada akun di accounts.txt!")
        return

    print(f"\n{c(WHITE, BOLD + f'Total akun  : {len(accounts)}')}")
    print(f"{c(WHITE, f'Total wallet: {len(addresses)}')}")
    print(f"{c(WHITE, f'Total twitter: {len(twitters)}')}")
    print()

    # Tampilkan daftar akun
    print(c(CYAN, "Daftar akun yang terdeteksi:"))
    for i, acc in enumerate(accounts, 1):
        wallet  = addresses[i-1] if i-1 < len(addresses) else c(RED, "(kosong)")
        twitter = twitters[i-1]  if i-1 < len(twitters)  else c(RED, "(kosong)")
        print(f"  {i}. {c(WHITE, acc['session_name']):<30} wallet: {wallet}  twitter: {twitter}")

    print()

    # Pilih sesi
    sel = input(c(YELLOW, "[?] Pilih nomor sesi (contoh: 1,2,3 atau 'all'): ")).strip().lower()

    if sel == "all":
        selected = list(range(len(accounts)))
    else:
        try:
            selected = [int(x.strip()) - 1 for x in sel.split(",")]
            selected = [i for i in selected if 0 <= i < len(accounts)]
        except ValueError:
            err("Format input salah!")
            return

    if not selected:
        err("Tidak ada sesi valid dipilih.")
        return

    print(f"\n{c(MAGENTA, BOLD + f'▶ Memulai {len(selected)} akun...')}")

    for count, idx in enumerate(selected):
        acc     = accounts[idx]
        wallet  = addresses[idx] if idx < len(addresses) else ""
        twitter = twitters[idx]  if idx < len(twitters)  else ""

        await run_account(
            session_name = acc["session_name"],
            api_id       = acc["api_id"],
            api_hash     = acc["api_hash"],
            wallet       = wallet,
            twitter      = twitter,
        )

        if count < len(selected) - 1:
            wait = config.DELAY_ACCOUNT
            print(c(YELLOW, f"   ⏳ Jeda {wait} detik sebelum akun berikutnya...\n"))
            await asyncio.sleep(wait)

    banner("═" * 52)
    ok(c(GREEN + BOLD, "✅ Semua akun selesai diproses!"))
    banner("═" * 52)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{c(RED, '[!] Dihentikan oleh user.')}")
    except Exception as e:
        print(f"\n{c(RED, f'[!] Error sistem: {e}')}")
