import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    print("Railway uchun Telethon StringSession yaratuvchi")
    api_id = int(input("TG_API_ID: ").strip())
    api_hash = input("TG_API_HASH: ").strip()

    client = TelegramClient(StringSession(), api_id, api_hash)
    await client.start()
    session_string = client.session.save()

    print("\n=== TG_SESSION_STRING ===")
    print(session_string)
    print("=== TAMOM ===\n")
    print("Buni Railway Variables ichidagi TG_SESSION_STRING ga qo'ying.")
    print("Bu login kaliti kabi maxfiy. Chatga yoki GitHub'ga yubormang.")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
