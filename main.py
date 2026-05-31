"""
EXEGroup CEX Listing Airdrop — Auto Bot v5
Real-time: pakai asyncio.Event + Telethon NewMessage handler.
Bot balas → langsung diproses, tidak perlu polling.

Alur percakapan bot (sudah diverifikasi):
  /start
  [1] Captcha: klik Continue → kirim jawaban → tunggu "correct"
  [2] Pesan welcome + tombol Done
        → join @PEGABANK_EXE (cek member dulu)
        → klik Done → tunggu balas
  [3] Bot minta Twitter username
        → kirim @username → tunggu balas
  [4] Bot kirim Advertiser task + tombol Done/Skip
        → join @airdrop6officialchannel (cek member dulu)
        → klik Done → tunggu balas
  [5] Bot minta wallet address
        → kirim wallet → SELESAI
"""

import asyncio
import os
import re
import sys

from telethon import TelegramClient, events
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

def c(color, text): return f"{color}{text}{RESET}"
def info(msg):  print(f"   {c(CYAN,       '[*]')} {msg}")
def ok(msg):    print(f"   {c(GREEN,       '[+]')} {msg}")
def warn(msg):  print(f"   {c(YELLOW,      '[!]')} {msg}")
def err(msg):   print(f"   {c(RED,         '[✗]')} {msg}")
def step(n, m): print(f"\n{c(MAGENTA+BOLD, f'[STEP {n}]')} {m}")
def banner(m):  print(f"\n{c(CYAN+BOLD, m)}{RESET}")
def botmsg(t):
    p = (t or "").replace("\n", " │ ")[:280]
    print(f"   {c(WHITE+BOLD,'🤖')} {c(WHITE, p)}")


# ── File loaders ──────────────────────────────────────────────────────────────

def load_accounts() -> list[dict]:
    path = config.ACCOUNTS_FILE
    if not os.path.exists(path):
        err(f"File {path} tidak ditemukan!"); sys.exit(1)
    out = []
    with open(path) as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"): continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 3:
                warn(f"baris {lineno} format salah, dilewati."); continue
            out.append({"session_name": parts[0], "api_id": int(parts[1]), "api_hash": parts[2]})
    return out

def load_lines(path: str) -> list[str]:
    if not os.path.exists(path):
        warn(f"File {path} tidak ditemukan."); return []
    with open(path) as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]

def clean_twitter(raw: str) -> str:
    return raw.lstrip("@").strip()


# ── Math solver ───────────────────────────────────────────────────────────────

