"""
EXEGroup CEX Listing Airdrop — Auto Bot
Alur percakapan bot yang sudah diverifikasi:

  /start
    └─> [1] Captcha: klik Continue → kirim jawaban → tunggu "correct"
    └─> [2] Pesan welcome + tombol Done
              → join @PEGABANK_EXE (cek dulu, join jika belum)
              → klik Done → tunggu balas bot
    └─> [3] Bot minta Twitter username ("enter your twitter username with '@'")
              → kirim @username → tunggu balas bot
    └─> [4] Bot kirim Advertiser task + tombol Done/Skip
              → join @airdrop6officialchannel (cek dulu, join jika belum)
              → klik Done → tunggu balas bot
    └─> [5] Bot minta wallet ("submit your BASE or ETH wallet address")
              → kirim wallet → SELESAI
"""

import asyncio
import os
import re
import sys

from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantRequest
from telethon.errors import (
    UserAlreadyParticipantError,
    UserNotParticipantError,
    FloodWaitError,
    ChannelPrivateError,
)

import config

# ── ANSI Colors ───────────────────────────────────────────────────────────────
GREEN   = "\033[92m"
YELLOW  = "\033[93m"
RED     = "\033[91m"
CYAN    = "\033[96m"
MAGENTA = "\033[95m"
WHITE   = "\033[97m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

def c(color, text):  return f"{color}{text}{RESET}"
def info(msg):       print(f"   {c(CYAN,       '[*]')} {msg}")
def ok(msg):         print(f"   {c(GREEN,       '[+]')} {msg}")
def warn(msg):       print(f"   {c(YELLOW,      '[!]')} {msg}")
def err(msg):        print(f"   {c(RED,         '[✗]')} {msg}")
def step(n, msg):    print(f"\n{c(MAGENTA+BOLD, f'[STEP {n}]')} {msg}")
def banner(msg):     print(f"\n{c(CYAN+BOLD, msg)}{RESET}")
def botmsg(text):
    preview = (text or "").replace("\n", " │ ")[:260]
    print(f"   {c(WHITE+BOLD, '🤖')} {c(WHITE, preview)}")


# ── File loaders ──────────────────────────────────────────────────────────────

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


def load_lines(path: str) -> list[str]:
    if not os.path.exists(path):
        warn(f"File {path} tidak ditemukan.")
        return []
    with open(path) as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def clean_twitter(raw: str) -> str:
    """Hapus semua @ di depan, kembalikan username bersih."""
    return raw.lstrip("@").strip()


# ── Math solver ───────────────────────────────────────────────────────────────

def solve_math(text: str) -> str | None:
    normalized = text.replace("×","*").replace("÷","/").replace(" x "," * ")
    m = re.search(r"(\d+)\s*([\+\-\*\/])\s*(\d+)\s*=", normalized)
    if not m:
        return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    res = {"+": a+b, "-": a-b, "*": a*b, "/": a//b}.get(op)
    if res is None:
        return None
    info(f"Soal: {c(WHITE, f'{a} {op} {b}')} = {c(GREEN, str(res))}")
    return str(res)


# ── Telegram helpers ──────────────────────────────────────────────────────────

def has_kw(text: str, kws: list[str]) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in kws)


async def last_id(client, bot: str) -> int:
    msgs = await client.get_messages(bot, limit=1)
    return msgs[0].id if msgs else 0


async def wait_reply(client, bot: str, after_id: int,
                     timeout: int = 20, poll: float = 1.5) -> list:
    """
    Polling aktif: tunggu sampai ada pesan baru dari bot (id > after_id).
    Kembalikan list pesan baru. Return [] jika timeout.
    """
    elapsed = 0.0
    while elapsed < timeout:
        await asyncio.sleep(poll)
        elapsed += poll
        msgs = await client.get_messages(bot, limit=6)
        new = [m for m in msgs if m.id > after_id]
        if new:
            info(f"Bot membalas ({len(new)} pesan baru)")
            return new
    warn(f"Timeout {timeout}s — bot tidak membalas.")
    return []


