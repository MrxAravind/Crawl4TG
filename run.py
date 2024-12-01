import asyncio
from crawl4ai import AsyncWebCrawler
from urllib.parse import unquote


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


async def main():
    """
    Main function to crawl data from onejav.com and missav.com.
    """
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

                    # Search on missav.com
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
                            print(f"Title: {title}")
                            print(f"Code: {name}")
                            print(f"Thumb: {image['src']}")
                            print(f"Link: {src}")
                            data.append(
                                {
                                    "Title": title,
                                    "Code": name,
                                    "Image": image["src"],
                                    "Source": src,
                                }
                            )
                except Exception as e:
                    print(f"Error processing image {image}: {e}", exc_info=True)

        except Exception as e:
            print(f"Error crawling onejav.com: {e}", exc_info=True)

        # Log final data
        print(f"Collected data: {len(data)} entries")
        for entry in data:
            print(entry)


if __name__ == "__main__":
    asyncio.run(main())