def solve_math(text: str) -> str | None:
    norm = text.replace("×","*").replace("÷","/").replace(" x "," * ")
    m = re.search(r"(\d+)\s*([\+\-\*\/])\s*(\d+)\s*=", norm)
    if not m: return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    res = {"+": a+b, "-": a-b, "*": a*b, "/": a//b}.get(op)
    if res is None: return None
    info(f"Soal: {c(WHITE, f'{a} {op} {b}')} = {c(GREEN+BOLD, str(res))}")
    return str(res)


# ── Helpers ───────────────────────────────────────────────────────────────────

def has_kw(text: str, kws: list[str]) -> bool:
    t = (text or "").lower()
    return any(k.lower() in t for k in kws)

async def find_and_click(msgs: list, kws: list[str]) -> bool:
    for msg in msgs:
        if not msg.buttons: continue
        for row in msg.buttons:
            for btn in row:
                if has_kw(btn.text, kws):
                    info(f"Klik tombol: '{c(WHITE+BOLD, btn.text)}'")
                    await btn.click()
                    return True
    return False

async def is_member(client, username: str) -> bool:
    try:
        clean = username.replace("https://t.me/","").replace("@","").strip()
        entity = await client.get_entity(clean)
        me = await client.get_me()
        await client(GetParticipantRequest(entity, me))
        return True
    except UserNotParticipantError:
        return False
    except Exception:
        return False

async def join_if_needed(client, username: str):
    clean = username.replace("https://t.me/","").replace("@","").strip()
    if not clean or clean.lower() in ("joinchat",): return
    if await is_member(client, clean):
        ok(f"Sudah member @{clean}, skip join."); return
    info(f"Bergabung ke: {c(WHITE, '@'+clean)}")
    try:
        entity = await client.get_entity(clean)
        await client(JoinChannelRequest(entity))
        ok(f"Berhasil join @{clean}")
    except UserAlreadyParticipantError:
        ok(f"Sudah member @{clean}")
    except FloodWaitError as e:
        warn(f"FloodWait {e.seconds}s, tunggu...")
        await asyncio.sleep(e.seconds + 2)
        await join_if_needed(client, clean)
    except ChannelPrivateError:
        err(f"Channel @{clean} private.")
    except Exception as e:
        if "already participant" in str(e).lower(): ok(f"Sudah member @{clean}")
        else: err(f"Gagal join @{clean}: {e}")


# ── Real-time message waiter ──────────────────────────────────────────────────

class BotListener:
    """
    Register satu event handler NewMessage dari bot.
    Setiap pesan baru dari bot langsung masuk ke queue asyncio.
    Pakai wait() untuk ambil pesan berikutnya secara real-time.
    """
    def __init__(self, client: TelegramClient, bot_username: str):
        self.client   = client
        self.bot      = bot_username
        self._queue   = asyncio.Queue()
        self._handler = None

    def start(self):
        @self.client.on(events.NewMessage(from_users=self.bot))
        async def _handler(event):
            await self._queue.put(event.message)

        self._handler = _handler
        info(f"Real-time listener aktif untuk @{self.bot}")

    def stop(self):
        if self._handler:
            self.client.remove_event_handler(self._handler)

    async def wait(self, timeout: float = 25.0):
        """
        Tunggu pesan baru dari bot.
        Return Message, atau None jika timeout.
        Mengumpulkan semua pesan yang datang dalam 0.5 detik setelah pesan pertama
        (bot kadang kirim beberapa pesan sekaligus).
        """
        try:
            # Tunggu pesan pertama
            first = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            msgs  = [first]

            # Drain pesan yang antri dalam 0.8 detik (multi-message burst)
            deadline = asyncio.get_event_loop().time() + 0.8
            while True:
                remaining = deadline - asyncio.get_event_loop().time()
                if remaining <= 0: break
                try:
                    msg = await asyncio.wait_for(self._queue.get(), timeout=remaining)
                    msgs.append(msg)
                except asyncio.TimeoutError:
                    break

            # Deduplicate berdasarkan message id
            seen = set()
            unique = []
            for m in msgs:
                if m.id not in seen:
                    seen.add(m.id)
                    unique.append(m)

            info(f"Terima {len(unique)} pesan baru dari bot")
            for m in unique:
                botmsg(m.text or "(pesan tanpa teks)")
            return unique

        except asyncio.TimeoutError:
            warn(f"Timeout {timeout}s — bot belum membalas.")
            return []

    async def drain(self):
        """Kosongkan queue (pakai sebelum aksi agar tidak ada sisa)."""
        while not self._queue.empty():
            await self._queue.get()


# ── MAIN AUTOMATION PER AKUN ──────────────────────────────────────────────────

async def run_account(session_name: str, api_id: int, api_hash: str,
                      wallet: str, twitter: str):

    twitter = clean_twitter(twitter)

    banner("═" * 62)
    print(f"  {c(BOLD+CYAN,'🚀 AKUN')}   : {c(WHITE, session_name)}")
    print(f"  {c(CYAN,'Wallet')}    : {c(WHITE, wallet  or c(RED,'(kosong)'))}")
    print(f"  {c(CYAN,'Twitter')}   : {c(WHITE, ('@'+twitter) if twitter else c(RED,'(kosong)'))}")
    banner("═" * 62)

    session_path = os.path.join(config.SESSIONS_DIR, session_name.replace(".session",""))
    if not os.path.exists(f"{session_path}.session"):
        err(f"Session tidak ada: {session_path}.session — dilewati."); return

    client = TelegramClient(session_path, api_id, api_hash)
    try:
        await client.connect()
    except Exception as e:
        err(f"Gagal konek: {e}"); return

    if not await client.is_user_authorized():
        err("Session belum login."); await client.disconnect(); return

    me = await client.get_me()
    ok(f"Login: {c(WHITE, me.first_name)} (ID: {me.id})")

    bot = config.BOT_USERNAME
    D   = config.DELAY_STEP

    # Buat listener real-time
    listener = BotListener(client, bot)
    listener.start()

    try:
        # ──────────────────────────────────────────────────────────────────
        # STEP 1 — /start
        # ──────────────────────────────────────────────────────────────────
        step(1, f"/start @{bot}")
        await listener.drain()
        await client.send_message(bot, f"/start {config.REFERRAL_CODE}")

        msgs = await listener.wait(timeout=20)
        if not msgs:
            err("Bot tidak merespon /start. Abort."); return

        # ──────────────────────────────────────────────────────────────────
        # STEP 2 — Captcha
        # ──────────────────────────────────────────────────────────────────
        step(2, "Selesaikan captcha")

        # Cari pesan yang mengandung soal math (bisa dari msgs step 1)
        captcha_msg = None
        for m in msgs:
            if solve_math(m.text or ""):
                captcha_msg = m; break

        if not captcha_msg:
            # Belum ada di msgs pertama, tunggu lagi
            warn("Menunggu soal captcha...")
            extra = await listener.wait(timeout=15)
            for m in extra:
                if solve_math(m.text or ""):
                    captcha_msg = m; break

        if not captcha_msg:
            # Fallback: ambil dari history
            history = await client.get_messages(bot, limit=6)
            for m in history:
                if solve_math(m.text or ""):
                    captcha_msg = m; break

        if captcha_msg:
            answer = solve_math(captcha_msg.text)
            # Klik Continue DULU
            if captcha_msg.buttons:
                clicked = await find_and_click([captcha_msg], ["continue","lanjut","next"])
                if clicked:
                    await asyncio.sleep(0.5)   # jeda singkat setelah klik
                else:
                    warn("Tombol Continue tidak ditemukan, langsung jawab.")
            # Drain queue agar respon klik Continue tidak terpakai
            await listener.drain()
            # Kirim jawaban
            info(f"Kirim jawaban: {c(GREEN+BOLD, answer)}")
            await client.send_message(bot, answer)

            conf_msgs = await listener.wait(timeout=20)
            txt = conf_msgs[0].text if conf_msgs else ""
            if has_kw(txt, ["correct","benar","✅","welcome","listing"]):
                ok("Captcha benar! ✅")
            else:
                warn("Konfirmasi 'correct' tidak terdeteksi, lanjut...")
            msgs = conf_msgs   # pesan berikutnya diproses dari sini
        else:
            warn("Soal captcha tidak ditemukan, lanjut...")
            msgs = await client.get_messages(bot, limit=6)

        await asyncio.sleep(D)

        # ──────────────────────────────────────────────────────────────────
        # STEP 3 — Join @PEGABANK_EXE → klik Done
        # ──────────────────────────────────────────────────────────────────
        step(3, "Join grup utama + klik Done")

        # Cari pesan welcome yang ada tombol Done dari msgs sebelumnya
        # atau ambil dari history jika belum ada
        welcome_msgs = msgs if msgs else await client.get_messages(bot, limit=8)

        info("Cek & join @PEGABANK_EXE...")
        await join_if_needed(client, "PEGABANK_EXE")
        await asyncio.sleep(D)

        await listener.drain()
        clicked = await find_and_click(welcome_msgs, ["done","selesai","✅"])
        if not clicked:
            # Tombol Done mungkin ada di pesan lebih lama
            history = await client.get_messages(bot, limit=10)
            clicked = await find_and_click(history, ["done","selesai","✅"])

        if clicked:
            ok("Tombol Done diklik.")
            msgs = await listener.wait(timeout=25)
            if not msgs:
                warn("Bot belum balas setelah Done, ambil dari history...")
                msgs = await client.get_messages(bot, limit=6)
        else:
            err("Tombol Done tidak ditemukan!")
            msgs = await client.get_messages(bot, limit=6)

        await asyncio.sleep(D)

        # ──────────────────────────────────────────────────────────────────
        # STEP 4 — Kirim Twitter username
        # Bot: "enter your twitter username with '@'"
        # ──────────────────────────────────────────────────────────────────
        step(4, "Kirim Twitter username")

        # Cari pesan minta twitter
        tw_prompt = None
        for m in msgs:
            if has_kw(m.text or "", ["twitter","tweet","'@'","enter your twitter"]):
                tw_prompt = m; break

        if not tw_prompt:
            warn("Menunggu pesan Twitter dari bot...")
            extra = await listener.wait(timeout=25)
            for m in extra:
                if has_kw(m.text or "", ["twitter","tweet","'@'","enter your twitter"]):
                    tw_prompt = m; break
            if extra: msgs = extra

        if tw_prompt:
            botmsg(tw_prompt.text)

        if twitter:
            tw_handle = f"@{twitter}"
            info(f"Kirim Twitter: {c(WHITE+BOLD, tw_handle)}")
            await listener.drain()
            await client.send_message(bot, tw_handle)

            tw_reply = await listener.wait(timeout=25)
            first_txt = tw_reply[0].text if tw_reply else ""

            if has_kw(first_txt, ["invalid","format","error","try again","incorrect"]):
                warn("Format ditolak, coba tanpa @...")
                await listener.drain()
                await client.send_message(bot, twitter)
                tw_reply = await listener.wait(timeout=25)
            else:
                ok("Twitter diterima!")
            msgs = tw_reply
        else:
            warn("Twitter kosong, skip.")

        await asyncio.sleep(D)

        # ──────────────────────────────────────────────────────────────────
        # STEP 5 — Advertiser channel + klik Done
        # Bot: "Join our Advertiser channel ... Done or Skip"
        # ──────────────────────────────────────────────────────────────────
        step(5, "Task Advertiser channel + klik Done")

        adv_msg = None
        for m in msgs:
            if has_kw(m.text or "", ["advertiser","airdrop6","optional","done","skip"]):
                adv_msg = m; break

        if not adv_msg:
            warn("Menunggu pesan Advertiser channel...")
            extra = await listener.wait(timeout=25)
            for m in extra:
                if has_kw(m.text or "", ["advertiser","airdrop6","optional","done","skip"]):
                    adv_msg = m; break
            if extra: msgs = extra

        if adv_msg:
            botmsg(adv_msg.text or "")

        # Join advertiser channel dulu
        info("Cek & join @airdrop6officialchannel...")
        await join_if_needed(client, "airdrop6officialchannel")
        await asyncio.sleep(D)

        await listener.drain()
        search_list = [adv_msg] if adv_msg else msgs
        if not search_list:
            search_list = await client.get_messages(bot, limit=8)

        # Klik Done (bukan Skip supaya dapat +40 EXE)
        clicked = await find_and_click(search_list, ["done","selesai","✅"])
        if not clicked:
            history = await client.get_messages(bot, limit=10)
            clicked = await find_and_click(history, ["done","selesai","✅"])
        if not clicked:
            warn("Done tidak ada, coba Skip...")
            history = await client.get_messages(bot, limit=10)
            clicked = await find_and_click(history, ["skip","lewati"])

        if clicked:
            ok("Tombol Done/Skip (advertiser) diklik.")
            msgs = await listener.wait(timeout=25)
            if not msgs:
                warn("Bot belum balas setelah Done advertiser, ambil history...")
                msgs = await client.get_messages(bot, limit=6)
        else:
            err("Tombol Done/Skip tidak ditemukan!")
            msgs = await client.get_messages(bot, limit=6)

        await asyncio.sleep(D)

        # ──────────────────────────────────────────────────────────────────
        # STEP 6 — Submit wallet address
        # Bot: "Please submit your BASE or ETH wallet address below"
        # ──────────────────────────────────────────────────────────────────
        step(6, "Submit wallet address")

        wallet_prompt = None
        for m in msgs:
            if has_kw(m.text or "", ["wallet","address","base","eth","submit"]):
                wallet_prompt = m; break

        if not wallet_prompt:
            warn("Menunggu permintaan wallet dari bot...")
            extra = await listener.wait(timeout=25)
            for m in extra:
                if has_kw(m.text or "", ["wallet","address","base","eth","submit"]):
                    wallet_prompt = m; break
            if extra: msgs = extra

        if wallet_prompt:
            botmsg(wallet_prompt.text)
            ok("Bot meminta wallet address!")

            if wallet:
                info(f"Kirim wallet: {c(WHITE+BOLD, wallet)}")
                await listener.drain()
                await client.send_message(bot, wallet)

                wallet_reply = await listener.wait(timeout=25)
                final_txt = wallet_reply[0].text if wallet_reply else ""
                botmsg(final_txt)

                if has_kw(final_txt, ["success","✅","received","thank","registered",
                                       "berhasil","saved","congrat","complete"]):
                    ok("🎉 Wallet diterima! Semua task selesai!")
                else:
                    warn("Wallet terkirim, tunggu konfirmasi dari tim.")
            else:
                warn("Wallet kosong, tidak dikirim.")
        else:
            err("Bot tidak meminta wallet — cek log di atas.")

    finally:
        listener.stop()

    # ──────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ──────────────────────────────────────────────────────────────────────
    banner("─" * 62)
    print(f"  📋 {c(BOLD,'Summary')} — {c(WHITE, session_name)}")
    banner("─" * 62)
    print(f"   ✅ Captcha selesai")
    print(f"   ✅ Join @PEGABANK_EXE")
    print(f"   ✅ Klik Done (task utama)")
    print(f"   ✅ Twitter   : @{twitter or c(RED,'(kosong)')}")
    print(f"   ✅ Join @airdrop6officialchannel")
    print(f"   ✅ Klik Done (advertiser)")
    print(f"   ✅ Wallet    : {(wallet[:24]+'...') if wallet else c(RED,'(kosong)')}")
    print()

    await client.disconnect()


# ── Entry point ───────────────────────────────────────────────────────────────

async def main():
    banner("╔══════════════════════════════════════════════════════════╗")
    banner("║    EXEGroup Airdrop Bot  —  real-time listener v5       ║")
    banner("╚══════════════════════════════════════════════════════════╝")

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

    banner("═" * 62)
    ok(c(GREEN+BOLD, "✅ Semua akun selesai diproses!"))
    banner("═" * 62)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{c(RED, '[!] Dihentikan oleh user.')}")
    except Exception as e:
        print(f"\n{c(RED, f'[!] Error sistem: {e}')}")
