import openai
import json
import streamlit as st
import requests
from urllib.parse import urlencode
import time

# new File sync wth repositoy
# version 0.761 working but issues naming the lists
# version 0.762 fixed the issue with repeated playlist names
# version 0.767 working ok
# version 0.769 just adding dif style

# Estilo de Spotify (colores verde y negro)
st.markdown(
    '''
    <style>
        body {
            background-color: #121212;
            color: white;
            font-family: 'Helvetica', sans-serif;
        }
        h1, h2, h3 {
            color: #00A551;
            font-weight: bold;
            text-align: center;
        }
        .stButton>button {
            background-color: #00A551;
            color: white;
            font-size: 16px;
            border-radius: 25px;
            padding: 10px 20px;
        }
        .stButton>button:hover {
            background-color: #00C36A;
        }
        .stTextInput>div>input, .stTextArea>div>textarea, .stSelectbox>div>div>div, .stMultiSelect>div>div>div {
            background-color: #2C2C2C;
            color: white;
            border: 1px solid #00A551;
            border-radius: 10px;
        }
    </style>
    ''',
    unsafe_allow_html=True
)

# Spotify API Credentials
CLIENT_ID = st.secrets["SPOTIFY_CLIENT_ID"]
CLIENT_SECRET = st.secrets["SPOTIFY_CLIENT_SECRET"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
REDIRECT_URI = st.secrets.get("SPOTIFY_REDIRECT_URI", "http://localhost:8501/callback")

# Scopes for Spotify API
SCOPES = "playlist-modify-private playlist-modify-public"

# Load configuration from Streamlit secrets
def load_config():
    """
    Load configuration from Streamlit secrets.
    """
    try:
        config = st.secrets["config"]
        return config
    except KeyError:
        st.error("❌ Configuration not found in Streamlit secrets.")
        return {"moods": [], "genres": []}

config = load_config()

# Load feature flags from Streamlit secrets
def load_feature_flags():
    """
    Load feature flags from Streamlit secrets.
    """
    try:
        feature_flags = st.secrets["feature_flags"]
        if feature_flags.get("debugging", False):
            st.write("🔍 Debug: Feature flags loaded:", feature_flags)  # Debugging statement
        return feature_flags
    except KeyError:
        st.error("❌ Feature flags not found in Streamlit secrets.")
        return {"hidden_gems": False, "new_music": False, "debugging": False}

feature_flags = load_feature_flags()

# Function to get authorization URL
def get_auth_url(client_id, redirect_uri, scopes):
    auth_url = "https://accounts.spotify.com/authorize"
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes,
    }
    return f"{auth_url}?{urlencode(params)}"

# Function to generate songs, playlist name, and description using ChatGPT
def generate_playlist_details(mood, genres, hidden_gems=False, discover_new=False, songs_from_films=False):
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    system_content = build_system_content(hidden_gems, discover_new, songs_from_films)
    user_content = build_user_content(mood, genres, hidden_gems, discover_new, songs_from_films)
    
    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=1500,
            temperature=0.8 if hidden_gems or discover_new else 0.7,
        )
        playlist_response = response.choices[0].message.content.strip()
        
        # Show debug messages if debugging is enabled
        if feature_flags.get("debugging", False):
            st.write("📝 Response received from ChatGPT")
            st.write("🔍 Response length:", len(playlist_response))
        
        return validate_and_clean_json(playlist_response)
    except Exception as e:
        st.error(f"❌ ChatGPT API Error: {str(e)}")
        return None, None, []

