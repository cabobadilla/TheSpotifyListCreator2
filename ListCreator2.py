import openai
import json
import streamlit as st
import requests
from urllib.parse import urlencode
from typing import Literal

# Initialize session state
def init_session_state():
    if "page" not in st.session_state:
        st.session_state.page = "auth"
    if "playlist_data" not in st.session_state:
        st.session_state.playlist_data = {}

# Function to change pages
def change_page(page: Literal["auth", "define", "generate"]):
    st.session_state.page = page

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
def generate_playlist_details(mood, genres, hidden_gems=False, discover_new=False):
    """
    Generate a playlist name, description, 15  songs that connect with the mood and genres provided.
    ChatGPT will act as a DJ curating songs that align with the mood.
    
    Args:
        mood (str): The desired mood for the playlist
        genres (list): List of music genres
        hidden_gems (bool): Whether to include lesser-known tracks
        discover_new (bool): Whether to include recent tracks (2020-2024)
    """
    client = openai.OpenAI(api_key=OPENAI_API_KEY)
    
    system_content = (
        "You are a music expert and DJ who curates playlists based on mood and genres. "
        "Your job is to act as a DJ and create a playlist that connects deeply with the given mood and genres. "
        "Generate a playlist name (max 5 words), a description (max 25 words), and 15 songs. "
        "IMPORTANT: Use only basic ASCII characters. No special quotes, apostrophes, or symbols. "
        "Each song MUST include these exact fields with proper JSON formatting: "
        "title (string), artist (string), year (integer), is_hidden_gem (boolean), is_new_music (boolean). "
        'RESPOND WITH ONLY THE FOLLOWING JSON STRUCTURE, NO OTHER TEXT: '
        '{"name": "Simple Name", "description": "Simple description", "songs": ['
        '{"title": "Song Name", "artist": "Artist Name", "year": 2024, "is_hidden_gem": false, "is_new_music": false}'
        ']}'
    )
    
    if hidden_gems:
        system_content += (
            "Since hidden gems mode is activated, create a more creative and unique playlist name "
            "that reflects the underground/alternative nature of the selection. "
            "The description should mention that this is a special curated selection of hidden gems. "
            "50% of songs should be lesser-known hidden gems in these genres. "
        )
    
    if discover_new:
        system_content += (
            "Since discover new music mode is activated, 50% of the songs should be from "
            "2023 onwards. Mark these songs with 'is_new_music' flag. "
            "The name and description should mention that this includes recent releases. "
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
                      f"{'Include 50% hidden gems and lesser-known songs.' if hidden_gems else ''} "
                      f"{'Include 50% songs from 2023-2024 with accurate release years.' if discover_new else ''} "
                      f"Ensure each song has an accurate release year as an integer."
        },
    ]
    
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=2000,
            temperature=0.8 if hidden_gems or discover_new else 0.7,
        )
        playlist_response = response.choices[0].message.content.strip()
        
        st.write("📝 Response received from ChatGPT")
        st.write("🔍 Response length:", len(playlist_response))
        
        try:
            return validate_and_clean_json(playlist_response)
        except ValueError as e:
            st.error("❌ JSON Validation Error:")
            st.error(str(e))
            return None, None, []

    except Exception as e:
        st.error(f"❌ ChatGPT API Error: {str(e)}")
        return None, None, []

