# ============================================================
#  CONFIG — EXEGroup Airdrop Auto Bot
#  Isi semua field di bawah sebelum menjalankan script
# ============================================================

# --- Telegram API Credentials ---
# Dapatkan di: https://my.telegram.org/apps
API_ID   = 0          # ganti dengan integer API ID kamu
API_HASH = ""         # ganti dengan string API HASH kamu

# --- Session ---
# Nama file .session Telethon (tanpa ekstensi)
# Jika belum ada, script akan membuat session baru (butuh login OTP)
SESSION_NAME = "session1"

# --- Multi-Account Support ---
# Tambahkan lebih dari 1 session untuk jalankan banyak akun sekaligus
# Format: [("session_name", api_id, "api_hash", "wallet_address")]
ACCOUNTS = [
    # ("session1", 12345678, "abcdef1234567890abcdef1234567890", "0xYourWalletHere"),
    # ("session2", 12345678, "abcdef1234567890abcdef1234567890", "0xYourWallet2Here"),
]

# --- Wallet Address (BASE atau ETH) ---
# Digunakan jika ACCOUNTS kosong (single account mode)
WALLET_ADDRESS = "0xYourBaseOrEthWalletHere"

# --- Target Bot ---
BOT_USERNAME    = "EXEGroupCEXListingAirdropBot"
REFERRAL_CODE   = "8467379432"   # kode referral dari link kamu

# --- Telegram Group to Join ---
GROUP_TO_JOIN   = "PEGABANK_EXE"

# --- Delay Settings (detik) ---
DELAY_BETWEEN_STEPS = 3    # jeda antar langkah (detik)
DELAY_BETWEEN_ACCOUNTS = 10  # jeda antar akun (detik)
