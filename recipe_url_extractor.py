"""
Recipe URL Extractor
Extracts recipe URLs from a listing page based on a customizable pattern.

Requirements:
    - beautifulsoup4: pip install beautifulsoup4
    - brotli (optional, for sites that use Content-Encoding: br): pip install brotli

Usage:
    python recipe_url_extractor.py
    Then follow the prompts, or edit DEFAULT_URL and DEFAULT_PATTERN at the top of the script.
"""

from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
import logging
import sys
import gzip
import zlib
import re

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("Error: beautifulsoup4 is required. Install it with: pip install beautifulsoup4")
    sys.exit(1)

try:
    import brotli
except ImportError:
    brotli = None  # Optional: needed only when server uses Content-Encoding: br

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('url_extractor_errors.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

# ============================================================================
# CONFIGURATION - You can modify these values directly in the script
# ============================================================================

# Default URL to scrape (leave empty string "" to be prompted for input)
DEFAULT_URL = "https://www.delish.com/cooking/recipe-ideas/g36715276/best-tiktok-recipes"

# Default URL pattern for BBC Good Food recipes
# Pattern uses regex to match recipe URLs
# Matches: https://www.bbcgoodfood.com/recipes/{recipe-slug}
# Excludes: /recipes/collection/ and /recipes/collections/
# Uses negative lookahead to exclude collection URLs
DEFAULT_PATTERN = r'https?://(www\.)?bbcgoodfood\.com/recipes/(?!collection)[^/?#]+'

# Default output filename
DEFAULT_OUTPUT_FILE = 'bbcgoodfood_high_protein_recipes.txt'

# You can customize the pattern. Examples:
# - For AllRecipes: r'https://www\.allrecipes\.com/recipe/\d+/.+?/'
# - For Food Network: r'https://www\.foodnetwork\.com/recipes/.+?'
# - For BBC Good Food (excludes collections): r'https?://(www\.)?bbcgoodfood\.com/recipes/(?!collection)[^/?#]+'
# - Generic recipe pattern: r'https://.*?/recipe/.+?'


def url_to_pattern(reference_url):
    """
    Build a regex pattern from a reference recipe URL so that similar URLs will match.
    
    - Scheme becomes https?://
    - Domain allows optional www. and is escaped
    - Path segments: all-digit segments become \\d+, others become [^/?#]+
    - Query and fragment are not required (matched URLs may have them)
    
    Example:
        https://www.bbcgoodfood.com/recipes/high-protein-bowl
        -> https?://(www\\.)?bbcgoodfood\\.com/recipes/[^/?#]+
    """
    parsed = urlparse(reference_url)
    scheme = "https?://"
    netloc = parsed.netloc
    if not netloc:
        raise ValueError("Reference URL has no host (e.g. missing https://)")
    # Optional www.
    if netloc.lower().startswith("www."):
        domain_part = re.escape(netloc[4:])  # after "www."
        netloc_re = f"(www\\.)?{domain_part}"
    else:
        netloc_re = re.escape(netloc)
    # Path: generalize each segment
    path = (parsed.path or "/").rstrip("/")
    segments = [s for s in path.split("/") if s]
    if not segments:
        path_re = "/"
    else:
        parts = []
        for seg in segments:
            if seg.isdigit():
                parts.append(r"\d+")
            else:
                parts.append(r"[^/?#]+")
        path_re = "/" + "/".join(parts)
    pattern = f"{scheme}{netloc_re}{path_re}"
    return pattern


def fetch_html(url):
    """Fetch HTML from a URL with proper headers and decompression."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        logging.info(f"Attempting to fetch URL: {url}")
        req = Request(url, headers=headers)
        
        with urlopen(req) as response:
            logging.info(f"HTTP Status Code: {response.getcode()}")
            
            # Read the raw response
            raw_data = response.read()
            logging.info(f"Raw response size: {len(raw_data)} bytes")
            
            # Check if content is gzip compressed
            content_encoding = response.headers.get('Content-Encoding', '').lower()
            logging.info(f"Content-Encoding: {content_encoding}")
            
            if content_encoding == 'gzip' or (raw_data[:2] == b'\x1f\x8b'):  # gzip magic number
                logging.info("Decompressing gzip content...")
                html = gzip.decompress(raw_data).decode("utf-8")
            elif content_encoding == 'deflate':
                logging.info("Decompressing deflate content...")
                html = zlib.decompress(raw_data).decode("utf-8")
            elif content_encoding == 'br':
                if brotli is None:
                    raise RuntimeError(
                        "Server returned Brotli-compressed content (Content-Encoding: br). "
                        "Install the brotli package: pip install brotli"
                    )
                logging.info("Decompressing Brotli content...")
                html = brotli.decompress(raw_data).decode("utf-8")
            else:
                html = raw_data.decode("utf-8")
            
            logging.info(f"Successfully fetched HTML (length: {len(html)} characters)")
            return html
            
    except HTTPError as e:
        logging.error(f"HTTP Error occurred: {e.code} - {e.reason}")
        logging.error(f"URL: {e.url}")
        raise
    except URLError as e:
        logging.error(f"URL Error occurred: {e.reason}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error occurred: {type(e).__name__} - {str(e)}")
        raise

def extract_recipe_urls(html, base_url, pattern=None):
    """
    Extract recipe URLs from HTML that match the given pattern.
    
    Args:
        html: HTML content as string
        base_url: Base URL for resolving relative links
        pattern: Regex pattern to match recipe URLs (default: AllRecipes pattern)
    
    Returns:
        List of unique recipe URLs
    """
    if pattern is None:
        pattern = DEFAULT_PATTERN
    
    logging.info(f"Using pattern: {pattern}")
    
    # Parse HTML with BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    
    # Find all anchor tags with href attributes
    all_links = []
    for tag in soup.find_all('a', href=True):
        href = tag.get('href')
        if href:
            # Convert relative URLs to absolute URLs
            absolute_url = urljoin(base_url, href)
            all_links.append(absolute_url)
    
    logging.info(f"Found {len(all_links)} total links on the page")
    
    # Filter links that match the pattern
    pattern_regex = re.compile(pattern)
    recipe_urls = []
    seen = set()
    
    for link in all_links:
        if pattern_regex.match(link) and link not in seen:
            recipe_urls.append(link)
            seen.add(link)
    
    logging.info(f"Found {len(recipe_urls)} recipe URLs matching the pattern")
    return recipe_urls

def save_urls_to_file(urls, filename='recipe_urls.txt'):
    """Save URLs to a text file, one per line."""
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for url in urls:
                f.write(url + '\n')
        logging.info(f"Saved {len(urls)} URLs to {filename}")
        return filename
    except Exception as e:
        logging.error(f"Error saving URLs to file: {type(e).__name__} - {str(e)}")
        raise

def main():
    """Main function to run the URL extractor."""
    # Get input URL
    if DEFAULT_URL:
        print(f"Using configured URL: {DEFAULT_URL}")
        print("(To change this, edit DEFAULT_URL at the top of the script)")
        use_default = input("Use this URL? (Y/n): ").strip().lower()
        if use_default and use_default != 'y':
            input_url = input("Enter the URL of the recipe listing page: ").strip()
        else:
            input_url = DEFAULT_URL
    else:
        input_url = input("Enter the URL of the recipe listing page: ").strip()
    
    if not input_url:
        logging.error("No URL provided")
        print("Error: URL is required")
        return
    
    # Get pattern: either from a reference URL or by typing a regex (or default)
    print("\nPattern can be set in two ways:")
    print("  1. Enter a REFERENCE recipe URL (one example of what a recipe link looks like)")
    print("  2. Or press Enter, then enter a custom regex (or use the default)")
    reference_url = input("Reference recipe URL (or press Enter to type pattern / use default): ").strip()
    if reference_url:
        try:
            pattern = url_to_pattern(reference_url)
            print(f"Generated pattern from reference URL:\n  {pattern}")
        except ValueError as e:
            logging.error(f"Invalid reference URL: {e}")
            print(f"Error: {e}")
            print("Falling back to pattern prompt.")
            custom_pattern = input("Enter a custom regex pattern (or press Enter to use default): ").strip()
            pattern = custom_pattern if custom_pattern else DEFAULT_PATTERN
    else:
        print(f"Default pattern: {DEFAULT_PATTERN}")
        custom_pattern = input("Enter a custom regex pattern (or press Enter to use default): ").strip()
        pattern = custom_pattern if custom_pattern else DEFAULT_PATTERN
    
    # Get output filename
    output_filename = input(f"\nEnter output filename (or press Enter for '{DEFAULT_OUTPUT_FILE}'): ").strip()
    if not output_filename:
        output_filename = DEFAULT_OUTPUT_FILE
    
    try:
        # Fetch HTML
        html = fetch_html(input_url)
        
        # Extract recipe URLs
        recipe_urls = extract_recipe_urls(html, input_url, pattern)
        
        if recipe_urls:
            # Save to file
            save_urls_to_file(recipe_urls, output_filename)
            print(f"\n✓ Successfully extracted {len(recipe_urls)} recipe URLs!")
            print(f"✓ Saved to: {output_filename}")
            print(f"\nFirst few URLs:")
            for i, url in enumerate(recipe_urls[:5], 1):
                print(f"  {i}. {url}")
            if len(recipe_urls) > 5:
                print(f"  ... and {len(recipe_urls) - 5} more")
        else:
            print(f"\n⚠ No recipe URLs found matching the pattern: {pattern}")
            print("Try adjusting the pattern or check if the page structure has changed.")
            
    except Exception as e:
        logging.error(f"Failed to extract URLs: {type(e).__name__} - {str(e)}")
        print(f"\n✗ Error: {str(e)}")
        print("Check url_extractor_errors.log for details.")

if __name__ == "__main__":
    main()

