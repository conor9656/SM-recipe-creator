"""
TikTok Recipe Image Generator

Reads recipe URLs from a text file, scrapes each recipe, then generates:
1. Meal image (1000×1500): scraped photo cropped to ratio, meal name at top centre.
2. Recipe card: title, meal image (left, ~3/4 up), ingredients (amount + item), instructions (~80 words), macros.

Instructions: Prefer Segmind (SEGMIND_API_KEY in .env) for Kimi K2; else OpenAI (OPENAI_API_KEY).
Otherwise truncated. Add key to .env for AI summarization (~80 words, numbered steps).

Configuration at top of file. Set RECIPE_CARD_BACKGROUND to your background image path when ready.
"""

from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from recipe_scrapers import scrape_html
import io
import re
import logging
import sys
import gzip
import json
import zlib
import os

# Load .env for SEGMIND_API_KEY / OPENAI_API_KEY (AI instruction summarization)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

# ============================================================================
# CONFIGURATION
# ============================================================================

# Text file with one recipe URL per line
URL_FILE = "chocolate_puds.txt"

# Output folder for generated images
OUTPUT_DIR = "tiktok_output"

# Meal image size (width, height) - TikTok-friendly
MEAL_IMAGE_SIZE = (1080, 1620)

# Logo on meal image: path (e.g. "foodpal_logo.png"), bottom-right with 50px gap, size 150×150
MEAL_IMAGE_LOGO = "foodpal_logo.png"
MEAL_IMAGE_LOGO_SIZE = (150, 150)
MEAL_IMAGE_LOGO_GAP = 50

# Recipe card size (match or adjust for your background)
RECIPE_CARD_SIZE = (1080, 1620)

# Background for recipe card. Use None for a solid beige; set to a path to use your image.
RECIPE_CARD_BACKGROUND = "background.png"  # e.g. "assets/recipe_card_bg.png"

# Colours (from your reference: beige background, dark brown text)
COLOR_BG = "#F5F0E8"
COLOR_TITLE = "#6B4D3F"
COLOR_BODY = "#5C5C5C"

# ============================================================================
# RECIPE CARD LAYOUT (centers measured from top-left; bottom-right is 1080 x 1620)
# ============================================================================

CARD_IMAGE_CENTER = (297, 445)
CARD_IMAGE_SIZE = (410, 410)  # cropped meal photo size on card (px)

CARD_TITLE_CENTER = (540, 127)
CARD_TITLE_FONT_SIZE = 88

CARD_INGREDIENTS_CENTER = (293, 1143)  # 100px down from original 1043
CARD_INGREDIENTS_FONT_SIZE = 30

CARD_INSTRUCTIONS_CENTER = (807, 777)
CARD_INSTRUCTIONS_FONT_SIZE = 30

CARD_MACROS_CENTER = (740, 1407)  # 200px right of centre (540 + 200)
CARD_MACROS_FONT_SIZE = 30

# Text wrapping widths (pixels) for multi-line blocks
INGREDIENTS_MAX_WIDTH_PX = 500
INSTRUCTIONS_MAX_WIDTH_PX = 500

# Opening image: font and drop shadow (diagonal left-down)
OPENING_TITLE_FONT = "bushiretrodemo"  # font name / filename stem
OPENING_TITLE_FONT_SIZE = 96
OPENING_SHADOW_OFFSET = (10, 10)  # diagonal left-down (shadow at x - 10, y + 10)
OPENING_IMAGE_FILENAME = "00_opening.png"

# Batch mode: recipes per "part" (one TikTok image collection per part)
RECIPES_PER_PART = 4

# ============================================================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
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


def slug_from_title(title):
    """Safe filename slug from recipe title."""
    s = re.sub(r"[^\w\s-]", "", title).strip().lower()
    return re.sub(r"[-\s]+", "-", s)[:80]


def download_image(url):
    """Download image from URL; return PIL Image or None."""
    try:
        req = Request(url, headers={**HEADERS, "Accept": "image/*"})
        with urlopen(req, timeout=15) as resp:
            data = resp.read()
        return Image.open(io.BytesIO(data)).convert("RGB")
    except Exception as e:
        logging.warning(f"Could not download image {url}: {e}")
        return None