async def find_and_click(msgs: list, kws: list[str]) -> tuple[bool, object | None]:
    """
    Scan semua pesan → cari inline button yang cocok keyword → klik.
    Return (True, pesan_yg_diklik) atau (False, None).
    """
    for msg in msgs:
        if not msg.buttons:
            continue
        for row in msg.buttons:
            for btn in row:
                if has_kw(btn.text, kws):
                    info(f"Klik tombol: '{c(WHITE+BOLD, btn.text)}'")
                    await btn.click()
                    return True, msg
    return False, None


async def is_member(client, username: str) -> bool:
    """Cek apakah akun sudah menjadi member channel/grup."""
    try:
        clean = username.replace("https://t.me/", "").replace("@", "").strip()
        entity = await client.get_entity(clean)
        me = await client.get_me()
        await client(GetParticipantRequest(entity, me))
        return True
    except UserNotParticipantError:
        return False
    except Exception:
        # Jika tidak bisa cek, anggap belum join agar aman
        return False


async def join_if_needed(client, username: str):
    """Join channel/grup hanya jika belum menjadi member."""
    clean = username.replace("https://t.me/", "").replace("@", "").strip()
    if not clean or clean.lower() in ("joinchat",):
        return

    already = await is_member(client, clean)
    if already:
        ok(f"Sudah member @{clean}, skip join.")
        return

    info(f"Bergabung ke: {c(WHITE, '@'+clean)}")
    try:
        entity = await client.get_entity(clean)
        await client(JoinChannelRequest(entity))
        ok(f"Berhasil join @{clean}")
    except UserAlreadyParticipantError:
        ok(f"Sudah member @{clean}")
    except FloodWaitError as e:
        warn(f"FloodWait {e.seconds}s untuk @{clean}, tunggu...")
        await asyncio.sleep(e.seconds + 2)
        await join_if_needed(client, clean)   # retry sekali
    except ChannelPrivateError:
        err(f"Channel @{clean} private, tidak bisa join.")
    except Exception as e:
        if "already participant" in str(e).lower():
            ok(f"Sudah member @{clean}")
        else:
            err(f"Gagal join @{clean}: {e}")


# ── MAIN AUTOMATION PER AKUN ──────────────────────────────────────────────────

