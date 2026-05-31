"""
Valorant Screenshot Capture Tool
Press F9 to capture screenshots for AI training
Press ESC to exit
"""

import cv2
import os
import time
import win32api
from datetime import datetime
from PIL import ImageGrab
import numpy as np

# Create output directory
OUTPUT_DIR = "images"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Keys
KEY_CAPTURE = 0x06  # F key
KEY_EXIT = 0x7B  # F12

def main():
    print("=" * 50)
    print("Valorant Screenshot Capture Tool")
    print("=" * 50)
    print(f"Screenshots will be saved to: {OUTPUT_DIR}")
    print("\nControls:")
    print("  F   - Capture screenshot")
    print("  F12 - Exit")
    print("\n[Ready] Point crosshair at enemies and press Side click")
    print("=" * 50)
    
    capture_count = 0
    f9_pressed = False
    
    try:
        while True:
            # Check for exit
            if win32api.GetAsyncKeyState(KEY_EXIT) & 0x8000:
                print("\n[Exit] Captured", capture_count, "screenshots")
                break
            
            # Check for capture
            if win32api.GetAsyncKeyState(KEY_CAPTURE) & 0x8000:
                if not f9_pressed:
                    # Use PIL ImageGrab instead of bettercam
                    screenshot = ImageGrab.grab()
                    frame = np.array(screenshot)
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                    
                    # Generate filename
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    filename = f"valorant_{timestamp}.jpg"
                    filepath = os.path.join(OUTPUT_DIR, filename)
                    
                    # Save
                    cv2.imwrite(filepath, frame_bgr)
                    capture_count += 1
                    print(f"[Captured] {filename} (Total: {capture_count})")
                    
                    f9_pressed = True
            else:
                f9_pressed = False
            
            time.sleep(0.01)
            
    except KeyboardInterrupt:
        pass
    
    print(f"\n[Done] Saved {capture_count} screenshots to {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
