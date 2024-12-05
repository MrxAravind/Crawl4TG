import asyncio
from crawl4ai import AsyncWebCrawler
from urllib.parse import unquote
import os
import asyncio
import logging
import sqlite3
from pyrogram import Client, filters
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
from telegraph import Telegraph
import subprocess

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress Pyrogram logs
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Load environment variables
load_dotenv()

API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing Telegram bot credentials. Please set TELEGRAM_API_ID, TELEGRAM_API_HASH, and BOT_TOKEN in .env file")

DB_PATH = os.path.join(os.getcwd(), 'crawler_cache', 'crawler_cache.db')

# Initialize the database
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

# Initialize Telegram client and tools
app = Client(
    "web_crawler_bot",
    api_id=int(API_ID),
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)
telegraph = Telegraph()
telegraph.create_account(short_name="WebCrawlerBot")
crawler = AsyncWebCrawler(database_type="sqlite", database_path=DB_PATH, cache_age=24*60*60)


# Utility: Generate thumbnail
def generate_thumbnail(video_path, output_path, timestamp="00:00:4"):
    command = [
        'ffmpeg',
        '-ss', str(timestamp),
        '-i', video_path,
        '-vframes', '1',
        '-q:v', '2',
        '-y',
        output_path
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
        print(f"Thumbnail saved as {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error generating thumbnail: {e}")


async def crawl_missav(link):
    """
    Crawls a specific missav link to extract the title and video source.
    """
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=link)
            title = [
                unquote(i["href"].split("&text=")[-1]).replace("+", " ")
                for i in result.links.get("external", [])
                if i["text"] == "Telegram"
            ]
            videos = [
                video["src"]
                for video in result.media.get("videos", [])
                if video.get("src")
            ]
            return title[0] if title else None, videos[0] if videos else None
    except Exception as e:
        print(f"Error while crawling link {link}: {e}", exc_info=True)
        return None, None


async def moj():
    async with AsyncWebCrawler() as crawler:
        seen = set()
        data = []

        try:
            # Crawl onejav.com to get initial data
            result = await crawler.arun(url="https://onejav.com/")
            images = result.media.get("images", [])[:30]
            if not images:
                print("No images found on onejav.com")
                return
            for image in images:
                try:
                    name = image.get("desc", "").split()[0]
                    if not name:
                        print(f"Skipping image with missing description: {image}")
                        continue
                    search_url = f"https://missav.com/en/search/{name}"
                    search_result = await crawler.arun(url=search_url)
                    vids = [
                        img["src"]
                        for img in search_result.media.get("images", [])
                        if img["src"].startswith("https://fivetiu.com")
                    ]
                    if not vids:
                        print(f"No videos found for search term {name}")
                        continue
                    # Process each video link
                    for img in vids:
                        link = f"https://missav.com/en/{img.split('/')[-2]}"
                        if link in seen:
                            print(f"Skipping already processed link: {link}")
                            continue
                        seen.add(link)

                        # Crawl missav link for detailed information
                        title, src = await crawl_missav(link)
                        if not title or not src:
                            print(f"Failed to extract details for link: {link}")
                            continue

                        if title.split()[0].replace("-", "") == name:
                            data.append(
                                [ title,name,image["src"],src
                                ]
                            )
                except Exception as e:
                    print(f"Error processing image {image}: {e}")

        except Exception as e:
            print(f"Error crawling onejav.com: {e}")
        return data




@app.on_message(filters.command("miss"))
async def moj_command(client, message):
    await message.reply_text("Usage: /miss [pages]\nExample: /miss")
    try:
        base_url = "https://onejav.com/"
        status_message = await message.reply_text("🔄 Fetching OneJav links...")

        # Fetch data using moj function
        links = await moj()  # Modify `moj` function to accept pages if needed

        # Check if links are found
        if not links:
            await status_message.edit_text("❌ No links found. Try again later.")
            return

        # Process links for Telegraph
        telegraph_content = ""
        for i, link in enumerate(links):
            title, code, img_url, video_url = link[0], link[1], link[2], link[3]
            telegraph_content += (
                f'<img src="{img_url}"/><br>'
                f"<h4>{i + 1}. {code}</h4>"
                f"<h8>{title}</h8>"
                f'<a href="{video_url}">Watch Video</a><br><br>'
            )

        # Create Telegraph page
        response = telegraph.create_page(
            title="OneJav Links",
            html_content=telegraph_content
        )
        telegraph_url = f"https://graph.org/{response['path']}"

        # Reply with the Telegraph link
        await status_message.edit_text(f"✅ Links fetched! View them here:\n\n{telegraph_url}")

    except ValueError:
        await message.reply_text("❌ Invalid number of pages. Please provide a valid integer.")
    except Exception as e:
        logger.error(f"Error in /mojtg command: {e}")
        await message.reply_text("❌ An error occurred while processing your request.")



@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text(
        "👋 Welcome to the Web Crawler Bot!\n\n"
        "Commands:\n"
        "/miss [base_url] [pages] - Fetch all links from MissAV pages\n"
        "/crawl [link] - Crawls any link\n"
        "/fetch [link] - Fetch video from link and upload to Telegram\n"
        "/start - Show this welcome message\n"
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

