def generate_video_from_drive(folder_id, on_video_title, output_file, task_path):
    """
    Generate video with enhanced captions from Google Drive folder.
    
    AUTHENTICATION SETUP (Choose one method):
    
    METHOD 1 - SERVICE ACCOUNT (Recommended - No browser popups):
    1. Go to Google Cloud Console (console.cloud.google.com)
    2. Create a new project or select existing one
    3. Enable Google Drive API
    4. Go to "Credentials" → "Create Credentials" → "Service Account"
    5. Download the JSON key file and rename it to 'service-account-key.json'
    6. Share your Google Drive folder with the service account email (found in the JSON file)
    7. Place the JSON file in the same directory as this script
    
    METHOD 2 - OAUTH (Fallback - Improved to last longer):
    1. Go to Google Cloud Console
    2. Enable Google Drive API
    3. Create OAuth 2.0 credentials (Desktop application)
    4. Download and save as 'credentials.json'
    5. The script will open browser for initial authentication
    6. Tokens will be saved and refreshed automatically
    """
    import os
    import glob
    import shutil
    import requests
    import whisper
    import numpy as np
    import pickle
    import io
    import time
    import uuid
    import hashlib
    import random  # Added for random font selection
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    from moviepy.editor import (
        ImageClip, concatenate_videoclips, AudioFileClip, CompositeVideoClip
    )
    from moviepy.config import change_settings
    import moviepy.config as moviepy_config
    from moviepy.video.VideoClip import TextClip
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from google.oauth2 import service_account
    from caption_styles import CaptionStyleManager  # Import the caption styles module

    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    SERVICE_ACCOUNT_FILE = 'service-account-key.json'  # Your service account key file
    
    # Create unique session ID for this process to avoid conflicts
    session_id = str(uuid.uuid4())[:8]
    process_hash = hashlib.md5(f"{folder_id}_{on_video_title}_{time.time()}".encode()).hexdigest()[:8]
    unique_id = f"{session_id}_{process_hash}"
    
    print(f"Starting video generation with unique ID: {unique_id}")
    
    # Create unique directories and files for this process
    task_dir = os.path.dirname(output_file)
    images_folder = os.path.join(task_dir, f"downloaded_images_{unique_id}")
    audio_path = os.path.join(task_dir, f"audio_{unique_id}.mp3")
    temp_dir = os.path.join(task_dir, f"temp_{unique_id}")
    
    # Ensure temp directory exists
    os.makedirs(temp_dir, exist_ok=True)
    
    custom_font = "Roboto-Bold.ttf"
    
    # Random font selection from scary_fonts folder
    scary_fonts_folder = "scary_fonts"
    
    def select_random_font():
        """Select a random font from the scary_fonts folder"""
        try:
            # Get all .ttf files from the scary_fonts folder
            font_files = glob.glob(os.path.join(scary_fonts_folder, "*.ttf"))
            
            if not font_files:
                print(f"No .ttf files found in {scary_fonts_folder} folder. Using fallback font.")
                return custom_font
            
            # Select random font
            selected_font = random.choice(font_files)
            print(f"Selected random font: {os.path.basename(selected_font)}")
            return selected_font
            
        except Exception as e:
            print(f"Error selecting random font: {e}. Using fallback font.")
            return custom_font
    
    # Select random title font at the start
    title_font = select_random_font()
    
    target_resolution = (576, 1024)

    def authenticate_drive():
        """
        Authenticate using service account - no browser popup needed!
        This method uses a service account key file for persistent authentication.
        """
        try:
            # Method 1: Service Account Authentication (Recommended)
            credentials = service_account.Credentials.from_service_account_file(
                SERVICE_ACCOUNT_FILE, 
                scopes=SCOPES
            )
            return build('drive', 'v3', credentials=credentials)
        
        except FileNotFoundError:
            print(f"Service account file '{SERVICE_ACCOUNT_FILE}' not found.")
            print("Falling back to OAuth authentication...")
            
            # Method 2: Fallback to improved OAuth with unique token files
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            
            creds = None
            token_file = f'token_{unique_id}.json'  # Unique token file for this process
            
            # Load existing credentials
            if os.path.exists(token_file):
                try:
                    from google.oauth2.credentials import Credentials
                    creds = Credentials.from_authorized_user_file(token_file, SCOPES)
                except Exception as e:
                    print(f"Error loading credentials: {e}")
                    creds = None
            
            # Try loading shared token if unique one doesn't exist
            if not creds and os.path.exists('token.json'):
                try:
                    from google.oauth2.credentials import Credentials
                    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
                    # Save copy for this process
                    if creds and creds.valid:
                        with open(token_file, 'w') as token:
                            token.write(creds.to_json())
                except Exception as e:
                    print(f"Error loading shared credentials: {e}")
                    creds = None
            
            # If credentials are invalid or don't exist, get new ones
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        print("Successfully refreshed credentials!")
                    except Exception as e:
                        print(f"Error refreshing credentials: {e}")
                        creds = None
                
                if not creds:
                    # Use unique port for each process
                    import random
                    port = 8080 + random.randint(1, 100)
                    
                    flow = InstalledAppFlow.from_client_secrets_file(
                        'credentials.json', 
                        SCOPES,
                        redirect_uri=f'http://localhost:{port}'
                    )
                    # Request offline access for refresh tokens
                    creds = flow.run_local_server(
                        port=port,
                        access_type='offline',
                        prompt='consent'  # Forces consent screen to get refresh token
                    )
                
                # Save the credentials for next time
                with open(token_file, 'w') as token:
                    token.write(creds.to_json())
                print(f"Credentials saved to {token_file}")
            
            return build('drive', 'v3', credentials=creds)

    def download_drive_folder(folder_id, image_folder, audio_filename):
        service = authenticate_drive()
        os.makedirs(image_folder, exist_ok=True)
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name, mimeType)").execute()
        files = results.get('files', [])

        for file in files:
            file_id = file['id']
            name = file['name']
            mime = file['mimeType']
            base, ext = os.path.splitext(name)

            if mime == 'image/png':
                if ext.lower() != ".png":
                    name = f"{base}.png"
                out_path = os.path.join(image_folder, name)
            elif mime in ['audio/mpeg', 'application/octet-stream']:
                out_path = audio_filename
            else:
                continue

            request = service.files().get_media(fileId=file_id)
            with open(out_path, 'wb') as f:
                downloader = MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()

    def prepare_base_image(image_path, target_size):
        img = Image.open(image_path).convert("RGB")
        bg = img.resize(target_size).filter(ImageFilter.GaussianBlur(20))
        img.thumbnail(target_size, Image.Resampling.LANCZOS)
        offset = ((target_size[0] - img.width) // 2, (target_size[1] - img.height) // 2)
        bg.paste(img, offset)
        final_path = image_path.replace(".png", f"_noborder_{unique_id}.png")
        bg.save(final_path)
        return final_path

    def create_title_overlay(title, size):
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        max_width = int(size[0] * 0.85)
        max_attempts = 10
        font_size = int(size[1] * 0.055)

        for attempt in range(max_attempts):
            try:
                font = ImageFont.truetype(title_font, font_size)  # Using randomly selected font
            except:
                try:
                    font = ImageFont.truetype(custom_font, font_size)  # Fallback to Roboto
                except:
                    font = ImageFont.load_default()  # Final fallback

            bbox = draw.textbbox((0, 0), title, font=font)
            text_w = bbox[2] - bbox[0]

            if text_w <= max_width:
                break
            font_size -= 2

        bbox = draw.textbbox((0, 0), title, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        # Calculate position for centered text
        x = (size[0] - text_w) // 2
        y = 70

        # Draw title text with randomly selected font - clean and simple
        draw.text((x, y), title, font=font, fill="white")

        title_path = os.path.join(temp_dir, f"title_overlay_{unique_id}.png")
        overlay.save(title_path)
        return title_path

    def blur_transition(clip, blur_duration=1.0):
        def fl(gf, t):
            frame = gf(t)
            alpha = 1.0
            if t < blur_duration:
                alpha = t / blur_duration
            elif t > clip.duration - blur_duration:
                alpha = (clip.duration - t) / blur_duration
            radius = int(20 * (1 - alpha))
            pil_frame = Image.fromarray(frame)
            if radius > 0:
                pil_frame = pil_frame.filter(ImageFilter.GaussianBlur(radius))
            return np.array(pil_frame)
        return clip.fl(fl)

    def generate_captions(audio_path):
        print("Transcribing audio with Whisper...")
        model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        return result["segments"]

    def create_typewriter_word_clip(word, start_time, duration, video_width):
        """Typewriter effect - letters appear one by one"""
        elevation = 120
        
        # Create typewriter effect by showing characters progressively
        def typewriter_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration * 0.1:  # During first 10% of duration
                chars_to_show = int((t / (duration * 0.1)) * len(word))
                partial_word = word[:chars_to_show] + "|"  # Add cursor
                return frame
            return frame
        
        text_clip = TextClip(
            txt=word,
            fontsize=45,
            font=custom_font,
            color="#FFD700",
            method="caption"
        ).set_duration(duration).set_start(start_time)
        
        text_clip = text_clip.set_position(("center", target_resolution[1] - 100 - elevation))
        return text_clip.fadein(0.1).fadeout(0.05)

    def create_glitch_word_clip(word, start_time, duration, video_width):
        """Glitch effect - text flickers with RGB shifts"""
        elevation = 120
        
        def glitch_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration * 0.15:  # Glitch during first 15%
                # Simple glitch simulation by returning frame
                return frame
            return frame
        
        text_clip = TextClip(
            txt=word,
            fontsize=45,
            font=custom_font,
            color="#FF0080",  # Glitch pink color
            method="caption"
        ).set_duration(duration).set_start(start_time)
        
        text_clip = text_clip.set_position(("center", target_resolution[1] - 100 - elevation))
        
        # Quick glitch-like transition
        return text_clip.fadein(0.02).fadeout(0.02)

    def create_slide_bounce_word_clip(word, start_time, duration, video_width):
        """Slide in from left with bounce effect"""
        elevation = 120
        
        text_clip = TextClip(
            txt=word,
            fontsize=45,
            font=custom_font,
            color="#00FF80",  # Bright green
            method="caption"
        ).set_duration(duration).set_start(start_time)
        
        # Slide in from left with bounce
        final_pos = ("center", target_resolution[1] - 100 - elevation)
        slide_duration = min(0.3, duration * 0.3)
        
        # Start position (off-screen left)
        start_pos = (-200, target_resolution[1] - 100 - elevation)
        
        # Create slide animation
        text_clip = text_clip.set_position(lambda t: (
            start_pos[0] + (target_resolution[0]//2 + 200) * min(1, t/slide_duration * 1.2),
            start_pos[1]
        ) if t < slide_duration else final_pos)
        
        return text_clip.fadeout(0.05)

    def create_smoke_reveal_word_clip(word, start_time, duration, video_width):
        """Smoke/fog reveal effect"""
        elevation = 120
        
        text_clip = TextClip(
            txt=word,
            fontsize=45,
            font=custom_font,
            color="#CCCCCC",  # Misty gray
            method="caption"
        ).set_duration(duration).set_start(start_time)
        
        text_clip = text_clip.set_position(("center", target_resolution[1] - 100 - elevation))
        
        # Slow mysterious fade in
        return text_clip.fadein(0.4).fadeout(0.1)

    def create_flash_shake_word_clip(word, start_time, duration, video_width):
        """Flash in with shake effect"""
        elevation = 120
        
        text_clip = TextClip(
            txt=word,
            fontsize=47,  # Slightly larger for impact
            font=custom_font,
            color="#FFFF00",  # Bright yellow for flash
            method="caption"
        ).set_duration(duration).set_start(start_time)
        
        # Add shake effect by slightly varying position
        def shake_position(t):
            if t < 0.2:  # Shake during first 0.2 seconds
                import math
                shake_x = int(3 * math.sin(t * 50))  # Horizontal shake
                shake_y = int(2 * math.sin(t * 60))  # Vertical shake
                return (target_resolution[0]//2 + shake_x, target_resolution[1] - 100 - elevation + shake_y)
            return ("center", target_resolution[1] - 100 - elevation)
        
        text_clip = text_clip.set_position(shake_position)
        
        # Very quick flash-like appearance
        return text_clip.fadein(0.02).fadeout(0.05)

    def create_word_clip_with_random_style(word, start_time, duration, video_width, style_index):
        """Create word clip with randomly selected style"""
        
        styles = [
            create_typewriter_word_clip,
            create_glitch_word_clip,
            create_slide_bounce_word_clip,
            create_smoke_reveal_word_clip,
            create_flash_shake_word_clip
        ]
        
        style_names = [
            "Typewriter Reveal",
            "Glitch Pop-In",
            "Slide + Bounce",
            "Smoke/Fog Reveal",
            "Flash In + Shake"
        ]
        
        selected_style = styles[style_index]
        return selected_style(word, start_time, duration, video_width)

    def create_caption_clips_optimized(segments, video_width):
        """Create precise word-by-word captions with clear-cut transitions"""
        clips = []
        
        for segment in segments:
            words = segment["text"].strip().split()
            if not words:
                continue
                
            # Calculate precise timing for each word - no overlaps
            segment_duration = segment["end"] - segment["start"]
            word_duration = segment_duration / len(words)  # Equal time per word
            
            current_start = segment["start"]
            
            for i, word in enumerate(words):
                # Clean up the word
                word = word.strip()
                if not word:
                    continue
                
                # Create precise word clip with exact timing
                word_clip = create_simple_word_clip(
                    word, 
                    current_start, 
                    word_duration,  # Exact duration, no extension
                    video_width
                )
                
                clips.append(word_clip)
                
                # Move to next word with precise timing - no overlap
                current_start += word_duration
        
        return clips

    def create_background_for_captions(video_width, video_height):
        """Create a simple background for better text readability"""
        bg_height = 150
        bg_y = video_height - bg_height
        
        # Create simple semi-transparent background
        bg_img = Image.new("RGBA", (video_width, bg_height), (0, 0, 0, 80))
        bg_path = os.path.join(task_dir, "caption_background.png")
        bg_img.save(bg_path)
        
        return ImageClip(bg_path).set_duration(999).set_position((0, bg_y))

    # Configure MoviePy settings with unique temp directory
    moviepy_config.change_settings({
        "FFMPEG_BINARY": "ffmpeg",
        "IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe",
        "TEMP_DIR": temp_dir  # Use unique temp directory
    })
    
    # Clean up any existing temporary files for this session
    for file in glob.glob(os.path.join(temp_dir, f"temp_caption_*_{unique_id}.png")):
        try:
            os.remove(file)
        except:
            pass

    # Download content from Google Drive
    download_drive_folder(folder_id, images_folder, audio_path)

    # Prepare images
    image_paths = []
    for i in range(1, 9):
        path = os.path.join(images_folder, f"image_{i}.png")
        styled = prepare_base_image(path, target_resolution)
        image_paths.append(styled)

    # Setup audio and timing
    audio = AudioFileClip(audio_path)
    video_duration = audio.duration
    clip_duration = video_duration / len(image_paths)

    # Create title overlay
    title_overlay_path = create_title_overlay(on_video_title, target_resolution)
    title_clip = ImageClip(title_overlay_path).set_duration(clip_duration).set_position(("center", "top"))

    # Create main video clips
    clips = []
    for path in image_paths:
        bg_clip = ImageClip(path).set_duration(clip_duration).resize(target_resolution)
        bg_blurred = blur_transition(bg_clip)
        comp = CompositeVideoClip([bg_blurred, title_clip.set_duration(clip_duration)])
        clips.append(comp)

    # Combine video clips
    video = concatenate_videoclips(clips, method="compose").set_fps(24)
    video_with_audio = video.set_audio(audio.set_duration(video.duration))

    # Generate captions with optimized performance using modular caption styles
    print("Generating optimized captions...")
    segments = generate_captions(audio_path)
    
    # Initialize caption style manager
    caption_manager = CaptionStyleManager(target_resolution, custom_font)
    
    # Create caption clips with random style
    caption_clips = caption_manager.create_caption_clips(segments, target_resolution[0])
    
    # Combine everything
    final_video = CompositeVideoClip([video_with_audio] + caption_clips)

    # Export final video
    print("Exporting final video with animated captions...")
    final_video.write_videofile(
        output_file, 
        fps=24, 
        codec="libx264", 
        audio_codec="aac",
        preset="medium",
        ffmpeg_params=["-crf", "23"]  # Good quality balance
    )

    # Clean up temporary files for this specific process
    print(f"Cleaning up temporary files for session {unique_id}...")
    
    # Clean caption temp files
    for file in glob.glob(os.path.join(temp_dir, f"temp_caption_*_{unique_id}.png")):
        try:
            os.remove(file)
        except:
            pass
    
    # Clean title overlay
    title_overlay_path = os.path.join(temp_dir, f"title_overlay_{unique_id}.png")
    if os.path.exists(title_overlay_path):
        try:
            os.remove(title_overlay_path)
        except:
            pass
    
    # Clean audio file
    if os.path.exists(audio_path):
        try:
            os.remove(audio_path)
        except:
            pass
    
    # Clean images folder
    if os.path.exists(images_folder):
        try:
            shutil.rmtree(images_folder)
        except:
            pass
    
    # Clean temp directory
    if os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir)
        except:
            pass
    
    # Clean OAuth token file for this process (keep shared token.json)
    token_file = f'token_{unique_id}.json'
    if os.path.exists(token_file):
        try:
            os.remove(token_file)
        except:
            pass
    
    print(f"Video generation completed successfully! Output: {output_file}")
    return output_file