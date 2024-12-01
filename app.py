import os
import asyncio
import logging
import sqlite3
from pyrogram import Client, filters
from crawl4ai import AsyncWebCrawler
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
from telegraph import Telegraph
import subprocess
import static_ffmpeg

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
static_ffmpeg.add_paths()

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

# Async function to fetch pages
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
                    [img["alt"], img["src"], f"https://missav.com/en/{img['src'].split('/')[-2]}"]
                    for img in result.media.get("images", [])
                    if img["src"] and "flag" not in img["src"]
                ]
                results.extend(videos)
            except Exception as e:
                logger.error(f"Error analyzing {url}: {e}")
    return results

# Crawl individual MissAV links
async def crawl_missav(link):
    async with AsyncWebCrawler() as crawler:
        try:
            result = await crawler.arun(url=link)
            title = [unquote(i["href"].split("&text=")[-1]).replace("+", " ") for i in result.links["external"] if i["text"] == "Telegram"]
            videos = [video["src"] for video in result.media.get("videos", []) if video.get("src")]
            return title[0], videos[0] if videos and title else None
        except Exception as e:
            print(f"Error crawling {link}: {e}")
            return None

# General crawl function for any link
async def simple_crawl(link):
    async with AsyncWebCrawler() as crawler:
        try:
            result = await crawler.arun(url=link)
            return result.markdown_v2[:4000] if result and len(result.markdown_v2) > 4000 else result.markdown_v2
        except Exception as e:
            logger.error(f"Error crawling {link}: {e}")
            return None

# Command: Fetch MissAV links from pages
@app.on_message(filters.command("miss"))
async def miss_command(client, message):
    if len(message.command) < 3:
        await message.reply_text("Usage: /miss [base_url] [pages]\nExample: /miss https://missav.com/dm561/en/uncensored-leak 2")
        return
    base_url, pages = message.command[1], int(message.command[2])
    status_message = await message.reply_text("🔄 Fetching MissAV links...")
    links = await fetch_pages(base_url, end_page=pages)
    formatted_links = "\n".join([f"{i + 1}. {link[0]}" for i, link in enumerate(links)])
    await status_message.edit_text(f"📄 Links fetched:\n\n{formatted_links}", disable_web_page_preview=True)



@app.on_message(filters.command("misstg"))
async def miss_command(client, message):
    if len(message.command) < 3:
        await message.reply_text(
            "Usage: /miss [base_url] [pages]\nExample: /miss https://missav.com/dm561/en/uncensored-leak 2"
        )
        return
    
    base_url, pages = message.command[1], int(message.command[2])
    status_message = await message.reply_text("🔄 Fetching MissAV links...")
    
    try:
        # Fetch the links and process
        links = await fetch_pages(base_url, end_page=pages)
        src_links = []
        for link in links:
            src = await crawl_missav(link[-1])[-1]
            link.append(src)
            src_links.append(link)
        # Prepare Telegraph content
        telegraph_content = ""
        for i, link in enumerate(src_links):
            title, img_url, video_url = link[0], link[1], link[2]
            video_src = link[3] if len(link) > 3 else "N/A"
            telegraph_content += (
                f'<img src="{img_url}"/><br>'
                f"<h4>{i + 1}. {title}</h4>"
                f'<a href="{video_src}">Watch Video</a><br><br>'
            )

        # Create and publish Telegraph page
        response = telegraph.create_page(
            title="MissAV Links",
            html_content=telegraph_content
        )
        
        telegraph_url = f"https://graph.org/{response['path']}"
        await status_message.edit_text(
            f"✅ Links fetched! View them here:\n\n{telegraph_url}"
        )
    except Exception as e:
        logger.error(f"Error fetching links: {e}")
        await status_message.edit_text("❌ Failed to fetch links. Please try again.")


# Command: Crawl any specific link
@app.on_message(filters.command("crawl"))
async def crawl_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /crawl [link]\nExample: /crawl https://www.google.com")
        return
    link = message.command[1]
    status_message = await message.reply_text("🔄 Fetching...")
    result = await simple_crawl(link)
    await status_message.edit_text(f"📄 Data Fetched:\n\n{result}", disable_web_page_preview=True)




@app.on_message(filters.command("linkfetch"))
async def fetch_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /fetch [link]\nExample: /fetch https://missav.com/en/...")
        return
    link = message.command[1]
    status_message = await message.reply_text("🔄 Fetching details for the given link...")
    
    data = await crawl_missav(link)
    if not data:
        await status_message.edit_text("❌ No video found for the given link.", disable_web_page_preview=True)
        return
    else:
        await status_message.edit_text(f"Title: {data[-1]}\nUrl: {data[-1]}", disable_web_page_preview=True)
        return 


# Command: Fetch video and upload
@app.on_message(filters.command("fetch"))
async def fetch_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /fetch [link]\nExample: /fetch https://missav.com/en/...")
        return
    link = message.command[1]
    status_message = await message.reply_text("🔄 Fetching details for the given link...")
    
    data = await crawl_missav(link)
    if not data:
        await status_message.edit_text("❌ No video found for the given link.", disable_web_page_preview=True)
        return
    
    title, video_url = data
    title = title[:25] if len(title) > 25 else title  # Truncate long titles
    thumb_path = f"{title}.png"
    
    try:
        output_template = os.path.join(os.getcwd(), "downloads", f"{title}.%(ext)s")
        os.makedirs(os.path.dirname(output_template), exist_ok=True)
        
        # Run yt-dlp with aria2c as the external downloader
        command = [
            "yt-dlp",
            "--external-downloader", "aria2c",
            "--output", output_template,
            video_url
        ]
        
        await status_message.edit_text("🔄 Downloading the video...")
        subprocess.run(command, check=True)
        
        # Locate the downloaded video file
        downloaded_video = next(
            (os.path.join("downloads", f) for f in os.listdir("downloads") if f.startswith(title)),
            None
        )
        
        if downloaded_video and os.path.exists(downloaded_video):
            await status_message.edit_text("📷 Generating Thumbnail for the video...")
            generate_thumbnail(downloaded_video, thumb_path)
            
            await status_message.edit_text("🔼 Uploading the video to Telegram...")
            await app.send_video(
                chat_id=message.chat.id,
                video=downloaded_video,
                caption=f"📹 {title}",
                thumb=thumb_path
            )
            await status_message.delete()
            
            # Clean up after upload
            os.remove(downloaded_video)
        else:
            await status_message.edit_text("❌ Video download failed. File not found.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Error downloading video: {e}")
        await status_message.edit_text("❌ Failed to download the video. Please check the URL or try again.")
    except Exception as e:
        logger.error(f"Error uploading video: {e}")
        await status_message.edit_text("❌ An error occurred while uploading the video.")




@app.on_message(filters.command("rawfetch"))
async def rawfetch_command(client, message):
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
        


# Command: Start message
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
