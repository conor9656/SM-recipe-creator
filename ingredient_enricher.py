"""
Ingredient Enricher - USDA FoodData Central API Integration
Reads ingredients from a CSV file, queries the USDA FoodData Central API for nutritional data,
and stores the enriched data in a SQLite database.

Requirements:
    - requests: pip install requests
    - sqlite3: Built-in with Python

Configuration:
    - INPUT_CSV: Path to CSV file with ingredients
    - API_KEY: Your USDA FoodData Central API key (get one at https://fdc.nal.usda.gov/api-guide.html)
    - DATABASE_FILE: Path to SQLite database file
"""

import csv
import sqlite3
import requests
import logging
import sys
import time
import json
from typing import Dict, List, Optional, Any

# ============================================================================
# CONFIGURATION - You can modify these values directly in the script
# ============================================================================

# Path to input CSV file
INPUT_CSV = "ingredient_list_v1.csv"

# USDA FoodData Central API key
# Get your API key at: https://api.data.gov/signup/
# You can use "DEMO_KEY" for testing, but it has lower rate limits
API_KEY = "hIhAidN81WVhZKzjEOPZrFFXz6AAD2OqZovOKt5h"  # Replace with your actual API key

# SQLite database file path
DATABASE_FILE = "ingredients.db"

# API endpoint
API_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

# Rate limiting: 1000 requests per hour per IP (default)
# Add delay between requests to avoid hitting rate limits
REQUEST_DELAY = 0.5  # seconds between requests

# ============================================================================

# Set up logging with UTF-8 encoding to handle special characters
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ingredient_enricher.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

def create_database_schema(db_path: str):
    """
    Create the database schema for ingredients with nutritional data.
    
    Args:
        db_path: Path to SQLite database file
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create ingredients table with comprehensive nutritional data
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ingredients (
            id INTEGER PRIMARY KEY,
            ingredient_name TEXT NOT NULL,
            category TEXT,
            subcategory TEXT,
            fdc_id INTEGER,
            data_type TEXT,
            description TEXT,
            brand_owner TEXT,
            gtin_upc TEXT,
            household_serving_full_text TEXT,
            serving_size REAL,
            serving_size_unit TEXT,
            food_nutrients TEXT,
            -- Macronutrients (per 100g)
            calories REAL,
            protein_g REAL,
            fat_g REAL,
            saturated_fat_g REAL,
            trans_fat_g REAL,
            carbohydrates_g REAL,
            fiber_g REAL,
            sugar_g REAL,
            -- Vitamins
            vitamin_a_iu REAL,
            vitamin_c_mg REAL,
            vitamin_d_iu REAL,
            vitamin_e_mg REAL,
            vitamin_k_mcg REAL,
            thiamin_mg REAL,
            riboflavin_mg REAL,
            niacin_mg REAL,
            vitamin_b6_mg REAL,
            folate_mcg REAL,
            vitamin_b12_mcg REAL,
            -- Minerals
            calcium_mg REAL,
            iron_mg REAL,
            magnesium_mg REAL,
            phosphorus_mg REAL,
            potassium_mg REAL,
            sodium_mg REAL,
            zinc_mg REAL,
            copper_mg REAL,
            manganese_mg REAL,
            selenium_mcg REAL,
            -- Other
            cholesterol_mg REAL,
            caffeine_mg REAL,
            -- Metadata
            api_response TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ingredient_name, fdc_id)
        )
    ''')
    
    # Create index for faster lookups
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_ingredient_name ON ingredients(ingredient_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_fdc_id ON ingredients(fdc_id)')
    
    conn.commit()
    conn.close()
    logging.info(f"Database schema created/verified at {db_path}")

def search_food(ingredient_name: str, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Search for a food item using the USDA FoodData Central API.
    
    Args:
        ingredient_name: Name of the ingredient to search for
        api_key: USDA API key
    
    Returns:
        Dictionary containing food data or None if not found
    """
    url = f"{API_BASE_URL}/foods/search"
    
    # Prepare search query
    payload = {
        "query": ingredient_name,
        "pageSize": 10,  # Get top 10 results
        "dataType": ["Foundation", "SR Legacy", "Branded"]  # Search all data types
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    params = {
        "api_key": api_key
    }
    
    try:
        logging.info(f"Searching for: {ingredient_name}")
        logging.debug(f"API URL: {url}")
        logging.debug(f"Payload: {payload}")
        response = requests.post(url, json=payload, headers=headers, params=params, timeout=10)
        logging.debug(f"Response status code: {response.status_code}")
        response.raise_for_status()
        
        data = response.json()
        logging.debug(f"API returned {len(data.get('foods', []))} results")
        
        if data.get("foods") and len(data["foods"]) > 0:
            # Return the first (most relevant) result
            food = data["foods"][0]
            logging.info(f"Found: {food.get('description', 'N/A')} (FDC ID: {food.get('fdcId', 'N/A')})")
            return food
        else:
            logging.warning(f"No results found for: {ingredient_name}")
            logging.debug(f"API response: {data}")
            return None
            
    except requests.exceptions.Timeout as e:
        logging.error(f"API request timeout for '{ingredient_name}': {str(e)}")
        return None
    except requests.exceptions.HTTPError as e:
        logging.error(f"API HTTP error for '{ingredient_name}': Status {response.status_code} - {str(e)}")
        try:
            error_body = response.text[:500]  # First 500 chars of error
            logging.error(f"Error response body: {error_body}")
        except:
            pass
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"API request failed for '{ingredient_name}': {type(e).__name__} - {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error searching for '{ingredient_name}': {type(e).__name__} - {str(e)}", exc_info=True)
        return None

