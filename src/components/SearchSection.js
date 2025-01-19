import React, { useState } from 'react';
import { generateMusicPrompt } from '../utils/promptTemplates';
import { fetchSongRecommendations } from '../services/songRecommendations';

function SearchSection({ onSearch }) {
  const [searchType, setSearchType] = useState('top');
  const [isLoading, setIsLoading] = useState(false);
  const [selectedGenre, setSelectedGenre] = useState('');
  const [selectedMood, setSelectedMood] = useState('');

  const handleSearch = async () => {
    setIsLoading(true);
    try {
      const prompt = generateMusicPrompt(
        selectedGenre, 
        selectedMood,
        searchType === 'top'
      );
      
      const response = await fetchSongRecommendations(prompt);
      const songs = response.map(song => ({
        ...song,
        is_top_song: song.is_top_song || false // Ensure the field exists
      }));
      
      onSearch(songs);
    } catch (error) {
      console.error('Error fetching songs:', error);
      // Handle error appropriately
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="search-section">
      <div className="search-options">
        <label>
          <input
            type="radio"
            value="top"
            checked={searchType === 'top'}
            onChange={(e) => setSearchType(e.target.value)}
          />
          Top Songs
        </label>
      </div>
    </div>
  );
}

export default SearchSection; 