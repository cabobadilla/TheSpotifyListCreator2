import openai
import json
import streamlit as st
import requests
from urllib.parse import urlencode
import time
from datetime import datetime
from pymongo import MongoClient

# ====================================
# VERSION AND ENVIRONMENT
# ====================================
#v0.963 working session
#Just test
# 764ee2ace2397c98a8f4d5093cfbd07b3c471eb8 working commit
# testing automatic commit

# ====================================
# UI STYLING
# ====================================
# Custom Spotify-themed styling (green and black colors)
# Controls the appearance of:
# - Background and text colors
# - Headers
# - Buttons
# - Input fields
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

# ====================================
# API CONFIGURATION
# ====================================
# Load API credentials from Streamlit secrets
CLIENT_ID = st.secrets["SPOTIFY_CLIENT_ID"]
CLIENT_SECRET = st.secrets["SPOTIFY_CLIENT_SECRET"]
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
REDIRECT_URI = st.secrets.get("SPOTIFY_REDIRECT_URI", "http://localhost:8501/callback")

# Spotify API endpoints
SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_URL = "https://api.spotify.com/v1"

# Required Spotify permissions for playlist creation and modification
SCOPES = "playlist-modify-private playlist-modify-public"

# ====================================
# CONFIGURATION MANAGEMENT
# ====================================
def load_config():
    """
    Loads mood and genre options from Streamlit secrets.
    Returns: Dictionary containing available moods, genres, and AI models
    """
    try:
        config = st.secrets["config"]
        # Add default AI models if not present in config
        if "ai_models" not in config:
            config["ai_models"] = {
                "gpt-3.5-turbo": "GPT-3.5 Turbo",
                "gpt-4": "GPT-4",
                "deepseek-chat": "DeepSeek Chat"
            }
        return config
    except KeyError:
        st.error("❌ Configuration not found in Streamlit secrets.")
        return {
            "moods": [], 
            "genres": [],
            "ai_models": {
                "gpt-3.5-turbo": "GPT-3.5 Turbo",
                "gpt-4": "GPT-4",
                "deepseek-chat": "DeepSeek Chat"
            }
        }

config = load_config()

def load_feature_flags():
    """
    Loads feature toggles from Streamlit secrets.
    Controls: hidden gems, new music, debugging mode, underground music, band music
    """
    try:
        feature_flags = st.secrets["feature_flags"]
        if feature_flags.get("debugging", False):
            st.write("🔍 Debug: Feature flags loaded:", feature_flags)
        return feature_flags
    except KeyError:
        st.error("❌ Feature flags not found in Streamlit secrets.")
        return {
            "hidden_gems": False, 
            "new_music": False, 
            "debugging": False,
            "underground_music": False,
            "band_music": False  # New feature flag
        }

feature_flags = load_feature_flags()

