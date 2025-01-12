import openai
import json
import streamlit as st
import requests
from urllib.parse import urlencode

# Estilo de Spotify (colores verde y negro)
st.markdown(
    '''
    <style>
        body {
            background-color: #121212;
            color: white;
        }
        h1, h2, h3 {
            color: #1DB954;
            font-weight: bold;
            text-align: center;
        }
        .stButton>button {
            background-color: #1DB954;
            color: white;
            font-size: 16px;
            border-radius: 25px;
            padding: 10px 20px;
        }
        .stButton>button:hover {
            background-color: #1ED760;
        }
        .stTextInput>div>input, .stTextArea>div>textarea, .stSelectbox>div>div>div, .stMultiSelect>div>div>div {
            background-color: #2C2C2C;
            color: white;
            border: 1px solid #1DB954;
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
def generate_playlist_details(mood, genres, hidden_gems=False):
    """
    Generate a playlist name, description, and 20 songs that connect with the mood and genres provided.
    ChatGPT will act as a DJ curating songs that align with the mood.
    
    Args:
        mood (str): The desired mood for the playlist
        genres (list): List of music genres
        hidden_gems (bool): Whether to include lesser-known tracks
    """
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    # Modify the system message based on hidden_gems
    system_content = (
        "You are a music expert and DJ who curates playlists based on mood and genres. "
        "Your job is to act as a DJ and create a playlist that connects deeply with the given mood and genres. "
    )
    
    if hidden_gems:
        system_content += (
            "Since hidden gems mode is activated, create a more creative and unique playlist name "
            "that reflects the underground/alternative nature of the selection. "
            "The description should mention that this is a special curated selection of hidden gems. "
            "40% of songs should be lesser-known hidden gems in these genres. "
        )
    
    system_content += (
        "Generate a playlist name (max 4 words), a description (max 20 words), and 20 songs. "
        "Ensure all song names are free from special characters to maintain JSON format compatibility. "
        "Each song must include 'title', 'artist', and 'is_hidden_gem' (boolean). "
        "Respond in JSON format with the following structure: "
        "{ 'name': '...', 'description': '...', 'songs': [{'title': '...', 'artist': '...', 'is_hidden_gem': boolean}] }"
    )

    messages = [
        {
            "role": "system",
            "content": system_content
        },
        {
            "role": "user",
            "content": f"Create a playlist for the mood '{mood}' and genres {', '.join(genres)}. "
                      f"Make sure the songs align with the mood and genres. "
                      f"{'Include 40% hidden gems and lesser-known songs.' if hidden_gems else ''}"
        },
    ]
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=750,
            temperature=0.8 if hidden_gems else 0.7,  # Slightly higher temperature for more creativity
        )
        playlist_response = response.choices[0].message.content.strip()

        try:
            return validate_and_clean_json(playlist_response)
        except ValueError as e:
            st.error(f"❌ Error al procesar la respuesta de ChatGPT: {e}")
            return None, None, []

    except Exception as e:
        st.error(f"❌ Error al generar la playlist: {e}")
        return None, None, []

# Function to validate and clean JSON
def validate_and_clean_json(raw_response):
    """
    Validate and clean the JSON response from ChatGPT.
    Ensures that it conforms to the expected structure.
    """
    if not raw_response:
        raise ValueError("ChatGPT response is empty.")
    try:
        playlist_data = json.loads(raw_response)
    except json.JSONDecodeError:
        cleaned_response = raw_response.replace("```json", "").replace("```", "").strip()
        try:
            playlist_data = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Could not process JSON even after cleaning: {e}")
    if not isinstance(playlist_data, dict):
        raise ValueError("JSON is not a valid object.")
    if "name" not in playlist_data or "description" not in playlist_data or "songs" not in playlist_data:
        raise ValueError("JSON does not contain expected keys ('name', 'description', 'songs').")
    if not isinstance(playlist_data["songs"], list):
        raise ValueError("The 'songs' field is not a list.")
    if not all("title" in song and "artist" in song for song in playlist_data["songs"]):
        raise ValueError("Songs do not contain 'title' and 'artist' fields.")
    if not all(isinstance(song.get('is_hidden_gem', False), bool) for song in playlist_data["songs"]):
        # If is_hidden_gem is missing, default to False
        for song in playlist_data["songs"]:
            if 'is_hidden_gem' not in song:
                song['is_hidden_gem'] = False
    return playlist_data["name"], playlist_data["description"], playlist_data["songs"]

# Function to search for songs on Spotify
def search_tracks(token, title, artist):
    """
    Search for a track on Spotify using the given title and artist.
    """
    query = f"{title} {artist}"
    url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"q": query, "type": "track", "limit": 1}
    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        st.error(f"❌ Error searching for songs: {response.json().get('error', {}).get('message', 'Unknown error')}")
        return {"tracks": {"items": []}}
    return response.json()

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

# Streamlit App
def main():
    st.markdown(
        """
        <h1 style='text-align: center;'>🎵 Spotify Playlist Creator 2.0 🎵</h1>
        <h3 style='text-align: center;'>Create personalized playlists based on your mood and favorite genre</h3>
        """,
        unsafe_allow_html=True
    )
    
    # Step 1: Authorization
    st.markdown("<h2 style='color: #1DB954;'>🔑 Authentication</h2>", unsafe_allow_html=True)
    if "access_token" not in st.session_state:
        auth_url = get_auth_url(CLIENT_ID, REDIRECT_URI, SCOPES)
        st.markdown(
            f"<div style='text-align: center;'><a href='{auth_url}' target='_blank' style='color: #1DB954; font-weight: bold;'>🔑 Login with Spotify</a></div>",
            unsafe_allow_html=True
        )
        query_params = st.query_params
        if "code" in query_params:
            code = query_params["code"]
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
    else:
        st.success("✅ Already authenticated.")

    # Step 2: Playlist generation
    if "access_token" in st.session_state:
        st.markdown("<h2>🎶 Generate and Create Playlist</h2>", unsafe_allow_html=True)
        user_id = st.text_input("🎤 Enter your Spotify user ID", placeholder="Spotify Username")
        mood = st.selectbox("😊 Select your desired mood", config["moods"])
        genres = st.multiselect("🎸 Select music genres", config["genres"])
        hidden_gems = st.checkbox("💎 Hidden Gems", help="Include lesser-known tracks in your playlist")

        if st.button("🎵 Generate and Create Playlist 🎵"):
            if user_id and mood and genres:
                st.info("🎧 Generating songs, name and description...")
                name, description, songs = generate_playlist_details(mood, genres, hidden_gems)

                if name and description and songs:
                    st.success(f"✅ Generated name: {name}")
                    st.info(f"📜 Generated description: {description}")
                    st.success(f"🎵 Generated songs:")
                    
                    st.markdown("<div style='margin-bottom: 10px'><b>Legend:</b> ⭐ = Top Hit | 💎 = Hidden Gem</div>", unsafe_allow_html=True)
                    
                    track_uris = []
                    for idx, song in enumerate(songs, 1):
                        title = song['title']
                        artist = song['artist']
                        is_hidden_gem = song.get('is_hidden_gem', False)
                        
                        search_response = search_tracks(token, title, artist)
                        if "tracks" in search_response and search_response["tracks"]["items"]:
                            track_uris.append(search_response["tracks"]["items"][0]["uri"])
                            icon = "💎" if is_hidden_gem else "⭐"
                            st.write(f"{idx}. **{title}** - {artist} {icon}")

                    if track_uris:
                        playlist_response = create_playlist(token, user_id, name, description)
                        if "id" in playlist_response:
                            st.success(f"✅ Playlist '{name}' successfully created on Spotify.")
                        else:
                            st.error("❌ Could not create playlist on Spotify.")
                else:
                    st.error("❌ Could not generate playlist.")
            else:
                st.warning("⚠️ Please complete all fields to create the playlist.")

if __name__ == "__main__":
    main()