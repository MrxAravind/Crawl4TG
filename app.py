import os
import asyncio
import logging
import sqlite3
import subprocess
from pyrogram import Client, filters
from crawl4ai import AsyncWebCrawler
from urllib.parse import urlparse, unquote
from dotenv import load_dotenv
from telegraph import Telegraph
import yt_dlp

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

def generate_thumbnail(video_path, output_path, timestamp="00:00:04"):
    """
    Generate a thumbnail from a video using FFmpeg.
    
    Args:
        video_path (str): Path to input video
        output_path (str): Path to save thumbnail
        timestamp (str, optional): Time to extract frame. Defaults to "00:00:04".
    
    Returns:
        bool: True if thumbnail generation was successful, False otherwise
    """
    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # FFmpeg command to extract thumbnail
    command = [
        'ffmpeg',
        '-ss', timestamp,      # Seek to timestamp
        '-i', video_path,      # Input file
        '-vframes', '1',       # Extract one frame
        '-q:v', '2',           # High quality
        '-y',                  # Overwrite output
        output_path            # Output path
    ]
    
    try:
        # Run FFmpeg command
        result = subprocess.run(
            command, 
            check=True, 
            capture_output=True, 
            text=True
        )
        
        # Verify thumbnail was created
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            print(f"Thumbnail saved as {output_path}")
            return True
        else:
            print("Thumbnail generation failed: Output file is empty")
            return False
    
    except subprocess.CalledProcessError as e:
        print(f"FFmpeg Error: {e}")
        print(f"STDOUT: {e.stdout}")
        print(f"STDERR: {e.stderr}")
        return False
    except Exception as e:
        print(f"Unexpected error generating thumbnail: {e}")
        return False

class VideoDownloader:
    @staticmethod
    def download_video(video_url, output_template):
        """Download video using yt-dlp."""
        ydl_opts = {
            'format': 'best',
            'outtmpl': output_template,
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

@app.on_message(filters.command("miss"))
async def miss_command(client, message):
    if len(message.command) < 3:
        await message.reply_text("Usage: /miss [base_url] [pages]\nExample: /miss https://missav.com/dm561/en/uncensored-leak 2")
        return
    base_url, pages = message.command[1], int(message.command[2])
    status_message = await message.reply_text("🔄 Fetching MissAV links...")
    links = await fetch_pages(base_url, end_page=pages)
    src_links = [link + [await crawl_missav(link[-1])[-1]] for link in links]
    formatted_links = "\n".join([f"{i + 1}. {link[0]}" for i, link in enumerate(src_links)])
    await status_message.edit_text(f"📄 Links fetched:\n\n{formatted_links}", disable_web_page_preview=True)

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
        
        # Try multiple status update methods
        try:
            await status_message.edit_text("🔄 Downloading the video...")
        except Exception:
            # If edit fails, send a new message
            await status_message.delete()
            status_message = await message.reply_text("🔄 Downloading the video...")
        
        # Download video
        downloaded_video = VideoDownloader.download_video(video_url, output_template)
        
        if not downloaded_video:
            await status_message.edit_text("❌ Failed to download video.")
            return
        
        # Generate thumbnail
        try:
            await status_message.edit_text("📷 Generating Thumbnail...")
        except Exception:
            status_message = await message.reply_text("📷 Generating Thumbnail...")
        
        # Generate thumbnail using FFmpeg
        thumbnail_success = generate_thumbnail(downloaded_video, thumb_path)
        
        # Upload video to Telegram
        try:
            await status_message.edit_text("🔼 Uploading the video to Telegram...")
        except Exception:
            status_message = await message.reply_text("🔼 Uploading the video to Telegram...")
        
        # Send video with optional thumbnail
        await app.send_video(
            chat_id=message.chat.id,
            video=downloaded_video,
            caption=f"📹 {title}",
            thumb=thumb_path if thumbnail_success and os.path.exists(thumb_path) else None
        )
        
        # Clean up files
        os.remove(downloaded_video)
        if thumbnail_success and os.path.exists(thumb_path):
            os.remove(thumb_path)
        
        # Delete status message
        await status_message.delete()
        
    except Exception as e:
        logger.error(f"Error processing video: {e}")
        try:
            await status_message.edit_text("❌ An error occurred while processing the video.")
        except Exception:
            await message.reply_text("❌ An error occurred while processing the video.")

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

@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text(
        "👋 Welcome to the Web Crawler Bot!\n\n"
        "Commands:\n"
        "/miss [base_url] [pages] - Fetch all links from MissAV pages\n"
        "/fetch [link] - Fetch and download a video from a MissAV link\n"
        "/help - Show this help message"
    )

@app.on_message(filters.command("help"))
async def help_command(client, message):
    await message.reply_text(
        "🤖 Web Crawler Bot Help\n\n"
        "Commands:\n"
        "/miss [base_url] [pages] - Fetch all links from MissAV pages\n"
        "/fetch [link] - Fetch and download a video from a MissAV link\n"
        "/start - Show welcome message\n\n"
        "Examples:\n"
        "/miss https://missav.com/dm561/en/uncensored-leak 2\n"
        "/fetch https://missav.com/en/..."
    )

# Run the bot
if __name__ == "__main__":
    print("Bot is running...")
    app.run()