# ====================================
# PLAYLIST GENERATION
# ====================================
def build_system_content(hidden_gems, discover_new, songs_from_films, underground_music=False, band_name=None):
    """
    Builds the system prompt for ChatGPT with specific rules:
    - Playlist name max 4 words
    - Description max 20 words
    - Exactly 15 songs
    - Special handling for hidden gems, new music, films, and underground music
    """
    content = (
        "You are a music expert and DJ who curates playlists based on mood and genres. "
        "Your role is to create a playlist that effectively captures the desired mood using the selected music genres. "
        "Generate a creative playlist name (max 4 words), a concise description (max 20 words), and exactly 15 songs. "
        "IMPORTANT: Use only basic ASCII characters. No special quotes, apostrophes, or symbols. "
        "Each song MUST include these exact fields with proper JSON formatting: "
        "title (string), artist (string), year (integer), is_hidden_gem (boolean), is_new_music (boolean), is_from_film (boolean). "
        'RESPOND WITH ONLY THE FOLLOWING JSON STRUCTURE, NO OTHER TEXT: '
        '{"name": "Simple Name", "description": "Simple description", "songs": ['
        '{"title": "Song Name", "artist": "Artist Name", "year": 2024, "is_hidden_gem": false, "is_new_music": false, "is_from_film": false}'
        ']}'
    )

    # Ensure 15 songs requirement for all modes
    content += (
        "Ensure the playlist contains exactly 15 songs, even if the filters limit the selection. "
        "If fewer than 15 songs are selected, fill the remaining slots with appropriate tracks from the same genres. "
    )

    if underground_music:
        content += (
            "Create a playlist that captures the raw, authentic spirit of underground music scenes. "
            "For song selection, prioritize: "
            "- Artists who primarily release music on Bandcamp, SoundCloud, or small indie labels "
            "- Songs with fewer than 500,000 total Spotify plays "
            "- Local/regional artists building grassroots followings "
            "- Mainly DIY musicians and self-released tracks "
            "- Mainly Artists who maintain creative control and artistic integrity "
            "- Music that pushes boundaries and experiments with genre conventions "
            "The playlist name should evoke discovery and authenticity. "
            "The description should emphasize the unfiltered creativity and artistic vision of these musicians. "
        )

    # Add other feature-specific content
    if hidden_gems:
        content += (
            "For hidden gems mode: "
            "- At least 60% of songs must be hidden gems with less than 1 million streams "
            "- Select songs from independent record labels and underground artists "
            "- Avoid any songs that have charted on Billboard Hot 100 or similar mainstream charts "
            "- Focus on B-sides, deep cuts, and songs that never became singles "
            "- Include songs from local music scenes and regional hits "
            "- Look for critically acclaimed but commercially overlooked tracks "
            "- Mark qualifying songs with 'is_hidden_gem': true "
            "The playlist name should contain words like 'Hidden', 'Undiscovered', or 'Rare'. "
            "The description must emphasize the curated nature and uniqueness of these lesser-known musical treasures. "
        )

    if discover_new:
        content += (
            "For the new music discovery mode: "
            "- At least 60% of songs MUST be released between 2021-2024 "
            "- Only include original releases, NO remasters/remixes/covers "
            "- Mark qualifying songs with 'is_new_music': true "
            "- Focus on emerging artists and breakthrough tracks "
            "- Include songs from different sub-genres within the selected genres "
            "- Avoid songs that already have over 50 million streams "
            "The playlist name should contain words like 'Fresh', 'New', or 'Rising'. "
            "The description must emphasize discovering the latest music and emerging talent. "
        )

    if songs_from_films:
        content += (
            "Incorporate songs that play a significant role in popular films or TV series, ensuring they enhance the storyline or are associated with memorable scenes. "
            "Aim for 40% of the playlist to consist of iconic soundtracks from critically acclaimed or commercially successful movies, appealing to a broad audience. "
            "Avoid songs from children's films or animated features, such as those produced by Disney, to ensure a more mature and diverse selection. "
            "These songs should be distinctly marked with the 'is_from_film' flag. "
            "The playlist name and description must highlight that it features unforgettable tracks from beloved films and series, captivating movie enthusiasts and fans of cinematic music."
        )

    if band_name:
        content += (
            f"Create a 15-song playlist inspired by the musical style and legacy of '{band_name}'. "
            f"- Include 3-5 essential songs from {band_name}: "
            f"  • 2-3 of their most representative or iconic tracks "
            f"  • 1-2 fan favorites or deep cuts that showcase their range "
            f"- For the remaining 10-12 songs, create a diverse selection: "
            f"  • 3-4 songs from artists with a very similar musical style "
            f"  • 2-3 songs from artists who cite {band_name} as an influence "
            f"  • 2-3 songs from artists from the same scene/era/genre "
            f"  • 1-2 notable cover versions or tributes to {band_name} "
            f"  • 2-3 songs that share similar themes, moods, or sonic elements "
            f"  • 2-3 songs featuring collaborations between {band_name} and other artists "
            f"  • 1-2 songs where members of {band_name} appear as featured artists "
            f"- When selecting similar artists, consider: "
            f"  • Artists who have toured or collaborated with {band_name} "
            f"  • Musicians from the same geographic scene or movement "
            f"  • Contemporary artists carrying forward their musical tradition "
            f"  • Side projects or solo work from {band_name} members "
            f"- If unable to find enough songs matching the above criteria, expand the search to: "
            f"  • Additional songs from {band_name}'s discography, including live versions and remixes "
            f"  • Songs from artists in related or adjacent genres "
            f"  • Songs from artists who share band members or producers with {band_name} "
            f"  • Songs that were popular during {band_name}'s peak era "
            f"  • Songs that influenced {band_name}'s musical style "
            f"  • Collaborative projects between {band_name} members and other musicians "
            "The playlist MUST contain exactly 15 songs - no more, no less. "
            "The playlist name should reference the band's signature sound or style. "
            "The description should explain how each song connects to the band's musical legacy. "
            "Mark songs by the main band with 'is_band_music': true. "
            "Mark collaborative songs with 'is_collaboration': true. "
            )

    return content

