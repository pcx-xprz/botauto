"""
EXEGroup CEX Listing Airdrop — Auto Bot v6
Real-time listener dengan BotListener yang benar.

ROOT CAUSE FIX v6:
  drain() dipanggil SEBELUM aksi (bukan sesudah), sehingga
  pesan balasan bot yang datang cepat tidak ikut terbuang.
  get_or_history() = ambil dari queue dulu, fallback ke history
  jika queue kosong setelah timeout singkat.

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
    Event-driven listener: setiap pesan baru dari bot langsung masuk asyncio.Queue.

    ATURAN PENTING:
      - drain() dipanggil SEBELUM melakukan aksi (send/click)
        agar pesan lama tidak bercampur dengan respon aksi baru.
      - JANGAN drain() setelah aksi — balasan bot yang datang cepat
        akan ikut terbuang dan menyebabkan timeout.
      - get_next() = ambil dari queue (real-time), fallback ke history
        jika queue kosong setelah timeout singkat.
    """

    def __init__(self, client: TelegramClient, bot_username: str):
        self.client  = client
        self.bot     = bot_username
        self._queue  = asyncio.Queue()
        self._seen   = set()        # deduplikasi berdasarkan msg.id
        self._handler = None

    def start(self):
        @self.client.on(events.NewMessage(from_users=self.bot))
        async def _on_msg(event):
            msg = event.message
            if msg.id not in self._seen:
                self._seen.add(msg.id)
                await self._queue.put(msg)

        self._handler = _on_msg
        info(f"Real-time listener aktif untuk @{self.bot}")

    def stop(self):
        if self._handler:
            self.client.remove_event_handler(self._handler)

    def drain(self):
        """
        Kosongkan queue secara SINKRON sebelum melakukan aksi.
        HARUS dipanggil sebelum send/click, bukan sesudah.
        """
        count = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        if count:
            info(f"Queue dikosongkan ({count} pesan lama dibuang)")

    async def get_next(self, timeout: float = 20.0) -> list:
        """
        Ambil pesan baru dari bot.
        1. Coba ambil dari queue (real-time, hasil event handler)
        2. Jika queue kosong setelah timeout → fallback ke get_messages (history)
        Kumpulkan burst 0.6 detik setelah pesan pertama.
        Return list pesan (bisa kosong jika benar-benar tidak ada).
        """
        try:
            # Tunggu pesan pertama dari queue
            first = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            msgs  = [first]

            # Kumpulkan burst (bot sering kirim 2-3 pesan sekaligus)
            burst_end = asyncio.get_event_loop().time() + 0.6
            while True:
                left = burst_end - asyncio.get_event_loop().time()
                if left <= 0: break
                try:
                    m = await asyncio.wait_for(self._queue.get(), timeout=left)
                    msgs.append(m)
                except asyncio.TimeoutError:
                    break

            info(f"Terima {len(msgs)} pesan baru dari bot (real-time)")
            for m in msgs:
                botmsg(m.text or "(no text)")
            return msgs

        except asyncio.TimeoutError:
            # Queue kosong → fallback ke history Telegram
            info("Queue kosong, ambil dari history Telegram...")
            history = await self.client.get_messages(self.bot, limit=6)
            # Filter hanya pesan yang belum pernah kita proses
            new = [m for m in history if m.id not in self._seen]
            if new:
                for m in new:
                    self._seen.add(m.id)
                info(f"History fallback: {len(new)} pesan baru")
                for m in new:
                    botmsg(m.text or "(no text)")
                return new
            # Benar-benar tidak ada pesan baru
            warn(f"Tidak ada pesan baru setelah {timeout}s.")
            return []

    async def get_latest_history(self, limit=8) -> list:
        """Ambil pesan terbaru dari history (untuk cari tombol/context)."""
        return await self.client.get_messages(self.bot, limit=limit)


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
        # ── STEP 1 — /start ───────────────────────────────────────────────
        step(1, f"/start @{bot}")
        listener.drain()                    # satu-satunya drain: bersihkan sisa sesi lama
        await client.send_message(bot, f"/start {config.REFERRAL_CODE}")
        msgs = await listener.get_next(timeout=10)
        if not msgs:
            err("Bot tidak merespon /start. Abort."); return

        # ── STEP 2 — Captcha ──────────────────────────────────────────────
        step(2, "Selesaikan captcha")

        captcha_msg = None
        for m in msgs:
            if solve_math(m.text or ""):
                captcha_msg = m; break
        if not captcha_msg:
            extra = await listener.get_next(timeout=10)
            for m in extra:
                if solve_math(m.text or ""): captcha_msg = m; break
        if not captcha_msg:
            for m in await listener.get_latest_history():
                if solve_math(m.text or ""): captcha_msg = m; break

        if captcha_msg:
            answer = solve_math(captcha_msg.text)

            # Klik Continue → bot balas "👍Great" → langsung kirim jawaban
            # TIDAK drain setelah klik — biarkan "👍Great" masuk queue
            if captcha_msg.buttons:
                clicked = await find_and_click([captcha_msg], ["continue","lanjut","next"])
                if clicked:
                    # Baca "👍Great" dari queue (buang, kita tidak perlu ini)
                    await listener.get_next(timeout=5)
                else:
                    warn("Tombol Continue tidak ditemukan, langsung jawab.")

            # Kirim jawaban — TANPA drain agar respon "correct!" tidak dibuang
            info(f"Kirim jawaban: {c(GREEN+BOLD, answer)}")
            await client.send_message(bot, answer)
            conf_msgs = await listener.get_next(timeout=10)
            txt = conf_msgs[0].text if conf_msgs else ""
            if has_kw(txt, ["correct","benar","✅","welcome","listing"]):
                ok("Captcha benar! ✅")
            else:
                warn("Tidak ada konfirmasi 'correct', lanjut...")
            msgs = conf_msgs if conf_msgs else await listener.get_latest_history()
        else:
            warn("Soal captcha tidak ditemukan, lanjut...")
            msgs = await listener.get_latest_history()

        await asyncio.sleep(D)

        # ── STEP 3 — Join @PEGABANK_EXE → klik Done ──────────────────────
        step(3, "Join grup utama + klik Done")

        info("Cek & join @PEGABANK_EXE...")
        await join_if_needed(client, "PEGABANK_EXE")
        await asyncio.sleep(1)

        # Cari tombol Done di msgs yg ada, fallback ke history
        search = msgs if msgs else await listener.get_latest_history(10)
        clicked = await find_and_click(search, ["done","selesai","✅"])
        if not clicked:
            clicked = await find_and_click(await listener.get_latest_history(10), ["done","selesai","✅"])

        if clicked:
            ok("Tombol Done diklik.")
            msgs = await listener.get_next(timeout=8)
            if not msgs: msgs = await listener.get_latest_history()
        else:
            err("Tombol Done tidak ditemukan!")
            msgs = await listener.get_latest_history()

        await asyncio.sleep(D)

        # ── STEP 4 — Kirim Twitter username ───────────────────────────────
        step(4, "Kirim Twitter username")

        tw_prompt = None
        for m in msgs:
            if has_kw(m.text or "", ["twitter","tweet","'@'","enter your twitter"]):
                tw_prompt = m; break
        if not tw_prompt:
            warn("Menunggu pesan Twitter dari bot...")
            extra = await listener.get_next(timeout=10)
            if extra:
                msgs = extra
                for m in extra:
                    if has_kw(m.text or "", ["twitter","tweet","'@'","enter your twitter"]):
                        tw_prompt = m; break
            if not tw_prompt:
                for m in await listener.get_latest_history():
                    if has_kw(m.text or "", ["twitter","tweet","'@'","enter your twitter"]):
                        tw_prompt = m; break

        if tw_prompt: botmsg(tw_prompt.text)

        if twitter:
            tw_handle = f"@{twitter}"
            info(f"Kirim Twitter: {c(WHITE+BOLD, tw_handle)}")
            # TANPA drain — agar balasan bot langsung tertangkap
            await client.send_message(bot, tw_handle)
            tw_reply = await listener.get_next(timeout=10)
            first_txt = tw_reply[0].text if tw_reply else ""
            if has_kw(first_txt, ["invalid","format","error","try again","incorrect"]):
                warn("Format ditolak, coba tanpa @...")
                await client.send_message(bot, twitter)
                tw_reply = await listener.get_next(timeout=10)
            else:
                ok("Twitter diterima!")
            msgs = tw_reply if tw_reply else await listener.get_latest_history()
        else:
            warn("Twitter kosong, skip.")

        await asyncio.sleep(D)

        # ── STEP 5 — Advertiser channel + klik Done ───────────────────────
        step(5, "Task Advertiser channel + klik Done")

        adv_msg = None
        for m in msgs:
            if has_kw(m.text or "", ["advertiser","airdrop6","optional","skip"]):
                adv_msg = m; break
        if not adv_msg:
            warn("Menunggu pesan Advertiser channel...")
            extra = await listener.get_next(timeout=10)
            if extra:
                msgs = extra
                for m in extra:
                    if has_kw(m.text or "", ["advertiser","airdrop6","optional","skip"]):
                        adv_msg = m; break
            if not adv_msg:
                for m in await listener.get_latest_history():
                    if has_kw(m.text or "", ["advertiser","airdrop6","optional","skip"]):
                        adv_msg = m; break

        if adv_msg: botmsg(adv_msg.text or "")

        info("Cek & join @airdrop6officialchannel...")
        await join_if_needed(client, "airdrop6officialchannel")
        await asyncio.sleep(1)

        search = [adv_msg] if adv_msg else msgs
        clicked = await find_and_click(search, ["done","selesai","✅"])
        if not clicked:
            clicked = await find_and_click(await listener.get_latest_history(10), ["done","selesai","✅"])
        if not clicked:
            warn("Done tidak ada, coba Skip...")
            clicked = await find_and_click(await listener.get_latest_history(10), ["skip","lewati"])

        if clicked:
            ok("Tombol Done/Skip (advertiser) diklik.")
            msgs = await listener.get_next(timeout=8)
            if not msgs: msgs = await listener.get_latest_history()
        else:
            err("Tombol Done/Skip tidak ditemukan!")
            msgs = await listener.get_latest_history()

        await asyncio.sleep(D)

        # ── STEP 6 — Submit wallet address ────────────────────────────────
        step(6, "Submit wallet address")

        wallet_prompt = None
        for m in msgs:
            if has_kw(m.text or "", ["wallet","address","base","eth","submit"]):
                wallet_prompt = m; break
        if not wallet_prompt:
            warn("Menunggu permintaan wallet dari bot...")
            extra = await listener.get_next(timeout=10)
            if extra:
                for m in extra:
                    if has_kw(m.text or "", ["wallet","address","base","eth","submit"]):
                        wallet_prompt = m; break
            if not wallet_prompt:
                for m in await listener.get_latest_history():
                    if has_kw(m.text or "", ["wallet","address","base","eth","submit"]):
                        wallet_prompt = m; break

        if wallet_prompt:
            botmsg(wallet_prompt.text)
            ok("Bot meminta wallet address!")
            if wallet:
                info(f"Kirim wallet: {c(WHITE+BOLD, wallet)}")
                # TANPA drain
                await client.send_message(bot, wallet)
                wallet_reply = await listener.get_next(timeout=10)
                final_txt = wallet_reply[0].text if wallet_reply else ""
                if final_txt: botmsg(final_txt)
                if has_kw(final_txt, ["success","✅","received","thank","registered",
                                       "berhasil","saved","congrat","complete"]):
                    ok("🎉 Wallet diterima! Semua task selesai!")
                else:
                    ok("Wallet terkirim.")
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
