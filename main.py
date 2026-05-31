"""
EXEGroup CEX Listing Airdrop — Auto Bot
Pure event-loop: baca balasan bot → klik tombol dulu jika ada → baru kirim data.
Tidak pernah kirim data sebelum bot meminta.
"""

import asyncio
import os
import re
import sys

from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import UserAlreadyParticipantError, FloodWaitError

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

def c(color, text): return f"{color}{text}{RESET}"
def info(msg):   print(f"   {c(CYAN,   '[*]')} {msg}")
def ok(msg):     print(f"   {c(GREEN,  '[+]')} {msg}")
def warn(msg):   print(f"   {c(YELLOW, '[!]')} {msg}")
def err(msg):    print(f"   {c(RED,    '[✗]')} {msg}")
def step(msg):   print(f"\n{c(MAGENTA+BOLD, '──▶')} {msg}")
def banner(msg): print(f"\n{c(CYAN+BOLD, msg)}{RESET}")
def botlog(text):
    preview = (text or "").replace("\n", " │ ")[:250]
    print(f"   {c(WHITE, '🤖')} {preview}")


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


def load_lines(filepath: str) -> list[str]:
    if not os.path.exists(filepath):
        warn(f"File {filepath} tidak ditemukan.")
        return []
    with open(filepath) as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]


def clean_twitter(raw: str) -> str:
    return raw.lstrip("@").strip()


# ── Math solver ───────────────────────────────────────────────────────────────

def solve_math(text: str) -> str | None:
    normalized = (
        text
        .replace("×", "*")
        .replace("÷", "/")
        .replace(" x ", " * ")
    )
    m = re.search(r"(\d+)\s*([\+\-\*\/])\s*(\d+)\s*=", normalized)
    if not m:
        return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    result = {"+": a+b, "-": a-b, "*": a*b, "/": a//b}.get(op)
    if result is None:
        return None
    info(f"Soal: {c(WHITE, f'{a} {op} {b}')} = {c(GREEN, str(result))}")
    return str(result)


# ── Keyword checker ───────────────────────────────────────────────────────────

def has_kw(text: str, keywords: list[str]) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in keywords)


# ── Telegram helpers ──────────────────────────────────────────────────────────

async def last_id(client, bot: str) -> int:
    msgs = await client.get_messages(bot, limit=1)
    return msgs[0].id if msgs else 0


async def wait_reply(client, bot: str, after_id: int, timeout=20, poll=1.5) -> list:
    """
    Tunggu sampai ada pesan BARU dari bot (id > after_id).
    Return list pesan baru, atau [] jika timeout.
    """
    elapsed = 0.0
    while elapsed < timeout:
        await asyncio.sleep(poll)
        elapsed += poll
        msgs = await client.get_messages(bot, limit=6)
        new = [m for m in msgs if m.id > after_id]
        if new:
            info(f"Bot balas ({len(new)} pesan baru)")
            return new
    warn(f"Timeout {timeout}s — bot tidak membalas.")
    return []


async def get_msgs(client, bot: str, limit=8) -> list:
    return await client.get_messages(bot, limit=limit)


async def join_channel(client, target: str):
    """Join channel/grup. Toleran sudah-member & FloodWait."""
    clean = target.replace("https://t.me/", "").replace("@", "").strip()
    if not clean:
        return
    info(f"Join: {c(WHITE, clean)}")
    try:
        entity = await client.get_entity(clean)
        await client(JoinChannelRequest(entity))
        ok(f"Bergabung ke @{clean}")
    except UserAlreadyParticipantError:
        ok(f"Sudah anggota @{clean}")
    except FloodWaitError as e:
        warn(f"FloodWait {e.seconds}s, tunggu...")
        await asyncio.sleep(e.seconds + 2)
    except Exception as e:
        if "already participant" in str(e).lower():
            ok(f"Sudah anggota @{clean}")
        else:
            err(f"Gagal join @{clean}: {e}")


def extract_tme_links(text: str) -> list[str]:
    """Ekstrak semua username dari link t.me/xxx dalam teks."""
    return re.findall(r"t\.me/([A-Za-z0-9_]+)", text or "")