def get_food_details(fdc_id: int, api_key: str) -> Optional[Dict[str, Any]]:
    """
    Get detailed nutritional information for a specific food item.
    
    Args:
        fdc_id: FoodData Central ID
        api_key: USDA API key
    
    Returns:
        Dictionary containing detailed food data or None if not found
    """
    url = f"{API_BASE_URL}/food/{fdc_id}"
    params = {"api_key": api_key}
    
    try:
        logging.debug(f"Fetching details for FDC ID {fdc_id}")
        response = requests.get(url, params=params, timeout=10)
        logging.debug(f"Details response status code: {response.status_code}")
        response.raise_for_status()
        data = response.json()
        logging.debug(f"Successfully retrieved details for FDC ID {fdc_id}")
        return data
    except requests.exceptions.Timeout as e:
        logging.error(f"Timeout getting details for FDC ID {fdc_id}: {str(e)}")
        return None
    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP error getting details for FDC ID {fdc_id}: Status {response.status_code} - {str(e)}")
        try:
            error_body = response.text[:500]
            logging.error(f"Error response body: {error_body}")
        except:
            pass
        return None
    except requests.exceptions.RequestException as e:
        logging.error(f"Request failed getting details for FDC ID {fdc_id}: {type(e).__name__} - {str(e)}")
        return None
    except Exception as e:
        logging.error(f"Unexpected error getting details for FDC ID {fdc_id}: {type(e).__name__} - {str(e)}", exc_info=True)
        return None

def extract_nutrient_value(food_data: Dict[str, Any], nutrient_id: int) -> Optional[float]:
    """
    Extract a specific nutrient value from food data.
    
    Args:
        food_data: Food data dictionary from API
        nutrient_id: Nutrient ID (see USDA nutrient ID reference)
    
    Returns:
        Nutrient value or None if not found
    """
    food_nutrients = food_data.get("foodNutrients", [])
    
    for nutrient in food_nutrients:
        if nutrient.get("nutrient", {}).get("id") == nutrient_id:
            amount = nutrient.get("amount")
            if amount is not None:
                return float(amount)
    return None