def center_crop_to_ratio(img, target_w, target_h):
    """Crop image to fill target size (center crop), then resize to exact size."""
    if img is None:
        return None
    w, h = img.size
    target_ratio = target_w / target_h
    current_ratio = w / h
    if current_ratio > target_ratio:
        # crop width
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 2
        img = img.crop((0, top, w, top + new_h))
    return img.resize((target_w, target_h), Image.Resampling.LANCZOS)


def get_font(size, bold=False):
    """Try system fonts; fallback to default."""
    if not ImageFont:
        return None
    # Script directory (recipe scraper folder – font pack can live here)
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    # Prefer Kiwi Maru: script dir first, then assets/fonts, then system
    names = [
        os.path.join(_script_dir, "KiwiMaru-Medium.ttf" if bold else "KiwiMaru-Regular.ttf"),
        os.path.join(_script_dir, "KiwiMaru-Regular.ttf"),
        os.path.join("assets", "fonts", "KiwiMaru-Medium.ttf" if bold else "KiwiMaru-Regular.ttf"),
        os.path.join("assets", "fonts", "KiwiMaru-Regular.ttf"),
        "KiwiMaru-Medium.ttf",
        "KiwiMaru-Regular.ttf",
        "Kiwi Maru Medium.ttf",
        "Kiwi Maru Regular.ttf",
        # fallbacks
        "arial.ttf",
        "Arial.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else None,
    ]
    for name in names:
        if not name:
            continue
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def get_opening_font(size=OPENING_TITLE_FONT_SIZE):
    """Load Bushire Tro Demo (or similar) for the opening image title."""
    if not ImageFont:
        return None
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    names = [
        os.path.join(_script_dir, "BushireTroDemo.ttf"),
        os.path.join(_script_dir, "bushiretrodemo.ttf"),
        os.path.join(_script_dir, "Bushire Tro Demo.ttf"),
        os.path.join("assets", "fonts", "BushireTroDemo.ttf"),
        os.path.join("assets", "fonts", "bushiretrodemo.ttf"),
        "BushireTroDemo.ttf",
        "bushiretrodemo.ttf",
    ]
    for path in names:
        if os.path.isfile(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return get_font(size)


def _paste_logo_on_image(img):
    """Paste MEAL_IMAGE_LOGO at bottom-right of img (50px gap, 150×150). Modifies img in place."""
    logo_path = MEAL_IMAGE_LOGO
    if not os.path.isabs(logo_path):
        _script_dir = os.path.dirname(os.path.abspath(__file__))
        logo_path = os.path.join(_script_dir, logo_path)
    if not os.path.isfile(logo_path) and not os.path.splitext(logo_path)[1]:
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            if os.path.isfile(logo_path + ext):
                logo_path = logo_path + ext
                break
    if not os.path.isfile(logo_path):
        return
    try:
        logo = Image.open(logo_path).convert("RGBA")
        logo = logo.resize(MEAL_IMAGE_LOGO_SIZE, Image.Resampling.LANCZOS)
        x = img.size[0] - MEAL_IMAGE_LOGO_GAP - MEAL_IMAGE_LOGO_SIZE[0]
        y = img.size[1] - MEAL_IMAGE_LOGO_GAP - MEAL_IMAGE_LOGO_SIZE[1]
        img.paste(logo, (x, y), logo)
    except Exception as e:
        logging.warning(f"Could not add logo: {e}")


def scrape_recipe(url):
    """Scrape one recipe; return dict with title, image_url, ingredients, instructions, nutrients."""
    html = fetch_html(url)
    scraper = scrape_html(html, org_url=url)
    title = safe_get(scraper.title) or "Recipe"
    image_url = safe_get(scraper.image)
    ingredients = safe_get(scraper.ingredients)
    if not isinstance(ingredients, list):
        ingredients = [ingredients] if ingredients else []
    instructions = safe_get(scraper.instructions)
    if isinstance(instructions, list):
        instructions = " ".join(instructions)
    else:
        instructions = str(instructions or "")

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
        "image_url": image_url,
        "ingredients": ingredients,
        "instructions": instructions,
        "calories": calories,
        "protein": protein,
        "fat": fat,
    }


