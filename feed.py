import asyncio
import datetime
import xml.etree.ElementTree as ET
from crawl4ai import AsyncWebCrawler


async def moj():
    """
    Optimized function to crawl OneJav and fetch related data from MissAV, 
    with the MissAV crawling logic directly integrated.
    """
    async with AsyncWebCrawler() as crawler:
        seen = set()  # Track processed links
        data = []

        try:
            # Step 1: Crawl the OneJav homepage for initial data
            result = await crawler.arun(url="https://onejav.com/")
            images = result.media.get("images", [])[:30]

            if not images:
                logger.warning("No images found on onejav.com.")
                return

            logger.info(f"Found {len(images)} images to process.")

            # Step 2: Process each image for related MissAV links
            async def process_image(image):
                try:
                    # Extract name and construct MissAV search URL
                    name = image.get("desc", "").split()[0]
                    if not name:
                        logger.debug("Skipping image with missing description.")
                        return None

                    search_url = f"https://missav.com/en/search/{name}"
                    search_result = await crawler.arun(url=search_url)

                    # Find video links in MissAV search results
                    vids = [
                        img["src"] for img in search_result.media.get("images", [])
                        if img["src"].startswith("https://fivetiu.com")
                    ]
                    if not vids:
                        logger.debug(f"No videos found for search term {name}.")
                        return None

                    for img_src in vids:
                        missav_link = f"https://missav.com/en/{img_src.split('/')[-2]}"
                        if missav_link in seen:
                            logger.debug(f"Skipping already processed link: {missav_link}")
                            continue

                        seen.add(missav_link)

                        # Crawl MissAV link for details (merged logic)
                        try:
                            missav_result = await crawler.arun(url=missav_link)
                            title = [
                                unquote(i["href"].split("&text=")[-1]).replace("+", " ")
                                for i in missav_result.links.get("external", [])
                                if i["text"] == "Telegram"
                            ]
                            videos = [
                                video["src"]
                                for video in missav_result.media.get("videos", [])
                                if video.get("src")
                            ]
                            title = title[0] if title else None
                            src = videos[0] if videos else None

                            if not title or not src:
                                logger.warning(f"Failed to extract details for link: {missav_link}")
                                continue

                            # Validate and append data
                            if title.split()[0].replace("-", "") == name:
                                return [title, name, image["src"], src]

                        except Exception as e:
                            logger.error(f"Error while crawling MissAV link {missav_link}: {e}")

                except Exception as e:
                    logger.error(f"Error processing image: {e}")

                return None

            # Step 3: Process images concurrently
            tasks = [process_image(image) for image in images]
            results = await asyncio.gather(*tasks)

            # Filter out None results
            data = [item for item in results if item]

        except Exception as e:
            logger.error(f"Error crawling onejav.com: {e}")

        return data
                        

# Function to create RSS feed
def create_rss_feed(data, rss_file="feed.xml"):
    """
    Creates an RSS feed file from the provided data.
    
    Args:
        data (list): A list of dictionaries containing feed item details.
        rss_file (str): The path to the RSS feed file to create.
    """
    try:
        # Create the RSS root
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")

        # Add channel metadata
        ET.SubElement(channel, "title").text = "OneJav & MissAV Feed"
        ET.SubElement(channel, "link").text = "https://onejav.com/"
        ET.SubElement(channel, "description").text = "Latest content crawled from OneJav and MissAV."
        ET.SubElement(channel, "language").text = "en-us"
        ET.SubElement(channel, "lastBuildDate").text = datetime.datetime.utcnow().strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )

        # Add items to the RSS feed
        for item in data:
            title, name, img_url, video_url = item

            rss_item = ET.SubElement(channel, "item")
            ET.SubElement(rss_item, "title").text = title
            ET.SubElement(rss_item, "link").text = video_url
            ET.SubElement(rss_item, "description").text = (
                f"Name: {name}<br><img src='{img_url}'/>"
            )
            ET.SubElement(rss_item, "guid").text = video_url
            ET.SubElement(rss_item, "pubDate").text = datetime.datetime.utcnow().strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )

        # Write to file
        tree = ET.ElementTree(rss)
        with open(rss_file, "wb") as f:
            tree.write(f, encoding="utf-8", xml_declaration=True)

        print(f"RSS feed created successfully: {rss_file}")

    except Exception as e:
        print(f"Error creating RSS feed: {e}")

# Run moj and create RSS feed
async def generate_rss_feed():
    """
    Runs the moj function to fetch data and generates an RSS feed.
    """
    print("Fetching data from OneJav and MissAV...")
    data = await moj()

    if not data:
        print("No data found to include in the RSS feed.")
        return

    print(f"Fetched {len(data)} items. Creating RSS feed...")
    create_rss_feed(data)

# Run the script
if __name__ == "__main__":
    asyncio.run(generate_rss_feed())
