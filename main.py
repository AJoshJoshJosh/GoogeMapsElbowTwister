#!/usr/bin/env python3
"""Find high-rated restaurants using Google Places Nearby Search API."""

import sys
import time
import argparse
from typing import List, Dict, Tuple, Optional
import requests
import math

# Configuration constants
DEFAULT_MIN_RATING = 4.7
DEFAULT_MIN_REVIEWS = 300
DEFAULT_RADIUS_MILES = 20
MAX_DISPLAY = 20
NEARBY_API_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"

# Strict restaurant types to include
RESTAURANT_TYPES = {
    "restaurant",
    "meal_delivery", 
    "meal_takeaway",
}

# Types to explicitly exclude
EXCLUDE_TYPES = {
    "lodging",
    "hotel",
    "motel",
    "gas_station",
    "grocery_or_supermarket",
    "convenience_store",
}

# City coordinates
CITY_COORDINATES = {
    "seattle": (47.6062, -122.3321),
    "san francisco": (37.7749, -122.4194),
    "los angeles": (34.0522, -118.2437),
    "new york": (40.7128, -74.0060),
    "chicago": (41.8781, -87.6298),
    "austin": (30.2672, -97.7431),
    "portland": (45.5152, -122.6784),
    "miami": (25.7617, -80.1918),
    "boston": (42.3601, -71.0589),
    "denver": (39.7392, -104.9903),
    "atlanta": (33.7490, -84.3880),
    "dallas": (32.7767, -96.7970),
    "houston": (29.7604, -95.3698),
    "philadelphia": (39.9526, -75.1652),
    "phoenix": (33.4484, -112.0740),
    "san diego": (32.7157, -117.1611),
    "washington dc": (38.9072, -77.0369),
    "las vegas": (36.1699, -115.1398),
    "nashville": (36.1627, -86.7816),
    "new orleans": (29.9511, -90.0715),
}


def get_location(city: Optional[str], coords: Optional[str]) -> Tuple[float, float, str]:
    """
    Get coordinates from city name or coordinate string.
    
    Args:
        city: City name
        coords: Comma-separated lat,lng string
        
    Returns:
        Tuple of (latitude, longitude, location_name)
    """
    if coords:
        try:
            parts = coords.split(',')
            if len(parts) != 2:
                raise ValueError("Coordinates must be in format: lat,lng")
            lat = float(parts[0].strip())
            lng = float(parts[1].strip())
            if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                raise ValueError("Invalid coordinate range")
            return lat, lng, f"({lat:.4f}, {lng:.4f})"
        except ValueError as e:
            print(f"Error parsing coordinates: {e}")
            sys.exit(1)
    
    elif city:
        city_lower = city.lower()
        if city_lower not in CITY_COORDINATES:
            print(f"Error: City '{city}' not found in database.")
            print(f"Available cities: {', '.join(sorted(CITY_COORDINATES.keys()))}")
            print(f"\nOr use --coords with latitude,longitude (e.g., --coords 47.6062,-122.3321)")
            sys.exit(1)
        lat, lng = CITY_COORDINATES[city_lower]
        return lat, lng, city.title()
    
    else:
        # Default to Seattle if nothing specified
        lat, lng = CITY_COORDINATES["seattle"]
        return lat, lng, "Seattle"


def miles_to_meters(miles: float) -> int:
    """Convert miles to meters."""
    return int(miles * 1609.34)


def is_true_restaurant(place: Dict) -> bool:
    """Check if a place is truly a restaurant."""
    place_types = set(place.get("types", []))
    
    # Exclude if it has any excluded types
    if place_types.intersection(EXCLUDE_TYPES):
        return False
    
    # Include only if it has restaurant-related types
    if place_types.intersection(RESTAURANT_TYPES):
        return True
    
    # Fallback: check name for restaurant keywords
    name_lower = place.get("name", "").lower()
    restaurant_keywords = ["restaurant", "grill", "kitchen", "bistro", "cafe", 
                          "diner", "eatery", "steakhouse", "pizzeria", "sushi"]
    return any(keyword in name_lower for keyword in restaurant_keywords)


