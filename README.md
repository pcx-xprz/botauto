# EXEGroup CEX Listing Airdrop — Auto Bot

Script Python berbasis **Telethon** untuk mengotomasi task airdrop di `@EXEGroupCEXListingAirdropBot`.

## ✅ Task yang Di-automate

| # | Task | Status |
|---|------|--------|
| 1 | Jawab math captcha (`75 - 14`) | ✅ Auto |
| 2 | Klik Continue | ✅ Auto |
| 3 | Join grup `@PEGABANK_EXE` | ✅ Auto |
| 4 | Klik tombol **Done** | ✅ Auto |
| 5 | Submit wallet address (BASE/ETH) | ✅ Auto |
| 6 | Follow Twitter `@PegaBankEXE` | ⚠️ Manual |
| 7 | Retweet pinned post | ⚠️ Manual |

---

## 🚀 Cara Pakai

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Dapatkan API ID & API Hash

Buka https://my.telegram.org/apps → buat aplikasi → copy **App api_id** dan **App api_hash**.

### 3. Isi `config.py`

```python
API_ID   = 12345678          # API ID kamu
API_HASH = "abcdef..."       # API Hash kamu
WALLET_ADDRESS = "0xYour..." # Wallet BASE atau ETH kamu
```

### 4. Buat session file (login pertama kali)

```bash
python login_helper.py
```

Masukkan nama session, nomor HP, dan kode OTP. File `.session` akan dibuat otomatis.

### 5. Jalankan bot

```bash
python main.py
```

---

## 👥 Multi-Account

Edit `ACCOUNTS` di `config.py`:

```python
ACCOUNTS = [
    ("session1", 12345678, "api_hash_1", "0xWallet1"),
    ("session2", 12345678, "api_hash_2", "0xWallet2"),
]
```

Jalankan tetap dengan:
```bash
python main.py
```

---

## ⚠️ Disclaimer

- Script ini hanya untuk edukasi dan personal use.
- Jangan pernah kirim uang / fee untuk airdrop apapun.
- Selalu backup file `.session` kamu.
