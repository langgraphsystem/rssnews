
import logging
from pg_client_new import PgClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_feeds():
    """Adds a list of RSS feeds to the database."""
    feeds_to_add = {
        'https://moxie.foxnews.com/google-publisher/latest.xml': 'latest',
        'https://moxie.foxnews.com/google-publisher/world.xml': 'world',
        'https://moxie.foxnews.com/google-publisher/politics.xml': 'politics',
        'https://moxie.foxnews.com/google-publisher/science.xml': 'science',
        'https://moxie.foxnews.com/google-publisher/health.xml': 'health',
        'https://moxie.foxnews.com/google-publisher/sports.xml': 'sports',
        'https://moxie.foxnews.com/google-publisher/travel.xml': 'travel',
        'https://moxie.foxnews.com/google-publisher/tech.xml': 'tech',
        'https://moxie.foxnews.com/google-publisher/opinion.xml': 'opinion',
        'https://moxie.foxnews.com/google-publisher/us.xml': 'us'
    }

    try:
        pg_client = PgClient()
        logger.info("Successfully connected to the database.")

        for url, category in feeds_to_add.items():
            logger.info(f"Adding feed: {url} with category: {category}")
            feed_id = pg_client.insert_feed(url=url, lang='en', category=category)
            if feed_id:
                logger.info(f"Successfully added feed with ID: {feed_id}")
            else:
                logger.warning(f"Feed already exists or could not be added: {url}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    add_feeds()