# Function to validate and clean JSON
def validate_and_clean_json(raw_response):
    """
    Validate and clean the JSON response from ChatGPT.
    Ensures that it conforms to the expected structure.
    """
    if not raw_response:
        raise ValueError("ChatGPT response is empty.")
    
    st.write("🔍 Debug: Processing raw response...")
    
    try:
        playlist_data = json.loads(raw_response)
        st.write("✅ Initial JSON parsing successful")
    except json.JSONDecodeError as e:
        st.write("⚠️ Initial JSON parsing failed, attempting cleanup...")
        # Remove any markdown formatting and clean the response
        cleaned_response = raw_response.replace("```json", "").replace("```", "").strip()
        # Replace smart quotes and apostrophes with standard ones
        cleaned_response = cleaned_response.replace(""", '"').replace(""", '"')
        cleaned_response = cleaned_response.replace("'", "'").replace("'", "'")
        # Remove any newlines and extra whitespace
        cleaned_response = " ".join(cleaned_response.split())
        # Ensure proper JSON string formatting
        cleaned_response = cleaned_response.replace('\\"', '"').replace('\\n', ' ')
        
        st.write("🔍 Cleaned response preview (first 200 chars):")
        st.code(cleaned_response[:200])
        
        try:
            playlist_data = json.loads(cleaned_response)
            st.write("✅ JSON parsing successful after cleanup")
        except json.JSONDecodeError as e:
            st.error(f"❌ JSON Error Details:\nPosition: {e.pos}\nLine: {e.lineno}\nColumn: {e.colno}")
            st.error("❌ Raw Response Preview:")
            st.code(raw_response[:200])
            raise ValueError(f"Could not process JSON even after cleaning. Error: {str(e)}")
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
    if not all(isinstance(song.get('is_new_music', False), bool) for song in playlist_data["songs"]):
        # If is_new_music is missing, default to False
        for song in playlist_data["songs"]:
            if 'is_new_music' not in song:
                song['is_new_music'] = False
    if not all("title" in song and "artist" in song and "year" in song for song in playlist_data["songs"]):
        raise ValueError("Songs do not contain required fields ('title', 'artist', 'year').")
    if not all(isinstance(song.get('year', 0), int) for song in playlist_data["songs"]):
        raise ValueError("Year must be an integer value.")
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
    
    if response.status_code == 201:  # HTTP 201 Created
        return response.json()  # Return the created playlist data
    else:
        st.error(f"❌ Error creating playlist: {response.json().get('error', {}).get('message', 'Unknown error')}")
        return None

# Function to add songs to a playlist on Spotify
def add_tracks_to_playlist(token, playlist_id, track_uris):
    url = f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"uris": track_uris}
    response = requests.post(url, headers=headers, json=payload)
    return response

def combined_auth_and_define_page():
    st.markdown(
        """
        <div style='text-align: center;'>
            <h1>🎵 Spotify Playlist Creator 2.0 🎵</h1>
            <h3>Create personalized playlists based on your mood and favorite genre</h3>
        </div>
        """,
        unsafe_allow_html=True
    )
    
    with st.container():
        if "access_token" not in st.session_state:
            auth_url = get_auth_url(CLIENT_ID, REDIRECT_URI, SCOPES)
            st.markdown(
                f"<div style='text-align: center;'><a href='{auth_url}' target='_blank' class='spotify-button'>🔑 Login with Spotify</a></div>",
                unsafe_allow_html=True
            )
            
            # Handle authentication code from URL
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
            st.success("✅ Already authenticated")
        
        # Playlist definition section
        config = load_config()  # Load configuration for moods and genres
        
        st.markdown("<h2>Define Your Playlist</h2>", unsafe_allow_html=True)
        
        user_id = st.text_input("🎤 Enter your Spotify user ID", placeholder="Spotify Username")
        mood = st.selectbox("😊 Select your desired mood", config["moods"])
        genres = st.multiselect("🎸 Select music genres", config["genres"])
        
        col_a, col_b = st.columns(2)
        with col_a:
            hidden_gems = st.checkbox("💎 Hidden Gems", help="Include lesser-known tracks")
        with col_b:
            discover_new = st.checkbox("🆕 New Music", help="Include recent tracks")
        
        # Button container for navigation
        if st.button("Generate Playlist →", type="primary"):
            if user_id and mood and genres:
                st.session_state.playlist_data = {
                    "user_id": user_id,
                    "mood": mood,
                    "genres": genres,
                    "hidden_gems": hidden_gems,
                    "discover_new": discover_new
                }
                change_page("generate")
            else:
                st.warning("⚠️ Please complete all required fields")

