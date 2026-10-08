PREMIUMHUB — RAILWAY TAYYORLASH

1) GitHub repo ichiga ushbu fayllarni joylang:
   - main.py
   - requirements.txt
   - Dockerfile
   - .dockerignore

2) Railway'da bot service'ga Volume ulang.
   Mount path: /data

3) Railway > Variables ichida .env.railway.example dagi qiymatlarni kiriting.
   Muhimlari:
   DATA_DIR=/data
   DB_PATH=/data/premiumhub.db

4) CardXabar avto-to'lov uchun eng yaxshi usul:
   Kompyuterda:
      pip install telethon
      python make_session.py
   Telefon raqam/kod bilan login qiling.
   Chiqqan TG_SESSION_STRING ni Railway Variables ga kiriting.
   UNI HECH KIMGA YUBORMANG VA GITHUB'GA QO'YMANG.

5) Railway'da faqat 1 replica ishlating.
   Sabab: Telegram polling + SQLite + CardXabar userbot bitta instance uchun sozlangan.

6) Deploydan keyin Telegram'da admin akkauntdan:
   /autopay_status
   yuboring. Userbot session va sozlamalar ✅ bo'lishi kerak.

7) Sinov:
   - kichik test buyurtma yarating
   - noyob summa chiqishini tekshiring
   - aynan shu summani kartaga yuboring
   - CardXabar xabari kelgach bot avtomatik tasdiqlashi kerak

KODDA QILINGAN O'ZGARISHLAR:
- SQLite bazasi /data volume'da saqlanadi
- SQLite WAL + 30 soniya lock timeout qo'shildi
- Railway uchun TG_SESSION_STRING qo'llab-quvvatlandi
- eski .session fayl usuli ham fallback sifatida qoldi
- noyob to'lov summasi <code> ko'rinishida bosib nusxalanadi
