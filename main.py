import requests
import time
import json

def get_anime_with_tvdb_ids():
    """
    Fetches current season anime from Jikan, filters them, and finds their
    corresponding TheTVDB IDs from an external mapping file.
    """
    # --- Step 1: Fetch and prepare the ID mapping data from GitHub ---
    # This is a large file, so we fetch it only once.
    try:
        print("Fetching anime ID mapping from GitHub...")
        response_github = requests.get('https://cdn.jsdelivr.net/gh/Fribb/anime-lists@master/anime-list-full.json')
        # Raise an HTTPError if the HTTP request returned an unsuccessful status code
        response_github.raise_for_status()
        github_data = response_github.json()

        # For much faster lookups, create a dictionary mapping mal_id to the item.
        # This is more efficient than searching the list every time.
        github_map = {
            item['mal_id']: item 
            for item in github_data 
            if 'mal_id' in item and 'thetvdb_id' in item and item['thetvdb_id']
        }
        print("Successfully created ID mapping.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching anime list from GitHub: {e}")
        return [] # Return an empty list on failure
    except ValueError: # Catches JSON decoding errors
        print("Error decoding JSON from GitHub response.")
        return []

    # --- Step 2: Paginate through Jikan API results ---
    has_next_page = True
    page = 1
    result = []

    while has_next_page:
        try:
            # Fetch data from the Jikan API for the current season
            print(f"Fetching page {page} from Jikan API...")
            api_url = f"https://api.jikan.moe/v4/seasons/now?page={page}"
            response_jikan = requests.get(api_url)
            response_jikan.raise_for_status()

            jikan_data = response_jikan.json()
            
            # --- Step 3: Filter the data from Jikan ---
            
            # Filter to keep only TV, OVA, or ONA types
            filtered_by_type = (
                item for item in jikan_data.get('data', []) 
                if item.get('type') in {'TV', 'OVA', 'ONA'}
            )

            # Filter out adult content
            filtered_by_rating = (
                item for item in filtered_by_type
                if item.get('rating') != 'Rx - Hentai'
            )

            # Further filter by score > 7.0 or members > 80,000
            filtered_by_score = (
                item for item in filtered_by_rating
                if (item.get('score') or 0) > 7.0 or (item.get('members') or 0) > 80000
            )

            # --- Step 4: Match with GitHub data and collect results ---
            for item in filtered_by_score:
                mal_id = item.get('mal_id')
                # Use the pre-built map for a fast lookup
                matched_item = github_map.get(mal_id)

                if matched_item:
                    # If a match is found, add the tvdb_id to the result list
                    result.append({'tvdbId': matched_item['thetvdb_id']})

            # Update pagination status and page number for the next loop
            has_next_page = jikan_data.get('pagination', {}).get('has_next_page', False)
            page += 1

            # Be a good API citizen and wait a bit before the next request
            if has_next_page:
                time.sleep(1)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching data from Jikan API: {e}")
            # Stop pagination on error
            break
        except ValueError:
            print("Error decoding JSON from Jikan API response.")
            break
            
    return result

if __name__ == '__main__':
    # Example of how to run the function and print the results
    final_results = get_anime_with_tvdb_ids()
    print("\n--- Final Results ---")
    if final_results:
        print(f"Found {len(final_results)} matching anime.")
        output_filename = 'anime_tvdb_ids.json'
        try:
            # Write the results to a JSON file with pretty printing
            with open(output_filename, 'w', encoding='utf-8') as f:
                json.dump(final_results, f, indent=4)
            print(f"Successfully saved results to {output_filename}")
        except IOError as e:
            print(f"Error writing to file {output_filename}: {e}")

    else:
        print("No results found or an error occurred.")
