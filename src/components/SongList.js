function SongList({ songs }) {
  return (
    <div className="song-list">
      {songs.map((song, index) => (
        <div key={index} className="song-item">
          <div className="song-info">
            <h3>{song.title}</h3>
            <p>{song.artist} ({song.year})</p>
            {song.is_top_song && <span className="top-song-badge">Popular</span>}
          </div>
          {/* ... existing code ... */}
        </div>
      ))}
    </div>
  );
}

export default SongList; 