def fetch_all_restaurants(
    lat: float, 
    lng: float, 
    radius_miles: float, 
    api_key: str
) -> List[Dict]:
    """Fetch all restaurant pages, filtering out non-restaurants."""
    all_restaurants = []
    next_page_token = None
    page_count = 0
    radius_meters = miles_to_meters(radius_miles)
    
    if radius_meters > 50000:
        radius_meters = 50000
        print(f"  Note: Radius capped at 31 miles (API limit)")
    
    while page_count < 3:
        params = {
            "key": api_key,
            "type": "restaurant",
            "keyword": "restaurant"
        }
        
        if page_count == 0:
            params["location"] = f"{lat},{lng}"
            params["radius"] = radius_meters
        else:
            params["pagetoken"] = next_page_token
            print(f"  Fetching page {page_count + 1}/3...")
            time.sleep(2)
        
        try:
            response = requests.get(NEARBY_API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"Error: API request failed: {e}")
            break
        
        if data.get("status") not in ["OK", "ZERO_RESULTS"]:
            print(f"Warning: API returned status '{data.get('status')}'")
            if data.get("error_message"):
                print(f"Details: {data['error_message']}")
            break
        
        results = data.get("results", [])
        
        # Filter for true restaurants only
        true_restaurants = [r for r in results if is_true_restaurant(r)]
        
        if len(true_restaurants) < len(results):
            filtered_out = len(results) - len(true_restaurants)
            print(f"    (Filtered out {filtered_out} non-restaurant results)")
        
        all_restaurants.extend(true_restaurants)
        
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break
            
        page_count += 1
    
    return all_restaurants


def calculate_score(restaurant: Dict) -> float:
    """Calculate composite score."""
    rating = restaurant.get("rating", 0)
    reviews = restaurant.get("user_ratings_total", 1)
    return (rating ** 2) * math.log10(max(reviews, 1))


def filter_and_rank_restaurants(
    restaurants: List[Dict], 
    min_rating: float, 
    min_reviews: int
) -> List[Dict]:
    """Filter and rank restaurants."""
    filtered = [
        r for r in restaurants 
        if r.get("rating", 0) >= min_rating 
        and r.get("user_ratings_total", 0) >= min_reviews
    ]
    return sorted(filtered, key=calculate_score, reverse=True)


def display_results(
    restaurants: List[Dict], 
    location_name: str,
    radius_miles: float,
    min_rating: float, 
    min_reviews: int,
    total_fetched: int,
    show_types: bool = False
) -> None:
    """Display restaurant search results."""
    print(f"\nRestaurants near {location_name}")
    print(f"Search radius: {radius_miles} miles")
    print(f"Filters: Rating >= {min_rating}, Reviews >= {min_reviews}")
    print(f"Fetched: {total_fetched} | Matched: {len(restaurants)}")
    print("-" * 70)
    
    if not restaurants:
        print("\nNo restaurants found matching your criteria.")
        print("Try adjusting your filters:")
        print(f"  --reviews {min_reviews // 2}")
        print(f"  --rating {max(min_rating - 0.2, 3.0):.1f}")
        print(f"  --radius {min(radius_miles + 10, 31)}")
        return
    
    print(f"\nTop {min(len(restaurants), MAX_DISPLAY)} restaurants:\n")
    
    for idx, restaurant in enumerate(restaurants[:MAX_DISPLAY], 1):
        name = restaurant.get("name", "Unknown")
        rating = restaurant.get("rating", 0)
        review_count = restaurant.get("user_ratings_total", 0)
        address = restaurant.get("vicinity", "Address not available")
        
        print(f"{idx:2}. {name}")
        print(f"    Rating: {rating} | Reviews: {review_count:,}")
        
        if show_types:
            types = restaurant.get("types", [])
            relevant_types = [t for t in types if t not in ["point_of_interest", "establishment", "food"]]
            if relevant_types:
                print(f"    Type: {', '.join(relevant_types[:3])}")
        
        if len(address) > 60:
            address = address[:57] + "..."
        print(f"    Location: {address}")
        print()


