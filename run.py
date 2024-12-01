import asyncio
from crawl4ai import AsyncWebCrawler, CacheMode
from urllib.parse import urlparse, unquote

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




async def main():
    async with AsyncWebCrawler() as crawler:
        data = []
        result = await crawler.arun(url="https://onejav.com/popular/")
        for image in result.media["images"][:30]:
          name = image['desc'].split()[0]
          vid = await crawler.arun(url=f"https://missav.com/en/search/{name}")
          vids = [img['src'] for img in vid.media["images"] if img['src'].startswith("https://fivetiu.com")]
          for img in vids:
                link = f"https://missav.com/en/{img.split('/')[-2]}"
                title,link = await crawl_missav(link)
                if title.split()[0].replace("-","") == name:
                    #print(f"Title: {title}")
                    #print(f"Code: {name}")
                    #print(f"Thumb: {image['src']}")
                    #print(f"Link: {link}")
                    data.append({'Title':title,'Code':name,'Image':image['src'],'Source':link})
        
if __name__ == "__main__":
    await main()
