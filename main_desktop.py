#!/usr/bin/env python3
"""UK Train Departure Display - Desktop Window Version"""

import os
import time
import tkinter as tk
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from PIL import Image, ImageDraw, ImageFont, ImageTk

from trains import loadDeparturesForStation
from config import loadConfig
from open import isRun


class BitmapTextCache:
    """Cache for rendered text bitmaps to improve performance"""
    
    def __init__(self) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def get_bitmap(self, text: str, font: ImageFont.FreeTypeFont) -> Tuple[int, int, Image.Image]:
        """Get or create a bitmap for the given text and font"""
        name_tuple = font.getname()
        font_key = ''.join(name_tuple)
        key = text + font_key
        
        if key in self._cache:
            cached = self._cache[key]
            return cached['txt_width'], cached['txt_height'], cached['bitmap']
        
        # Create new bitmap
        _, _, txt_width, txt_height = font.getbbox(text)
        bitmap = Image.new('L', (txt_width, txt_height), color=0)
        draw = ImageDraw.Draw(bitmap)
        draw.text((0, 0), text=text, font=font, fill=255)
        
        self._cache[key] = {
            'bitmap': bitmap,
            'txt_width': txt_width,
            'txt_height': txt_height
        }
        
        return txt_width, txt_height, bitmap


