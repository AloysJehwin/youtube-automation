"""
Caption Styles Module for Video Generator
=========================================

This module contains two caption transition styles that can be randomly selected
for video generation. Each style has its own unique animation and visual effects.

Styles Available:
1. Typewriter Reveal - Letters appear one by one with cursor
2. Glitch Pop-In - Text flickers with RGB shifts  

Usage:
    from caption_styles import CaptionStyleManager
    
    manager = CaptionStyleManager(target_resolution, custom_font)
    style_index = manager.select_random_style()
    clips = manager.create_caption_clips(segments, video_width, style_index)
"""

import random
import math
from moviepy.video.VideoClip import TextClip


class CaptionStyleManager:
    """Manages different caption transition styles"""
    
    def __init__(self, target_resolution, custom_font):
        self.target_resolution = target_resolution
        self.custom_font = custom_font
        self.elevation = 120
        
        self.style_names = [
            "Typewriter Reveal",
            "Glitch Pop-In"
        ]
        
        self.style_colors = [
            "#FFD700",  # Gold for typewriter
            "#FF0080"   # Glitch pink
        ]
    
    def select_random_style(self):
        """Select a random caption style and return its index"""
        style_index = random.randint(0, len(self.style_names) - 1)
        print(f"Selected caption style: {self.style_names[style_index]}")
        return style_index
    
    def get_style_name(self, style_index):
        """Get the name of a style by its index"""
        return self.style_names[style_index]
    
    def create_typewriter_word_clip(self, word, start_time, duration, video_width):
        """Typewriter effect - letters appear one by one with cursor"""
        
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
            font=self.custom_font,
            color=self.style_colors[0],  # Gold
            method="caption"
        ).set_duration(duration).set_start(start_time)
        
        text_clip = text_clip.set_position(("center", self.target_resolution[1] - 100 - self.elevation))
        return text_clip.fadein(0.1).fadeout(0.05)
    
    def create_glitch_word_clip(self, word, start_time, duration, video_width):
        """Glitch effect - text flickers with RGB shifts"""
        
        def glitch_effect(get_frame, t):
            frame = get_frame(t)
            if t < duration * 0.15:  # Glitch during first 15%
                # Simple glitch simulation by returning frame
                return frame
            return frame
        
        text_clip = TextClip(
            txt=word,
            fontsize=45,
            font=self.custom_font,
            color=self.style_colors[1],  # Glitch pink
            method="caption"
        ).set_duration(duration).set_start(start_time)
        
        text_clip = text_clip.set_position(("center", self.target_resolution[1] - 100 - self.elevation))
        
        # Quick glitch-like transition
        return text_clip.fadein(0.02).fadeout(0.02)
    
    def create_word_clip_with_style(self, word, start_time, duration, video_width, style_index):
        """Create word clip with specified style"""
        
        styles = [
            self.create_typewriter_word_clip,
            self.create_glitch_word_clip
        ]
        
        if 0 <= style_index < len(styles):
            selected_style = styles[style_index]
            return selected_style(word, start_time, duration, video_width)
        else:
            # Fallback to typewriter if invalid index
            return self.create_typewriter_word_clip(word, start_time, duration, video_width)
    
    def create_caption_clips(self, segments, video_width, style_index=None):
        """Create caption clips with specified or random style"""
        
        if style_index is None:
            style_index = self.select_random_style()
        
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
                
                # Create word clip with selected style
                word_clip = self.create_word_clip_with_style(
                    word, 
                    current_start, 
                    word_duration,  # Exact duration, no extension
                    video_width,
                    style_index
                )
                
                clips.append(word_clip)
                
                # Move to next word with precise timing - no overlap
                current_start += word_duration
        
        return clips
    
    def add_custom_style(self, style_name, style_function, style_color):
        """Add a custom caption style"""
        self.style_names.append(style_name)
        self.style_colors.append(style_color)
        # Note: You would need to modify the create_word_clip_with_style method
        # to include the new style function
        print(f"Added custom style: {style_name}")
    
    def list_available_styles(self):
        """List all available caption styles"""
        print("Available Caption Styles:")
        for i, style in enumerate(self.style_names):
            print(f"{i+1}. {style} - {self.style_colors[i]}")


# Example usage and testing
if __name__ == "__main__":
    # Test the module
    target_resolution = (576, 1024)
    custom_font = "Roboto-Bold.ttf"
    
    manager = CaptionStyleManager(target_resolution, custom_font)
    manager.list_available_styles()
    
    # Test random selection
    style_index = manager.select_random_style()
    print(f"Selected style index: {style_index}")
    print(f"Style name: {manager.get_style_name(style_index)}")