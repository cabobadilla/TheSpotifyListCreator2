export const generateMusicPrompt = (genre, mood) => {
  return `Suggest 10 ${genre} songs that evoke a ${mood} mood. ` +
    'For each song provide the following JSON structure: ' +
    '{"title": "song name", "artist": "artist name", "year": "release year"}. ' +
    'Return only a JSON array with these objects.';
}; 