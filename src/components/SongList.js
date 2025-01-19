function SongList({ songs }) {
  return (
    <div className="song-list">
      {songs.map((song, index) => (
        <div key={index} className="song-item">
          <div className="song-info">
            <h3>{song.title}</h3>
            <p>{song.artist} ({song.year})</p>
          </div>
          {/* ... existing code ... */}
        </div>
      ))}
    </div>
  );
}

export default SongList; 