class DepartureBoard:
    """Main departure board display window"""
    
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.root = tk.Tk()
        self.root.title("UK Train Departure Display")
        
        # Display dimensions (2x scale for better visibility)
        self.display_width = 256 * 2
        self.display_height = 64 * 2
        self.scale_factor = 2
        
        # Create canvas for drawing
        self.canvas = tk.Canvas(
            self.root,
            width=self.display_width,
            height=self.display_height,
            bg='black',
            highlightthickness=0
        )
        self.canvas.pack()
        
        # Load fonts
        self._load_fonts()
        
        # Initialize state
        self.bitmap_cache = BitmapTextCache()
        self.current_image: Optional[ImageTk.PhotoImage] = None
        self.canvas_item_id: Optional[int] = None  # Store canvas item ID to reuse
        self.departure_data: Optional[List[Dict[str, Any]]] = None
        self.station_name: str = ""
        
        # Animation state for scrolling text
        self.pixels_left = 1
        self.pixels_up = 0
        self.has_elevated = False
        self.pause_count = 0
        self.station_render_count = 0
        
        # Timing
        self.last_refresh = time.time() - config["refreshTime"]
        
        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        
    def _load_fonts(self) -> None:
        """Load all required fonts"""
        def make_font(name: str, size: int) -> ImageFont.FreeTypeFont:
            font_path = os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    'fonts',
                    name
                )
            )
            return ImageFont.truetype(font_path, size, layout_engine=ImageFont.Layout.BASIC)
        
        self.font = make_font("Dot Matrix Regular.ttf", 10)
        self.font_bold = make_font("Dot Matrix Bold.ttf", 10)
        self.font_bold_tall = make_font("Dot Matrix Bold Tall.ttf", 10)
        self.font_bold_large = make_font("Dot Matrix Bold.ttf", 20)
    
    def _on_close(self) -> None:
        """Handle window close event"""
        self.root.quit()
    
    def render_frame(self) -> None:
        """Render a single frame of the departure board"""
        # Create image buffer
        img = Image.new('RGB', (256, 64), color='black')
        draw = ImageDraw.Draw(img)
        
        # Check if we need to refresh data
        current_time = time.time()
        if current_time - self.last_refresh >= self.config["refreshTime"]:
            self._refresh_data()
            self.last_refresh = current_time
        
        # Draw departure board
        if self.departure_data is None or len(self.departure_data) == 0:
            self._draw_no_trains(draw)
        else:
            self._draw_departures(draw)
        
        # Draw time at bottom
        self._draw_time(draw)
        
        # Scale up the image
        img = img.resize((self.display_width, self.display_height), Image.NEAREST)
        
        # Convert to PhotoImage and display
        self.current_image = ImageTk.PhotoImage(img)

        # Reuse canvas item instead of creating new ones
        if self.canvas_item_id is None:
            # Create canvas item only once
            self.canvas_item_id = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.current_image)
        else:
            # Update existing canvas item
            self.canvas.itemconfig(self.canvas_item_id, image=self.current_image)

    def _refresh_data(self) -> None:
        """Refresh departure data from API"""
        try:
            # Check operating hours
            if self.config["api"]["operatingHours"]:
                hours = self.config["api"]["operatingHours"].split('-')
                if len(hours) == 2:
                    if not isRun(int(hours[0]), int(hours[1])):
                        self.departure_data = []
                        return
            
            # Load data
            departures, station, dest_station = loadDeparturesForStation(
                self.config["journey"],
                self.config["api"]["apiKey"],
                "10"
            )
            
            self.departure_data = departures
            self.station_name = station
            self.root.title(f"{station}{f' to {dest_station}' if dest_station else ''} - Departures")
            
            # Filter by platform if needed
            platform = self.config["journey"]["screen1Platform"]
            if platform:
                self.departure_data = [
                    dep for dep in (self.departure_data or [])
                    if dep.get('platform') == platform
                ]
            
            # Reset animation state
            self.pixels_left = 1
            self.pixels_up = 0
            self.has_elevated = False
            self.pause_count = 0
            self.station_render_count = 0
            
        except Exception as e:
            print(f"Error loading data: {e}")
            self.departure_data = []
    
    def _draw_departures(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw departure information"""
        departures = self.departure_data or []
        if len(departures) == 0:
            return
        
        # First departure (row 1 & 2)
        first_font = self.font_bold if self.config['firstDepartureBold'] else self.font
        self._draw_departure_row(draw, departures[0], 0, first_font, show_calling=True)
        
        # Second departure (row 3)
        if len(departures) > 1:
            self._draw_departure_row(draw, departures[1], 24, self.font, show_calling=False)
        
        # Third departure (row 4)
        if len(departures) > 2:
            self._draw_departure_row(draw, departures[2], 36, self.font, show_calling=False)
    
    def _draw_departure_row(
        self,
        draw: ImageDraw.ImageDraw,
        departure: Dict[str, Any],
        y_pos: int,
        font: ImageFont.FreeTypeFont,
        show_calling: bool = False
    ) -> None:
        """Draw a single departure row"""
        # Time and destination
        time_str = departure["aimed_departure_time"]
        dest_str = departure["destination_name"]
        
        if self.config["showDepartureNumbers"] and y_pos == 0:
            train_text = f"1st  {time_str}  {dest_str}"
        elif self.config["showDepartureNumbers"] and y_pos == 24:
            train_text = f"2nd  {time_str}  {dest_str}"
        elif self.config["showDepartureNumbers"] and y_pos == 36:
            train_text = f"3rd  {time_str}  {dest_str}"
        else:
            train_text = f"{time_str}  {dest_str}"
        
        w, h, bitmap = self.bitmap_cache.get_bitmap(train_text, font)
        self._draw_bitmap(draw, 0, y_pos, bitmap)
        
        # Status
        status_text = self._get_status_text(departure)
        w_status, h_status, status_bitmap = self.bitmap_cache.get_bitmap(status_text, self.font)
        self._draw_bitmap(draw, 256 - w_status, y_pos, status_bitmap)
        
        # Platform (if available)
        if "platform" in departure:
            platform_text = "BUS" if departure["platform"].lower() == "bus" else f"Plat {departure['platform']}"
            w_plat, h_plat, plat_bitmap = self.bitmap_cache.get_bitmap(platform_text, self.font)
            self._draw_bitmap(draw, 256 - w_status - w_plat - 5, y_pos, plat_bitmap)
        
        # Calling at (for first departure only)
        if show_calling:
            calling_text = "Calling at: "
            w_call, h_call, call_bitmap = self.bitmap_cache.get_bitmap(calling_text, self.font)
            self._draw_bitmap(draw, 0, y_pos + 12, call_bitmap)
            
            # Scrolling stations text
            stations = departure["calling_at_list"]
            self._draw_scrolling_text(draw, stations, w_call, y_pos + 12, 256 - w_call)

    def _draw_scrolling_text(
            self,
            draw: ImageDraw.ImageDraw,
            text: str,
            x_offset: int,
            y_pos: int,
            max_width: int
    ) -> None:
        """Draw scrolling text with animation"""
        w, h, bitmap = self.bitmap_cache.get_bitmap(text, self.font)

        if self.has_elevated:
            # Scroll left
            x_pos = x_offset + self.pixels_left - 1
            self._draw_bitmap_clipped(draw, x_pos, y_pos, bitmap, x_offset, max_width)
            if -self.pixels_left > w and self.pause_count < 8:
                self.pause_count += 1
                self.pixels_left = 0
                self.has_elevated = False
            else:
                self.pause_count = 0
                self.pixels_left -= 1
        else:
            # Scroll up
            self._draw_bitmap_clipped(draw, x_offset, y_pos + h - self.pixels_up, bitmap, x_offset, max_width)
            if self.pixels_up == h:
                self.pause_count += 1
                if self.pause_count > 100:
                    self.has_elevated = True
                    self.pixels_up = 0
            else:
                self.pixels_up += 1

    def _draw_bitmap_clipped(
            self,
            draw: ImageDraw.ImageDraw,
            x: int,
            y: int,
            bitmap: Image.Image,
            clip_x_start: int,
            clip_width: int
    ) -> None:
        """Draw a monochrome bitmap with yellow color, clipped to a specific region"""
        pixels = bitmap.load()
        clip_x_end = clip_x_start + clip_width

        # Vertical clipping - only show within the line (y_pos to y_pos + 10)
        clip_y_start = y
        clip_y_end = y + 10  # Each line is 10 pixels tall

        for py in range(bitmap.height):
            for px in range(bitmap.width):
                if pixels[px, py] > 0:
                    screen_x = x + px
                    screen_y = y + py
                    # Only draw if within clip region (both horizontal and vertical) and screen bounds
                    if (clip_x_start <= screen_x < clip_x_end and
                            clip_y_start <= screen_y < clip_y_end and
                            0 <= screen_x < 256 and
                            0 <= screen_y < 22):
                        draw.point((screen_x, screen_y), fill='yellow')
    
    def _draw_bitmap(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        bitmap: Image.Image
    ) -> None:
        """Draw a monochrome bitmap with yellow color"""
        # Convert bitmap to yellow on black
        pixels = bitmap.load()
        for py in range(bitmap.height):
            for px in range(bitmap.width):
                if pixels[px, py] > 0:
                    if 0 <= x + px < 256 and 0 <= y + py < 64:
                        draw.point((x + px, y + py), fill='yellow')
    
    def _get_status_text(self, departure: Dict[str, Any]) -> str:
        """Get status text for a departure"""
        expected = departure["expected_departure_time"]
        aimed = departure["aimed_departure_time"]
        
        if expected == "On time":
            return "On time"
        elif expected == "Cancelled":
            return "Cancelled"
        elif expected == "Delayed":
            return "Delayed"
        elif isinstance(expected, str) and expected != aimed:
            return f"Exp {expected}"
        else:
            return "On time"
    
    def _draw_no_trains(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw 'no trains' message"""
        station_text = self.station_name or self.config["journey"].get("outOfHoursName", "")
        
        # Welcome to
        text1 = "Welcome to"
        w1, h1, bmp1 = self.bitmap_cache.get_bitmap(text1, self.font_bold)
        self._draw_bitmap(draw, (256 - w1) // 2, 5, bmp1)
        
        # Station name
        w2, h2, bmp2 = self.bitmap_cache.get_bitmap(station_text, self.font_bold)
        self._draw_bitmap(draw, (256 - w2) // 2, 17, bmp2)
        
        # No trains message
        text3 = "No trains scheduled"
        w3, h3, bmp3 = self.bitmap_cache.get_bitmap(text3, self.font)
        self._draw_bitmap(draw, (256 - w3) // 2, 35, bmp3)
    
    def _draw_time(self, draw: ImageDraw.ImageDraw) -> None:
        """Draw current time at bottom of display"""
        now = datetime.now().time()
        hour, minute, second = str(now).split('.')[0].split(':')
        
        hm_text = f"{hour}:{minute}"
        s_text = f":{second}"
        
        w1, h1, hm_bitmap = self.bitmap_cache.get_bitmap(hm_text, self.font_bold_large)
        w2, h2, s_bitmap = self.bitmap_cache.get_bitmap(s_text, self.font_bold_tall)
        
        total_width = w1 + w2
        start_x = (256 - total_width) // 2
        
        self._draw_bitmap(draw, start_x, 50, hm_bitmap)
        self._draw_bitmap(draw, start_x + w1, 55, s_bitmap)
    
    def update(self) -> None:
        """Update the display (called by animation loop)"""
        self.render_frame()
        self.root.after(int(1000 / self.config["targetFPS"]), self.update)
    
    def run(self) -> None:
        """Start the application"""
        print("Starting UK Train Departure Display (Desktop Version)")
        print(f"Station: {self.config['journey']['departureStation']}")
        if self.config['journey']['destinationStation']:
            print(f"Filtered to: {self.config['journey']['destinationStation']}")
        
        # Initial data load
        self._refresh_data()
        
        # Start animation loop
        self.root.after(0, self.update)
        
        # Run main loop
        self.root.mainloop()


def main() -> None:
    """Main entry point"""
    try:
        config = loadConfig()
        
        # Validate configuration
        if not config["api"]["apiKey"]:
            print("Error: Please configure the apiKey environment variable")
            return
        
        if not config["journey"]["departureStation"]:
            print("Error: Please configure the departureStation environment variable")
            return
        
        # Create and run the departure board
        board = DepartureBoard(config)
        board.run()
        
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