def build_system_content(hidden_gems, discover_new, songs_from_films):
    content = (
        "You are a music expert and DJ who curates playlists based on mood and genres. "
        "Your job is to act as a DJ and create a playlist that connects deeply with the given mood and genres. "
        "Generate a creative playlist name (max 5 words), a description (max 25 words), and exactly 15 songs. "
        "If the filters or conditions limit the selection to fewer than 15 songs, complete the playlist with similar songs of the same mood and genres. "
        "IMPORTANT: Use only basic ASCII characters. No special quotes, apostrophes, or symbols. "
        "Each song MUST include these exact fields with proper JSON formatting: "
        "title (string), artist (string), year (integer), is_hidden_gem (boolean), is_new_music (boolean), is_from_film (boolean). "
        'RESPOND WITH ONLY THE FOLLOWING JSON STRUCTURE, NO OTHER TEXT: '
        '{"name": "Simple Name", "description": "Simple description", "songs": ['
        '{"title": "Song Name", "artist": "Artist Name", "year": 2024, "is_hidden_gem": false, "is_new_music": false, "is_from_film": false}'
        ']}'
    )
    if hidden_gems:
        content += (
            "Since hidden gems mode is activated, create a more creative and unique playlist name "
            "that reflects the underground/alternative nature of the selection. "
            "The description should mention that this is a special curated selection of hidden gems. "
            "50% of songs should be lesser-known hidden gems in these genres. "
            "The playlist name and description should evoke a sense of discovery and exclusivity. "
        )
    if discover_new:
        content += (
            "Since discover new music mode is activated, 50% of the songs should be from "
            "2022 onwards. Mark these songs with 'is_new_music' flag. "
            "The description should mention that this includes recent releases. "
        )
    if songs_from_films:
        content += (
            "Include songs that are featured in popular films. "
            "40% of the songs should be movie soundtracks from top or well-known movies. "
            "Avoid songs from child or kids-style movies like Disney movies. "
            "Mark these songs with 'is_from_film' flag. "
            "The description should mention that this includes songs from popular films. "
        )
    return content

def build_user_content(mood, genres, hidden_gems, discover_new, songs_from_films):
    return (
        f"Create a playlist for the mood '{mood}' and genres {', '.join(genres)}. "
        f"Make sure the songs align with the mood and genres. "
        f"{'Include 40% hidden gems and lesser-known songs.' if hidden_gems else ''} "
        f"{'Include 40% songs from 2023-2024 with accurate release years.' if discover_new else ''} "
        f"{'Include 40% songs from popular films, avoiding child or kids-style movies like Disney.' if songs_from_films else ''} "
        f"Ensure each song has an accurate release year as an integer."
    )

# Function to validate and clean JSON
def validate_and_clean_json(raw_response):
    if not raw_response:
        raise ValueError("ChatGPT response is empty.")
    
    if feature_flags.get("debugging", False):
        st.write("🔍 Debug: Processing raw response...")
    
    try:
        playlist_data = json.loads(raw_response)
        if feature_flags.get("debugging", False):
            st.write("✅ Initial JSON parsing successful")
    except json.JSONDecodeError:
        playlist_data = attempt_json_cleanup(raw_response)
    
    validate_playlist_data(playlist_data)
    return playlist_data["name"], playlist_data["description"], playlist_data["songs"]

def attempt_json_cleanup(raw_response):
    if feature_flags.get("debugging", False):
        st.write("⚠️ Initial JSON parsing failed, attempting cleanup...")
    cleaned_response = clean_response(raw_response)
    if feature_flags.get("debugging", False):
        st.write("🔍 Cleaned response preview (first 200 chars):")
        st.code(cleaned_response[:200])
    
    try:
        return json.loads(cleaned_response)
    except json.JSONDecodeError as e:
        st.error(f"❌ JSON Error Details:\nPosition: {e.pos}\nLine: {e.lineno}\nColumn: {e.colno}")
        st.error("❌ Raw Response Preview:")
        st.code(raw_response[:200])
        raise ValueError(f"Could not process JSON even after cleaning. Error: {str(e)}")

def clean_response(raw_response):
    cleaned_response = raw_response.replace("```json", "").replace("```", "").strip()
    cleaned_response = cleaned_response.replace(""", '"').replace(""", '"')
    cleaned_response = cleaned_response.replace("'", "'").replace("'", "'")
    cleaned_response = " ".join(cleaned_response.split())
    return cleaned_response.replace('\\"', '"').replace('\\n', ' ')