def generate_playlist_page():
    st.markdown("<h1>Generate Playlist</h1>", unsafe_allow_html=True)
    
    data = st.session_state.playlist_data
    
    if data:
        st.info("🎧 Generating your playlist...")
        
        name, description, songs = generate_playlist_details(data["mood"], data["genres"], data["hidden_gems"], data["discover_new"])
        
        if name and description and songs:
            st.success(f"✅ Generated name: {name}")
            st.info(f"📜 Generated description: {description}")
            st.success("🎵 Generated songs:")
            
            for idx, song in enumerate(songs, 1):
                st.write(f"{idx}. **{song['title']}** - {song['artist']} ({song['year']})")
            
            # Create the playlist on Spotify
            if st.button("Create Playlist on Spotify"):
                user_id = data["user_id"]
                playlist_response = create_playlist(st.session_state.access_token, user_id, name, description)
                
                if playlist_response and "id" in playlist_response:
                    st.success("✅ Playlist created successfully on Spotify!")
                    st.write(f"🔗 [Open your playlist here](https://open.spotify.com/playlist/{playlist_response['id']})")
                else:
                    st.error("❌ Failed to create playlist on Spotify.")
        else:
            st.error("❌ Failed to generate playlist details.")
    else:
        st.error("❌ No playlist data found.")

def define_playlist_page():
    st.markdown("<h1>Define Your Playlist</h1>", unsafe_allow_html=True)
    
    with st.container():
        config = load_config()  # Load configuration for moods and genres
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            user_id = st.text_input("🎤 Enter your Spotify user ID", placeholder="Spotify Username")
            mood = st.selectbox("😊 Select your desired mood", config["moods"])
            genres = st.multiselect("🎸 Select music genres", config["genres"])
            
            col_a, col_b = st.columns(2)
            with col_a:
                hidden_gems = st.checkbox("💎 Hidden Gems", help="Include lesser-known tracks")
            with col_b:
                discover_new = st.checkbox("🆕 New Music", help="Include recent tracks")
        
        with col2:
            st.markdown(
                """
                <div class='step-container'>
                    <h4>Tips</h4>
                    <ul>
                        <li>Choose up to 3 genres for better results</li>
                        <li>Hidden Gems mode finds unique tracks</li>
                        <li>New Music focuses on recent releases</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True
            )
        
        # Button container with custom CSS for button layout
        st.markdown(
            """
            <style>
            .button-container {
                display: flex;
                justify-content: center;
                gap: 20px;
                margin-top: 20px;
            }
            .button-container .stButton button {
                width: 200px;  /* Set a fixed width for buttons */
            }
            </style>
            """,
            unsafe_allow_html=True
        )
        
        # Create a button container
        st.markdown('<div class="button-container">', unsafe_allow_html=True)
        
        if st.button("← Back", use_container_width=True):
            change_page("auth")
        
        if st.button("Generate Playlist →", type="primary", use_container_width=True):
            if user_id and mood and genres:
                st.session_state.playlist_data = {
                    "user_id": user_id,
                    "mood": mood,
                    "genres": genres,
                    "hidden_gems": hidden_gems,
                    "discover_new": discover_new
                }
                change_page("generate")
            else:
                st.warning("⚠️ Please complete all required fields")
        
        st.markdown('</div>', unsafe_allow_html=True)

def main():
    init_session_state()
    
    # Add responsive CSS
    st.markdown(
        """
        <style>
            /* Base styles */
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
            
            /* Responsive styles */
            @media (max-width: 768px) {
                .stButton>button {
                    width: 100%;
                    margin: 5px 0;
                }
                .step-container {
                    padding: 10px;
                }
            }
            
            /* Custom components */
            .spotify-button {
                background-color: #1DB954;
                color: white;
                padding: 12px 24px;
                border-radius: 25px;
                text-decoration: none;
                display: inline-block;
                margin: 10px 0;
                font-weight: bold;
            }
            
            .step-container {
                background-color: #2C2C2C;
                padding: 20px;
                border-radius: 10px;
                margin: 20px 0;
            }
        </style>
        """,
        unsafe_allow_html=True
    )
    
    # Route to correct page
    if st.session_state.page == "auth":
        combined_auth_and_define_page()
    elif st.session_state.page == "define":
        define_playlist_page()
    elif st.session_state.page == "generate":
        generate_playlist_page()

if __name__ == "__main__":
    main()