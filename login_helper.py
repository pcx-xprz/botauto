"""
Login Helper — Buat session file Telethon baru.
Jalankan sekali per nomor HP untuk generate file .session
"""

import asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
import config


async def create_session():
    session = input("Nama session (contoh: session1): ").strip() or "session1"
    api_id = config.API_ID if config.API_ID != 0 else int(input("API ID: ").strip())
    api_hash = config.API_HASH if config.API_HASH else input("API HASH: ").strip()

    client = TelegramClient(session, api_id, api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        phone = input("Nomor HP (format: +628xxx): ").strip()
        await client.send_code_request(phone)
        code = input("Kode OTP yang dikirim Telegram: ").strip()
        try:
            await client.sign_in(phone, code)
        except SessionPasswordNeededError:
            pw = input("2FA Password: ").strip()
            await client.sign_in(password=pw)

    me = await client.get_me()
    print(f"\n✅ Session berhasil dibuat!")
    print(f"   Nama    : {me.first_name} {me.last_name or ''}")
    print(f"   Username: @{me.username}")
    print(f"   ID      : {me.id}")
    print(f"   File    : {session}.session\n")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(create_session())
