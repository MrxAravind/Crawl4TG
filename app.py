import os
import asyncio
import logging
import sqlite3
from pyrogram import Client, filters
from crawl4ai import AsyncWebCrawler
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
from telegraph import Telegraph
import yt_dlp
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Suppress Pyrogram and yt-dlp logs
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("yt_dlp").setLevel(logging.WARNING)

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

# Initialize Telegraph
telegraph = Telegraph()
telegraph.create_account(short_name="WebCrawlerBot")

crawler = AsyncWebCrawler(database_type="sqlite", database_path=DB_PATH, cache_age=24*60*60)

class VideoDownloader:
    @staticmethod
    def generate_thumbnail(video_path, output_path):
        """Generate a thumbnail from a video."""
        ydl_opts = {
            'writesubtitles': False,
            'no_warnings': True,
            'quiet': True,
            'no_color': True,
            'outtmpl': output_path,
            'format': 'worst',  # Smallest thumbnail
            'postprocessors': [{
                'key': 'FFmpegThumbnailsConvertor',
                'format': 'png',
            }]
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_path])
            return True
        except Exception as e:
            logger.error(f"Thumbnail generation error: {e}")
            return False

    @staticmethod
    def download_video(video_url, output_template):
        """Download video using yt-dlp."""
        ydl_opts = {
            'format': 'best',
            'outtmpl': output_template,
            'max_downloads': 1,
            'no_warnings': True,
            'quiet': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                
            # Get the actual downloaded file path
            if info and 'requested_downloads' in info:
                downloaded_file = info['requested_downloads'][0]['filepath']
                return downloaded_file
            return None
        except Exception as e:
            logger.error(f"Video download error: {e}")
            return None

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
            title = [ unquote(i["href"].split("&text=")[-1]).replace("+", " ") for i in result.links["external"] if i["text"] == "Telegram"]
            videos = [ video["src"] for video in result.media.get("videos", []) if video.get("src") ]
            return title[0], videos[0] if videos and title else None
        except Exception as e:
            print(f"Error crawling {link}: {e}")
            return None

async def simple_crawl(link):
    async with AsyncWebCrawler() as crawler:
        try:
            result = await crawler.arun(url=link)
            return result.markdown_v2[4000] if result and len(result.markdown_v2) > 4000 else result.markdown_v2
        except Exception as e:
            logger.error(f"Error crawling {link}: {e}")
            return None


@app.on_message(filters.command("fetch"))
async def fetch_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Usage: /fetch [link]\nExample: /fetch https://missav.com/en/...")
        return
    
    link = message.command[1]
    status_message = await message.reply_text("🔄 Fetching details for the given link...")
    
    # Crawl and fetch the video link
    data = await crawl_missav(link)
    
    if not data or not data[1]:
        await status_message.edit_text("❌ No video found for the given link.", disable_web_page_preview=True)
        return
    
    video_url = data[1]
    title = data[0][:50] if data[0] else "video"  # Truncate title to prevent filename issues
    
    try:
        # Create downloads directory if it doesn't exist
        os.makedirs(os.path.join(os.getcwd(), "downloads"), exist_ok=True)
        
        # Prepare file paths
        output_template = os.path.join(os.getcwd(), "downloads", f"{title}.%(ext)s")
        thumb_path = os.path.join(os.getcwd(), "downloads", f"{title}_thumb.png")
        
        # Update status
        await status_message.edit_text("🔄 Downloading the video...")
        
        # Download video
        downloaded_video = VideoDownloader.download_video(video_url, output_template)
        
        if not downloaded_video:
            await status_message.edit_text("❌ Failed to download video.")
            return
        
        # Generate thumbnail
        await status_message.edit_text("📷 Generating Thumbnail...")
        VideoDownloader.generate_thumbnail(downloaded_video, thumb_path)
        
        # Upload video to Telegram
        await status_message.edit_text("🔼 Uploading the video to Telegram...")
        await app.send_video(
            chat_id=message.chat.id,
            video=downloaded_video,
            caption=f"📹 {title}",
            thumb=thumb_path
        )
        
        # Clean up files
        os.remove(downloaded_video)
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        await status_message.delete()
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        await status_message.edit_text("❌ An error occurred while processing the video.")

# ... [Rest of the previous implementation remains the same] ...

# Run the bot
if __name__ == "__main__":
    print("Bot is running...")
    app.run()