def validate_playlist_data(playlist_data):
    if not isinstance(playlist_data, dict):
        raise ValueError("JSON is not a valid object.")
    required_keys = {"name", "description", "songs"}
    if not required_keys.issubset(playlist_data):
        raise ValueError(f"JSON does not contain expected keys {required_keys}.")
    if not isinstance(playlist_data["songs"], list):
        raise ValueError("The 'songs' field is not a list.")
    for song in playlist_data["songs"]:
        if not all(key in song for key in ["title", "artist", "year"]):
            raise ValueError("Songs do not contain required fields ('title', 'artist', 'year').")
        if not isinstance(song.get('year', 0), int):
            raise ValueError("Year must be an integer value.")
        song.setdefault('is_hidden_gem', False)
        song.setdefault('is_new_music', False)

# Function to search for songs on Spotify
def search_tracks(token, title, artist, year):
    # Construct a more precise query with title, artist, and year
    query = f"track:{title} artist:{artist} year:{year}"
    url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "q": query,
        "type": "track",
        "limit": 5,  # Adjust limit as needed
        "market": "US"  # Specify market if needed
    }
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code != 200:
        handle_spotify_error(response)
        return {"tracks": {"items": []}}
    
    try:
        if feature_flags.get("debugging", False):
            st.write("🔍 Debug: Response content:", response.content)
        return response.json()
    except json.JSONDecodeError:
        st.error("❌ Error decoding JSON response from Spotify.")
        return {"tracks": {"items": []}}

def handle_spotify_error(response):
    error_message = response.json().get('error', {}).get('message', 'Unknown error')
    st.error(f"❌ Error searching for songs: {error_message}")

# Function to create a playlist on Spotify
def create_playlist(token, user_id, name, description):
    url = f"https://api.spotify.com/v1/users/{user_id}/playlists"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"name": name, "description": description, "public": False}
    response = requests.post(url, headers=headers, json=payload)
    return response.json()

# Function to add songs to a playlist on Spotify
def add_tracks_to_playlist(token, playlist_id, track_uris):
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"uris": track_uris}
    response = requests.post(url, headers=headers, json=payload)
    return response

def generate_unique_playlist_name(desired_name):
    # Generate a 4-digit timestamp
    timestamp = int(time.time()) % 10000  # Get the last 4 digits of the current timestamp
    unique_name = f"{desired_name} - {timestamp:04d}"
    
    if feature_flags.get("debugging", False):
        st.write(f"🔍 Debug: Generated unique playlist name: '{unique_name}'")
    
    return unique_name

# Streamlit App
def main():
    st.markdown(
        """
        <h1 style='text-align: center;'>🎵 GenAI Playlist Creator 🎵</h1>
        <h2 style='text-align: center;'>by BCG Platinion</h2>
        <h3 style='text-align: center;'>Create personalized playlists automatically based on your mood and favorite music using chatGPT</h3>
        <p style='text-align: center; color: #888;'>2025 This application doesn't store any personal data, just uses your Spotify account to create the playlist.</p>
        """,
        unsafe_allow_html=True
    )
    
    st.markdown("<h2 style='color: #1DB954;'>🔑 Authentication</h2>", unsafe_allow_html=True)
    if "access_token" not in st.session_state:
        display_authentication_link()
    else:
        st.success("✅ Already authenticated.")

    if "access_token" in st.session_state:
        display_playlist_creation_form()

def display_authentication_link():
    auth_url = get_auth_url(CLIENT_ID, REDIRECT_URI, SCOPES)
    st.markdown(
        f"<div style='text-align: center;'><a href='{auth_url}' target='_blank' style='color: #1DB954; font-weight: bold;'>🔑 Login with Spotify</a></div>",
        unsafe_allow_html=True
    )
    query_params = st.query_params
    if "code" in query_params:
        handle_spotify_authentication(query_params["code"])

def handle_spotify_authentication(code):
    token_response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    ).json()
    if "access_token" in token_response:
        st.session_state.access_token = token_response["access_token"]
        st.success("✅ Authentication completed.")
    else:
        st.error("❌ Authentication error.")

