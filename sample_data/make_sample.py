"""Build a deliberately messy sample dataset (no real customer data)."""
import csv
import random
from pathlib import Path

random.seed(7)
HEADER = ["Review ID", " Customer Name", "Country", "Product Category", "Rating", "Review Text", "Submitted At", "Notes"]

products = ["Electronics", "electronics", "ELECTRONICS ", "Home & Kitchen", "home & kitchen", "Books", "books", "Toys"]
countries = ["USA", "usa", "U.S.A.", "United States", "UK", "uk", "Nigeria", "nigeria ", "Canada"]
names = ["Ada Obi", "john smith", "MARIA GARCIA", "Chen Wei", "Fatima Bello", "Tom O'Neil", "Priya Nair", "Lars Berg"]
reviews = [
    "Absolutely <b>love</b> this product!!! Works great 😍😍 https://example.com/p/123",
    "Terrible quality. Broke after 2 days&nbsp;&mdash; want a refund. Contact me at buyer@example.com",
    "Sooooo goooood, would buy again!!!!   @shopsupport #happy",
    "It's okay, nothing special. Delivery took 3 weeks which is far too long for me.",
    "The packaging was damaged but the item inside was fine. Support replied in a day.",
    "Not what I expected — the colour is different from the photos on the site.",
    "Great value for the price. Battery lasts all day and the screen is sharp.",
    "Stopped charging after a month. Call me on +1 (555) 010-2030 please.",
    "<p>Five stars.</p><p>My kids use it every single day and it still looks new.</p>",
    "Instructions were confusing, took me two hours to set up. Works now though.",
]
dates = ["2026-03-14", "14/03/2026", "March 5, 2026", "2026-02-30", "03-22-2026", "2026/01/09", "not sure"]
ratings = ["5", "4", " 3 ", "4.0", "2", "1", "N/A", "five", ""]

rows = []
for i in range(1, 49):
    rows.append([
        1000 + i,
        random.choice(names + ["", "N/A"]),
        random.choice(countries),
        random.choice(products),
        random.choice(ratings),
        random.choice(reviews),
        random.choice(dates),
        "",
    ])

# Exact duplicates under new IDs, and near duplicates (case / punctuation / spacing).
for j, src in enumerate([3, 7, 11, 19]):
    dup = list(rows[src])
    dup[0] = 2000 + j
    rows.append(dup)
for j, src in enumerate([5, 13, 21]):
    dup = list(rows[src])
    dup[0] = 3000 + j
    dup[5] = "  " + dup[5].upper().replace("!", " !") + "  "
    rows.append(dup)

rows.append([4000, "", "null", "", "", "", "", ""])          # mostly empty
rows.append(["", "", "", "", "", "", "", ""])                # fully empty
rows.append([4001, "Bot Account", "USA", "Toys", "5", "ok", "2026-04-01", ""])   # too short to be useful
random.shuffle(rows)

out = Path(__file__).with_name("messy_reviews.csv")
with out.open("w", newline="", encoding="utf-8") as fh:
    writer = csv.writer(fh)
    writer.writerow(HEADER)
    writer.writerows(rows)
print(f"wrote {len(rows)} rows to {out}")