def clean_ingredient(line):
    """Reduce to 'amount + ingredient'; drop extra wording where possible."""
    line = line.strip()
    if not line:
        return ""
    # Optional: strip parentheticals and trailing prep notes for brevity
    line = re.sub(r"\s*\([^)]*\)\s*", " ", line)
    # Trim common trailing fluff (chopped, diced, etc.) – keep amount + core ingredient
    for suffix in (
        ", finely chopped", ", chopped", ", diced", ", minced", ", sliced",
        ", crushed", ", grated", ", optional", ", to serve", ", plus extra",
        " to serve", ", drained", ", rinsed",
    ):
        if line.lower().endswith(suffix.lower()):
            line = line[: -len(suffix)].strip()
    return line


def condense_instructions(text, max_words=80):
    """Shorten instructions to about max_words (fallback when AI is not used)."""
    if not (text or "").strip():
        return ""
    words = text.split()
    if len(words) <= max_words:
        return text.strip()
    return " ".join(words[:max_words]).strip()


def get_recipe_urls_from_ai(search_query):
    """
    Ask AI (Segmind then OpenAI) for recipe URLs matching the search query.
    Returns list of URLs, or empty list on failure.
    """
    if not (search_query or "").strip():
        return []
    prompt = f"""I need 5-10 recipe URLs for: {search_query.strip()}
Return only the full URLs, one per line. Use real recipe sites (e.g. bbcgoodfood.com, allrecipes.com, food.com, delish.com). No numbering, no other text."""
    response_text = None
    # Try Segmind
    api_key = os.environ.get("SEGMIND_API_KEY", "").strip()
    if api_key:
        url = "https://api.segmind.com/v1/kimi-k2-instruct-0905"
        body = json.dumps({
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 500,
            "temperature": 0.3,
        }).encode("utf-8")
        req = Request(url, data=body, headers={"x-api-key": api_key, "Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            choices = data.get("choices") or data.get("output")
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message", choices[0]) if isinstance(choices[0], dict) else {}
                response_text = (msg.get("content") if isinstance(msg, dict) else None) or ""
            elif isinstance(choices, str):
                response_text = choices
            else:
                response_text = data.get("text") or data.get("output") or ""
        except Exception as e:
            logging.warning(f"Segmind API failed for URL search ({e}).")
    # Try OpenAI if Segmind didn't return anything
    if not (response_text or "").strip():
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if api_key:
            try:
                import openai
                client = openai.OpenAI(api_key=api_key)
                r = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=500,
                    temperature=0.3,
                )
                response_text = (r.choices[0].message.content or "").strip()
            except Exception as e:
                logging.warning(f"OpenAI API failed for URL search ({e}).")
    if not (response_text or "").strip():
        print("No AI response for recipe search. Check SEGMIND_API_KEY or OPENAI_API_KEY in .env")
        return []
    # Extract URLs (http or https)
    urls = re.findall(r"https?://[^\s<>\"'\]]+", response_text)
    urls = [u.rstrip(".,;:)") for u in urls if u.startswith("http")]
    urls = list(dict.fromkeys(urls))  # dedupe, keep order
    logging.info(f"AI returned {len(urls)} recipe URL(s) for: {search_query.strip()}")
    return urls


def _condense_instructions_segmind(text, max_words=80):
    """Call Segmind Kimi K2 (kimi-k2-instruct-0905) to condense instructions. Returns None on failure."""
    api_key = os.environ.get("SEGMIND_API_KEY", "").strip()
    if not api_key:
        return None
    prompt = f"""Condense these recipe instructions into approximately {max_words} words. Use numbered steps (1. 2. 3.) for distinct steps where it makes sense. Keep the essential cooking steps and order. Output only the condensed instructions, no preamble or title.

Instructions to condense:
{text[:6000]}"""
    url = "https://api.segmind.com/v1/kimi-k2-instruct-0905"
    body = json.dumps({
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 300,
        "temperature": 0.3,
    }).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={
            "x-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # OpenAI-compatible response
        choices = data.get("choices") or data.get("output")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message", choices[0]) if isinstance(choices[0], dict) else {}
            content = msg.get("content") if isinstance(msg, dict) else None
        elif isinstance(choices, str):
            content = choices
        else:
            content = data.get("text") or data.get("output")
        result = (content or "").strip()
        if result:
            return result
    except Exception as e:
        logging.warning(f"Segmind API failed ({e}); trying fallback.")
    return None


def _condense_instructions_openai(text, max_words=80):
    """Call OpenAI to condense instructions. Returns None on failure."""
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        import openai
    except ImportError:
        return None
    prompt = f"""Condense these recipe instructions into approximately {max_words} words. Use numbered steps (1. 2. 3.) for distinct steps where it makes sense. Keep the essential cooking steps and order. Output only the condensed instructions, no preamble or title.

Instructions to condense:
{text[:6000]}"""
    try:
        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.3,
        )
        result = (response.choices[0].message.content or "").strip()
        if result:
            return result
    except Exception:
        pass
    return None


def condense_instructions_ai(text, max_words=80):
    """
    Condense recipe instructions to ~max_words with numbered steps.
    Tries Segmind (SEGMIND_API_KEY) first, then OpenAI (OPENAI_API_KEY), then truncation.
    """
    if not (text or "").strip():
        return ""
    # 1) Segmind Kimi K2
    result = _condense_instructions_segmind(text, max_words)
    if result:
        logging.info("Summarizing instructions with AI (Segmind Kimi K2)...")
        return result
    # 2) OpenAI
    result = _condense_instructions_openai(text, max_words)
    if result:
        logging.info("Summarizing instructions with AI (OpenAI)...")
        return result
    logging.debug("No AI API key set or API failed; using truncated instructions.")
    return condense_instructions(text, max_words)


def format_macro(value, unit_hint=""):
    """Normalise macro string (e.g. '336 calories' -> '336 kcal', '33.4 grams protein' -> '33.4g')."""
    if not value:
        return ""
    value = value.strip()
    value = re.sub(r"\s*grams?\s*", "g ", value, flags=re.I)
    value = re.sub(r"\s*g\s*$", "g", value)
    if "calorie" in value.lower() and "kcal" not in value.lower():
        value = re.sub(r"\s*calories?\s*", " kcal", value, flags=re.I)
    return value.strip()


def _text_bbox(draw, text, font):
    try:
        return draw.textbbox((0, 0), text, font=font)
    except Exception:
        # Rough fallback
        fsize = getattr(font, "size", 20)
        return (0, 0, int(len(str(text)) * (fsize * 0.6)), fsize)


def _wrap_text_pixels(draw, text, font, max_width_px):
    """Word-wrap text to fit within max_width_px (pixel-aware)."""
    words = str(text or "").split()
    if not words:
        return []
    lines = []
    cur = ""
    for w in words:
        cand = f"{cur} {w}".strip() if cur else w
        bbox = _text_bbox(draw, cand, font)
        if (bbox[2] - bbox[0]) <= max_width_px:
            cur = cand
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _draw_centered_lines(draw, lines, center_xy, font, fill, line_gap=6):
    """Draw lines as a vertically centered block around center_xy (each line center-aligned)."""
    if not lines:
        return
    cx, cy = center_xy
    # Measure line height
    heights = []
    for line in lines:
        bbox = _text_bbox(draw, line, font)
        heights.append(bbox[3] - bbox[1])
    line_h = max(heights) if heights else getattr(font, "size", 20)
    total_h = len(lines) * line_h + (len(lines) - 1) * line_gap
    y = int(cy - total_h / 2)
    for line in lines:
        bbox = _text_bbox(draw, line, font)
        tw = bbox[2] - bbox[0]
        x = int(cx - tw / 2)
        draw.text((x, y), line, fill=fill, font=font)
        y += line_h + line_gap


def _instruction_lines_with_step_gaps(draw, instr, font, max_width_px):
    """
    Split instructions on numbered steps (1. 2. 3.) and return a list of lines with "" between steps
    so the drawer can add a visual gap. Each step is word-wrapped to max_width_px.
    """
    if not (instr or "").strip():
        return []
    # Split on space that is followed by "number." so each step starts with "1." or "2." etc.
    steps = re.split(r" (?=\d+\.)", instr.strip())
    steps = [s.strip() for s in steps if s.strip()]
    lines = []
    for i, step in enumerate(steps):
        for wrapped in _wrap_text_pixels(draw, step, font, max_width_px):
            lines.append(wrapped)
        if i < len(steps) - 1:
            lines.append("")  # gap before next step
    return lines


def _draw_centered_block_left_aligned(draw, lines, center_xy, font, fill, max_width_px, line_gap=6, blank_line_gap=0):
    """Position block so its center is at center_xy; draw all lines left-aligned. If blank_line_gap>0, empty strings add extra vertical gap."""
    if not lines:
        return
    cx, cy = center_xy
    x_left = int(cx - max_width_px / 2)
    heights = []
    for line in lines:
        if line:
            bbox = _text_bbox(draw, line, font)
            heights.append(bbox[3] - bbox[1])
    line_h = max(heights) if heights else getattr(font, "size", 20)
    gap_for_blank = blank_line_gap if blank_line_gap else line_h
    total_h = sum(gap_for_blank if not line else line_h for line in lines) + (len(lines) - 1) * line_gap
    y = int(cy - total_h / 2)
    for line in lines:
        if line:
            draw.text((x_left, y), line, fill=fill, font=font)
            y += line_h
        else:
            y += gap_for_blank
        y += line_gap


def _draw_glow_text(draw, xy, text, font, fill="white", glow_fill="black", glow_radius=3):
    """Draw text with a subtle glow behind it."""
    x, y = xy
    for dx in range(-glow_radius, glow_radius + 1):
        for dy in range(-glow_radius, glow_radius + 1):
            if dx == 0 and dy == 0:
                continue
            if abs(dx) + abs(dy) > glow_radius + 2:
                continue
            draw.text((x + dx, y + dy), text, fill=glow_fill, font=font)
    draw.text((x, y), text, fill=fill, font=font)


def make_meal_image(recipe, output_path):
    """Create 1000×1500 meal image: downloaded image cropped to ratio + title at top centre."""
    if not Image or not ImageDraw:
        logging.error("Pillow (PIL) is required for image generation.")
        return False
    img = download_image(recipe["image_url"]) if recipe.get("image_url") else None
    if img is None:
        return False
    img = center_crop_to_ratio(img, MEAL_IMAGE_SIZE[0], MEAL_IMAGE_SIZE[1])
    if img is None:
        return False
    draw = ImageDraw.Draw(img)
    font = get_font(88, bold=True) or get_font(88)
    title = recipe["title"]
    # Wrap title to fit on image (pixel-based); add lines as needed, all centred
    margin = 80
    max_title_width = MEAL_IMAGE_SIZE[0] - 2 * margin
    title_lines = _wrap_text_pixels(draw, title, font, max_title_width)
    if not title_lines:
        title_lines = [title]
    y = 210
    for line in title_lines:
        bbox = _text_bbox(draw, line, font)
        tw = bbox[2] - bbox[0]
        x = (MEAL_IMAGE_SIZE[0] - tw) // 2  # centre every line
        _draw_glow_text(draw, (x, y), line, font=font, fill="white", glow_fill="black", glow_radius=8)
        y += 92
    _paste_logo_on_image(img)
    img.save(output_path, "PNG")
    logging.info(f"Saved meal image: {output_path}")
    return True


def make_recipe_card(recipe, meal_image_path, output_path):
    """Create recipe card: background, meal image left ~3/4 up, ingredients, instructions ~80 words, macros."""
    if not Image or not ImageDraw:
        return False
    w, h = RECIPE_CARD_SIZE
    if RECIPE_CARD_BACKGROUND and os.path.isfile(RECIPE_CARD_BACKGROUND):
        card = Image.open(RECIPE_CARD_BACKGROUND).convert("RGB")
        card = card.resize((w, h), Image.Resampling.LANCZOS)
    else:
        card = Image.new("RGB", (w, h), COLOR_BG)
    draw = ImageDraw.Draw(card)

    # Fonts (Kiwi Maru preferred)
    font_title = get_font(CARD_TITLE_FONT_SIZE, bold=True) or get_font(CARD_TITLE_FONT_SIZE)
    font_ing = get_font(CARD_INGREDIENTS_FONT_SIZE) or get_font(30)
    font_inst = get_font(CARD_INSTRUCTIONS_FONT_SIZE) or get_font(30)
    font_macros = get_font(CARD_MACROS_FONT_SIZE) or get_font(30)

    # Meal image on card (cropped to 410x410, centered at 297x445) — drawn first so title can sit on top
    meal_src = None
    if recipe.get("image_url"):
        meal_src = download_image(recipe["image_url"])
    if meal_src is None and os.path.isfile(meal_image_path):
        # fallback: uses generated meal image (may contain title overlay)
        meal_src = Image.open(meal_image_path).convert("RGB")
    if meal_src is not None:
        meal_sq = center_crop_to_ratio(meal_src, CARD_IMAGE_SIZE[0], CARD_IMAGE_SIZE[1])
        x0 = int(CARD_IMAGE_CENTER[0] - CARD_IMAGE_SIZE[0] / 2)
        y0 = int(CARD_IMAGE_CENTER[1] - CARD_IMAGE_SIZE[1] / 2)
        card.paste(meal_sq, (x0, y0))

    # Title on top of card (drawn after image so it appears in front)
    title_lines = _wrap_text_pixels(draw, recipe["title"], font_title, 980)
    _draw_centered_lines(draw, title_lines, CARD_TITLE_CENTER, font_title, COLOR_TITLE, line_gap=8)

    # Ingredients block (centered at your coordinate, left-aligned text)
    ingredients = [clean_ingredient(i) for i in recipe["ingredients"] if clean_ingredient(i)]
    ing_lines = []
    for item in ingredients:
        ing_lines.extend(_wrap_text_pixels(draw, item, font_ing, INGREDIENTS_MAX_WIDTH_PX))
    _draw_centered_block_left_aligned(
        draw, ing_lines[:30], CARD_INGREDIENTS_CENTER, font_ing, COLOR_BODY, INGREDIENTS_MAX_WIDTH_PX, line_gap=6
    )

    # Instructions block: split on "1." "2." etc., wrap each step, add gap between steps
    instr = condense_instructions_ai(recipe["instructions"], 80)
    instr_lines = _instruction_lines_with_step_gaps(draw, instr, font_inst, INSTRUCTIONS_MAX_WIDTH_PX)
    _draw_centered_block_left_aligned(
        draw,
        instr_lines[:40],
        CARD_INSTRUCTIONS_CENTER,
        font_inst,
        COLOR_BODY,
        INSTRUCTIONS_MAX_WIDTH_PX,
        line_gap=6,
        blank_line_gap=12,
    )

    # Macros block (centered at your coordinate)
    cal = format_macro(recipe["calories"]) or "—"
    prot = format_macro(recipe["protein"]) or "—"
    fat_s = format_macro(recipe["fat"]) or "—"
    macro_lines = [
        "Macros",
        f"Calories: {cal}",
        f"Protein: {prot}",
        f"Fat: {fat_s}",
    ]
    _draw_centered_lines(draw, macro_lines, CARD_MACROS_CENTER, font_macros, COLOR_BODY, line_gap=6)

    card.save(output_path, "PNG")
    logging.info(f"Saved recipe card: {output_path}")
    return True


def make_opening_image(video_title, image_url, output_path):
    """Opening image: 3rd recipe photo + logo + video title (front and centre, Bushire Tro Demo, diagonal left-down shadow)."""
    if not Image or not ImageDraw:
        return False
    img = download_image(image_url)
    if img is None:
        logging.warning("Could not download image for opening; skipping opening image.")
        return False
    img = center_crop_to_ratio(img, MEAL_IMAGE_SIZE[0], MEAL_IMAGE_SIZE[1])
    if img is None:
        return False
    draw = ImageDraw.Draw(img)
    font = get_opening_font(OPENING_TITLE_FONT_SIZE)
    title = (video_title or "Video").strip()
    # Word-wrap title for centre block (max ~40 chars per line)
    title_lines = _wrap_text_pixels(draw, title, font, 900)
    if not title_lines:
        title_lines = [title]
    # Vertical centre of image
    line_h = 0
    for line in title_lines:
        bbox = _text_bbox(draw, line, font)
        line_h = max(line_h, bbox[3] - bbox[1])
    line_gap = 12
    total_h = len(title_lines) * line_h + (len(title_lines) - 1) * line_gap
    cy = MEAL_IMAGE_SIZE[1] // 2
    y = int(cy - total_h / 2)
    # Black background box behind title text (padding in px)
    pad = 24
    max_w = 0
    for line in title_lines:
        bbox = _text_bbox(draw, line, font)
        max_w = max(max_w, bbox[2] - bbox[0])
    box_left = (MEAL_IMAGE_SIZE[0] - max_w) // 2 - pad
    box_right = (MEAL_IMAGE_SIZE[0] + max_w) // 2 + pad
    box_top = y - pad
    box_bottom = y + total_h + pad
    draw.rectangle([box_left, box_top, box_right, box_bottom], fill="black")
    # Draw title text (shadow then white)
    sx, sy = OPENING_SHADOW_OFFSET  # diagonal left-down: shadow to the left and below
    for line in title_lines:
        bbox = _text_bbox(draw, line, font)
        tw = bbox[2] - bbox[0]
        x = (MEAL_IMAGE_SIZE[0] - tw) // 2
        draw.text((x - sx, y + sy), line, fill="black", font=font)
        draw.text((x, y), line, fill="white", font=font)
        y += line_h + line_gap
    _paste_logo_on_image(img)
    img.save(output_path, "PNG")
    logging.info(f"Saved opening image: {output_path}")
    return True


def run_image_generation(video_title: str, urls: list[str]) -> str:
    """
    Generate recipe card and opening images for all URLs, split into parts.
    Returns the run directory path (e.g. tiktok_output/17).
    """
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    batches = [
        urls[i : i + RECIPES_PER_PART]
        for i in range(0, len(urls), RECIPES_PER_PART)
    ]
    logging.info(f"Split {len(urls)} recipe(s) into {len(batches)} part(s) (up to {RECIPES_PER_PART} recipes per part).")

    existing = [d for d in os.listdir(OUTPUT_DIR) if os.path.isdir(os.path.join(OUTPUT_DIR, d)) and d.isdigit()]
    run_number = max([int(d) for d in existing], default=0) + 1
    run_dir = os.path.join(OUTPUT_DIR, str(run_number))
    os.makedirs(run_dir, exist_ok=True)
    logging.info(f"Output folder: {run_dir}")

    for part_index, batch in enumerate(batches, start=1):
        part_title = f"{video_title} (Part {part_index})"
        part_dir = os.path.join(run_dir, f"Part_{part_index}")
        os.makedirs(part_dir, exist_ok=True)
        logging.info(f"--- Part {part_index}: {len(batch)} recipe(s) ---")

        batch_image_urls = []
        for i, url in enumerate(batch):
            logging.info(f"[Part {part_index}] [{i + 1}/{len(batch)}] {url}")
            try:
                recipe = scrape_recipe(url)
            except Exception as e:
                logging.error(f"Scrape failed: {e}")
                continue
            batch_image_urls.append(recipe.get("image_url"))
            slug = slug_from_title(recipe["title"])
            meal_path = os.path.join(part_dir, f"{slug}_meal.png")
            recipe_path = os.path.join(part_dir, f"{slug}_recipe.png")
            success = make_meal_image(recipe, meal_path)
            if not success:
                user_url = input(
                    f"Could not find image for '{recipe['title']}'. Enter image URL (or press Enter to skip): "
                ).strip()
                if user_url:
                    recipe["image_url"] = user_url
                    batch_image_urls[-1] = user_url
                    make_meal_image(recipe, meal_path)
            make_recipe_card(recipe, meal_path, recipe_path)

        opening_image_url = None
        if len(batch_image_urls) > 2:
            opening_image_url = batch_image_urls[2]
        elif batch_image_urls:
            opening_image_url = batch_image_urls[-1]
        if opening_image_url:
            opening_path = os.path.join(part_dir, OPENING_IMAGE_FILENAME)
            make_opening_image(part_title, opening_image_url, opening_path)
        else:
            logging.warning(f"Part {part_index}: Could not create opening image (no recipe image available).")

    return run_dir


def main():
    video_title = input("Enter the video title: ").strip()

    source = input("Do you want to use the txt file or AI helper? (txt file / AI helper): ").strip().lower()
    urls = []
    if source in ("txt file", "txt", "file", "t"):
        if os.path.isfile(URL_FILE):
            with open(URL_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        urls.append(line)
        if not urls:
            print(f"No URLs found in {URL_FILE}")
            return
    elif source in ("ai helper", "ai", "a", "helper"):
        search_query = input("What do you want to search for? ").strip()
        if not search_query:
            print("No search query entered.")
            return
        urls = get_recipe_urls_from_ai(search_query)
        if not urls:
            print("No recipe URLs returned from AI. Try again or use the txt file.")
            return
    else:
        print("Please answer 'txt file' or 'AI helper'.")
        return

    run_dir = run_image_generation(video_title, urls)
    print(f"Done. Outputs in: {os.path.abspath(run_dir)}")


if __name__ == "__main__":
    main()
