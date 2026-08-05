import os
import requests
from tqdm import tqdm


OUTPUT_FOLDER = "nature_images"
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
IMGS = 1000
for i in tqdm(range(1000)):
    r = requests.get(
        "https://picsum.photos/1200/800",
        allow_redirects=True,
        timeout=30,
    )

    with open(f"{OUTPUT_FOLDER}/{i}.jpg", "wb") as f:
        f.write(r.content)
        print

print("Done")