def extract_nutritional_data(food_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract nutritional data from food API response.
    
    Args:
        food_data: Food data dictionary from API
    
    Returns:
        Dictionary with extracted nutritional values
    """
    # Common nutrient IDs (see USDA documentation for full list)
    NUTRIENT_IDS = {
        "calories": 1008,
        "protein_g": 1003,
        "fat_g": 1004,
        "saturated_fat_g": 1258,
        "trans_fat_g": 1257,
        "carbohydrates_g": 1005,
        "fiber_g": 1079,
        "sugar_g": 2000,
        "calcium_mg": 1087,
        "iron_mg": 1089,
        "magnesium_mg": 1090,
        "phosphorus_mg": 1091,
        "potassium_mg": 1092,
        "sodium_mg": 1093,
        "zinc_mg": 1095,
        "copper_mg": 1098,
        "manganese_mg": 1101,
        "selenium_mcg": 1103,
        "vitamin_c_mg": 1162,
        "thiamin_mg": 1165,
        "riboflavin_mg": 1166,
        "niacin_mg": 1167,
        "vitamin_b6_mg": 1175,
        "folate_mcg": 1177,
        "vitamin_b12_mcg": 1178,
        "vitamin_a_iu": 1104,
        "vitamin_e_mg": 1109,
        "vitamin_d_iu": 1114,
        "vitamin_k_mcg": 1185,
        "cholesterol_mg": 1253,
        "caffeine_mg": 1057,
    }
    
    nutrition = {}
    
    for key, nutrient_id in NUTRIENT_IDS.items():
        nutrition[key] = extract_nutrient_value(food_data, nutrient_id)
    
    return nutrition

def insert_ingredient(conn: sqlite3.Connection, row_data: Dict[str, Any], food_data: Optional[Dict[str, Any]] = None):
    """
    Insert or update ingredient data in the database.
    
    Args:
        conn: SQLite database connection
        row_data: Data from CSV row
        food_data: Food data from API (optional)
    """
    cursor = conn.cursor()
    
    # Prepare base data
    ingredient_id = row_data.get("id")
    ingredient_name = row_data.get("ingredient", "")
    category = row_data.get("category", "")
    subcategory = row_data.get("subcategory", "")
    
    # Initialize nutritional data
    nutritional_data = {}
    fdc_id = None
    description = None
    data_type = None
    brand_owner = None
    gtin_upc = None
    household_serving_full_text = None
    serving_size = None
    serving_size_unit = None
    food_nutrients_json = None
    api_response_json = None
    
    if food_data:
        fdc_id = food_data.get("fdcId")
        description = food_data.get("description")
        data_type = food_data.get("dataType")
        brand_owner = food_data.get("brandOwner")
        gtin_upc = food_data.get("gtinUpc")
        household_serving_full_text = food_data.get("householdServingFullText")
        
        # Extract serving size information
        if "foodPortions" in food_data and food_data["foodPortions"]:
            portion = food_data["foodPortions"][0]
            serving_size = portion.get("amount")
            serving_size_unit = portion.get("measureUnit", {}).get("name")
        
        # Extract nutritional data
        nutritional_data = extract_nutritional_data(food_data)
        
        # Store food nutrients as JSON
        food_nutrients_json = json.dumps(food_data.get("foodNutrients", []))
        
        # Store full API response as JSON
        api_response_json = json.dumps(food_data)
    
    # Prepare values tuple - ensure all values are properly formatted
    # Convert ingredient_id to int if it's a string
    try:
        ingredient_id_int = int(ingredient_id) if ingredient_id else None
    except (ValueError, TypeError):
        ingredient_id_int = None
        logging.warning(f"Could not convert ingredient_id '{ingredient_id}' to int, using None")
    
    # Ensure all None values are properly handled (SQLite accepts None)
    values_list = [
        ingredient_id_int, ingredient_name, category, subcategory, fdc_id, data_type,
        description, brand_owner, gtin_upc, household_serving_full_text,
        serving_size, serving_size_unit, food_nutrients_json,
        nutritional_data.get("calories"),
        nutritional_data.get("protein_g"),
        nutritional_data.get("fat_g"),
        nutritional_data.get("saturated_fat_g"),
        nutritional_data.get("trans_fat_g"),
        nutritional_data.get("carbohydrates_g"),
        nutritional_data.get("fiber_g"),
        nutritional_data.get("sugar_g"),
        nutritional_data.get("vitamin_a_iu"),
        nutritional_data.get("vitamin_c_mg"),
        nutritional_data.get("vitamin_d_iu"),
        nutritional_data.get("vitamin_e_mg"),
        nutritional_data.get("vitamin_k_mcg"),
        nutritional_data.get("thiamin_mg"),
        nutritional_data.get("riboflavin_mg"),
        nutritional_data.get("niacin_mg"),
        nutritional_data.get("vitamin_b6_mg"),
        nutritional_data.get("folate_mcg"),
        nutritional_data.get("vitamin_b12_mcg"),
        nutritional_data.get("calcium_mg"),
        nutritional_data.get("iron_mg"),
        nutritional_data.get("magnesium_mg"),
        nutritional_data.get("phosphorus_mg"),
        nutritional_data.get("potassium_mg"),
        nutritional_data.get("sodium_mg"),
        nutritional_data.get("zinc_mg"),
        nutritional_data.get("copper_mg"),
        nutritional_data.get("manganese_mg"),
        nutritional_data.get("selenium_mcg"),
        nutritional_data.get("cholesterol_mg"),
        nutritional_data.get("caffeine_mg"),
        api_response_json
    ]
    
    # Count columns and values for verification
    # Note: last_updated has DEFAULT CURRENT_TIMESTAMP, so we don't include it
    column_names = [
        'id', 'ingredient_name', 'category', 'subcategory', 'fdc_id', 'data_type',
        'description', 'brand_owner', 'gtin_upc', 'household_serving_full_text',
        'serving_size', 'serving_size_unit', 'food_nutrients',
        'calories', 'protein_g', 'fat_g', 'saturated_fat_g', 'trans_fat_g',
        'carbohydrates_g', 'fiber_g', 'sugar_g',
        'vitamin_a_iu', 'vitamin_c_mg', 'vitamin_d_iu', 'vitamin_e_mg', 'vitamin_k_mcg',
        'thiamin_mg', 'riboflavin_mg', 'niacin_mg', 'vitamin_b6_mg', 'folate_mcg', 'vitamin_b12_mcg',
        'calcium_mg', 'iron_mg', 'magnesium_mg', 'phosphorus_mg', 'potassium_mg', 'sodium_mg',
        'zinc_mg', 'copper_mg', 'manganese_mg', 'selenium_mcg',
        'cholesterol_mg', 'caffeine_mg',
        'api_response'
    ]
    
    # Verify we have exactly 45 columns (excluding last_updated which has a default)
    expected_column_count = 45
    if len(column_names) != expected_column_count:
        error_msg = f"INTERNAL ERROR: Column list has {len(column_names)} items, expected {expected_column_count}"
        logging.error(error_msg)
        raise ValueError(error_msg)
    
    # Convert to tuple and verify count
    values_tuple = tuple(values_list)
    
    # Log value types for debugging
    logging.debug(f"Value types check - Total items: {len(values_tuple)}")
    for idx, (col_name, val) in enumerate(zip(column_names, values_tuple)):
        val_type = type(val).__name__
        val_repr = str(val)[:30] if val is not None else "None"
        if len(str(val)) > 30:
            val_repr += "..."
        logging.debug(f"  [{idx+1}] {col_name}: {val_type} = {val_repr}")
    
    # Create placeholders string
    placeholders = ', '.join(['?'] * len(column_names))
    
    # Log detailed information
    logging.info(f"Preparing to insert ingredient '{ingredient_name}' (ID: {ingredient_id})")
    logging.debug(f"Column count: {len(column_names)}, Values count: {len(values_tuple)}")
    
    # Verify counts match BEFORE attempting insert
    if len(column_names) != len(values_tuple):
        error_msg = f"MISMATCH: {len(column_names)} columns but {len(values_tuple)} values for ingredient '{ingredient_name}'"
        logging.error(error_msg)
        logging.error(f"Column names ({len(column_names)}): {column_names}")
        logging.error(f"Values ({len(values_tuple)}):")
        for idx, val in enumerate(values_tuple):
            val_repr = repr(val)[:100]  # Limit length
            logging.error(f"  [{idx+1}] {val_repr}")
        raise ValueError(error_msg)
    
    # Log a sample of values for debugging
    logging.debug(f"Sample values - ID: {ingredient_id}, Name: {ingredient_name}, FDC ID: {fdc_id}, Has food data: {food_data is not None}")
    
    try:
        # Check if ingredient already exists by name (and optionally fdc_id)
        cursor.execute('''
            SELECT id FROM ingredients 
            WHERE ingredient_name = ? AND (fdc_id = ? OR (fdc_id IS NULL AND ? IS NULL))
        ''', (ingredient_name, fdc_id, fdc_id))
        existing_row = cursor.fetchone()
        
        if existing_row:
            # Ingredient exists - UPDATE it, preserving the existing ID
            existing_id = existing_row[0]
            logging.info(f"Ingredient '{ingredient_name}' already exists with ID {existing_id}, updating...")
            
            # Build UPDATE statement (exclude 'id' from update)
            update_columns = [col for col in column_names if col != 'id']
            update_placeholders = ', '.join([f'{col} = ?' for col in update_columns])
            update_values = [val for col, val in zip(column_names, values_tuple) if col != 'id']
            update_values.append(existing_id)  # Add ID for WHERE clause
            
            update_sql = f'''
                UPDATE ingredients 
                SET {update_placeholders}
                WHERE id = ?
            '''
            
            cursor.execute(update_sql, update_values)
            conn.commit()
            logging.info(f"Updated ingredient '{ingredient_name}' (ID: {existing_id})")
        else:
            # Ingredient doesn't exist - INSERT it
            # Check if the CSV ID is available, if not find next available ID
            if ingredient_id_int is None:
                # No ID provided, find next available
                cursor.execute('SELECT MAX(id) FROM ingredients')
                max_id_result = cursor.fetchone()[0]
                next_id = (max_id_result + 1) if max_id_result else 1
                logging.info(f"No ID provided, using next available ID: {next_id}")
                values_list[0] = next_id
                values_tuple = tuple(values_list)
            else:
                cursor.execute('SELECT id FROM ingredients WHERE id = ?', (ingredient_id_int,))
                if cursor.fetchone():
                    # ID is taken, find next available
                    cursor.execute('SELECT MAX(id) FROM ingredients')
                    max_id_result = cursor.fetchone()[0]
                    next_id = (max_id_result + 1) if max_id_result else 1
                    logging.info(f"ID {ingredient_id_int} is taken, using next available ID: {next_id}")
                    # Update the values tuple with the new ID
                    values_list[0] = next_id
                    values_tuple = tuple(values_list)
                else:
                    # Use the CSV ID
                    logging.debug(f"Using CSV ID: {ingredient_id_int}")
            
            # Build INSERT statement
            sql = f'''
                INSERT INTO ingredients (
                    {', '.join(column_names)}
                ) VALUES ({placeholders})
            '''
            
            logging.debug(f"SQL statement prepared with {len(column_names)} columns and {len(values_tuple)} values")
            
            # Insert ingredient
            cursor.execute(sql, values_tuple)
            conn.commit()
            inserted_id = values_tuple[0]
            logging.info(f"Inserted new ingredient '{ingredient_name}' (ID: {inserted_id})")
    except sqlite3.OperationalError as e:
        error_msg = f"SQL OperationalError inserting '{ingredient_name}': {str(e)}"
        logging.error(error_msg)
        logging.error(f"Column count: {len(column_names)}, Values count: {len(values_tuple)}")
        logging.error(f"Column names: {column_names}")
        logging.error(f"All values: {values_tuple}")
        # Log each value with its corresponding column name
        for idx, (col, val) in enumerate(zip(column_names, values_tuple)):
            val_str = str(val)[:50] if val is not None else "None"
            if len(str(val)) > 50:
                val_str += "..."
            logging.error(f"  [{idx+1}] {col} = {val_str}")
        raise
    except sqlite3.IntegrityError as e:
        logging.error(f"SQL IntegrityError inserting '{ingredient_name}': {str(e)}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error inserting '{ingredient_name}': {type(e).__name__} - {str(e)}", exc_info=True)
        raise

def process_csv_file(csv_path: str, db_path: str, api_key: str):
    """
    Process CSV file, query API, and populate database.
    
    Args:
        csv_path: Path to input CSV file
        db_path: Path to SQLite database file
        api_key: USDA API key
    """
    # Create database schema
    create_database_schema(db_path)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    # Read CSV file
    try:
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            # Read first few lines to understand format
            lines = []
            for i in range(3):
                line = csvfile.readline()
                if line:
                    lines.append(line.strip())
                else:
                    break
            csvfile.seek(0)  # Reset to beginning
            
            first_line = lines[0] if lines else ""
            second_line = lines[1] if len(lines) > 1 else ""
            
            logging.info(f"First line of CSV: '{first_line}'")
            logging.info(f"Second line of CSV: '{second_line}'")
            
            # Check if first line looks like headers (contains common CSV header words)
            has_headers = any(keyword in first_line.lower() for keyword in ['id', 'ingredient', 'name', 'category', 'subcategory'])
            
            # Check if it's a simple list (just ingredient names, one per line, no commas)
            is_simple_list = ',' not in first_line and first_line and not has_headers
            
            rows = []
            if has_headers:
                reader = csv.DictReader(csvfile)
                logging.info(f"CSV file has headers: {first_line}")
                rows = list(reader)
            elif is_simple_list:
                # Simple list format - just ingredient names, one per line
                logging.info("CSV appears to be a simple list format (one ingredient per line)")
                for i, line in enumerate(csvfile, 1):
                    ingredient_name = line.strip()
                    if ingredient_name:  # Skip empty lines
                        rows.append({
                            'id': str(i),
                            'ingredient': ingredient_name,
                            'category': '',
                            'subcategory': ''
                        })
                logging.info(f"Parsed {len(rows)} ingredients from simple list format")
            else:
                # No headers - assume format: id,ingredient,category,subcategory
                logging.warning(f"CSV file appears to have no headers. First line: '{first_line}'")
                logging.info("Assuming format: id,ingredient,category,subcategory")
                reader = csv.DictReader(csvfile, fieldnames=['id', 'ingredient', 'category', 'subcategory'])
                rows = list(reader)
        
        # Log column names detected
        if rows:
            detected_columns = list(rows[0].keys())
            logging.info(f"Detected CSV columns: {detected_columns}")
            logging.info(f"Sample first row: {rows[0]}")
        else:
            logging.error("No rows found in CSV file!")
            return
            
        logging.info(f"Found {len(rows)} rows in CSV file")
        
        # Process each ingredient
        for i, row in enumerate(rows, 1):
            # Try multiple possible column names for ingredient
            ingredient_name = None
            possible_keys = ['ingredient', 'name', 'ingredient_name', 'food', 'item']
            
            for key in possible_keys:
                if key in row:
                    ingredient_name = row.get(key, "").strip()
                    if ingredient_name:
                        break
            
            # If still not found, try to get any non-empty value from first few columns
            if not ingredient_name:
                for key, value in list(row.items())[:4]:  # Check first 4 columns
                    if value and str(value).strip():
                        # Skip if it looks like an ID (numeric only)
                        if not str(value).strip().isdigit():
                            ingredient_name = str(value).strip()
                            logging.info(f"Row {i}: Using '{key}' column as ingredient name: '{ingredient_name}'")
                            break
            
            # Log detailed row information for debugging
            if not ingredient_name:
                logging.warning(f"Row {i}: Empty ingredient name. Row data: {row}")
                logging.debug(f"Row {i} keys: {list(row.keys())}, values: {list(row.values())}")
                continue
            
            logging.info(f"Processing {i}/{len(rows)}: {ingredient_name}")
            
            # Search for ingredient
            food_data = search_food(ingredient_name, api_key)
            
            # If found, get detailed information
            if food_data and food_data.get("fdcId"):
                detailed_data = get_food_details(food_data["fdcId"], api_key)
                if detailed_data:
                    food_data = detailed_data
            
            # Insert into database
            try:
                insert_ingredient(conn, row, food_data)
                logging.info(f"[SUCCESS] Processed {i}/{len(rows)}: {ingredient_name}")
            except Exception as e:
                logging.error(f"[FAILED] Failed to insert ingredient '{ingredient_name}' (row {i}): {type(e).__name__} - {str(e)}")
                logging.error(f"Exception details: {repr(e)}", exc_info=True)
                # Continue processing other ingredients even if one fails
                continue
            
            # Rate limiting delay
            if i < len(rows):
                time.sleep(REQUEST_DELAY)
        
        # Count successful inserts
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM ingredients")
        total_in_db = cursor.fetchone()[0]
        logging.info(f"Successfully processed {len(rows)} rows. Total ingredients in database: {total_in_db}")
        
    except FileNotFoundError:
        logging.error(f"CSV file not found: {csv_path}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"Error processing CSV file: {type(e).__name__} - {str(e)}")
        raise
    finally:
        conn.close()

def main():
    """Main function to run the ingredient enricher."""
    print("=" * 60)
    print("Ingredient Enricher - USDA FoodData Central API")
    print("=" * 60)
    print(f"\nInput CSV: {INPUT_CSV}")
    print(f"Database: {DATABASE_FILE}")
    print(f"API Key: {'DEMO_KEY (for testing)' if API_KEY == 'DEMO_KEY' else 'Configured'}")
    print("\nNote: Using DEMO_KEY has lower rate limits.")
    print("Get your API key at: https://api.data.gov/signup/")
    print("=" * 60)
    
    # Check if API key is set
    if not API_KEY or API_KEY == "DEMO_KEY":
        response = input("\nUsing DEMO_KEY. Continue? (y/n): ").strip().lower()
        if response != 'y':
            print("Please set your API_KEY in the script configuration.")
            return
    
    try:
        process_csv_file(INPUT_CSV, DATABASE_FILE, API_KEY)
        print(f"\n✓ Successfully enriched ingredients and saved to {DATABASE_FILE}")
        print(f"✓ Check ingredient_enricher.log for detailed logs")
    except Exception as e:
        logging.error(f"Failed to process ingredients: {str(e)}")
        print(f"\n✗ Error: {str(e)}")
        print("Check ingredient_enricher.log for details.")
        sys.exit(1)

if __name__ == "__main__":
    main()
