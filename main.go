package main

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// FribbEntry represents one entry from the Fribb anime-list-full.json
type FribbEntry struct {
	MalID  *int `json:"mal_id"`
	TvdbID *int `json:"tvdb_id"`
}

// JikanResponse represents the top-level Jikan API response
type JikanResponse struct {
	Pagination struct {
		HasNextPage     bool `json:"has_next_page"`
		LastVisiblePage int  `json:"last_visible_page"`
	} `json:"pagination"`
	Data []JikanAnime `json:"data"`
}

// JikanAnime represents a single anime entry from Jikan
type JikanAnime struct {
	MalID   int     `json:"mal_id"`
	Type    string  `json:"type"`
	Rating  string  `json:"rating"`
	Score   float64 `json:"score"`
	Members int     `json:"members"`
}

// OutputEntry is what gets written to anime_tvdb_ids.json
type OutputEntry struct {
	TvdbID int `json:"tvdbId"`
}

func fetchJSON(url string, target interface{}) error {
	const retries = 3
	for i := 0; i < retries; i++ {
		resp, err := http.Get(url)
		if err != nil {
			fmt.Printf("Error fetching %s: %v\n", url, err)
			if i < retries-1 {
				time.Sleep(2 * time.Second)
			}
			continue
		}
		body, err := io.ReadAll(resp.Body)
		resp.Body.Close()

		if resp.StatusCode == 429 {
			wait := time.Duration(5*(i+1)) * time.Second
			fmt.Printf("Rate limited on %s. Waiting %v...\n", url, wait)
			time.Sleep(wait)
			continue
		}
		if resp.StatusCode != 200 {
			fmt.Printf("HTTP %d on %s\n", resp.StatusCode, url)
			if i < retries-1 {
				time.Sleep(2 * time.Second)
			}
			continue
		}
		if err != nil {
			fmt.Printf("Error reading body from %s: %v\n", url, err)
			if i < retries-1 {
				time.Sleep(2 * time.Second)
			}
			continue
		}
		return json.Unmarshal(body, target)
	}
	return fmt.Errorf("failed to fetch %s after %d retries", url, retries)
}

func main() {
	start := time.Now()

	// Step 1: Fetch Fribb mapping
	fmt.Println("Fetching anime ID mapping from GitHub...")
	var fribbData []FribbEntry
	if err := fetchJSON("https://cdn.jsdelivr.net/gh/Fribb/anime-lists@master/anime-list-full.json", &fribbData); err != nil {
		fmt.Printf("Failed to fetch ID mapping: %v\n", err)
		os.Exit(1)
	}

	githubMap := make(map[int]int)
	for _, entry := range fribbData {
		if entry.MalID != nil && entry.TvdbID != nil {
			githubMap[*entry.MalID] = *entry.TvdbID
		}
	}
	fmt.Printf("Successfully created ID mapping for %d anime.\n", len(githubMap))

	// Step 2: Fetch first page from Jikan
	fmt.Println("Fetching page 1 from Jikan API...")
	var firstPage JikanResponse
	if err := fetchJSON("https://api.jikan.moe/v4/seasons/now?page=1", &firstPage); err != nil {
		fmt.Printf("Failed to fetch first page: %v\n", err)
		os.Exit(1)
	}

	pages := []JikanResponse{firstPage}
	lastPage := firstPage.Pagination.LastVisiblePage

	// Fetch remaining pages sequentially
	if firstPage.Pagination.HasNextPage && lastPage > 1 {
		fmt.Printf("Fetching remaining %d pages sequentially (respecting 3 req/sec limit)...\n", lastPage-1)
		for page := 2; page <= lastPage; page++ {
			time.Sleep(500 * time.Millisecond)
			var pageData JikanResponse
			url := fmt.Sprintf("https://api.jikan.moe/v4/seasons/now?page=%d", page)
			if err := fetchJSON(url, &pageData); err != nil {
				fmt.Printf("Warning: failed to fetch page %d: %v\n", page, err)
				continue
			}
			pages = append(pages, pageData)
		}
	}

	// Step 3: Filter and map
	var result []OutputEntry
	for _, page := range pages {
		for _, anime := range page.Data {
			if anime.Type != "TV" && anime.Type != "OVA" && anime.Type != "ONA" {
				continue
			}
			if anime.Rating == "Rx - Hentai" {
				continue
			}
			if anime.Score > 7.0 || anime.Members > 80000 {
				if tvdbID, ok := githubMap[anime.MalID]; ok {
					result = append(result, OutputEntry{TvdbID: tvdbID})
				}
			}
		}
	}

	fmt.Printf("\nCompleted in %.2f seconds\n", time.Since(start).Seconds())
	fmt.Printf("\n--- Final Results ---\n")
	fmt.Printf("Found %d matching anime.\n", len(result))

	// Ensure we always write a valid JSON array
	if result == nil {
		result = []OutputEntry{}
	}

	output, err := json.MarshalIndent(result, "", "    ")
	if err != nil {
		fmt.Printf("Error marshalling JSON: %v\n", err)
		os.Exit(1)
	}

	if err := os.WriteFile("anime_tvdb_ids.json", output, 0644); err != nil {
		fmt.Printf("Error writing to file: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("Successfully saved results to anime_tvdb_ids.json")
}
