import requests
from bs4 import BeautifulSoup
import time

TARGET_WORDS = 1000000
OUTPUT_FILE = "shamela_1M_words.txt"

word_count = 0
book_id = 10
page_id = 1

print(f"Starting to scrape Arabic text into {OUTPUT_FILE}...")

with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
    while word_count < TARGET_WORDS:
        url = f"https://shamela.ws/book/{book_id}/{page_id}"

        try:
            response = requests.get(url, timeout=10)

            if response.status_code != 200:
                book_id += 1
                page_id = 1
                continue

            soup = BeautifulSoup(response.content, 'html.parser')
            content_div = soup.find('div', class_='nass')

            if content_div:
                text = content_div.get_text(separator=" ", strip=True)
            else:
                paragraphs = soup.find_all('p')
                text = " ".join([p.get_text(strip=True) for p in paragraphs])

            words = text.split()

            if len(words) == 0:
                book_id += 1
                page_id = 1
                continue

            f.write(text + "\n\n")
            word_count += len(words)

            print(f"Book: {book_id} | Page: {page_id} | Total Words: {word_count:,} / {TARGET_WORDS:,}")

            page_id += 1
            time.sleep(0.01)

        except Exception as e:
            print(f"Error scraping {url}: {e}")
            time.sleep(1)

print(f"\nSuccess! {TARGET_WORDS} Arabic words have been saved to {OUTPUT_FILE}")