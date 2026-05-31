"""
EXEGroup CEX Listing Airdrop — Auto Bot
Conversation-driven: setiap step BACA dulu balasan bot, baru respon.
"""

import asyncio
import os
import re
import sys

from telethon import TelegramClient, events
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError, FloodWaitError

import config

# ── ANSI Colors ──────────────────────────────────────────────────────────────
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
WHITE   = "\033[97m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

def c(color, text): return f"{color}{text}{RESET}"
def info(msg):   print(f"   {c(CYAN,   '[*]')} {msg}")
def ok(msg):     print(f"   {c(GREEN,  '[+]')} {msg}")
def warn(msg):   print(f"   {c(YELLOW, '[!]')} {msg}")
def err(msg):    print(f"   {c(RED,    '[✗]')} {msg}")
def step(n, msg):print(f"\n{c(MAGENTA, f'──▶ STEP {n}')} — {msg}")
def banner(msg): print(f"\n{c(CYAN, BOLD + msg + RESET)}")
def botlog(msg): print(f"   {c(WHITE, '🤖 BOT:')} {c(WHITE, msg[:200])}")


# ── Loader helpers ───────────────────────────────────────────────────────────

def load_accounts() -> list[dict]:
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
    if not os.path.exists(filepath):
        warn(f"File {filepath} tidak ditemukan.")
        return []
    with open(filepath, "r") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def clean_twitter(raw: str) -> str:
    """Normalkan username Twitter: hapus @ di depan, kembalikan tanpa @."""
    return raw.lstrip("@").strip()


# ── Math captcha solver ──────────────────────────────────────────────────────

