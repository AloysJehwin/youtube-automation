def generate_video_from_drive(folder_id, on_video_title, output_file, task_path):
    import os
    import glob
    import shutil
    import requests
    import whisper
    import numpy as np
    import pickle
    import io
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    from moviepy.editor import (
        ImageClip, concatenate_videoclips, AudioFileClip, CompositeVideoClip
    )
    from moviepy.config import change_settings
    import moviepy.config as moviepy_config
    from moviepy.video.VideoClip import TextClip
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    from google_auth_oauthlib.flow import InstalledAppFlow

    SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
    task_dir = os.path.dirname(output_file)
    images_folder = os.path.join(task_dir, "downloaded_images")
    audio_path = os.path.join(task_dir, "audio.mp3")
    custom_font = "Roboto-Bold.ttf"
    target_resolution = (576, 1024)

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
        final_path = image_path.replace(".png", "_noborder.png")
        bg.save(final_path)
        return final_path

    def create_title_overlay(title, size):
        overlay = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        max_width = int(size[0] * 0.9)  # 90% of width (e.g. 518 px)
        max_attempts = 10
        font_size = int(size[1] * 0.045)

        # Try reducing font size until text fits
        for attempt in range(max_attempts):
            try:
                font = ImageFont.truetype(custom_font, font_size)
            except:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), title, font=font)
            text_w = bbox[2] - bbox[0]

            if text_w <= max_width:
                break
            font_size -= 2  # Reduce font size gradually

        # Final bounding box and padding
        bbox = draw.textbbox((0, 0), title, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        pad_x, pad_y = 80, 40
        box_w, box_h = text_w + pad_x, text_h + pad_y
        x = (size[0] - box_w) // 2
        y = 50

        # Create rounded background box
        box = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
        draw_box = ImageDraw.Draw(box)
        draw_box.rounded_rectangle([(0, 0), (box_w, box_h)], radius=30, fill=(0, 0, 0, 128))
        overlay.paste(box, (x, y), box)

        # Draw final text
        draw.text((x + pad_x // 2, y + pad_y // 2), title, font=font, fill="white")

        title_path = os.path.join(task_dir, "title_overlay.png")
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
        elevation = 120
        for segment in segments:
            words = segment["text"].split()
            word_duration = (segment["end"] - segment["start"]) / len(words)
            current_start = segment["start"]
            full_text = ""
            for word in words:
                full_text += word + " "
                caption_path = os.path.join(task_dir, f"temp_caption_{len(clips)}.png")
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

    moviepy_config.change_settings({
        "FFMPEG_BINARY": "ffmpeg",
        "IMAGEMAGICK_BINARY": r"C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe",
        "TEMP_DIR": task_path  # <= This line is the fix
            })
    for file in glob.glob(os.path.join(task_dir, "temp_caption_*.png")):
        os.remove(file)

    download_drive_folder(folder_id, images_folder, audio_path)

    image_paths = []
    for i in range(1, 9):
        path = os.path.join(images_folder, f"image_{i}.png")
        styled = prepare_base_image(path, target_resolution)
        image_paths.append(styled)

    audio = AudioFileClip(audio_path)
    video_duration = audio.duration
    clip_duration = video_duration / len(image_paths)

    title_overlay_path = create_title_overlay(on_video_title, target_resolution)
    title_clip = ImageClip(title_overlay_path).set_duration(clip_duration).set_position(("center", "top"))

    clips = []
    for path in image_paths:
        bg_clip = ImageClip(path).set_duration(clip_duration).resize(target_resolution)
        bg_blurred = blur_transition(bg_clip)
        comp = CompositeVideoClip([bg_blurred, title_clip.set_duration(clip_duration)])
        clips.append(comp)

    video = concatenate_videoclips(clips, method="compose").set_fps(24)
    video_with_audio = video.set_audio(audio.set_duration(video.duration))

    segments = generate_captions(audio_path)
    caption_clips = create_caption_clips_typing(segments, target_resolution[0])
    final_video = CompositeVideoClip([video_with_audio] + caption_clips)

    final_video.write_videofile(output_file, fps=24, codec="libx264", audio_codec="aac")

    for file in glob.glob(os.path.join(task_dir, "temp_caption_*.png")):
        os.remove(file)
    if os.path.exists(os.path.join(task_dir, "title_overlay.png")):
        os.remove(os.path.join(task_dir, "title_overlay.png"))
    if os.path.exists(audio_path):
        os.remove(audio_path)
    if os.path.exists(images_folder):
        shutil.rmtree(images_folder)

    return output_file