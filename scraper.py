"""
Recipe Scraper - Batch Mode
Reads recipe URLs from a text file and scrapes them all into a single CSV file.

Configuration:
    - URL_FILE: Path to text file containing URLs (one per line)
    - OUTPUT_CSV: Name of the output CSV file
"""

from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from recipe_scrapers import scrape_html
import csv
import logging
import sys
import gzip
import zlib
import os
import re
import json

try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False
    logging.warning("BeautifulSoup not available. HTML tag parsing will be limited.")

# ============================================================================
# CONFIGURATION - You can modify these values directly in the script
# ============================================================================

# Path to the text file containing recipe URLs (one URL per line)
URL_FILE = "high_protein.txt"

# Output CSV filename
OUTPUT_CSV = "high_protein.csv"

# CSS selector for extracting tags from HTML (leave empty string "" to use auto-detection)
# Examples:
#   BBC Good Food: "div.post-header--masthead__tags-item" or ".post-header--masthead__tags-item"
#   AllRecipes: "span.badge" or "[data-tag]"
#   Generic: "span.tag, a.tag, [class*='tag']"
# Leave as empty string "" to try auto-detection first, then fallback to common patterns
TAG_SELECTOR = "div.post-header--masthead__tags-item"

# ============================================================================

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper_errors.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# Create a request with proper headers to mimic a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

def fetch_html(url):
    """Fetch HTML from a URL with proper headers and decompression."""
    try:
        logging.info(f"Fetching URL: {url}")
        req = Request(url, headers=HEADERS)
        
        with urlopen(req) as response:
            logging.debug(f"HTTP Status Code: {response.getcode()}")
            
            # Read the raw response
            raw_data = response.read()
            logging.debug(f"Raw response size: {len(raw_data)} bytes")
            
            # Check if content is gzip compressed
            content_encoding = response.headers.get('Content-Encoding', '').lower()
            
            if content_encoding == 'gzip' or (raw_data[:2] == b'\x1f\x8b'):  # gzip magic number
                html = gzip.decompress(raw_data).decode("utf-8")
            elif content_encoding == 'deflate':
                html = zlib.decompress(raw_data).decode("utf-8")
            else:
                html = raw_data.decode("utf-8")
            
            logging.debug(f"Successfully fetched HTML (length: {len(html)} characters)")
            return html
            
    except HTTPError as e:
        logging.error(f"HTTP Error for {url}: {e.code} - {e.reason}")
        raise
    except URLError as e:
        logging.error(f"URL Error for {url}: {e.reason}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error fetching {url}: {type(e).__name__} - {str(e)}")
        raise