def parse_arguments():
    """Parse command line arguments with flexibility."""
    parser = argparse.ArgumentParser(
        description="Find high-rated restaurants using Google Places API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using city name
  python3 restaurants.py YOUR_API_KEY --city seattle --radius 10 --rating 4.5

  # Using coordinates
  python3 restaurants.py YOUR_API_KEY --coords 47.6062,-122.3321 --reviews 500

  # Arguments in any order
  python3 restaurants.py --rating 4.8 --city austin YOUR_API_KEY --radius 15

  # Minimal usage (API key only, uses Seattle defaults)
  python3 restaurants.py YOUR_API_KEY
  
Available cities: atlanta, austin, boston, chicago, dallas, denver, houston,
las vegas, los angeles, miami, nashville, new orleans, new york, philadelphia,
phoenix, portland, san diego, san francisco, seattle, washington dc
        """
    )
    
    # Required API key (but can be anywhere in arguments)
    parser.add_argument("api_key", 
                       help="Google Places API key")
    
    # Location options (mutually exclusive)
    location = parser.add_mutually_exclusive_group()
    location.add_argument("--city", "-c",
                         help="City name (e.g., seattle, 'san francisco')")
    location.add_argument("--coords", "--coordinates", "--latlong",
                         help="Coordinates as lat,lng (e.g., 47.6062,-122.3321)")
    
    # Filter options
    parser.add_argument("--radius", "-r",
                       type=float,
                       default=DEFAULT_RADIUS_MILES,
                       help=f"Search radius in miles (default: {DEFAULT_RADIUS_MILES})")
    
    parser.add_argument("--rating", "--min-rating",
                       type=float,
                       default=DEFAULT_MIN_RATING,
                       help=f"Minimum rating 0-5 (default: {DEFAULT_MIN_RATING})")
    
    parser.add_argument("--reviews", "--min-reviews",
                       type=int,
                       default=DEFAULT_MIN_REVIEWS,
                       help=f"Minimum review count (default: {DEFAULT_MIN_REVIEWS})")
    
    # Display options
    parser.add_argument("--show-types", "-t",
                       action="store_true",
                       help="Show place types in results")
    
    parser.add_argument("--limit",
                       type=int,
                       default=MAX_DISPLAY,
                       help=f"Maximum results to display (default: {MAX_DISPLAY})")
    
    args = parser.parse_args()
    
    # Validate arguments
    if not 0.1 <= args.radius <= 31:
        parser.error("Radius must be between 0.1 and 31 miles")
    
    if not 0 <= args.rating <= 5:
        parser.error("Rating must be between 0 and 5")
    
    if args.reviews < 0:
        parser.error("Review count must be non-negative")
    
    return args


def main() -> None:
    """Main execution function."""
    args = parse_arguments()
    
    # Get location (from city or coordinates)
    lat, lng, location_name = get_location(args.city, args.coords)
    print(f"Location: {location_name} ({lat:.4f}, {lng:.4f})")
    
    # Search for restaurants
    print(f"Searching restaurants within {args.radius} miles...")
    print("  Fetching page 1/3...")
    all_restaurants = fetch_all_restaurants(lat, lng, args.radius, args.api_key)
    print(f"  Retrieved {len(all_restaurants)} true restaurants")
    
    # Filter and rank
    filtered_restaurants = filter_and_rank_restaurants(
        all_restaurants, args.rating, args.reviews
    )
    
    # Display results
    global MAX_DISPLAY
    MAX_DISPLAY = args.limit
    display_results(
        filtered_restaurants, location_name, args.radius, 
        args.rating, args.reviews, len(all_restaurants),
        args.show_types
    )


if __name__ == "__main__":
    main()
