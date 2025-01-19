export const generateMusicPrompt = (genre, mood, isTopSongs = true) => {
  const topSongsClause = isTopSongs 
    ? "Focus on well-known, popular, and top-charting songs (at least 80% of suggestions should be hits or popular tracks). "
    : "";

  return `Suggest 10 ${genre} songs that evoke a ${mood} mood. ${topSongsClause}` +
    'For each song provide the following JSON structure: ' +
    '{"title": "song name", "artist": "artist name", "year": "release year", "is_top_song": boolean}. ' +
    'Return only a JSON array with these objects.';
}; 