# ── Inti: scan satu pesan bot → eksekusi → return True jika ada aksi ─────────

async def handle_message(
    client,
    bot: str,
    msg,
    wallet: str,
    twitter: str,
    state: dict,
) -> bool:
    """
    Terima satu pesan bot. Analisa isi & tombol.
    Urutan prioritas:
      1. Jika ada tombol → klik dulu, tunggu balasan → return True
      2. Jika ada soal math → selesaikan → return True
      3. Jika bot minta twitter → kirim → return True
      4. Jika bot minta wallet → kirim → return True
    Return False jika tidak ada yang dilakukan.
    """
    text    = msg.text or ""
    buttons = msg.buttons or []

    # ─────────────────────────────────────────────────────────────────────────
    # 1. SELALU scan & klik tombol terlebih dahulu sebelum apapun
    #    Priority klik: Continue > Done > Skip
    #    Kecuali tombol yang sudah pernah kita klik (track di state)
    # ─────────────────────────────────────────────────────────────────────────
    if buttons:
        # Kumpulkan semua tombol yang ada di pesan ini
        all_btns = []
        for row in buttons:
            for btn in row:
                all_btns.append(btn)

        btn_labels = [b.text for b in all_btns]
        info(f"Tombol terdeteksi: {c(WHITE, str(btn_labels))}")

        # --- Kasus A: Ada soal math + tombol Continue ---
        # Instruksi bot: "Click Continue BEFORE typing the code"
        answer = solve_math(text)
        if answer and not state.get("captcha_done"):
            # Cari tombol Continue
            cont_btn = next(
                (b for b in all_btns if has_kw(b.text, ["continue", "lanjut", "next"])),
                None
            )
            if cont_btn:
                step(f"Captcha: klik '{cont_btn.text}' dulu")
                chk = await last_id(client, bot)
                await cont_btn.click()
                await asyncio.sleep(config.DELAY_STEP)
                # Sekarang kirim jawaban
                info(f"Kirim jawaban: {c(GREEN, answer)}")
                chk2 = await last_id(client, bot)
                await client.send_message(bot, answer)
                conf = await wait_reply(client, bot, chk2)
                if conf:
                    botlog(conf[0].text or "")
                state["captcha_done"] = True
                return True

        # --- Kasus B: Ada tombol Done/Skip (bukan captcha) ---
        # Klik Done dulu, tunggu bot balas, baru lanjut
        action_btn = next(
            (b for b in all_btns if has_kw(b.text,
                ["done", "skip", "selesai", "✅", "lanjut", "next", "continue"])),
            None
        )
        if action_btn and not state.get(f"btn_clicked_{msg.id}"):
            state[f"btn_clicked_{msg.id}"] = True

            # Sebelum klik Done, auto join semua channel yang disebut di pesan
            tme_links = extract_tme_links(text)
            for link in tme_links:
                # Jangan join bot itu sendiri
                if link.lower() not in [bot.lower(), "joinchat"]:
                    if link not in state.get("joined_channels", set()):
                        await join_channel(client, link)
                        state.setdefault("joined_channels", set()).add(link)
                        await asyncio.sleep(1)

            step(f"Tombol '{action_btn.text}' ditemukan → klik")
            chk = await last_id(client, bot)
            await action_btn.click()
            ok(f"Klik '{action_btn.text}' selesai, tunggu balasan bot...")

            # Tunggu balasan bot setelah klik
            replies = await wait_reply(client, bot, chk)
            if replies:
                for r in replies:
                    botlog(r.text or "")
            return True

    # ─────────────────────────────────────────────────────────────────────────
    # 2. Tidak ada tombol — cek konteks teks pesan
    # ─────────────────────────────────────────────────────────────────────────

    # --- Soal math tanpa tombol ---
    answer = solve_math(text)
    if answer and not state.get("captcha_done"):
        step("Captcha (tanpa tombol) → kirim jawaban")
        chk = await last_id(client, bot)
        await client.send_message(bot, answer)
        conf = await wait_reply(client, bot, chk)
        if conf:
            botlog(conf[0].text or "")
        state["captcha_done"] = True
        return True

    # --- Bot minta Twitter ---
    if (not state.get("twitter_sent")
            and has_kw(text, ["twitter", "tweet", "follow twitter",
                               "your twitter", "twitter username", "twitter handle"])):
        step("Bot minta Twitter username")
        botlog(text)
        if twitter:
            tw = f"@{twitter}"
            info(f"Kirim Twitter: {c(WHITE, tw)}")
            chk = await last_id(client, bot)
            await client.send_message(bot, tw)
            tw_reply = await wait_reply(client, bot, chk)
            if tw_reply:
                tw_text = tw_reply[0].text or ""
                botlog(tw_text)
                # Fallback: jika bot tolak format dengan @
                if has_kw(tw_text, ["invalid", "format", "error", "try again"]):
                    warn("Ditolak, coba tanpa @...")
                    chk2 = await last_id(client, bot)
                    await client.send_message(bot, twitter)
                    r2 = await wait_reply(client, bot, chk2)
                    if r2: botlog(r2[0].text or "")
                else:
                    ok("Twitter diterima!")
        else:
            warn("Twitter kosong, skip.")
        state["twitter_sent"] = True
        return True

    # --- Bot minta Wallet ---
    # HANYA kirim wallet jika bot benar-benar memintanya (ada keyword)
    if (not state.get("wallet_sent")
            and state.get("twitter_sent")   # wallet selalu SETELAH twitter
            and has_kw(text, [
                "wallet", "address", "eth address", "base address",
                "submit your", "enter your", "your wallet", "0x",
                "wallet address", "erc", "bep", "metamask"
            ])):
        step("Bot minta wallet address")
        botlog(text)
        if wallet:
            info(f"Kirim wallet: {c(WHITE, wallet)}")
            chk = await last_id(client, bot)
            await client.send_message(bot, wallet)
            w_reply = await wait_reply(client, bot, chk)
            if w_reply:
                wt = w_reply[0].text or ""
                botlog(wt)
                if has_kw(wt, ["success", "✅", "received", "thank", "registered", "berhasil", "saved"]):
                    ok("Wallet diterima!")
                else:
                    warn("Tidak ada konfirmasi wallet.")
        else:
            warn("Wallet kosong, skip.")
        state["wallet_sent"] = True
        return True

    return False   # tidak ada aksi


