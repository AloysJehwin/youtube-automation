import os
import requests
import numpy as np
from moviepy.editor import (
    ImageClip, concatenate_videoclips, AudioFileClip,
    CompositeVideoClip
)
from moviepy.video.VideoClip import TextClip
from moviepy.video.fx.all import resize
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import whisper
from moviepy.config import change_settings
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle
import io
import glob
import shutil


# -------- CLEANUP TEMP FILES --------
for file in glob.glob("temp_caption_*.png"):
    os.remove(file)

# -------- CONFIGURE IMAGEMAGICK PATH --------
change_settings({"IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"})

# -------- SETTINGS --------
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
folder_id = "1E6KK9cKpHvpn6Q8TKLe2z4150amKXdQe"  # Replace with your actual Drive folder ID
images_folder = "downloaded_images"
audio_path = "audio.mp3"
on_video_title = "Emerging from Darkness"
output_file = "shorts_video.mp4"
target_resolution = (576, 1024)
custom_font = "Roboto-Bold.ttf"  # Ensure this is in the directory

# -------- GOOGLE DRIVE FUNCTIONS --------
def authenticate_drive():
    creds = None
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
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

        # Extract name and extension
        base, ext = os.path.splitext(name)

        if mime == 'image/png':
            # Ensure correct extension
            if ext.lower() != ".png":
                name = f"{base}.png"
            out_path = os.path.join(image_folder, name)

        elif mime in ['audio/mpeg', 'application/octet-stream']:
            # Save audio with the desired audio filename
            out_path = audio_filename

        else:
            continue  # Skip unsupported files

        request = service.files().get_media(fileId=file_id)
        with open(out_path, 'wb') as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

    print(f"✅ Download complete: {len(files)} files")


# -------- UTILS --------
def prepare_base_image(image_path, target_size):
    img = Image.open(image_path).convert("RGB")
    bg = img.resize(target_size).filter(ImageFilter.GaussianBlur(20))
    img.thumbnail(target_size, Image.Resampling.LANCZOS)
    offset = ((target_size[0] - img.width) // 2, (target_size[1] - img.height) // 2)
    bg.paste(img, offset)
    final_path = image_path.replace(".jpg", "_noborder.png")
    bg.save(final_path)
    return final_path

def create_title_overlay(title, size):
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = int(size[1] * 0.045)

    try:
        font = ImageFont.truetype(custom_font, font_size)
    except:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), title, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x, pad_y = 80, 40
    box_w, box_h = text_w + pad_x, text_h + pad_y
    x = (size[0] - box_w) // 2
    y = 50

    box = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw_box = ImageDraw.Draw(box)
    draw_box.rounded_rectangle([(0, 0), (box_w, box_h)], radius=30, fill=(0, 0, 0, 128))
    overlay.paste(box, (x, y), box)
    draw.text((x + pad_x // 2, y + pad_y // 2), title, font=font, fill="white")

    title_path = "title_overlay.png"
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

def create_caption_clips_typing(segments, video_width):
    clips = []
    max_width = video_width - 100
    elevation = 40

    for segment in segments:
        words = segment["text"].split()
        word_duration = (segment["end"] - segment["start"]) / len(words)
        current_start = segment["start"]
        full_text = ""

        for word in words:
            full_text += word + " "
            text_clip = TextClip(
                txt=full_text.strip(),
                fontsize=40,
                font=custom_font,
                color="white",
                size=(max_width, None),
                method="caption"
            ).set_start(current_start).set_duration(word_duration)

            text_clip = text_clip.set_position(
                lambda t: (
                    "center",
                    target_resolution[1] - text_clip.size[1] - elevation
                )
            )
            clips.append(text_clip)
            current_start += word_duration

    return clips

# -------- DOWNLOAD DATA --------
download_drive_folder(folder_id, images_folder, audio_path)

# -------- IMAGE PROCESSING --------
image_paths = []
print("Styling downloaded images...")
for i in range(1, 9):
    path = f"{images_folder}/image_{i}.png"
    styled = prepare_base_image(path, target_resolution)
    image_paths.append(styled)

# -------- AUDIO SETUP --------
audio = AudioFileClip(audio_path)
video_duration = audio.duration
clip_duration = video_duration / len(image_paths)

# -------- TITLE SETUP --------
title_overlay_path = create_title_overlay(on_video_title, target_resolution)
title_clip = ImageClip(title_overlay_path).set_duration(clip_duration).set_position(("center", "top"))

# -------- VIDEO CREATION --------
clips = []
for path in image_paths:
    bg_clip = ImageClip(path).set_duration(clip_duration).resize(target_resolution)
    bg_blurred = blur_transition(bg_clip)
    comp = CompositeVideoClip([bg_blurred, title_clip.set_duration(clip_duration)])
    clips.append(comp)

video = concatenate_videoclips(clips, method="compose").set_fps(24)
video_with_audio = video.set_audio(audio.set_duration(video.duration))

# -------- CAPTION SETUP --------
segments = generate_captions(audio_path)
caption_clips = create_caption_clips_typing(segments, target_resolution[0])
final_video = CompositeVideoClip([video_with_audio] + caption_clips)

# -------- EXPORT --------
print("Exporting final video...")
final_video.write_videofile(output_file, fps=24, audio_codec="aac")
print("✅ Done! Saved as:", output_file)
print("Cleaning up temporary files...")

# Delete temp caption images
for file in glob.glob("temp_caption_*.png"):
    os.remove(file)

# Delete title overlay
if os.path.exists("title_overlay.png"):
    os.remove("title_overlay.png")

# Delete downloaded audio
if os.path.exists(audio_path):
    os.remove(audio_path)

# Delete styled + raw downloaded images folder
if os.path.exists(images_folder):
    shutil.rmtree(images_folder)

print("🧹 Cleanup complete.")
