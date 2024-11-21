import os
import asyncio
import logging
from pyrogram import Client, filters
from crawl4ai import AsyncWebCrawler
from urllib.parse import urlparse
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Fetch credentials from environment variables
API_ID = os.getenv('TELEGRAM_API_ID')
API_HASH = os.getenv('TELEGRAM_API_HASH')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

# Validate credentials
if not all([API_ID, API_HASH, BOT_TOKEN]):
    raise ValueError("Missing Telegram bot credentials. Please set TELEGRAM_API_ID, TELEGRAM_API_HASH, and TELEGRAM_BOT_TOKEN in .env file")

# Initialize the Pyrogram client
app = Client(
    "web_crawler_bot",
    api_id=int(API_ID),  # Convert to integer
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Initialize the web crawler with explicit database configuration
crawler = AsyncWebCrawler(
    # Explicitly set database parameters to avoid potential conflicts
    database_type="sqlite",  # or another type if needed
    database_path=os.path.join(os.getcwd(), "crawler_cache.db"),
    cache_age=24*60*60  # Cache for 24 hours
)

def is_valid_url(url):
    """Check if the provided URL is valid"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception as e:
        logger.error(f"URL validation error: {e}")
        return False

async def crawl_url(url, bypass_cache=False):
    """Perform web crawling with robust error handling"""
    try:
        # Additional URL validation
        if not is_valid_url(url):
            return "Invalid URL provided."
        
        # Enhanced crawling with explicit error handling
        try:
            result = await crawler.arun(
                url=url, 
                bypass_cache=bypass_cache,
                timeout=10  # Added timeout to prevent hanging
            )
            
            # Check if result is empty or None
            if not result or not result.markdown:
                return "No content could be retrieved from the URL."
            
            # Truncate to Telegram message length
            return result.markdown[:4000]
        
        except Exception as crawl_error:
            logger.error(f"Crawling error for {url}: {crawl_error}")
            return f"Crawling failed: {str(crawl_error)}"
    
    except Exception as unexpected_error:
        logger.error(f"Unexpected error in crawl_url: {unexpected_error}")
        return "An unexpected error occurred during crawling."

# Command handler for /start
@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text(
        "👋 Welcome to the Web Crawler Bot!\n\n"
        "Commands:\n"
        "/crawl [url] - Crawl a specific URL\n"
        "/fresh [url] - Crawl without using cache\n"
        "/help - Show this help message"
    )

# Command handler for /help
@app.on_message(filters.command("help"))
async def help_command(client, message):
    await message.reply_text(
        "🤖 Web Crawler Bot Help\n\n"
        "Available commands:\n"
        "/crawl [url] - Crawl a webpage and get its content\n"
        "/fresh [url] - Crawl a webpage without using cache\n"
        "/start - Show welcome message\n\n"
        "Example:\n"
        "/crawl https://example.com"
    )

# Command handler for /crawl
@app.on_message(filters.command("crawl"))
async def crawl_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Please provide a URL to crawl.\nExample: /crawl https://example.com")
        return
    
    url = message.command[1]
    
    # Send "processing" message
    status_message = await message.reply_text("🔄 Processing your request...")
    
    # Perform crawling
    result = await crawl_url(url)
    
    # Update with results
    await status_message.edit_text(
        f"📄 Crawling results for {url}:\n\n{result}",
        disable_web_page_preview=True
    )

# Command handler for /fresh (bypass cache)
@app.on_message(filters.command("fresh"))
async def fresh_crawl_command(client, message):
    if len(message.command) < 2:
        await message.reply_text("Please provide a URL to crawl.\nExample: /fresh https://example.com")
        return
    
    url = message.command[1]
    
    status_message = await message.reply_text("🔄 Processing your request (bypassing cache)...")
    
    result = await crawl_url(url, bypass_cache=True)
    
    await status_message.edit_text(
        f"📄 Fresh crawling results for {url}:\n\n{result}",
        disable_web_page_preview=True
    )

# Run the bot
if __name__ == "__main__":
    print("Bot is running...")
    app.run()