def read_urls_from_file(filename):
    """Read URLs from a text file, one per line."""
    urls = []
    try:
        if not os.path.exists(filename):
            logging.error(f"URL file not found: {filename}")
            return urls
        
        with open(filename, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                url = line.strip()
                if url and not url.startswith('#'):  # Skip empty lines and comments
                    urls.append(url)
        
        logging.info(f"Read {len(urls)} URLs from {filename}")
        return urls
    except Exception as e:
        logging.error(f"Error reading URL file {filename}: {type(e).__name__} - {str(e)}")
        raise

# Helper function to safely get attribute or return empty string
def safe_get(func, default="", field_name=""):
    try:
        result = func()
        if result is not None:
            logging.debug(f"Successfully extracted {field_name}: {str(result)[:50]}...")
        return result if result is not None else default
    except Exception as e:
        logging.warning(f"Could not extract {field_name}: {type(e).__name__} - {str(e)}")
        return default

# Helper function to convert time to minutes
def time_to_minutes(time_str):
    """Convert time string (e.g., 'PT30M', '1H 30M') to minutes"""
    if not time_str:
        return ""
    try:
        # Handle ISO 8601 duration format (PT30M, PT1H30M)
        if time_str.startswith('PT'):
            time_str = time_str[2:]
            minutes = 0
            if 'H' in time_str:
                hours, rest = time_str.split('H')
                minutes += int(hours) * 60
                time_str = rest
            if 'M' in time_str:
                minutes += int(time_str.replace('M', ''))
            return str(minutes)
        # Handle other formats (try to parse)
        return str(time_str)
    except:
        return str(time_str)

def extract_tags_from_html(html, url):
    """Extract tags from HTML when recipe_scrapers doesn't provide them."""
    tags_list = []
    
    if not BEAUTIFULSOUP_AVAILABLE:
        return tags_list
    
    try:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Method 1: Use configured TAG_SELECTOR if provided
        if TAG_SELECTOR and TAG_SELECTOR.strip():
            try:
                elements = soup.select(TAG_SELECTOR)
                for elem in elements:
                    text = elem.get_text(strip=True)
                    if text and len(text) < 100:  # Reasonable tag length
                        tags_list.append(text)
                if tags_list:
                    logging.debug(f"Found {len(tags_list)} tags using configured selector: {TAG_SELECTOR}")
                    # Clean up and return early if we found tags with the configured selector
                    tags_list = [tag.strip() for tag in tags_list if tag and tag.strip()]
                    tags_list = list(dict.fromkeys(tags_list))
                    return tags_list
            except Exception as e:
                logging.debug(f"Error using configured tag selector '{TAG_SELECTOR}': {type(e).__name__} - {str(e)}")
        
        # Method 2: Look for meta keywords
        meta_keywords = soup.find('meta', attrs={'name': 'keywords'})
        if meta_keywords and meta_keywords.get('content'):
            keywords = meta_keywords.get('content').split(',')
            tags_list.extend([k.strip() for k in keywords if k.strip()])
        
        # Method 3: Look for recipe tags/categories in common class names
        tag_selectors = [
            'span[class*="tag"]',
            'a[class*="tag"]',
            'div[class*="tag"]',
            'span[class*="badge"]',
            'span[class*="label"]',
            '[data-tag]',
            '[data-category]'
        ]
        
        for selector in tag_selectors:
            elements = soup.select(selector)
            for elem in elements:
                text = elem.get_text(strip=True)
                if text and len(text) < 100:  # Reasonable tag length
                    tags_list.append(text)
        
        # Method 4: Look for structured data (JSON-LD)
        json_scripts = soup.find_all('script', type='application/ld+json')
        for script in json_scripts:
            try:
                data = json.loads(script.string)
                # Look for keywords, tags, or recipeCategory in structured data
                if isinstance(data, dict):
                    for key in ['keywords', 'tags', 'recipeCategory', 'recipeCuisine']:
                        if key in data:
                            value = data[key]
                            if isinstance(value, list):
                                tags_list.extend([str(v) for v in value])
                            elif isinstance(value, str):
                                tags_list.append(value)
            except:
                pass
        
        # Clean up: remove duplicates and empty strings
        tags_list = [tag.strip() for tag in tags_list if tag and tag.strip()]
        tags_list = list(dict.fromkeys(tags_list))  # Remove duplicates
        
    except Exception as e:
        logging.debug(f"Error extracting tags from HTML for {url}: {type(e).__name__} - {str(e)}")
    
    return tags_list

def scrape_recipe(url):
    """Scrape a single recipe URL and return the data as a dictionary."""
    html = None
    try:
        # Fetch HTML
        html = fetch_html(url)
        
        # Parse with recipe_scrapers
        scraper = scrape_html(html, org_url=url)
        
        # Extract recipe information
        recipe_title = safe_get(scraper.title, field_name="title")
        description = safe_get(scraper.description, field_name="description") or safe_get(lambda: scraper.summary() if hasattr(scraper, 'summary') else None, field_name="summary")
        cover_image_url = safe_get(scraper.image, field_name="image")
        
        # Time extraction
        prep_time = safe_get(scraper.prep_time, field_name="prep_time")
        prep_time_minutes = time_to_minutes(prep_time) if prep_time else ""
        cook_time = safe_get(scraper.cook_time, field_name="cook_time")
        cook_time_minutes = time_to_minutes(cook_time) if cook_time else ""
        
        # Servings
        servings = safe_get(scraper.yields, field_name="yields") or safe_get(lambda: scraper.servings() if hasattr(scraper, 'servings') else None, field_name="servings")
        
        # Difficulty level (may not be available for all sites)
        difficulty = safe_get(lambda: scraper.difficulty() if hasattr(scraper, 'difficulty') else None, field_name="difficulty")
        
        # Ingredients list
        ingredients = safe_get(scraper.ingredients, field_name="ingredients")
        ingredients_list = "; ".join(ingredients) if isinstance(ingredients, list) else str(ingredients)
        
        # Instructions
        instructions = safe_get(scraper.instructions, field_name="instructions")
        if isinstance(instructions, list):
            step_by_step = " | ".join([f"Step {i+1}: {step}" for i, step in enumerate(instructions)])
        else:
            step_by_step = str(instructions)
        
        # Nutritional information
        nutrients = safe_get(scraper.nutrients, field_name="nutrients")
        calories = ""
        protein = ""
        carbs = ""
        fat = ""
        fiber = ""
        
        if nutrients:
            if isinstance(nutrients, dict):
                # Try different possible key names for nutrition data
                calories = str(nutrients.get('calories', nutrients.get('Calories', '')))
                protein = str(nutrients.get('protein', nutrients.get('Protein', nutrients.get('proteinContent', ''))))
                carbs = str(nutrients.get('carbohydrates', nutrients.get('Carbohydrates', nutrients.get('carbohydrateContent', nutrients.get('carbs', '')))))
                fat = str(nutrients.get('fat', nutrients.get('Fat', nutrients.get('fatContent', ''))))
                fiber = str(nutrients.get('fiber', nutrients.get('Fiber', nutrients.get('fiberContent', ''))))
        
        # Cuisine type
        cuisine = safe_get(lambda: scraper.cuisine() if hasattr(scraper, 'cuisine') else None, field_name="cuisine")
        
        # Meal type
        meal_type = safe_get(lambda: scraper.category() if hasattr(scraper, 'category') else None, field_name="category")
        if not meal_type:
            meal_type = safe_get(lambda: scraper.meal_type() if hasattr(scraper, 'meal_type') else None, field_name="meal_type")
        
        # Rating
        rating_avg = ""
        rating_count = ""
        try:
            if hasattr(scraper, 'ratings'):
                ratings = scraper.ratings()
                if ratings:
                    rating_avg = str(ratings)
            if hasattr(scraper, 'rating'):
                rating_avg = str(safe_get(scraper.rating, field_name="rating"))
            if hasattr(scraper, 'ratings_count'):
                rating_count = str(safe_get(scraper.ratings_count, field_name="ratings_count"))
        except Exception as e:
            logging.warning(f"Error extracting rating for {url}: {type(e).__name__} - {str(e)}")
        
        # Tags (dietary tags, categories, etc.)
        tags = ""
        try:
            # Try different methods that recipe_scrapers might use for tags
            tags_list = []
            
            # Method 1: tags() method
            if hasattr(scraper, 'tags'):
                try:
                    tags_result = scraper.tags()
                    if tags_result:
                        if isinstance(tags_result, list):
                            tags_list.extend(tags_result)
                        else:
                            tags_list.append(str(tags_result))
                except:
                    pass
            
            # Method 2: keywords() method
            if hasattr(scraper, 'keywords'):
                try:
                    keywords_result = scraper.keywords()
                    if keywords_result:
                        if isinstance(keywords_result, list):
                            tags_list.extend(keywords_result)
                        else:
                            tags_list.append(str(keywords_result))
                except:
                    pass
            
            # Method 3: dietary_restrictions() or similar
            if hasattr(scraper, 'dietary_restrictions'):
                try:
                    dietary = scraper.dietary_restrictions()
                    if dietary:
                        if isinstance(dietary, list):
                            tags_list.extend(dietary)
                        else:
                            tags_list.append(str(dietary))
                except:
                    pass
            
            # Method 4: Check if there's a to_json() that might contain tags
            try:
                json_data = scraper.to_json()
                if isinstance(json_data, dict):
                    # Look for common tag-related keys
                    for key in ['tags', 'keywords', 'categories', 'dietary', 'dietary_restrictions']:
                        if key in json_data and json_data[key]:
                            if isinstance(json_data[key], list):
                                tags_list.extend([str(t) for t in json_data[key]])
                            else:
                                tags_list.append(str(json_data[key]))
            except:
                pass
            
            # Method 5: Fallback to HTML parsing if no tags found yet
            if not tags_list and html:
                html_tags = extract_tags_from_html(html, url)
                tags_list.extend(html_tags)
            
            # Remove duplicates and empty strings, then join
            tags_list = [str(tag).strip() for tag in tags_list if tag and str(tag).strip()]
            tags_list = list(dict.fromkeys(tags_list))  # Remove duplicates while preserving order
            tags = ", ".join(tags_list) if tags_list else ""
            
            if tags:
                logging.debug(f"Found tags: {tags}")
        except Exception as e:
            logging.warning(f"Error extracting tags for {url}: {type(e).__name__} - {str(e)}")
        
        # Prepare CSV data
        csv_data = {
            'Recipe URL': url,
            'Recipe Title': recipe_title,
            'Description/Summary': description,
            'Cover Image URL': cover_image_url,
            'Prep Time (minutes)': prep_time_minutes,
            'Cook Time (minutes)': cook_time_minutes,
            'Servings/Serves': servings,
            'Difficulty Level': difficulty,
            'Ingredients List': ingredients_list,
            'Step-by-Step Instructions': step_by_step,
            'Calories': calories,
            'Protein': protein,
            'Carbs': carbs,
            'Fat': fat,
            'Fiber': fiber,
            'Cuisine Type': cuisine,
            'Meal Type': meal_type,
            'Tags': tags,
            'Rating (Average)': rating_avg,
            'Rating (Count)': rating_count
        }
        
        logging.info(f"✓ Successfully scraped: {recipe_title}")
        return csv_data
        
    except Exception as e:
        logging.error(f"✗ Failed to scrape {url}: {type(e).__name__} - {str(e)}")
        # Return a row with error information
        return {
            'Recipe URL': url,
            'Recipe Title': f"ERROR: {str(e)[:100]}",
            'Description/Summary': '',
            'Cover Image URL': '',
            'Prep Time (minutes)': '',
            'Cook Time (minutes)': '',
            'Servings/Serves': '',
            'Difficulty Level': '',
            'Ingredients List': '',
            'Step-by-Step Instructions': '',
            'Calories': '',
            'Protein': '',
            'Carbs': '',
            'Fat': '',
            'Fiber': '',
            'Cuisine Type': '',
            'Meal Type': '',
            'Tags': '',
            'Rating (Average)': '',
            'Rating (Count)': ''
        }

def main():
    """Main function to scrape all recipes from the URL file."""
    # Read URLs from file
    urls = read_urls_from_file(URL_FILE)
    
    if not urls:
        print(f"Error: No URLs found in {URL_FILE}")
        print("Please make sure the file exists and contains URLs (one per line).")
        return
    
    print(f"\nStarting batch scrape of {len(urls)} recipes...")
    print(f"Reading URLs from: {URL_FILE}")
    print(f"Output will be saved to: {OUTPUT_CSV}\n")
    
    # Scrape all recipes
    all_recipe_data = []
    successful = 0
    failed = 0
    
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] Scraping: {url}")
        recipe_data = scrape_recipe(url)
        all_recipe_data.append(recipe_data)
        
        if recipe_data.get('Recipe Title', '').startswith('ERROR:'):
            failed += 1
        else:
            successful += 1
    
    # Write all data to CSV
    if all_recipe_data:
        try:
            logging.info(f"Writing {len(all_recipe_data)} recipes to {OUTPUT_CSV}...")
            fieldnames = list(all_recipe_data[0].keys())
            
            with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_recipe_data)
            
            print(f"\n{'='*60}")
            print(f"✓ Batch scraping complete!")
            print(f"  Total recipes: {len(all_recipe_data)}")
            print(f"  Successful: {successful}")
            print(f"  Failed: {failed}")
            print(f"  Output file: {OUTPUT_CSV}")
            print(f"{'='*60}")
            logging.info(f"Successfully saved {len(all_recipe_data)} recipes to {OUTPUT_CSV}")
        except Exception as e:
            logging.error(f"Error writing CSV file: {type(e).__name__} - {str(e)}")
            print(f"\n✗ Error writing CSV file: {str(e)}")
            raise
    else:
        print("\n✗ No recipe data to save.")

if __name__ == "__main__":
    main()