# ── Main loop per akun ────────────────────────────────────────────────────────

async def run_account(
    session_name: str,
    api_id: int,
    api_hash: str,
    wallet: str,
    twitter: str,
):
    twitter = clean_twitter(twitter)

    banner("═" * 58)
    print(f"  {c(BOLD+CYAN, '🚀 AKUN')}   : {c(WHITE, session_name)}")
    print(f"  {c(CYAN, 'Wallet')}    : {c(WHITE, wallet or '(kosong)')}")
    print(f"  {c(CYAN, 'Twitter')}   : {c(WHITE, ('@'+twitter) if twitter else '(kosong)')}")
    banner("═" * 58)

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

    # State tracker
    state: dict = {
        "captcha_done":   False,
        "twitter_sent":   False,
        "wallet_sent":    False,
        "joined_channels": set(),
    }

    # ── /start ────────────────────────────────────────────────────────────────
    step(f"/start @{bot} (ref: {config.REFERRAL_CODE})")
    chk = await last_id(client, bot)
    await client.send_message(bot, f"/start {config.REFERRAL_CODE}")
    first = await wait_reply(client, bot, chk, timeout=15)
    if not first:
        err("Bot tidak merespon /start. Abort.")
        await client.disconnect()
        return

    # ── EVENT LOOP ────────────────────────────────────────────────────────────
    # Proses pesan satu per satu, selalu cek tombol dulu
    pending = first          # pesan yang belum diproses
    max_rounds = 30
    no_action_streak = 0

    for round_num in range(max_rounds):

        # Selesai?
        if state["wallet_sent"]:
            break

        acted_any = False

        # Proses setiap pesan di batch pending (dari terbaru ke terlama)
        for msg in pending:
            if not msg.text and not msg.buttons:
                continue
            acted = await handle_message(client, bot, msg, wallet, twitter, state)
            if acted:
                acted_any = True
                # Ambil pesan baru dari bot setelah aksi
                await asyncio.sleep(config.DELAY_STEP)
                latest_id = max(m.id for m in pending)
                new = await wait_reply(client, bot, latest_id, timeout=15)
                if new:
                    pending = new
                else:
                    # Tidak ada pesan baru, ambil ulang semua
                    pending = await get_msgs(client, bot)
                break   # mulai ulang loop dengan pesan baru

        if not acted_any:
            # Tidak ada aksi dari batch ini
            # Cek ulang semua pesan terbaru
            latest_id = pending[0].id if pending else 0
            fresh = await get_msgs(client, bot, limit=10)
            new_msgs = [m for m in fresh if m.id > latest_id]

            if new_msgs:
                info(f"Pesan baru ditemukan ({len(new_msgs)}), proses...")
                pending = new_msgs
                no_action_streak = 0
            else:
                no_action_streak += 1
                info(f"Tidak ada pesan baru (streak {no_action_streak}), tunggu {config.DELAY_STEP}s...")

                if no_action_streak >= 3:
                    # Paksa ambil semua pesan & coba proses ulang
                    warn("3x tidak ada aksi. Ambil ulang semua pesan bot...")
                    pending = await get_msgs(client, bot, limit=10)
                    no_action_streak = 0

                    # Jika masih tidak ada yang bisa dilakukan, keluar
                    all_acted = any(
                        bool(m.text or m.buttons) for m in pending
                    )
                    if not all_acted:
                        warn("Tidak ada konteks baru. Menghentikan loop.")
                        break

                await asyncio.sleep(config.DELAY_STEP)

    # ── Summary ───────────────────────────────────────────────────────────────
    step("Status akhir dari bot")
    final = await get_msgs(client, bot, limit=4)
    print()
    for m in final[:3]:
        if m.text:
            botlog(m.text[:250])

    joined = state.get("joined_channels", set())
    print()
    print(f"  📊 {c(BOLD, 'Summary')} akun {c(WHITE, session_name)}:")
    print(f"     {'Captcha':<14}: {'✅' if state['captcha_done'] else '❌'}")
    print(f"     {'Join channel':<14}: {'✅ ' + str(joined) if joined else '❌'}")
    print(f"     {'Twitter':<14}: {'✅' if state['twitter_sent'] else '❌'}")
    print(f"     {'Wallet':<14}: {'✅' if state['wallet_sent']  else '❌'}")
    print()

    await client.disconnect()