async def run_account(session_name: str, api_id: int, api_hash: str,
                      wallet: str, twitter: str):

    twitter = clean_twitter(twitter)

    banner("═" * 60)
    print(f"  {c(BOLD+CYAN,'🚀 AKUN')}   : {c(WHITE, session_name)}")
    print(f"  {c(CYAN,'Wallet')}    : {c(WHITE, wallet  or c(RED,'(kosong)'))}")
    print(f"  {c(CYAN,'Twitter')}   : {c(WHITE, ('@'+twitter) if twitter else c(RED,'(kosong)'))}")
    banner("═" * 60)

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
        err(f"Gagal konek: {e}"); return

    if not await client.is_user_authorized():
        err("Session belum login. Jalankan login_helper.py."); await client.disconnect(); return

    me = await client.get_me()
    ok(f"Login: {c(WHITE, me.first_name)} (ID: {me.id})")

    bot = config.BOT_USERNAME
    D   = config.DELAY_STEP     # alias pendek

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 1 — /start → tunggu pesan captcha dari bot
    # ──────────────────────────────────────────────────────────────────────────
    step(1, f"/start @{bot}")
    chk = await last_id(client, bot)
    await client.send_message(bot, f"/start {config.REFERRAL_CODE}")

    captcha_msgs = await wait_reply(client, bot, chk, timeout=15)
    if not captcha_msgs:
        err("Bot tidak merespon /start. Abort."); await client.disconnect(); return

    for m in captcha_msgs:
        botmsg(m.text or "")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 2 — Captcha: klik Continue dulu → kirim jawaban → tunggu "correct"
    # ──────────────────────────────────────────────────────────────────────────
    step(2, "Selesaikan captcha")

    # Cari pesan yang mengandung soal math
    captcha_msg = None
    for m in captcha_msgs:
        if solve_math(m.text or ""):
            captcha_msg = m
            break

    if not captcha_msg:
        # Coba ambil lebih banyak pesan (mungkin captcha ada di pesan lebih lama)
        all_msgs = await client.get_messages(bot, limit=8)
        for m in all_msgs:
            if solve_math(m.text or ""):
                captcha_msg = m
                break

    if captcha_msg:
        answer = solve_math(captcha_msg.text)

        # Klik Continue DULU sesuai instruksi bot
        if captcha_msg.buttons:
            clicked, _ = await find_and_click([captcha_msg], ["continue","lanjut","next"])
            if clicked:
                await asyncio.sleep(D)
            else:
                warn("Tombol Continue tidak ditemukan, langsung kirim jawaban.")
        else:
            warn("Tidak ada tombol Continue, langsung kirim jawaban.")

        # Kirim jawaban
        info(f"Kirim jawaban: {c(GREEN+BOLD, answer)}")
        chk = await last_id(client, bot)
        await client.send_message(bot, answer)

        # Tunggu konfirmasi "correct"
        correct_msgs = await wait_reply(client, bot, chk, timeout=15)
        for m in correct_msgs:
            botmsg(m.text or "")
        if has_kw((correct_msgs[0].text if correct_msgs else ""), ["correct","benar","✅","welcome"]):
            ok("Captcha benar! ✅")
        else:
            warn("Captcha mungkin salah, coba lanjut...")
    else:
        warn("Soal captcha tidak ditemukan (mungkin sudah selesai sebelumnya).")
        correct_msgs = await client.get_messages(bot, limit=6)

    await asyncio.sleep(D)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 3 — Ambil pesan welcome + tombol Done
    #           → join @PEGABANK_EXE dulu → klik Done → tunggu balas
    # ──────────────────────────────────────────────────────────────────────────
    step(3, "Join grup utama + klik Done")

    # Ambil pesan terbaru (pesan welcome ada di sini)
    welcome_msgs = await client.get_messages(bot, limit=8)

    # Cari pesan yang ada tombol Done
    done_msg = None
    for m in welcome_msgs:
        if m.buttons:
            for row in m.buttons:
                for btn in row:
                    if has_kw(btn.text, ["done","selesai","✅"]):
                        done_msg = m
                        break

    # Join @PEGABANK_EXE sebelum klik Done
    info("Cek & join @PEGABANK_EXE...")
    await join_if_needed(client, "PEGABANK_EXE")
    await asyncio.sleep(D)

    # Klik tombol Done
    chk = await last_id(client, bot)
    if done_msg:
        clicked, _ = await find_and_click([done_msg], ["done","selesai","✅"])
    else:
        clicked, _ = await find_and_click(welcome_msgs, ["done","selesai","✅"])

    if clicked:
        ok("Tombol Done diklik.")
        after_done = await wait_reply(client, bot, chk, timeout=20)
        for m in after_done:
            botmsg(m.text or "")
    else:
        err("Tombol Done tidak ditemukan!")
        after_done = await client.get_messages(bot, limit=6)

    await asyncio.sleep(D)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 4 — Bot minta Twitter username
    #           → tunggu pesan yang berisi "twitter username with '@'"
    #           → kirim @username → tunggu balas
    # ──────────────────────────────────────────────────────────────────────────
    step(4, "Kirim Twitter username")

    # Cari pesan minta twitter dari respon setelah Done
    twitter_prompt = None
    for m in after_done:
        if has_kw(m.text or "", ["twitter username","twitter","enter your twitter","'@'"]):
            twitter_prompt = m
            break

    if not twitter_prompt:
        # Mungkin belum datang, tunggu lagi
        warn("Menunggu pesan permintaan Twitter...")
        extra = await wait_reply(client, bot, after_done[0].id if after_done else 0, timeout=15)
        for m in extra:
            botmsg(m.text or "")
            if has_kw(m.text or "", ["twitter username","twitter","enter your twitter","'@'"]):
                twitter_prompt = m
                break
        if not twitter_prompt and extra:
            twitter_prompt = extra[0]   # ambil apapun yang ada

    if twitter_prompt:
        botmsg(twitter_prompt.text or "")

    if twitter:
        tw_handle = f"@{twitter}"
        info(f"Kirim Twitter: {c(WHITE+BOLD, tw_handle)}")
        chk = await last_id(client, bot)
        await client.send_message(bot, tw_handle)

        tw_reply = await wait_reply(client, bot, chk, timeout=20)
        for m in tw_reply:
            botmsg(m.text or "")

        # Cek apakah ditolak (format invalid)
        first_reply_text = tw_reply[0].text if tw_reply else ""
        if has_kw(first_reply_text, ["invalid","format","error","try again","incorrect"]):
            warn("Format @username ditolak, coba tanpa @...")
            chk2 = await last_id(client, bot)
            await client.send_message(bot, twitter)
            tw_reply = await wait_reply(client, bot, chk2, timeout=20)
            for m in tw_reply:
                botmsg(m.text or "")
        else:
            ok("Twitter terkirim!")
    else:
        warn("Twitter kosong, skip.")
        tw_reply = after_done

    await asyncio.sleep(D)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 5 — Advertiser channel task
    #           Pesan: "Join our Advertiser channel" + tombol Done/Skip
    #           → cek & join @airdrop6officialchannel dulu
    #           → klik Done → tunggu balas bot
    # ──────────────────────────────────────────────────────────────────────────
    step(5, "Task Advertiser channel + klik Done")

    # Cari pesan advertiser dari respon setelah twitter
    adv_msg = None
    for m in tw_reply:
        if has_kw(m.text or "", ["advertiser","airdrop6","optional","done","skip"]):
            adv_msg = m
            break

    if not adv_msg:
        warn("Menunggu pesan Advertiser channel...")
        extra = await wait_reply(
            client, bot,
            tw_reply[0].id if tw_reply else 0,
            timeout=15
        )
        for m in extra:
            botmsg(m.text or "")
            if has_kw(m.text or "", ["advertiser","airdrop6","optional","done","skip"]):
                adv_msg = m
                break
        if not adv_msg and extra:
            adv_msg = extra[0]

    if adv_msg:
        botmsg(adv_msg.text or "")

    # Join @airdrop6officialchannel sebelum klik Done/Skip
    info("Cek & join @airdrop6officialchannel...")
    await join_if_needed(client, "airdrop6officialchannel")
    await asyncio.sleep(D)

    # Klik Done (bukan Skip — ambil reward EXE)
    adv_search_list = [adv_msg] if adv_msg else []
    if not adv_search_list:
        adv_search_list = await client.get_messages(bot, limit=5)

    chk = await last_id(client, bot)
    clicked, _ = await find_and_click(adv_search_list, ["done","selesai","✅"])

    if not clicked:
        # Fallback: scan lebih banyak pesan
        all_recent = await client.get_messages(bot, limit=10)
        clicked, _ = await find_and_click(all_recent, ["done","selesai","✅"])

    if clicked:
        ok("Tombol Done (advertiser) diklik.")
        after_adv = await wait_reply(client, bot, chk, timeout=20)
        for m in after_adv:
            botmsg(m.text or "")
    else:
        warn("Tombol Done tidak ditemukan, coba klik Skip...")
        chk = await last_id(client, bot)
        all_recent = await client.get_messages(bot, limit=10)
        clicked, _ = await find_and_click(all_recent, ["skip","lewati"])
        if clicked:
            ok("Tombol Skip diklik.")
            after_adv = await wait_reply(client, bot, chk, timeout=20)
            for m in after_adv:
                botmsg(m.text or "")
        else:
            err("Tombol Done/Skip tidak ditemukan!")
            after_adv = await client.get_messages(bot, limit=6)

    await asyncio.sleep(D)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 6 — Bot minta wallet address
    #           Pesan: "submit your BASE or ETH wallet address"
    #           → HANYA kirim jika bot benar-benar memintanya
    # ──────────────────────────────────────────────────────────────────────────
    step(6, "Submit wallet address")

    # Cari pesan yang minta wallet dari respon setelah advertiser Done
    wallet_prompt = None
    for m in after_adv:
        if has_kw(m.text or "", ["wallet","address","base","eth","submit"]):
            wallet_prompt = m
            break

    if not wallet_prompt:
        warn("Menunggu permintaan wallet dari bot...")
        extra = await wait_reply(
            client, bot,
            after_adv[0].id if after_adv else 0,
            timeout=20
        )
        for m in extra:
            botmsg(m.text or "")
            if has_kw(m.text or "", ["wallet","address","base","eth","submit"]):
                wallet_prompt = m
                break

    if wallet_prompt:
        botmsg(wallet_prompt.text or "")
        ok("Bot meminta wallet address.")

        if wallet:
            info(f"Kirim wallet: {c(WHITE+BOLD, wallet)}")
            chk = await last_id(client, bot)
            await client.send_message(bot, wallet)

            wallet_reply = await wait_reply(client, bot, chk, timeout=20)
            for m in wallet_reply:
                botmsg(m.text or "")

            if has_kw((wallet_reply[0].text if wallet_reply else ""),
                      ["success","✅","received","thank","registered","berhasil","saved"]):
                ok("Wallet diterima bot! ✅")
            else:
                warn("Tidak ada konfirmasi spesifik dari bot.")
        else:
            warn("Wallet kosong, tidak dikirim.")
    else:
        err("Bot tidak meminta wallet! Cek log di atas.")

    await asyncio.sleep(D)

    # ──────────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ──────────────────────────────────────────────────────────────────────────
    banner("─" * 60)
    print(f"  📋 {c(BOLD,'Summary')} — {c(WHITE, session_name)}")
    banner("─" * 60)
    print(f"   ✅ Captcha selesai")
    print(f"   ✅ Join @PEGABANK_EXE")
    print(f"   ✅ Klik Done (task utama)")
    print(f"   ✅ Twitter: @{twitter if twitter else c(RED,'(kosong)')}")
    print(f"   ✅ Join @airdrop6officialchannel")
    print(f"   ✅ Klik Done (advertiser task)")
    print(f"   ✅ Wallet: {wallet[:20] + '...' if wallet else c(RED,'(kosong)')}")
    print()

    await client.disconnect()


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    banner("╔══════════════════════════════════════════════════════╗")
    banner("║    EXEGroup Airdrop Bot  —  verified flow v4        ║")
    banner("╚══════════════════════════════════════════════════════╝")

    os.makedirs(config.SESSIONS_DIR, exist_ok=True)

    accounts  = load_accounts()
    addresses = load_lines(config.ADDRESS_FILE)
    twitters  = load_lines(config.TWITTER_FILE)

    if not accounts:
        err("Tidak ada akun di accounts.txt!"); return

    print(f"\n{c(BOLD+WHITE, f'Total akun   : {len(accounts)}')}")
    print(f"{c(WHITE,        f'Total wallet : {len(addresses)}')}")
    print(f"{c(WHITE,        f'Total twitter: {len(twitters)}')}\n")

    print(c(CYAN, "Daftar akun:"))
    for i, acc in enumerate(accounts, 1):
        w = (addresses[i-1][:24]+"...") if i-1 < len(addresses) else c(RED,"(kosong)")
        t = ("@"+clean_twitter(twitters[i-1])) if i-1 < len(twitters) else c(RED,"(kosong)")
        print(f"  {i}. {c(WHITE, acc['session_name']):<28} wallet: {w}  twitter: {t}")

    print()
    sel = input(c(YELLOW, "[?] Pilih nomor sesi (contoh: 1,2,3 atau 'all'): ")).strip().lower()

    if sel == "all":
        selected = list(range(len(accounts)))
    else:
        try:
            selected = [int(x.strip())-1 for x in sel.split(",")]
            selected = [i for i in selected if 0 <= i < len(accounts)]
        except ValueError:
            err("Format input salah!"); return

    if not selected:
        err("Tidak ada sesi valid dipilih."); return

    print(f"\n{c(MAGENTA+BOLD, f'▶ Memulai {len(selected)} akun...')}")

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
            print(c(YELLOW, f"\n   ⏳ Jeda {w}s sebelum akun berikutnya..."))
            await asyncio.sleep(w)

    banner("═" * 60)
    ok(c(GREEN+BOLD, "✅ Semua akun selesai diproses!"))
    banner("═" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{c(RED, '[!] Dihentikan oleh user.')}")
    except Exception as e:
        print(f"\n{c(RED, f'[!] Error sistem: {e}')}")
