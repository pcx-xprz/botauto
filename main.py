"""
EXEGroup CEX Listing Airdrop — Auto Bot
Event-loop driven: baca setiap pesan bot → deteksi konteks → respon tepat.
Tidak ada urutan step yang hardcoded — semua dinamis dari isi pesan bot.
"""

import asyncio
import os
import re
import sys

from telethon import TelegramClient
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
def step(msg):   print(f"\n{c(MAGENTA, '──▶')} {msg}")
def banner(msg): print(f"\n{c(CYAN, BOLD + msg + RESET)}")
def botlog(text):
    preview = text.replace("\n", " │ ")[:220]
    print(f"   {c(WHITE, '🤖 BOT:')} {preview}")


# ── File loaders ─────────────────────────────────────────────────────────────

def load_accounts() -> list[dict]:
    path = config.ACCOUNTS_FILE
    if not os.path.exists(path):
        err(f"File {path} tidak ditemukan!")
        sys.exit(1)
    out = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                warn(f"accounts.txt baris {lineno} format salah, dilewati.")
                continue
            out.append({
                "session_name": parts[0],
                "api_id":       int(parts[1]),
                "api_hash":     parts[2],
            })
    return out


def load_lines(filepath: str) -> list[str]:
    if not os.path.exists(filepath):
        warn(f"File {filepath} tidak ditemukan.")
        return []
    with open(filepath) as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def clean_twitter(raw: str) -> str:
    """Hapus semua @ di depan username."""
    return raw.lstrip("@").strip()


# ── Math solver ───────────────────────────────────────────────────────────────

