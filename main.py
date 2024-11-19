import asyncio
from pyrogram import Client, filters
from crawl4ai import AsyncWebCrawler
from urllib.parse import urlparse
import os
from datetime import datetime

API_ID = 23080322
API_HASH = "b3611c291bf82d917637d61e4a136535"
BOT_TOKEN = "7259823333:AAEzKjJSr5AY8dtIR7inBL7S_14S_h1uvZc"



# Initialize the Pyrogram client
app = Client(
    "web_crawler_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Initialize the web crawler
crawler = AsyncWebCrawler()

def is_valid_url(url):
    """Check if the provided URL is valid"""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

async def crawl_url(url, bypass_cache=False):
    """Perform web crawling with error handling"""
    try:
        result = await crawler.arun(url=url, bypass_cache=bypass_cache)
        return result.markdown[:4000]  # Telegram has message length limits
    except Exception as e:
        return f"Error crawling the URL: {str(e)}"

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
    # Check if URL is provided
    if len(message.command) < 2:
        await message.reply_text("Please provide a URL to crawl.\nExample: /crawl https://example.com")
        return

    url = message.command[1]
    if not is_valid_url(url):
        await message.reply_text("Please provide a valid URL.")
        return

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
    if not is_valid_url(url):
        await message.reply_text("Please provide a valid URL.")
        return

    status_message = await message.reply_text("🔄 Processing your request (bypassing cache)...")
    
    result = await crawl_url(url, bypass_cache=True)
    
    await status_message.edit_text(
        f"📄 Fresh crawling results for {url}:\n\n{result}",
        disable_web_page_preview=True
    )


# Main function to run the bot
async def main():
    await app.start()
    print("Bot is running...")
    await app.idle()

if __name__ == "__main__":
    asyncio.run(main())