def build_user_content(mood, genres, hidden_gems, discover_new, songs_from_films, underground_music=False, band_name=None):
    """
    Creates the user prompt for ChatGPT combining:
    - Selected mood and genres (if not band mode)
    - Band focus (if band mode)
    - Feature-specific requirements
    """
    # Set base content based on mode
    if band_name:
        user_content = (
            f"Create a comprehensive playlist showcasing {band_name}'s musical journey and influence. "
            f"Include a mix of their iconic hits, deep cuts, and songs from related artists. "
            "Focus on capturing the essence and evolution of their sound. "
        )
    elif underground_music:
        user_content = (
            "Create an underground music playlist that explores the authentic underground scene. "
            "Focus on independent artists, DIY releases, and emerging talent. "
            "Avoid any mainstream or commercially successful tracks. "
        )
    else:
        user_content = (
            f"Create a playlist for the mood '{mood}' and genres {', '.join(genres)}. "
            f"Make sure the songs align with the mood and genres. "
        )

    # Add feature requirements
    if hidden_gems:
        user_content += "Include 60% hidden gems and lesser-known songs that are not mainstream. "

    if discover_new:
        user_content += "Include 68% of songs from 2021 onwards with accurate release years. "

    if songs_from_films:
        user_content += "Include 40% songs from popular films, avoiding child or kids-style movies like Disney. "

    if underground_music:
        user_content += (
            "Ensure all songs are from the underground scene. "
            "Focus on independent labels, local scenes, and emerging artists. "
            "Avoid any commercially successful or mainstream tracks. "
        )

    # Always include year requirement
    user_content += "Ensure each song has an accurate release year as an integer."

    return user_content

def generate_playlist_details(mood, genres, hidden_gems=False, discover_new=False, songs_from_films=False, underground_music=False, band_name=None, model="gpt-3.5-turbo"):
    """
    Generates playlist details using selected AI model based on user preferences.
    Returns: Tuple of (playlist_name, description, songs_list)
    """
    try:
        if model.startswith("gpt"):
            # Use OpenAI for GPT models
            client = openai.OpenAI(api_key=OPENAI_API_KEY)
            
            # Build the system and user content for the prompt
            system_content = build_system_content(hidden_gems, discover_new, songs_from_films, underground_music, band_name)
            user_content = build_user_content(mood, genres, hidden_gems, discover_new, songs_from_films, underground_music, band_name)
            
            # Make the API call to GPT
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.7
            )
            
            # Get the response content
            raw_response = response.choices[0].message.content
            
        elif model == "deepseek-chat":
            # Use DeepSeek API
            DEEPSEEK_API_KEY = st.secrets["DEEPSEEK_API_KEY"]
            DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
            
            # Build the system and user content for the prompt
            system_content = build_system_content(hidden_gems, discover_new, songs_from_films, underground_music, band_name)
            user_content = build_user_content(mood, genres, hidden_gems, discover_new, songs_from_films, underground_music, band_name)
            
            # Make the API call to DeepSeek
            response = requests.post(
                DEEPSEEK_API_URL,
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [
                        {"role": "system", "content": system_content},
                        {"role": "user", "content": user_content}
                    ],
                    "temperature": 0.7
                }
            )
            
            if response.status_code != 200:
                raise Exception(f"DeepSeek API error: {response.text}")
            
            # Get the response content
            raw_response = response.json()["choices"][0]["message"]["content"]
        
        else:
            raise ValueError(f"Unsupported model: {model}")
        
        # Process and validate the response
        if feature_flags.get("debugging", False):
            st.write(f"🔍 Debug: Raw {model} Response:", raw_response)
        
        # Clean and validate the JSON response
        name, description, songs = validate_and_clean_json(raw_response)
        
        return name, description, songs
        
    except Exception as e:
        st.error(f"❌ Error generating playlist with {model}: {str(e)}")
        if feature_flags.get("debugging", False):
            st.write("🔍 Debug: Error details:", str(e))
        return None, None, None

# ====================================
# JSON PROCESSING
# ====================================
def validate_and_clean_json(raw_response):
    """
    Processes ChatGPT's response:
    1. Validates JSON format
    2. Cleans special characters
    3. Ensures required fields exist
    4. Handles error cases
    """
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
    """
    Attempts to fix common JSON formatting issues:
    - Removes code block markers
    - Fixes quote characters
    - Removes extra whitespace
    """
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
    """
    Validates the playlist data structure and sets default values
    """
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
        # Set default values for all feature flags
        song.setdefault('is_hidden_gem', False)
        song.setdefault('is_new_music', False)
        song.setdefault('is_from_film', False)
        song.setdefault('is_underground', False)
        song.setdefault('is_band_music', False)

