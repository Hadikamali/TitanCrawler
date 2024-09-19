import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import configparser
import logging
import os
import concurrent.futures
import time
import random
from threading import Lock
from collections import deque

# Global variables for thread safety
visited_urls = set()
url_queue = deque()
lock = Lock()

# Load user agents for random selection
def load_user_agents(file='user_agents.txt'):
    with open(file, 'r') as f:
        return [line.strip() for line in f.readlines()]

# Set up logging
def setup_logging(log_file):
    logging.basicConfig(filename=log_file, level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')
    logging.info('Logger initialized')

# Read configuration
def read_config(config_file='config.ini'):
    config = configparser.ConfigParser()
    config.read(config_file)
    return config['CRAWLER_SETTINGS']

# Check if URL is within the same domain
def is_same_domain(url, base_url):
    base_domain = urlparse(base_url).netloc
    link_domain = urlparse(url).netloc
    return link_domain == base_domain or not link_domain

# Fetch robots.txt and parse disallowed paths
def is_allowed_to_crawl(url):
    parsed_url = urlparse(url)
    robots_txt_url = urljoin(f"{parsed_url.scheme}://{parsed_url.netloc}", '/robots.txt')

    try:
        robots_txt = requests.get(robots_txt_url, timeout=5).text
        disallowed_paths = [line.split(': ')[1] for line in robots_txt.splitlines() if line.startswith('Disallow')]
        for path in disallowed_paths:
            if parsed_url.path.startswith(path):
                logging.info(f"URL {url} blocked by robots.txt")
                return False
    except requests.RequestException as e:
        logging.warning(f"Could not retrieve robots.txt from {robots_txt_url}: {str(e)}")

    return True

# Crawl function (with threading)
def crawl(current_url, base_url, max_depth, user_agents, delay):
    with lock:
        if current_url in visited_urls:
            return
        visited_urls.add(current_url)

    try:
        headers = {'User-Agent': random.choice(user_agents)}
        response = requests.get(current_url, headers=headers, timeout=10)

        if response.status_code == 200:
            logging.info(f"Successfully crawled: {current_url}")
            print(f"Crawled: {current_url}")
            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all links on the page
            for link in soup.find_all('a', href=True):
                full_url = urljoin(current_url, link['href'])

                # Check if the URL is within the same domain and allowed by robots.txt
                if is_same_domain(full_url, base_url) and is_allowed_to_crawl(full_url):
                    with lock:
                        if full_url not in visited_urls:
                            url_queue.append((full_url, max_depth + 1))
        else:
            logging.warning(f"Failed to retrieve {current_url}, Status code: {response.status_code}")
    except requests.RequestException as e:
        logging.error(f"Error crawling {current_url}: {str(e)}")

    # Delay between requests
    time.sleep(delay)

# Main function to start crawling with concurrency
def start_crawl(base_url, max_depth, max_workers, user_agents, delay):
    url_queue.append((base_url, 0))

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        while url_queue:
            current_url, depth = url_queue.popleft()
            if depth <= max_depth:
                executor.submit(crawl, current_url, base_url, depth, user_agents, delay)

if __name__ == '__main__':
    config = read_config()
    base_url = config['url']
    max_depth = int(config.get('max_depth', 3))
    log_file = config.get('log_file', 'logs/crawl.log')
    max_workers = int(config.get('max_workers', 5))  # Number of threads
    delay = float(config.get('delay', 1.0))  # Delay between requests

    # Ensure log directory exists
    os.makedirs(os.path.dirname(log_file), exist_ok=True)

    # Set up logging
    setup_logging(log_file)
    logging.info(f"Starting crawl for {base_url} with max depth {max_depth}")

    # Load user agents
    user_agents = load_user_agents()

    # Start crawling with concurrency
    start_crawl(base_url, max_depth, max_workers, user_agents, delay)
