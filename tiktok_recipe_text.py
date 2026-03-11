"""
TikTok Recipe Text Export

Reads recipe URLs from a text file, scrapes each recipe, and outputs one text
document formatted for copy-paste (e.g. into TikTok captions):

  Recipe Name
  (break)
  Ingredients:
  (list)
  (break)
  Instructions (numbered 1. 2. 3., max 25 chars per line, words kept together)
  (break)
  Macros
"""

from urllib.request import urlopen, Request
from recipe_scrapers import scrape_html
import re
import logging
import sys
import gzip
import zlib
import os

# ============================================================================
# CONFIGURATION
# ============================================================================

# Text file with one recipe URL per line
URL_FILE = "Conor-Meals.txt"

# Output text file
OUTPUT_FILE = "tiktok_recipe_captions.txt"

# Max characters per line for instructions (word wrap, words kept together)
MAX_LINE_CHARS = 25

# ============================================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)


def fetch_html(url):
    """Fetch HTML from a URL."""
    req = Request(url, headers=HEADERS)
    with urlopen(req) as response:
        raw = response.read()
        enc = response.headers.get("Content-Encoding", "").lower()
        if enc == "gzip" or (raw[:2] == b"\x1f\x8b"):
            html = gzip.decompress(raw).decode("utf-8")
        elif enc == "deflate":
            html = zlib.decompress(raw).decode("utf-8")
        else:
            html = raw.decode("utf-8")
    return html


def safe_get(func, default=""):
    try:
        r = func()
        return r if r is not None else default
    except Exception:
        return default


def clean_ingredient(line):
    """Reduce to 'amount + ingredient'; drop extra wording where possible."""
    line = line.strip()
    if not line:
        return ""
    line = re.sub(r"\s*\([^)]*\)\s*", " ", line)
    for suffix in (
        ", finely chopped", ", chopped", ", diced", ", minced", ", sliced",
        ", crushed", ", grated", ", optional", ", to serve", ", plus extra",
        " to serve", ", drained", ", rinsed",
    ):
        if line.lower().endswith(suffix.lower()):
            line = line[: -len(suffix)].strip()
    return line


def format_macro(value):
    """Normalise macro string (e.g. '336 calories' -> '336 kcal')."""
    if not value:
        return ""
    value = value.strip()
    value = re.sub(r"\s*grams?\s*", "g ", value, flags=re.I)
    value = re.sub(r"\s*g\s*$", "g", value)
    if "calorie" in value.lower() and "kcal" not in value.lower():
        value = re.sub(r"\s*calories?\s*", " kcal", value, flags=re.I)
    return value.strip()


def word_wrap(text, max_chars):
    """Split text into lines of at most max_chars, keeping words together."""
    if not text or max_chars < 1:
        return []
    lines = []
    words = text.split()
    current = []
    current_len = 0
    for word in words:
        need = len(word) + (1 if current else 0)
        if current_len + need <= max_chars:
            current.append(word)
            current_len += need
        else:
            if current:
                lines.append(" ".join(current))
            # If single word is longer than max_chars, put it on its own line
            if len(word) > max_chars:
                current = []
                current_len = 0
                lines.append(word)
            else:
                current = [word]
                current_len = len(word)
    if current:
        lines.append(" ".join(current))
    return lines


def scrape_recipe(url):
    """Scrape one recipe; return dict with title, ingredients list, instructions list, macros."""
    html = fetch_html(url)
    scraper = scrape_html(html, org_url=url)
    title = safe_get(scraper.title) or "Recipe"
    ingredients = safe_get(scraper.ingredients)
    if not isinstance(ingredients, list):
        ingredients = [ingredients] if ingredients else []
    instructions = safe_get(scraper.instructions)
    if not isinstance(instructions, list):
        instructions = [instructions] if instructions else []
    instructions = [s.strip() for s in instructions if s and str(s).strip()]

    nutrients = safe_get(scraper.nutrients)
    calories = protein = fat = ""
    if isinstance(nutrients, dict):
        calories = str(
            nutrients.get("calories")
            or nutrients.get("Calories")
            or nutrients.get("calorieContent")
            or ""
        )
        protein = str(
            nutrients.get("protein")
            or nutrients.get("Protein")
            or nutrients.get("proteinContent")
            or ""
        )
        fat = str(
            nutrients.get("fat")
            or nutrients.get("Fat")
            or nutrients.get("fatContent")
            or ""
        )

    return {
        "title": title,
        "ingredients": ingredients,
        "instructions": instructions,
        "calories": calories,
        "protein": protein,
        "fat": fat,
    }


def format_recipe_block(recipe):
    """Format one recipe as text: name, break, ingredients, break, instructions (numbered, wrapped), break, macros."""
    lines = []

    # First line: Recipe Name
    lines.append(recipe["title"])
    lines.append("")

    # Ingredients:
    lines.append("Ingredients:")
    for raw in recipe["ingredients"]:
        cleaned = clean_ingredient(raw)
        if cleaned:
            lines.append(cleaned)
    lines.append("")

    # Instructions (numbered, max 25 chars per line, words together)
    lines.append("Instructions")
    for i, step in enumerate(recipe["instructions"], 1):
        wrapped = word_wrap(step, MAX_LINE_CHARS)
        for j, wline in enumerate(wrapped):
            if j == 0:
                lines.append(f"{i}. {wline}")
            else:
                lines.append(f"   {wline}")
    lines.append("")

    # Macros
    cal = format_macro(recipe["calories"]) or "—"
    prot = format_macro(recipe["protein"]) or "—"
    fat_s = format_macro(recipe["fat"]) or "—"
    lines.append("Macros")
    lines.append(f"Calories: {cal}")
    lines.append(f"Protein: {prot}")
    lines.append(f"Fat: {fat_s}")

    return "\n".join(lines)


def main():
    if not os.path.exists(URL_FILE):
        print(f"URL file not found: {URL_FILE}")
        return

    urls = []
    with open(URL_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    if not urls:
        print(f"No URLs found in {URL_FILE}")
        return

    blocks = []
    for i, url in enumerate(urls):
        logging.info(f"[{i + 1}/{len(urls)}] {url}")
        try:
            recipe = scrape_recipe(url)
            blocks.append(format_recipe_block(recipe))
        except Exception as e:
            logging.error(f"Scrape failed: {e}")
            blocks.append(f"[Error scraping: {url}]\n")

    out_text = "\n\n----------\n\n".join(blocks)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(out_text)

    print(f"Done. Captions saved to: {os.path.abspath(OUTPUT_FILE)}")


if __name__ == "__main__":
    main()