# ====================================
# SPOTIFY INTEGRATION
# ====================================
def get_auth_url(client_id, redirect_uri, scopes):
    """
    Generates the Spotify authorization URL
    Args:
        client_id: Spotify client ID
        redirect_uri: URL to redirect after authentication
        scopes: Required Spotify permissions
    Returns:
        Authorization URL string
    """
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "show_dialog": True
    }
    auth_url = f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"
    return auth_url

def search_tracks(token, title, artist, year):
    """
    Searches Spotify for tracks using:
    - Song title
    - Artist name
    - Release year
    Returns top 5 matching results
    """
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

def create_playlist(token, user_id, name, description):
    """
    Creates a new playlist on Spotify
    Args:
        token: Spotify access token
        user_id: Spotify user ID
        name: Playlist name
        description: Playlist description
    Returns:
        Response from Spotify API
    """
    url = f"{SPOTIFY_API_URL}/users/{user_id}/playlists"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "name": name,
        "description": description,
        "public": True
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 201:
            st.error(f"❌ Error creating playlist: {response.json().get('error', {}).get('message', 'Unknown error')}")
            return {}
        return response.json()
    except Exception as e:
        st.error(f"❌ Error creating playlist: {str(e)}")
        return {}

def add_tracks_to_playlist(token, playlist_id, track_uris):
    """
    Adds tracks to a Spotify playlist
    Args:
        token: Spotify access token
        playlist_id: ID of the playlist
        track_uris: List of Spotify track URIs
    """
    url = f"{SPOTIFY_API_URL}/playlists/{playlist_id}/tracks"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {"uris": track_uris}
    
    try:
        response = requests.post(url, headers=headers, json=data)
        if response.status_code != 201:
            st.error(f"❌ Error adding tracks: {response.json().get('error', {}).get('message', 'Unknown error')}")
    except Exception as e:
        st.error(f"❌ Error adding tracks: {str(e)}")

# ====================================
# DATA PERSISTENCE
# ====================================
def save_playlist_data(user_id, playlist_name, status, playlist_uri, num_songs, feature_selected):
    """
    Records playlist creation data in MongoDB:
    - User ID
    - Playlist details
    - Creation status
    - Feature usage
    - Timestamp
    """
    if feature_flags.get("playlist_data_record", False):
        # Get the connection string and database name from Streamlit secrets
        connection_string = st.secrets["mongodb"]["connection_string"]
        database_name = st.secrets["mongodb"]["database_name"]
        collection_name = st.secrets["mongodb"]["collection_name"]

        try:
            # Debugging: Log the start of the database connection process
            if feature_flags.get("debugging", False):
                st.write("🔍 Debug: Attempting to connect to MongoDB Atlas.")

            # Connect to the MongoDB Atlas database
            client = MongoClient(connection_string)
            db = client[database_name]
            collection = db[collection_name]

            # Debugging: Log the connection success
            if feature_flags.get("debugging", False):
                st.write("🔍 Debug: Connected to MongoDB Atlas successfully.")

            # Prepare data to insert
            date_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            data = {
                "spotify_user_id": user_id,
                "date_time": date_time,
                "playlist_name": playlist_name,
                "status": status,
                "playlist_uri": playlist_uri,
                "num_songs": num_songs,
                "feature_selected": feature_selected
            }

            # Debugging: Log the data to be inserted
            if feature_flags.get("debugging", False):
                st.write("🔍 Debug: Data to be inserted:", data)

            # Insert the playlist information
            collection.insert_one(data)

            # Debugging: Log the success of the data insertion
            if feature_flags.get("debugging", False):
                st.write("🔍 Debug: Data inserted successfully into MongoDB.")

        except Exception as e:
            st.error(f"❌ MongoDB error: {e}")
            if feature_flags.get("debugging", False):
                st.write("🔍 Debug: Failed to insert data into MongoDB.")

