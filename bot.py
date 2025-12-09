import os
import time
import json
import logging
import requests
import feedparser
from bs4 import BeautifulSoup
import telebot

# --- Configuration (via environment variables) ---
TOKEN = os.getenv("TOKEN")
CHANNEL = os.getenv("CHANNEL", "@AnimeNewsuz")  # default channel name
RSS_URLS = os.getenv("RSS_URLS", "https://www.animenewsnetwork.com/news/rss.xml").split(";")
INTERVAL = int(os.getenv("INTERVAL_SECONDS", str(4 * 60 * 60)))  # default 4 hours
MAX_PER_RUN = int(os.getenv("MAX_PER_RUN", "5"))
STORAGE_FILE = os.getenv("STORAGE_FILE", "posted.json")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "10"))

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("AnimeNewsBot")

if not TOKEN:
    logger.error("TOKEN muhim! Iltimos Render/GitHub Actions/Server environment variables-ga TOKEN qo'ying.")
    raise SystemExit("TOKEN not set")

bot = telebot.TeleBot(TOKEN, parse_mode=None)

# --- Persistent storage of posted links ---
def load_posted(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data)
    except FileNotFoundError:
        return set()
    except Exception as e:
        logger.warning(f"posted faylni yuklashda xatolik: {e}")
        return set()

def save_posted(path, posted_set):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(list(posted_set), f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"posted faylni yozishda xato: {e}")

posted = load_posted(STORAGE_FILE)
logger.info(f"Avvalgi postlar yuklandi: {len(posted)} ta")

# --- Helpers ---
def get_image_from_page(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; AnimeNewsBot/1.0)"}
        r = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        # Try common meta tags
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]
        twitter = soup.find("meta", attrs={"name": "twitter:image"})
        if twitter and twitter.get("content"):
            return twitter["content"]
        # Fallback: first <img> inside article
        article_img = soup.select_one("article img")
        if article_img and article_img.get("src"):
            return article_img["src"]
    except Exception as e:
        logger.debug(f"Rasm olishda xatolik ({url}): {e}")
    return None

def safe_caption(title, link):
    # simple markdown escape for [ ] ( ) in MarkdownV2 not used; we will send caption as plain text
    return f"📰 {title}\n\nBatafsil: {link}"

def send_post(title, link, img_url=None):
    caption = safe_caption(title, link)
    try:
        if img_url:
            # telebot can accept URL directly
            bot.send_photo(CHANNEL, img_url, caption=caption)
        else:
            bot.send_message(CHANNEL, caption)
        logger.info(f"Yuborildi: {title}")
        return True
    except Exception as e:
        logger.error(f"Telegramga yuborishda xato: {e}")
        return False

# --- Main checking loop ---
def check_feeds():
    new_count = 0
    for rss in RSS_URLS:
        try:
            feed = feedparser.parse(rss)
        except Exception as e:
            logger.warning(f"RSS parse xatolik ({rss}): {e}")
            continue

        entries = feed.entries[:MAX_PER_RUN]
        for entry in entries:
            try:
                link = entry.link
                title = entry.title
            except Exception:
                continue

            if link in posted:
                continue

            img = get_image_from_page(link)
            ok = send_post(title, link, img)
            if ok:
                posted.add(link)
                new_count += 1
                # small delay between posts to avoid hitting rate limits
                time.sleep(2)

            if new_count >= MAX_PER_RUN:
                break
        if new_count >= MAX_PER_RUN:
            break

    if new_count:
        save_posted(STORAGE_FILE, posted)
    return new_count

if __name__ == "__main__":
    logger.info("Bot ishga tushdi. Interval: %s soniya", INTERVAL)
    try:
        while True:
            try:
                count = check_feeds()
                logger.info("Tekshirildi. Yangi postlar: %d", count)
            except Exception as e:
                logger.exception("check_feeds davomida xato")
            # save periodically
            save_posted(STORAGE_FILE, posted)
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        logger.info("To'xtadi (KeyboardInterrupt). Saqlanmoqda...")
        save_posted(STORAGE_FILE, posted)
    except Exception as e:
        logger.exception("Bot kutilmagan xato bilan to'xtadi")
        save_posted(STORAGE_FILE, posted)
