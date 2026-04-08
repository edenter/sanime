import aiohttp
import asyncio
import json
import time

async def fetch_json(session, url, retries=3):
    for i in range(retries):
        try:
            async with session.get(url) as response:
                if response.status == 429:
                    print(f"Rate limited on {url}. Waiting {5 * (i + 1)} seconds...")
                    await asyncio.sleep(5 * (i + 1))
                    continue
                response.raise_for_status()
                return await response.json()
        except Exception as e:
            print(f"Error fetching {url}: {e}")
            if i == retries - 1:
                return None
            await asyncio.sleep(2)
    return None

async def get_anime_with_tvdb_ids():
    """
    Fetches current season anime from Jikan, filters them, and finds their
    corresponding TheTVDB IDs from an external mapping file.
    """
    timeout = aiohttp.ClientTimeout(total=30, connect=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        # Fetch ID mapping and first Jikan page concurrently
        print("Fetching anime ID mapping and first page concurrently...")
        github_data, first_page = await asyncio.gather(
            fetch_json(session, 'https://cdn.jsdelivr.net/gh/Fribb/anime-lists@master/anime-list-full.json'),
            fetch_json(session, 'https://api.jikan.moe/v4/seasons/now?page=1')
        )

        if not github_data:
            print("Failed to fetch ID mapping.")
            return []

        github_map = {item['mal_id']: item['tvdb_id'] for item in github_data if item.get('mal_id') and item.get('tvdb_id') is not None}
        del github_data
        print(f"Successfully created ID mapping for {len(github_map)} anime.")

        if not first_page:
            return []

        jikan_pages = [first_page]
        raw_last_page = first_page.get('pagination', {}).get('last_visible_page', 1)
        last_page = min(raw_last_page, 20)
        if raw_last_page > 20:
            print(f"Warning: API reports {raw_last_page} pages, capping at 20.")

        if last_page > 1:
            print(f"Fetching remaining {last_page - 1} pages sequentially (respecting 3 req/sec limit)...")
            
            for page in range(2, last_page + 1):
                await asyncio.sleep(0.5) # 0.5s delay guarantees < 3 requests per second
                page_data = await fetch_json(session, f"https://api.jikan.moe/v4/seasons/now?page={page}")
                if page_data:
                    jikan_pages.append(page_data)

        result = []
        for page_data in jikan_pages:
            for item in page_data.get('data', []):
                if item.get('type') not in {'TV', 'OVA', 'ONA'}:
                    continue
                if item.get('rating') == 'Rx - Hentai':
                    continue
                if (item.get('score') or 0) > 7.0 or (item.get('members') or 0) > 80000:
                    mal_id = item.get('mal_id')
                    matched_tvdb_id = github_map.get(mal_id)
                    if matched_tvdb_id:
                        result.append({'tvdbId': matched_tvdb_id})

        return result

if __name__ == '__main__':
    # Setup asyncio for Windows compatibility if needed
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    start_time = time.monotonic()
    final_results = asyncio.run(get_anime_with_tvdb_ids())
    print(f"\nCompleted in {time.monotonic() - start_time:.2f} seconds")
    
    print("\n--- Final Results ---")
    print(f"Found {len(final_results)} matching anime.")
    output_filename = 'anime_tvdb_ids.json'
    try:
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, indent=4)
        print(f"Successfully saved results to {output_filename}")
    except IOError as e:
        print(f"Error writing to file {output_filename}: {e}")