# ====================================
# USER INTERFACE
# ====================================
def main():
    """
    Main application flow:
    1. Display header and description
    2. Handle authentication
    3. Show playlist creation form
    4. Process user input
    5. Generate and create playlist
    """
    st.markdown(
        """
        <h1 style='text-align: center;'>🎵 GenAI Playlist Creator 🎵</h1>
        <h2 style='text-align: center;'>by BCG Platinion 🤖 ❤️</h2>
        <p style='text-align: center; color: #1DB954; font-size: 16px;'>Powered by OpenAI GPT-3.5 Turbo</p>
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

# ====================================
# AUTHENTICATION HANDLING
# ====================================
def display_authentication_link():
    """
    Shows Spotify login link and processes callback
    """
    auth_url = get_auth_url(CLIENT_ID, REDIRECT_URI, SCOPES)
    st.markdown(
        f"<div style='text-align: center;'><a href='{auth_url}' target='_blank' style='color: #1DB954; font-weight: bold;'>🔑 Login with Spotify</a></div>",
        unsafe_allow_html=True
    )
    query_params = st.query_params
    if "code" in query_params:
        handle_spotify_authentication(query_params["code"])

def handle_spotify_authentication(code):
    """
    Exchanges auth code for access token
    Stores token in session state
    """
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

# ====================================
# PLAYLIST CREATION WORKFLOW
# ====================================
def display_playlist_creation_form():
    """
    Shows the main interface with updated feature options
    """
    st.markdown("<h2>🎶 Generate and Create Playlist</h2>", unsafe_allow_html=True)
    
    # Initialize selected_model with default value
    selected_model = "gpt-3.5-turbo"
    
    # Create initial column for user ID
    user_id = st.text_input("Enter your Spotify user ID", placeholder="Spotify Username", label_visibility="collapsed")
    
    # Show AI model selection only if feature flag is enabled
    if feature_flags.get("ai_models", False):
        st.markdown("<h3>Select AI Model</h3>", unsafe_allow_html=True)
        model_options = feature_flags.get("ai_models_config", {
            "gpt-3.5-turbo": "GPT-3.5 Turbo"  # Default if not configured
        })
        selected_model = st.selectbox(
            "Select AI Model",
            options=list(model_options.keys()),
            format_func=lambda x: model_options[x],
            index=0,
            help="Choose the AI model to generate your playlist"
        )
    
    # Create two columns for the radio button and band name input
    col1, col2 = st.columns([2, 2])
    
    with col1:
        # Updated available features list
        available_features = ["⭐ Top Songs"]
        if feature_flags.get("hidden_gems", False):
            available_features.append("💎 Hidden Gems")
        if feature_flags.get("new_music", False):
            available_features.append("🆕 New Music")
        if feature_flags.get("songs_from_films", False):
            available_features.append("🎬 Movie Soundtracks")
        if feature_flags.get("underground_music", False):
            available_features.append("🎸 Underground Music")
        if feature_flags.get("band_music", False):
            available_features.append("🎼 Music of a Band")
        
        feature_selection = st.radio(
            "Select a feature for your playlist:",
            available_features,
            index=0
        )

    # Add band name input field in the second column if band music is selected
    band_name = None
    with col2:
        if feature_selection == "🎼 Music of a Band":
            band_name = st.text_input("Enter band/artist name:", placeholder="e.g., The Beatles", key="band_name_input")
    
    # Show mood and genre selection based on feature
    mood = None
    genres = []
    if feature_selection == "🎸 Underground Music":
        st.info("🎸 Creating an underground music playlist with authentic underground tracks from your selected genres.")
        genres = st.multiselect("🎸 Select music genres for underground exploration", config["genres"], label_visibility="collapsed")
    elif feature_selection == "🎼 Music of a Band":
        st.info("🎼 Creating a playlist focused on your selected artist/band and related music.")
    else:
        mood = st.selectbox("😊 Select your desired mood", config["moods"], label_visibility="collapsed")
        genres = st.multiselect("🎸 Select music genres", config["genres"], label_visibility="collapsed")

    # Rest of the function remains the same but uses selected_model
    if st.button("🎵 Generate and Create Playlist 🎵"):
        if user_id:
            if feature_selection == "🎼 Music of a Band":
                if not band_name:
                    st.warning("⚠️ Please enter a band/artist name.")
                    return
            elif feature_selection == "🎸 Underground Music":
                if not genres:
                    st.warning("⚠️ Please select at least one genre for underground music exploration.")
                    return
            elif not mood or not genres:
                st.warning("⚠️ Please complete all fields to create the playlist.")
                return
                
            st.info("🎧 Generating songs, name and description...")
            
            # Check if the token is valid
            if not is_token_valid(st.session_state.access_token):
                st.info("🔄 Refreshing token...")
                if not refresh_token():
                    st.error("❌ Could not refresh token. Please re-authenticate.")
                    return
            
            start_time = time.time()
            
            # Pass the selected model to generate_playlist_details
            if feature_selection == "🎸 Underground Music":
                name, description, songs = generate_playlist_details(
                    "any",
                    genres,
                    hidden_gems=False,
                    discover_new=False,
                    songs_from_films=False,
                    underground_music=True,
                    band_name=None,
                    model=selected_model
                )
            elif feature_selection == "🎼 Music of a Band":
                name, description, songs = generate_playlist_details(
                    "any",
                    [],
                    hidden_gems=False,
                    discover_new=False,
                    songs_from_films=False,
                    underground_music=False,
                    band_name=band_name,
                    model=selected_model
                )
            else:
                name, description, songs = generate_playlist_details(
                    mood,
                    genres,
                    hidden_gems=(feature_selection == "💎 Hidden Gems"),
                    discover_new=(feature_selection == "🆕 New Music"),
                    songs_from_films=(feature_selection == "🎬 Movie Soundtracks"),
                    underground_music=False,
                    band_name=None,
                    model=selected_model
                )
            handle_playlist_creation(user_id, name, description, songs, start_time, feature_selection)
        else:
            st.warning("⚠️ Please enter your Spotify user ID.")

def handle_playlist_creation(user_id, name, description, songs, start_time, feature_selection):
    """
    Orchestrates the playlist creation process:
    1. Validates inputs
    2. Searches for tracks
    3. Creates playlist
    4. Adds tracks
    5. Shows results
    6. Records creation data
    """
    if name and description and songs:
        st.success(f"✅ Generated name: {name}")
        st.info(f"📜 Generated description: {description}")
        st.success(f"🎵 Generated songs:")
        
        # Get a unique playlist name
        unique_name = generate_unique_playlist_name(name)
        
        st.markdown("<div style='margin-bottom: 10px'><b>Legend:</b> ⭐ = Top Hit | 💎 = Hidden Gem | 🆕 = New Music | 🎬 = Movie Soundtrack | 🎸 = Underground Music</div>", unsafe_allow_html=True)
        
        # Determine if underground music is selected
        is_underground = feature_selection == "🎸 Underground Music"
        
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
                if is_underground:
                    icons.append("🎸")
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
                
                # Generate Spotify URL from URI
                playlist_url = f"https://open.spotify.com/playlist/{playlist_id}"
                
                st.success(f"✅ Playlist '{unique_name}' successfully created on Spotify - created in {duration:.2f} seconds.")
                
                # Display a styled button with a link to the playlist
                st.markdown(f"""
                    <a href="{playlist_url}" target="_blank">
                        <button style="
                            background-color: #1DB954;
                            color: white;
                            font-size: 16px;
                            border-radius: 25px;
                            padding: 10px 20px;
                            border: none;
                            cursor: pointer;
                            text-align: center;
                            display: inline-block;
                            margin-top: 10px;
                        ">Enjoy your New Playlist in Spotify</button>
                    </a>
                """, unsafe_allow_html=True)

                # Save playlist data
                save_playlist_data(user_id, unique_name, "created", playlist_url, len(songs), feature_selection)
            else:
                st.error("❌ Could not create playlist on Spotify.")
                save_playlist_data(user_id, unique_name, "fail", "", 0, "")
    else:
        st.error("❌ Could not generate playlist.")
        save_playlist_data(user_id, name, "fail", "", 0, "")

def generate_unique_playlist_name(desired_name):
    # Generate a 4-digit timestamp
    timestamp = int(time.time()) % 10000  # Get the last 4 digits of the current timestamp
    unique_name = f"{desired_name} - {timestamp:04d}"
    
    if feature_flags.get("debugging", False):
        st.write(f"🔍 Debug: Generated unique playlist name: '{unique_name}'")
    
    return unique_name

def is_token_valid(token):
    # Check if the token is valid by making a simple request
    url = "https://api.spotify.com/v1/me"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.status_code == 200

def refresh_token():
    # Refresh the token using the refresh token
    refresh_token = st.secrets["SPOTIFY_REFRESH_TOKEN"]
    response = requests.post(
        "https://accounts.spotify.com/api/token",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
    ).json()
    if "access_token" in response:
        st.session_state.access_token = response["access_token"]
        return True
    else:
        st.error("❌ Could not refresh token.")
        return False

# Application entry point
if __name__ == "__main__":
    main()