async def get_msgs(client, bot: str, limit=8) -> list:
    return await client.get_messages(bot, limit=limit)


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    banner("╔════════════════════════════════════════════════════╗")
    banner("║    EXEGroup Airdrop Bot  —  dynamic event-loop    ║")
    banner("╚════════════════════════════════════════════════════╝")

    os.makedirs(config.SESSIONS_DIR, exist_ok=True)

    accounts  = load_accounts()
    addresses = load_lines(config.ADDRESS_FILE)
    twitters  = load_lines(config.TWITTER_FILE)

    if not accounts:
        err("Tidak ada akun di accounts.txt!")
        return

    print(f"\n{c(BOLD+WHITE, f'Total akun   : {len(accounts)}')}")
    print(f"{c(WHITE,        f'Total wallet : {len(addresses)}')}")
    print(f"{c(WHITE,        f'Total twitter: {len(twitters)}')}\n")

    print(c(CYAN, "Daftar akun:"))
    for i, acc in enumerate(accounts, 1):
        w = (addresses[i-1][:22] + "...") if i-1 < len(addresses) else c(RED, "(kosong)")
        t = ("@" + clean_twitter(twitters[i-1])) if i-1 < len(twitters) else c(RED, "(kosong)")
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

    banner("═" * 58)
    ok(c(GREEN+BOLD, "✅ Semua akun selesai diproses!"))
    banner("═" * 58)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{c(RED, '[!] Dihentikan oleh user.')}")
    except Exception as e:
        print(f"\n{c(RED, f'[!] Error sistem: {e}')}")
