import os
import asyncio
import logging
import sqlite3
from pyrogram import Client, filters
from crawl4ai import AsyncWebCrawler
from urllib.parse import urlparse
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing Telegram bot credentials. Please set TELEGRAM_API_ID, TELEGRAM_API_HASH, and BOT_TOKEN in .env file")

DB_PATH = os.path.join(os.getcwd(), 'crawler_cache', 'crawler_cache.db')

def initialize_database(db_path):
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS crawled_data (
                url TEXT PRIMARY KEY,
                content TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
        conn.close()
        logger.info(f"Database initialized at {db_path}")
    except Exception as e:
        logger.error(f"Database initialization error: {e}")
        raise

initialize_database(DB_PATH)

app = Client(
    "web_crawler_bot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

crawler = AsyncWebCrawler(database_type="sqlite", database_path=DB_PATH, cache_age=24*60*60)

async def fetch_pages(base_url, end_page):
    results = []
    async with AsyncWebCrawler() as crawler:
        for page_num in range(1, end_page + 1):
            url = f"{base_url}?page={page_num}"
            try:
                result = await crawler.arun(
                    url=url,
                    exclude_external_links=True,
                    exclude_social_media_links=True,
                )
                videos = [
                    [img["alt"],img["src"], f"https://missav.com/en/{img['src'].split('/')[-2]}"]
                    for img in result.media.get("images", [])
                    if img["src"] and "flag" not in img["src"]
                ]
                results.extend(videos)
            except Exception as e:
                logger.error(f"Error analyzing {url}: {e}")
    return results

async def crawl_missav(link):
    async with AsyncWebCrawler() as crawler:
        try:
            result = await crawler.arun(url=link)
            videos = [
                video["src"]
                for video in result.media.get("videos", [])
                if video.get("src")
            ]
            return videos[0] if videos else None  # Return the first video if available
        except Exception as e:
            logger.error(f"Error crawling {link}: {e}")
            return None


async def simple_crawl(link):
    async with AsyncWebCrawler() as crawler:
        try:
            result = await crawler.arun(url=link)
            return result[4000] if result else None
        except Exception as e:
            logger.error(f"Error crawling {link}: {e}")
            return None


# Telegram bot commands
@app.on_message(filters.command("miss"))
async def miss_command(client, message):
    if len(message.command) < 3:
        await message.reply_text("Usage: /miss [base_url] [pages]\nExample: /miss https://missav.com/dm561/en/uncensored-leak 2")
        return
    base_url, pages = message.command[1], int(message.command[2])
    status_message = await message.reply_text("🔄 Fetching MissAV links...")
    links = await fetch_pages(base_url, end_page=pages)
    src_links = [link + [await crawl_missav(link[-1])] for link in links]
    formatted_links = "\n".join([f"{i + 1}. {link[0]}" for i, link in enumerate(src_links)])
    await status_message.edit_text(f"📄 Links fetched:\n\n{formatted_links}", disable_web_page_preview=True)


@app.on_message(filters.command("crawl"))
async def miss_command(client, message):
    if len(message.command) < 3:
        await message.reply_text("Usage: /crawl [link]\nExample: /crawl https://www.google.com")
        return
    link = message.command[1]
    status_message = await message.reply_text("🔄 Fetching...")
    result = await simple_crawl(link)
    await status_message.edit_text(f"📄 Data Fetched:\n\n{result}", disable_web_page_preview=True)


@app.on_message(filters.command("fetch"))
async def fetchm_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /Fetchm [link]\nExample: /Fetchm https://missav.com/en/...")
        return
    link = message.command[1]
    status_message = await message.reply_text("🔄 Fetching details for the given link...")
    video = await crawl_missav(link)
    if video:
        await status_message.edit_text(f"📄 Video URL:\n{video}", disable_web_page_preview=True)
    else:
        await status_message.edit_text("❌ No video found for the given link.", disable_web_page_preview=True)

@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text(
        "👋 Welcome to the Web Crawler Bot!\n\n"
        "Commands:\n"
        "/miss [base_url] [pages] - Fetch all links from MissAV pages\n"
        "/Fetchm [link] - Fetch details for a specific MissAV link\n"
        "/help - Show this help message"
    )

@app.on_message(filters.command("help"))
async def help_command(client, message):
    await message.reply_text(
        "🤖 Web Crawler Bot Help\n\n"
        "Commands:\n"
        "/miss [base_url] [pages] - Fetch all links from MissAV pages\n"
        "/fetchm [link] - Fetch details for a specific MissAV link\n"
        "/start - Show welcome message\n\n"
        "Examples:\n"
        "/miss https://missav.com/dm561/en/uncensored-leak 2\n"
        "/fetchm https://missav.com/en/..."
    )

# Run the bot
if __name__ == "__main__":
    print("Bot is running...")
    app.run()
