import asyncio

from app.config.settings import Settings
from app.telegram.client import build_telegram_client


async def main():
    settings = Settings()
    client = build_telegram_client(settings)

    async with client:
        me = await client.get_me()

        print("\nLogged in as:")
        print("Name:", me.first_name)
        print("Username:", me.username)
        print("ID:", me.id)

        channel = await client.get_entity("@MostaqlDevelopment")

        print("\nChannel:")
        print("Title:", getattr(channel, "title", None))
        print("Username:", getattr(channel, "username", None))
        print("ID:", channel.id)

        print("\nLast 10 messages:\n")

        messages = await client.get_messages(channel, limit=10)

        for message in messages:
            print(
                "ID:",
                message.id,
                "| Date:",
                message.date,
                "| Text:",
                (message.text or "")[:100],
                "| Has media:",
                bool(message.media),
            )


if __name__ == "__main__":
    asyncio.run(main())