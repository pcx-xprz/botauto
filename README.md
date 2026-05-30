# EXEGroup CEX Listing Airdrop — Auto Bot

Script Python berbasis **Telethon** untuk mengotomasi seluruh task Telegram pada `@EXEGroupCEXListingAirdropBot`.  
Mendukung **multi-account**, auto-solve math captcha, auto join grup, auto submit wallet & twitter.

---

## ✅ Task yang Di-automate

| # | Task | Status |
|---|------|:------:|
| 1 | `/start` dengan referral code | ✅ Auto |
| 2 | Deteksi & jawab math captcha (angka dinamis) | ✅ Auto |
| 3 | Klik tombol **Continue** | ✅ Auto |
| 4 | Join grup `@PEGABANK_EXE` | ✅ Auto |
| 5 | Klik tombol **Done** | ✅ Auto |
| 6 | Submit Twitter username | ✅ Auto |
| 7 | Submit wallet address (BASE / ETH) | ✅ Auto |
| 8 | Follow Twitter `@PegaBankEXE` | ⚠️ Manual |
| 9 | Retweet pinned post | ⚠️ Manual |

---

## 📁 Struktur Folder

```
botauto/
├── sessions/               ← taruh semua file *.session di sini
│   ├── ash.session
│   ├── budi.session
│   └── ...
├── accounts.txt            ← daftar akun
├── address.txt             ← daftar wallet address
├── twitter.txt             ← daftar username twitter
├── config.py               ← konfigurasi bot & path
├── main.py                 ← script utama
├── login_helper.py         ← helper buat session baru
└── requirements.txt
```

---

## 📄 Format File Input

### `accounts.txt`
Satu akun per baris, format: `namasesi,api_id,api_hash`

```
ash,20189390,0f38d53f4fc26bc21496299718d9fa18
budi,20189391,1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d
citra,20189392,abcdef1234567890abcdef1234567890
```

> ⚠️ `namasesi` harus sama persis dengan nama file `.session` di folder `sessions/`  
> Contoh: `ash` → `sessions/ash.session`

---

### `address.txt`
Satu wallet per baris. Urutan **harus sama** dengan urutan akun di `accounts.txt`.

```
0xABC123...walletAkun1
0xDEF456...walletAkun2
0xGHI789...walletAkun3
```

---

### `twitter.txt`
Satu username Twitter per baris (tanpa `@`). Urutan sama dengan `accounts.txt`.

```
twitterAkun1
twitterAkun2
twitterAkun3
```

---

## 🚀 Cara Pakai

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Dapatkan API ID & API Hash

Buka → [https://my.telegram.org/apps](https://my.telegram.org/apps)  
Buat aplikasi → copy **App api_id** dan **App api_hash**.

### 3. Buat session file (sekali per akun)

```bash
python login_helper.py
```

Ikuti prompt: masukkan nama session, nomor HP, kode OTP.  
File `namasesi.session` akan muncul — **pindahkan ke folder `sessions/`**.

### 4. Isi semua file input

| File | Isi |
|------|-----|
| `accounts.txt` | namasesi, api_id, api_hash |
| `address.txt` | wallet BASE/ETH per akun |
| `twitter.txt` | username Twitter per akun |

### 5. Jalankan!

```bash
python main.py
```

Akan tampil daftar akun beserta wallet & twitter yang akan digunakan.  
Pilih sesi yang ingin dijalankan:

```
[?] Pilih nomor sesi (contoh: 1,2,3 atau 'all'): all
```

---

## 🔄 Alur Script

```
/start <referral_code>
        │
        ▼
Deteksi soal: 75 - 14 =  →  klik Continue  →  kirim "61"
        │
        ▼
Join @PEGABANK_EXE  (JoinChannelRequest)
        │
        ▼
Klik tombol "Done"
        │
        ▼
Submit @twitterUsername
        │
        ▼
Submit wallet address (BASE / ETH)
        │
        ▼
Log preview pesan akhir dari bot
```

---

## ⚙️ Konfigurasi (`config.py`)

| Variable | Default | Keterangan |
|----------|---------|------------|
| `BOT_USERNAME` | `EXEGroupCEXListingAirdropBot` | Username bot target |
| `REFERRAL_CODE` | `8467379432` | Kode referral di URL |
| `GROUP_TO_JOIN` | `PEGABANK_EXE` | Grup yang harus di-join |
| `SESSIONS_DIR` | `sessions` | Folder file `.session` |
| `ACCOUNTS_FILE` | `accounts.txt` | File daftar akun |
| `ADDRESS_FILE` | `address.txt` | File daftar wallet |
| `TWITTER_FILE` | `twitter.txt` | File daftar twitter |
| `DELAY_STEP` | `3` | Jeda antar langkah (detik) |
| `DELAY_ACCOUNT` | `10` | Jeda antar akun (detik) |

---

## ⚠️ Disclaimer

- Script ini untuk **personal use & edukasi** saja.
- **Jangan pernah** kirim uang / fee untuk airdrop apapun.
- Selalu **backup** file `.session` kamu — jangan di-share ke siapapun.
- Akun Telegram bisa kena ban jika terlalu agresif — gunakan delay yang wajar.
