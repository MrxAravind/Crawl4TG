import requests
from urllib.parse import unquote
import json
import logging
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CRAWL_SERVER = "http://localhost:11235"

def submit_crawl_job(url, priority=10):
    """
    Submit a crawl job to the server.
    """
    try:
        response = requests.post(
            f"{CRAWL_SERVER}/crawl",
            json={"urls": url, "priority": priority}
        )
        response.raise_for_status()
        return response.json().get("task_id")
    except requests.RequestException as e:
        logger.error(f"Error submitting crawl job for URL {url}: {e}")
        return None


def poll_crawl_status(task_id, poll_interval=5, max_attempts=20):
    """
    Poll the crawl job status until it completes or reaches the maximum attempts.
    """
    for attempt in range(max_attempts):
        try:
            response = requests.get(f"{CRAWL_SERVER}/task/{task_id}")
            response.raise_for_status()
            status_data = response.json()
            if status_data.get("status") == "completed":
                return status_data.get("result")
            logger.info(f"Polling attempt {attempt + 1}: Status is {status_data.get('status')}")
        except requests.RequestException as e:
            logger.error(f"Error polling crawl status for task {task_id}: {e}")
        
        time.sleep(poll_interval)
    logger.warning("Maximum polling attempts reached. Task may not be complete.")
    return None


def crawl_missav(link):
    """
    Crawls a specific missav link to extract the title and video source.
    """
    task_id = submit_crawl_job(link)
    if not task_id:
        return None, None

    result = poll_crawl_status(task_id)
    if not result:
        return None, None

    try:
        title = [
            unquote(i["href"].split("&text=")[-1]).replace("+", " ")
            for i in result.get("links", {}).get("external", [])
            if i["text"] == "Telegram"
        ]
        videos = [
            video["src"]
            for video in result.get("media", {}).get("videos", [])
            if video.get("src")
        ]
        return title[0] if title else None, videos[0] if videos else None
    except Exception as e:
        logger.error(f"Error while processing link {link}: {e}")
        return None, None


def main():
    """
    Main function to crawl data from onejav.com and missav.com.
    """
    seen = set()
    data = []

    # Crawl onejav.com
    onejav_task_id = submit_crawl_job("https://onejav.com/")
    if not onejav_task_id:
        logger.error("Failed to submit crawl job for onejav.com.")
        return

    onejav_result = poll_crawl_status(onejav_task_id)
    if not onejav_result:
        logger.error("Failed to fetch data from onejav.com.")
        return

    images = onejav_result.get("media", {}).get("images", [])[:30]
    if not images:
        logger.info("No images found on onejav.com.")
        return

    for image in images:
        try:
            name = image.get("desc", "").split()[0]
            if not name:
                logger.info(f"Skipping image with missing description: {image}")
                continue

            # Search on missav.com
            search_url = f"https://missav.com/en/search/{name}"
            search_task_id = submit_crawl_job(search_url)
            if not search_task_id:
                logger.info(f"Failed to submit crawl job for search term {name}")
                continue

            search_result = poll_crawl_status(search_task_id)
            if not search_result:
                logger.info(f"Failed to fetch search results for {name}")
                continue

            vids = [
                img["src"]
                for img in search_result.get("media", {}).get("images", [])
                if img["src"].startswith("https://fivetiu.com")
            ]

            if not vids:
                logger.info(f"No videos found for search term {name}")
                continue

            # Process each video link
            for img in vids:
                link = f"https://missav.com/en/{img.split('/')[-2]}"
                if link in seen:
                    logger.info(f"Skipping already processed link: {link}")
                    continue
                seen.add(link)

                # Crawl missav link for detailed information
                title, src = crawl_missav(link)
                if not title or not src:
                    logger.info(f"Failed to extract details for link: {link}")
                    continue

                if title.split()[0].replace("-", "") == name:
                    logger.info(f"Title: {title}")
                    logger.info(f"Code: {name}")
                    logger.info(f"Thumb: {image['src']}")
                    logger.info(f"Link: {src}")
                    data.append(
                        {
                            "Title": title,
                            "Code": name,
                            "Image": image["src"],
                            "Source": src,
                        }
                    )
        except Exception as e:
            logger.error(f"Error processing image {image}: {e}", exc_info=True)

    # Save the collected data to a file
    with open("output.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    logger.info(f"Collected data: {len(data)} entries")


if __name__ == "__main__":
    main()
