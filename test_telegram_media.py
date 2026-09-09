import asyncio

from app.config.settings import Settings
from app.telegram.client import build_telegram_client


async def main():
    settings = Settings()
    client = build_telegram_client(settings)

    async with client:
        channel = await client.get_entity("@MostaqlDevelopment")

        count = 0

        async for message in client.iter_messages(channel, limit=100):
            if message.media:
                print(
                    f"ID: {message.id} | "
                    f"Date: {message.date} | "
                    f"Media: {type(message.media).__name__} | "
                    f"Text: {(message.text or '')[:100]}"
                )
                count += 1

        print(f"\nMessages with media: {count}")


if __name__ == "__main__":
    asyncio.run(main())