def display_playlist_creation_form():
    st.markdown("<h2>🎶 Generate and Create Playlist</h2>", unsafe_allow_html=True)
    user_id = st.text_input("Enter your Spotify user ID", placeholder="Spotify Username", label_visibility="collapsed")
    mood = st.selectbox("😊 Select your desired mood", config["moods"], label_visibility="collapsed")
    genres = st.multiselect("🎸 Select music genres", config["genres"], label_visibility="collapsed")
    
    # Determine available features based on feature flags
    available_features = ["None"]
    if feature_flags.get("hidden_gems", False):
        available_features.append("💎 Hidden Gems")
    if feature_flags.get("new_music", False):
        available_features.append("🆕 New Music")
    if feature_flags.get("songs_from_films", False):
        available_features.append("🎬 Movie Soundtracks")
    
    # Use a single radio button for feature selection
    feature_selection = st.radio(
        "Select a feature for your playlist:",
        available_features
    )

    hidden_gems = feature_selection == "💎 Hidden Gems"
    discover_new = feature_selection == "🆕 New Music"
    songs_from_films = feature_selection == "🎬 Movie Soundtracks"

    # Show debug message if debugging is enabled
    if feature_flags.get("debugging", False):
        st.write("🔍 Debug: Feature selected:", feature_selection)
        st.write("🔍 Debug: Hidden Gems:", hidden_gems)
        st.write("🔍 Debug: New Music:", discover_new)
        st.write("🔍 Debug: Movie Soundtracks:", songs_from_films)

    if st.button("🎵 Generate and Create Playlist 🎵"):
        if user_id and mood and genres:
            st.info("🎧 Generating songs, name and description...")
            
            # Start the timer
            start_time = time.time()
            
            name, description, songs = generate_playlist_details(mood, genres, hidden_gems, discover_new, songs_from_films)
            handle_playlist_creation(user_id, name, description, songs, start_time)
        else:
            st.warning("⚠️ Please complete all fields to create the playlist.")

def handle_playlist_creation(user_id, name, description, songs, start_time):
    if name and description and songs:
        st.success(f"✅ Generated name: {name}")
        st.info(f"📜 Generated description: {description}")
        st.success(f"🎵 Generated songs:")
        
        # Get a unique playlist name
        unique_name = generate_unique_playlist_name(name)
        
        st.markdown("<div style='margin-bottom: 10px'><b>Legend:</b> ⭐ = Top Hit | 💎 = Hidden Gem | 🆕 = New Music | 🎬 = Movie Soundtrack</div>", unsafe_allow_html=True)
        
        track_uris = []
        for idx, song in enumerate(songs, 1):
            title = song['title']
            artist = song['artist']
            is_hidden_gem = song.get('is_hidden_gem', False)
            is_new_music = song.get('is_new_music', False)
            is_from_film = song.get('is_from_film', False)
            
            search_response = search_tracks(st.session_state.access_token, title, artist, song.get('year', ''))
            if "tracks" in search_response and search_response["tracks"]["items"]:
                track_uris.append(search_response["tracks"]["items"][0]["uri"])
                icons = []
                if is_hidden_gem:
                    icons.append("💎")
                if is_new_music:
                    icons.append("🆕")
                if is_from_film:
                    icons.append("🎬")
                if not icons:
                    icons.append("⭐")
                year = song.get('year', 'N/A')
                st.write(f"{idx}. **{title}** - {artist} ({year}) {' '.join(icons)}")

        if track_uris:
            playlist_response = create_playlist(st.session_state.access_token, user_id, unique_name, description)
            if "id" in playlist_response:
                playlist_id = playlist_response["id"]
                add_tracks_to_playlist(st.session_state.access_token, playlist_id, track_uris)
                
                # End the timer
                end_time = time.time()
                duration = end_time - start_time
                
                st.success(f"✅ Playlist '{unique_name}' successfully created on Spotify - created in {duration:.2f} seconds.")
            else:
                st.error("❌ Could not create playlist on Spotify.")
    else:
        st.error("❌ Could not generate playlist.")

if __name__ == "__main__":
    main()