def solve_math(text: str) -> str | None:
    """
    Cari dan selesaikan ekspresi matematika di dalam teks.
    Mendukung: + - * / × ÷ x (sebagai perkalian)
    Mengembalikan string hasil, atau None jika tidak ditemukan.
    """
    normalized = (
        text
        .replace("×", "*")
        .replace("÷", "/")
        # 'x' sebagai perkalian hanya jika diapit spasi/digit agar tidak salah parse
        .replace(" x ", " * ")
    )
    match = re.search(r"(\d+)\s*([\+\-\*\/])\s*(\d+)\s*=", normalized)
    if not match:
        return None
    a, op, b = int(match.group(1)), match.group(2), int(match.group(3))
    result = {"+": a+b, "-": a-b, "*": a*b, "/": a//b}.get(op)
    if result is None:
        return None
    info(f"Soal terdeteksi: {c(WHITE, f'{a} {op} {b}')} = {c(GREEN, str(result))}")
    return str(result)


# ── Tunggu & baca pesan baru dari bot ────────────────────────────────────────

async def wait_for_bot_reply(
    client: TelegramClient,
    bot: str,
    after_id: int,
    timeout: int = 15,
    poll: float = 1.5,
) -> list:
    """
    Polling sampai ada pesan baru dari bot dengan id > after_id.
    Kembalikan list pesan baru (terbaru di index 0), atau [] jika timeout.
    """
    waited = 0.0
    while waited < timeout:
        await asyncio.sleep(poll)
        waited += poll
        msgs = await client.get_messages(bot, limit=5)
        new = [m for m in msgs if m.id > after_id]
        if new:
            return new
    warn(f"Timeout {timeout}s menunggu balasan bot.")
    return []


async def last_bot_id(client: TelegramClient, bot: str) -> int:
    """Ambil id pesan terbaru dari bot (sebagai checkpoint)."""
    msgs = await client.get_messages(bot, limit=1)
    return msgs[0].id if msgs else 0


# ── Button helpers ───────────────────────────────────────────────────────────

async def click_button_in_msgs(msgs: list, keywords: list[str]) -> bool:
    """Cari dan klik tombol inline dari list pesan berdasarkan keyword."""
    for msg in msgs:
        if not msg.buttons:
            continue
        for row in msg.buttons:
            for btn in row:
                if any(kw.lower() in btn.text.lower() for kw in keywords):
                    info(f"Klik tombol: '{c(WHITE, btn.text)}'")
                    await btn.click()
                    return True
    return False


async def get_button_in_msgs(msgs: list, keywords: list[str]):
    for msg in msgs:
        if not msg.buttons:
            continue
        for row in msg.buttons:
            for btn in row:
                if any(kw.lower() in btn.text.lower() for kw in keywords):
                    return btn
    return None


def msgs_contain(msgs: list, keywords: list[str]) -> tuple[bool, str]:
    """
    Cek apakah salah satu pesan mengandung keyword (case-insensitive).
    Kembalikan (True, teks pesan) atau (False, "").
    """
    for msg in msgs:
        if not msg.text:
            continue
        lower = msg.text.lower()
        if any(kw.lower() in lower for kw in keywords):
            return True, msg.text
    return False, ""


def dump_msgs(msgs: list, limit: int = 2):
    """Print preview pesan bot untuk debug."""
    for m in msgs[:limit]:
        if m.text:
            preview = m.text.replace("\n", " │ ")[:220]
            botlog(preview)


# ── Join channel/grup ────────────────────────────────────────────────────────

async def join_channel(client: TelegramClient, target: str):
    clean = target.replace("https://t.me/", "").replace("@", "").strip()
    info(f"Join channel/grup: {c(WHITE, clean)}")
    try:
        entity = await client.get_entity(clean)
        await client(JoinChannelRequest(entity))
        ok("Berhasil bergabung!")
    except UserAlreadyParticipantError:
        ok("Sudah menjadi anggota.")
    except FloodWaitError as e:
        warn(f"FloodWait {e.seconds}s, menunggu...")
        await asyncio.sleep(e.seconds + 2)
    except ValueError:
        err(f"Username/link tidak valid: {clean}")
    except Exception as e:
        if "already participant" in str(e).lower():
            ok("Sudah menjadi anggota.")
        else:
            err(f"Gagal join: {e}")


# ── Core: conversation-driven automation ─────────────────────────────────────

async def run_account(
    session_name: str,
    api_id: int,
    api_hash: str,
    wallet: str,
    twitter: str,
):
    twitter = clean_twitter(twitter)   # pastikan tidak ada @ ganda

    banner("═" * 56)
    print(f"  {c(BOLD+CYAN,'🚀 AKUN')}  : {c(WHITE, session_name)}")
    print(f"  {c(CYAN,'Wallet')}   : {c(WHITE, wallet  or '(kosong)')}")
    print(f"  {c(CYAN,'Twitter')}  : {c(WHITE, '@'+twitter if twitter else '(kosong)')}")
    banner("═" * 56)

    session_path = os.path.join(
        config.SESSIONS_DIR,
        session_name.replace(".session", "")
    )

    if not os.path.exists(f"{session_path}.session"):
        err(f"Session tidak ditemukan: {session_path}.session — dilewati.")
        return

    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()
    except Exception as e:
        err(f"Gagal konek: {e}")
        return

    if not await client.is_user_authorized():
        err("Session belum login. Jalankan login_helper.py.")
        await client.disconnect()
        return

    me = await client.get_me()
    ok(f"Login: {c(WHITE, me.first_name)} (ID: {me.id})")

    bot = config.BOT_USERNAME

    # ────────────────────────────────────────────────────────────────────────
    # STEP 1 — /start
    # ────────────────────────────────────────────────────────────────────────
    step(1, "/start dengan referral code")
    checkpoint = await last_bot_id(client, bot)
    await client.send_message(bot, f"/start {config.REFERRAL_CODE}")

    # Tunggu bot balas
    replies = await wait_for_bot_reply(client, bot, checkpoint)
    if not replies:
        err("Bot tidak merespon /start. Abort.")
        await client.disconnect()
        return
    dump_msgs(replies)

    # ────────────────────────────────────────────────────────────────────────
    # STEP 2 — Math captcha
    # Baca pesan bot → cari soal → klik Continue → kirim jawaban
    # ────────────────────────────────────────────────────────────────────────
    step(2, "Deteksi & jawab math captcha")

    # Ambil semua pesan recent untuk cari soal
    all_msgs = await client.get_messages(bot, limit=6)
    captcha_done = False

    for msg in all_msgs:
        if not msg.text:
            continue
        answer = solve_math(msg.text)
        if not answer:
            continue

        # Instruksi bot: "Click on Continue BEFORE typing the code"
        cont_btn = await get_button_in_msgs([msg], ["continue", "lanjut", "next"])
        if cont_btn:
            info("Klik 'Continue' sesuai instruksi bot...")
            checkpoint = await last_bot_id(client, bot)
            await cont_btn.click()
            # Tunggu bot update/konfirmasi
            await asyncio.sleep(config.DELAY_STEP)

        # Kirim jawaban
        info(f"Kirim jawaban: {c(GREEN, answer)}")
        checkpoint = await last_bot_id(client, bot)
        await client.send_message(bot, answer)

        # Tunggu konfirmasi "That's correct"
        conf = await wait_for_bot_reply(client, bot, checkpoint)
        dump_msgs(conf)
        found, txt = msgs_contain(conf, ["correct", "benar", "welcome", "✅"])
        if found:
            ok("Captcha berhasil!")
        else:
            warn("Tidak ada konfirmasi 'correct', lanjut saja...")

        captcha_done = True
        break

    if not captcha_done:
        warn("Soal captcha tidak ditemukan — mungkin sudah dikerjakan sebelumnya.")
        # Refresh pesan terbaru untuk langkah berikutnya
        all_msgs = await client.get_messages(bot, limit=6)

    # ────────────────────────────────────────────────────────────────────────
    # STEP 3 — Join Telegram grup/channel
    # ────────────────────────────────────────────────────────────────────────
    step(3, f"Join grup @{config.GROUP_TO_JOIN}")
    await join_channel(client, config.GROUP_TO_JOIN)
    await asyncio.sleep(config.DELAY_STEP)

    # ────────────────────────────────────────────────────────────────────────
    # STEP 4 — Klik tombol "Done"
    # Baca pesan bot terbaru → cari tombol Done → klik → tunggu respon
    # ────────────────────────────────────────────────────────────────────────
    step(4, "Klik tombol 'Done'")
    all_msgs = await client.get_messages(bot, limit=8)
    dump_msgs(all_msgs, limit=1)

    checkpoint = await last_bot_id(client, bot)
    done_clicked = await click_button_in_msgs(
        all_msgs, ["done", "selesai", "✅", "complete", "finished"]
    )

    if done_clicked:
        # Tunggu respon bot setelah klik Done
        done_reply = await wait_for_bot_reply(client, bot, checkpoint)
        dump_msgs(done_reply)
        ok("Tombol Done diklik.")
    else:
        warn("Tombol 'Done' tidak ditemukan — kirim teks 'Done'")
        checkpoint = await last_bot_id(client, bot)
        await client.send_message(bot, "Done")
        done_reply = await wait_for_bot_reply(client, bot, checkpoint)
        dump_msgs(done_reply)

    # ────────────────────────────────────────────────────────────────────────
    # STEP 5 — Submit Twitter username
    # Baca instruksi bot → cari permintaan twitter → kirim
    # ────────────────────────────────────────────────────────────────────────
    step(5, "Submit Twitter username")
    all_msgs = await client.get_messages(bot, limit=5)

    # Cek apakah bot sudah meminta twitter
    has_twitter_req, _ = msgs_contain(
        all_msgs, ["twitter", "follow", "tweet", "retweet", "@"]
    )

    if twitter:
        tw_handle = f"@{twitter}"
        if has_twitter_req:
            info(f"Bot meminta twitter → kirim: {c(WHITE, tw_handle)}")
        else:
            # Mungkin ada tombol twitter
            tw_btn = await get_button_in_msgs(all_msgs, ["twitter", "follow"])
            if tw_btn:
                info(f"Klik tombol Twitter...")
                checkpoint = await last_bot_id(client, bot)
                await tw_btn.click()
                await wait_for_bot_reply(client, bot, checkpoint)
                all_msgs = await client.get_messages(bot, limit=5)
            info(f"Kirim twitter: {c(WHITE, tw_handle)}")

        checkpoint = await last_bot_id(client, bot)
        await client.send_message(bot, tw_handle)
        tw_reply = await wait_for_bot_reply(client, bot, checkpoint)
        dump_msgs(tw_reply)

        # Cek apakah ada error format dari bot
        error_found, err_txt = msgs_contain(tw_reply, ["invalid", "format", "error", "salah"])
        if error_found:
            # Coba kirim tanpa @ sebagai fallback
            warn(f"Format twitter ditolak bot, coba tanpa @...")
            checkpoint = await last_bot_id(client, bot)
            await client.send_message(bot, twitter)
            tw_reply2 = await wait_for_bot_reply(client, bot, checkpoint)
            dump_msgs(tw_reply2)
        else:
            ok("Twitter terkirim!")
    else:
        warn("SKIP — twitter.txt kosong untuk akun ini.")

    # ────────────────────────────────────────────────────────────────────────
    # STEP 6 — Submit wallet address
    # Baca instruksi bot → tunggu permintaan wallet → kirim
    # ────────────────────────────────────────────────────────────────────────
    step(6, "Submit wallet address")
    all_msgs = await client.get_messages(bot, limit=5)
    dump_msgs(all_msgs, limit=1)

    has_wallet_req, _ = msgs_contain(
        all_msgs, ["wallet", "address", "submit", "eth", "base", "0x", "enter your"]
    )

    if wallet:
        if has_wallet_req:
            info(f"Bot meminta wallet → kirim: {c(WHITE, wallet)}")
        else:
            info(f"Kirim wallet langsung: {c(WHITE, wallet)}")

        checkpoint = await last_bot_id(client, bot)
        await client.send_message(bot, wallet)
        wallet_reply = await wait_for_bot_reply(client, bot, checkpoint)
        dump_msgs(wallet_reply)

        ok_found, _ = msgs_contain(
            wallet_reply, ["success", "received", "berhasil", "✅", "thank", "registered"]
        )
        if ok_found:
            ok("Wallet diterima bot!")
        else:
            warn("Tidak ada konfirmasi wallet dari bot.")
    else:
        warn("SKIP — address.txt kosong untuk akun ini.")

    # ────────────────────────────────────────────────────────────────────────
    # STEP 7 — Status akhir
    # ────────────────────────────────────────────────────────────────────────
    step(7, "Status akhir dari bot")
    await asyncio.sleep(2)
    final = await client.get_messages(bot, limit=4)
    print()
    for m in final[:3]:
        if m.text:
            preview = m.text.replace("\n", " │ ")[:250]
            botlog(preview)

    ok(f"Akun {c(WHITE, session_name)} selesai!\n")

    await client.disconnect()


# ── Entry point ──────────────────────────────────────────────────────────────

async def main():
    banner("╔════════════════════════════════════════════════╗")
    banner("║   EXEGroup Airdrop Auto Bot  —  conversation  ║")
    banner("╚════════════════════════════════════════════════╝")

    os.makedirs(config.SESSIONS_DIR, exist_ok=True)

    accounts  = load_accounts()
    addresses = load_lines(config.ADDRESS_FILE)
    twitters  = load_lines(config.TWITTER_FILE)

    if not accounts:
        err("Tidak ada akun di accounts.txt!")
        return

    print(f"\n{c(BOLD+WHITE, f'Total akun   : {len(accounts)}')}")
    print(f"{c(WHITE, f'Total wallet : {len(addresses)}')}")
    print(f"{c(WHITE, f'Total twitter: {len(twitters)}')}\n")

    print(c(CYAN, "Daftar akun:"))
    for i, acc in enumerate(accounts, 1):
        w = addresses[i-1] if i-1 < len(addresses) else c(RED, "(kosong)")
        t = ("@" + clean_twitter(twitters[i-1])) if i-1 < len(twitters) else c(RED, "(kosong)")
        print(f"  {i}. {c(WHITE, acc['session_name']):<28} "
              f"wallet: {w[:20]}...  twitter: {t}")

    print()
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
            w = config.DELAY_ACCOUNT
            print(c(YELLOW, f"   ⏳ Jeda {w}s sebelum akun berikutnya...\n"))
            await asyncio.sleep(w)

    banner("═" * 56)
    ok(c(GREEN + BOLD, "✅ Semua akun selesai diproses!"))
    banner("═" * 56)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{c(RED, '[!] Dihentikan oleh user.')}")
    except Exception as e:
        print(f"\n{c(RED, f'[!] Error sistem: {e}')}")