def solve_math(text: str) -> str | None:
    """Deteksi & selesaikan soal matematika dari teks bot (dinamis)."""
    normalized = text.replace("×", "*").replace("÷", "/").replace(" x ", " * ")
    m = re.search(r"(\d+)\s*([\+\-\*\/])\s*(\d+)\s*=", normalized)
    if not m:
        return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    result = {"+": a + b, "-": a - b, "*": a * b, "/": a // b}.get(op)
    if result is None:
        return None
    info(f"Soal: {c(WHITE, f'{a} {op} {b}')} = {c(GREEN, str(result))}")
    return str(result)


# ── Helpers ───────────────────────────────────────────────────────────────────

def has_keyword(text: str, keywords: list[str]) -> bool:
    t = text.lower()
    return any(k.lower() in t for k in keywords)


async def get_bot_msgs(client, bot, limit=6):
    return await client.get_messages(bot, limit=limit)


async def last_msg_id(client, bot) -> int:
    msgs = await client.get_messages(bot, limit=1)
    return msgs[0].id if msgs else 0


async def wait_reply(client, bot, after_id: int, timeout=20, poll=1.5) -> list:
    """Polling sampai ada pesan baru dari bot setelah after_id."""
    elapsed = 0.0
    while elapsed < timeout:
        await asyncio.sleep(poll)
        elapsed += poll
        msgs = await client.get_messages(bot, limit=6)
        new = [m for m in msgs if m.id > after_id]
        if new:
            return new
    warn(f"Timeout {timeout}s menunggu balasan bot.")
    return []


async def find_and_click_button(msgs: list, keywords: list[str]) -> bool:
    """
    Scan semua pesan dari list → cari inline button yg cocok keyword → klik.
    Return True jika berhasil klik.
    """
    for msg in msgs:
        if not msg.buttons:
            continue
        for row in msg.buttons:
            for btn in row:
                if has_keyword(btn.text, keywords):
                    info(f"Klik tombol: '{c(WHITE, btn.text)}'")
                    await btn.click()
                    return True
    return False


async def join_channel(client, target: str):
    clean = target.replace("https://t.me/", "").replace("@", "").strip()
    info(f"Join: {c(WHITE, clean)}")
    try:
        entity = await client.get_entity(clean)
        await client(JoinChannelRequest(entity))
        ok("Berhasil bergabung!")
    except UserAlreadyParticipantError:
        ok("Sudah menjadi anggota.")
    except FloodWaitError as e:
        warn(f"FloodWait {e.seconds}s...")
        await asyncio.sleep(e.seconds + 2)
    except Exception as e:
        if "already participant" in str(e).lower():
            ok("Sudah menjadi anggota.")
        else:
            err(f"Gagal join: {e}")


# ── Inti: respond_to_bot — baca setiap balasan, respon sesuai konteks ─────────

async def respond_to_bot(
    client,
    bot: str,
    msgs: list,
    wallet: str,
    twitter: str,
    state: dict,
) -> bool:
    """
    Terima list pesan terbaru dari bot.
    Deteksi apa yang diminta bot → eksekusi → return True jika ada aksi.
    state: dict untuk tracking apa yang sudah dikerjakan.
    """
    acted = False

    for msg in msgs:
        if not msg.text and not msg.buttons:
            continue

        text = msg.text or ""

        # ── A. Ada soal math → klik Continue dulu → kirim jawaban ────────────
        if not state.get("captcha_done") and solve_math(text):
            answer = solve_math(text)
            step("Captcha: klik Continue → kirim jawaban")
            botlog(text[:120])

            # Klik Continue jika ada
            if msg.buttons:
                clicked = await find_and_click_button([msg], ["continue", "lanjut", "next"])
                if clicked:
                    await asyncio.sleep(config.DELAY_STEP)

            # Kirim jawaban
            chk = await last_msg_id(client, bot)
            info(f"Kirim jawaban: {c(GREEN, answer)}")
            await client.send_message(bot, answer)

            # Tunggu konfirmasi bot
            conf = await wait_reply(client, bot, chk)
            if conf:
                dump_text = conf[0].text or ""
                botlog(dump_text[:180])
                if has_keyword(dump_text, ["correct", "benar", "welcome", "✅"]):
                    ok("Captcha benar!")

            state["captcha_done"] = True
            acted = True
            break   # proses ulang dari pesan baru

        # ── B. Ada tombol Done/Continue yang belum diklik ─────────────────────
        #    Kondisi: captcha sudah selesai, dan ada button Done/Continue
        if state.get("captcha_done") and not state.get("done_clicked"):
            if msg.buttons:
                has_done = any(
                    has_keyword(btn.text, ["done", "selesai", "✅", "continue", "next", "lanjut"])
                    for row in msg.buttons for btn in row
                )
                if has_done:
                    step("Tombol aksi ditemukan — klik")
                    botlog(text[:120] if text else "(pesan dengan tombol)")
                    chk = await last_msg_id(client, bot)
                    clicked = await find_and_click_button(
                        [msg], ["done", "selesai", "✅", "continue", "next", "lanjut"]
                    )
                    if clicked:
                        state["done_clicked"] = True
                        # Tunggu respon bot
                        new_msgs = await wait_reply(client, bot, chk)
                        if new_msgs:
                            botlog((new_msgs[0].text or "")[:180])
                        acted = True
                        break

        # ── C. Bot minta Twitter ──────────────────────────────────────────────
        if (not state.get("twitter_sent")
                and has_keyword(text, ["twitter", "tweet", "follow", "retweet", "your twitter"])):
            step("Bot minta Twitter username")
            botlog(text[:180])

            # Join grup Telegram dulu jika belum
            if not state.get("group_joined"):
                await join_channel(client, config.GROUP_TO_JOIN)
                state["group_joined"] = True
                await asyncio.sleep(config.DELAY_STEP)

            # Klik Done/Continue jika masih ada tombol
            if msg.buttons:
                chk = await last_msg_id(client, bot)
                clicked = await find_and_click_button(
                    [msg], ["done", "selesai", "✅", "continue", "next", "lanjut", "join"]
                )
                if clicked:
                    state["done_clicked"] = True
                    new_msgs = await wait_reply(client, bot, chk)
                    if new_msgs:
                        # Cek apakah pesan baru sudah minta twitter
                        new_text = new_msgs[0].text or ""
                        botlog(new_text[:180])
                        if has_keyword(new_text, ["twitter", "tweet", "follow"]):
                            # Langsung kirim twitter di sini
                            chk2 = await last_msg_id(client, bot)
                            tw = f"@{twitter}" if twitter else ""
                            info(f"Kirim Twitter: {c(WHITE, tw)}")
                            await client.send_message(bot, tw)
                            tw_reply = await wait_reply(client, bot, chk2)
                            if tw_reply:
                                tw_text = tw_reply[0].text or ""
                                botlog(tw_text[:180])
                                if has_keyword(tw_text, ["invalid", "format", "error"]):
                                    warn("Format ditolak, coba tanpa @...")
                                    chk3 = await last_msg_id(client, bot)
                                    await client.send_message(bot, twitter)
                                    r = await wait_reply(client, bot, chk3)
                                    if r: botlog((r[0].text or "")[:180])
                                else:
                                    ok("Twitter diterima!")
                            state["twitter_sent"] = True
                            acted = True
                            break
                    acted = True
                    break

            # Tidak ada tombol, langsung kirim twitter
            if twitter and not state.get("twitter_sent"):
                chk = await last_msg_id(client, bot)
                tw = f"@{twitter}"
                info(f"Kirim Twitter: {c(WHITE, tw)}")
                await client.send_message(bot, tw)
                tw_reply = await wait_reply(client, bot, chk)
                if tw_reply:
                    tw_text = tw_reply[0].text or ""
                    botlog(tw_text[:180])
                    if has_keyword(tw_text, ["invalid", "format", "error"]):
                        warn("Format ditolak, coba tanpa @...")
                        chk2 = await last_msg_id(client, bot)
                        await client.send_message(bot, twitter)
                        r = await wait_reply(client, bot, chk2)
                        if r: botlog((r[0].text or "")[:180])
                    else:
                        ok("Twitter diterima!")
                state["twitter_sent"] = True
                acted = True
                break

        # ── D. Bot minta wallet address ───────────────────────────────────────
        if (not state.get("wallet_sent")
                and has_keyword(text, ["wallet", "address", "eth", "base", "0x", "submit your", "enter your"])):
            step("Bot minta wallet address")
            botlog(text[:180])

            if wallet:
                chk = await last_msg_id(client, bot)
                info(f"Kirim wallet: {c(WHITE, wallet)}")
                await client.send_message(bot, wallet)
                w_reply = await wait_reply(client, bot, chk)
                if w_reply:
                    wt = w_reply[0].text or ""
                    botlog(wt[:180])
                    if has_keyword(wt, ["success", "✅", "received", "thank", "registered", "berhasil"]):
                        ok("Wallet diterima!")
                    else:
                        warn("Tidak ada konfirmasi wallet dari bot.")
                state["wallet_sent"] = True
            else:
                warn("Wallet kosong, skip.")
                state["wallet_sent"] = True

            acted = True
            break

        # ── E. Bot minta join grup (via pesan teks, bukan tombol) ─────────────
        if (not state.get("group_joined")
                and has_keyword(text, ["join", "bergabung", "t.me/"])
                and not state.get("twitter_sent")):
            step("Deteksi instruksi join grup")
            botlog(text[:120])
            await join_channel(client, config.GROUP_TO_JOIN)
            state["group_joined"] = True
            await asyncio.sleep(config.DELAY_STEP)
            # Jangan break — lanjut cek tombol di pesan yang sama

    return acted


# ── Main loop per akun ────────────────────────────────────────────────────────

async def run_account(
    session_name: str,
    api_id: int,
    api_hash: str,
    wallet: str,
    twitter: str,
):
    twitter = clean_twitter(twitter)

    banner("═" * 56)
    print(f"  {c(BOLD+CYAN, '🚀 AKUN')}   : {c(WHITE, session_name)}")
    print(f"  {c(CYAN, 'Wallet')}    : {c(WHITE, wallet or '(kosong)')}")
    print(f"  {c(CYAN, 'Twitter')}   : {c(WHITE, '@'+twitter if twitter else '(kosong)')}")
    banner("═" * 56)

    session_path = os.path.join(
        config.SESSIONS_DIR,
        session_name.replace(".session", "")
    )
    if not os.path.exists(f"{session_path}.session"):
        err(f"Session tidak ada: {session_path}.session — dilewati.")
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

    # State tracker — apa yang sudah dikerjakan
    state = {
        "captcha_done":  False,
        "group_joined":  False,
        "done_clicked":  False,
        "twitter_sent":  False,
        "wallet_sent":   False,
    }

    # ── MULAI: kirim /start ───────────────────────────────────────────────────
    step(f"/start @{bot} (ref: {config.REFERRAL_CODE})")
    chk = await last_msg_id(client, bot)
    await client.send_message(bot, f"/start {config.REFERRAL_CODE}")
    first_reply = await wait_reply(client, bot, chk, timeout=15)
    if not first_reply:
        err("Bot tidak merespon /start. Abort.")
        await client.disconnect()
        return

    # ── LOOP UTAMA: proses respon bot sampai semua task selesai ───────────────
    current_msgs = first_reply
    max_rounds   = 20   # batas loop agar tidak infinite

    for round_num in range(max_rounds):
        # Semua task selesai?
        if state["wallet_sent"]:
            ok("Semua task selesai!")
            break

        acted = await respond_to_bot(client, bot, current_msgs, wallet, twitter, state)

        if not acted:
            # Tidak ada aksi → cek apakah ada pesan baru yang belum diproses
            all_msgs = await get_bot_msgs(client, bot, limit=8)
            # Cek dari pesan yang lebih baru dari checkpoint terakhir
            acted = await respond_to_bot(client, bot, all_msgs, wallet, twitter, state)
            if not acted:
                warn(f"Round {round_num+1}: tidak ada aksi terdeteksi, tunggu {config.DELAY_STEP}s...")
                await asyncio.sleep(config.DELAY_STEP)
                chk = await last_msg_id(client, bot)
                new = await wait_reply(client, bot, chk, timeout=10)
                if new:
                    current_msgs = new
                else:
                    # Jika twitter sudah sent tapi wallet belum, ambil pesan terbaru paksa
                    if state["twitter_sent"] and not state["wallet_sent"]:
                        current_msgs = await get_bot_msgs(client, bot, limit=6)
                    else:
                        break
        else:
            # Ada aksi → ambil pesan terbaru dari bot untuk round berikutnya
            await asyncio.sleep(config.DELAY_STEP)
            current_msgs = await get_bot_msgs(client, bot, limit=6)

    # ── Status akhir ─────────────────────────────────────────────────────────
    step("Status akhir")
    final = await get_bot_msgs(client, bot, limit=4)
    print()
    for m in final[:3]:
        if m.text:
            botlog(m.text[:250])

    print()
    print(f"  📊 Summary akun {c(WHITE, session_name)}:")
    print(f"     Captcha  : {'✅' if state['captcha_done'] else '❌'}")
    print(f"     Join grup: {'✅' if state['group_joined'] else '❌'}")
    print(f"     Done klik: {'✅' if state['done_clicked'] else '❌'}")
    print(f"     Twitter  : {'✅' if state['twitter_sent'] else '❌'}")
    print(f"     Wallet   : {'✅' if state['wallet_sent']  else '❌'}")
    print()

    await client.disconnect()


# ── Entry point ──────────────────────────────────────────────────────────────

async def main():
    banner("╔══════════════════════════════════════════════════╗")
    banner("║   EXEGroup Airdrop Auto Bot  —  dynamic flow    ║")
    banner("╚══════════════════════════════════════════════════╝")

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
        w = addresses[i-1][:20] + "..." if i-1 < len(addresses) else c(RED, "(kosong)")
        t = "@" + clean_twitter(twitters[i-1]) if i-1 < len(twitters) else c(RED, "(kosong)")
        print(f"  {i}. {c(WHITE, acc['session_name']):<28} wallet: {w}  twitter: {t}")

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
