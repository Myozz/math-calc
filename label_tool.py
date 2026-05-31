"""
Multi-class Label Tool for Valorant AI
Label head and body for enemy detection

Controls:
- Left Click + Drag: Draw bounding box
- 1: Set class to HEAD (red box)
- 2: Set class to BODY (blue box)
- N: Next image
- P: Previous image
- D: Delete last box
- S: Save and next
- Q: Quit
- Mouse Scroll: Zoom in/out
- Right Click + Drag: Pan zoomed image
- R: Reset zoom
"""

import cv2
import os
import glob
import numpy as np

# Directories
IMAGE_DIR = "images"
LABEL_DIR = "labels"
os.makedirs(LABEL_DIR, exist_ok=True)

# Classes
CLASSES = {
    0: ("head", (0, 0, 255)),    # Red
    1: ("body", (255, 0, 0)),    # Blue
}

class LabelTool:
    def __init__(self):
        self.images = sorted(glob.glob(os.path.join(IMAGE_DIR, "*.jpg")))
        self.images += sorted(glob.glob(os.path.join(IMAGE_DIR, "*.png")))
        
        if not self.images:
            print("No images found in", IMAGE_DIR)
            return
            
        print(f"Found {len(self.images)} images")
        
        self.current_idx = 0
        self.current_class = 0  # Default: head
        self.boxes = []  # [(class_id, x1, y1, x2, y2), ...]
        self.drawing = False
        self.panning = False
        self.start_point = None
        self.pan_start = None
        
        # Zoom parameters
        self.zoom_level = 1.0
        self.zoom_center_x = 0
        self.zoom_center_y = 0
        self.offset_x = 0
        self.offset_y = 0
        
        # Find first unlabeled image
        for i, img_path in enumerate(self.images):
            label_path = self.get_label_path(img_path)
            if not os.path.exists(label_path):
                self.current_idx = i
                break
        
        self.load_current()
        
    def get_label_path(self, img_path):
        basename = os.path.splitext(os.path.basename(img_path))[0]
        return os.path.join(LABEL_DIR, basename + ".txt")
    
    def load_current(self):
        """Load current image and its labels"""
        self.image = cv2.imread(self.images[self.current_idx])
        self.display = self.image.copy()
        self.h, self.w = self.image.shape[:2]
        self.boxes = []
        
        # Reset zoom
        self.zoom_level = 1.0
        self.offset_x = 0
        self.offset_y = 0
        
        # Load existing labels
        label_path = self.get_label_path(self.images[self.current_idx])
        if os.path.exists(label_path):
            with open(label_path, 'r') as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 5:
                        cls = int(parts[0])
                        cx, cy, bw, bh = map(float, parts[1:])
                        # Convert YOLO format to pixel coordinates
                        x1 = int((cx - bw/2) * self.w)
                        y1 = int((cy - bh/2) * self.h)
                        x2 = int((cx + bw/2) * self.w)
                        y2 = int((cy + bh/2) * self.h)
                        self.boxes.append((cls, x1, y1, x2, y2))
        
        self.update_display()
    
    def screen_to_image(self, sx, sy):
        """Convert screen coordinates to image coordinates"""
        ix = int(sx / self.zoom_level + self.offset_x)
        iy = int(sy / self.zoom_level + self.offset_y)
        return ix, iy
    
    def image_to_screen(self, ix, iy):
        """Convert image coordinates to screen coordinates"""
        sx = int((ix - self.offset_x) * self.zoom_level)
        sy = int((iy - self.offset_y) * self.zoom_level)
        return sx, sy
    
    def update_display(self):
        """Update display with boxes and zoom"""
        # Draw boxes on image
        img_with_boxes = self.image.copy()
        
        for cls, x1, y1, x2, y2 in self.boxes:
            color = CLASSES[cls][1]
            label = CLASSES[cls][0]
            cv2.rectangle(img_with_boxes, (x1, y1), (x2, y2), color, 2)
            cv2.putText(img_with_boxes, label, (x1, y1-5), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        
        # Apply zoom
        if self.zoom_level != 1.0:
            # Calculate visible region
            view_w = int(self.w / self.zoom_level)
            view_h = int(self.h / self.zoom_level)
            
            # Clamp offset
            self.offset_x = max(0, min(self.offset_x, self.w - view_w))
            self.offset_y = max(0, min(self.offset_y, self.h - view_h))
            
            # Crop and resize
            x1 = int(self.offset_x)
            y1 = int(self.offset_y)
            x2 = int(x1 + view_w)
            y2 = int(y1 + view_h)
            
            cropped = img_with_boxes[y1:y2, x1:x2]
            self.display = cv2.resize(cropped, (self.w, self.h), interpolation=cv2.INTER_LINEAR)
        else:
            self.display = img_with_boxes
        
        # Status bar
        zoom_str = f"Zoom: {self.zoom_level:.1f}x" if self.zoom_level != 1.0 else ""
        status = f"[{self.current_idx+1}/{len(self.images)}] "
        status += f"Class: {CLASSES[self.current_class][0].upper()} | "
        status += f"Boxes: {len(self.boxes)} | {zoom_str}"
        
        cv2.putText(self.display, status, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # Help text
        help_text = "1=Head 2=Body N/P=Navigate D=Del S=Save R=ResetZoom Q=Quit"
        cv2.putText(self.display, help_text, (10, self.h - 10), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        cv2.imshow("Label Tool", self.display)
    
    def save_labels(self):
        """Save labels in YOLO format"""
        label_path = self.get_label_path(self.images[self.current_idx])
        with open(label_path, 'w') as f:
            for cls, x1, y1, x2, y2 in self.boxes:
                # Convert to YOLO format (normalized)
                cx = (x1 + x2) / 2 / self.w
                cy = (y1 + y2) / 2 / self.h
                bw = (x2 - x1) / self.w
                bh = (y2 - y1) / self.h
                f.write(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n")
        print(f"Saved {len(self.boxes)} boxes to {label_path}")
    
    def mouse_callback(self, event, x, y, flags, param):
        # Scroll to zoom
        if event == cv2.EVENT_MOUSEWHEEL:
            # Get mouse position in image coords before zoom
            old_ix, old_iy = self.screen_to_image(x, y)
            
            # Zoom in/out
            if flags > 0:
                self.zoom_level = min(5.0, self.zoom_level * 1.2)
            else:
                self.zoom_level = max(1.0, self.zoom_level / 1.2)
            
            if self.zoom_level == 1.0:
                self.offset_x = 0
                self.offset_y = 0
            else:
                # Adjust offset to keep mouse position stable
                new_ix, new_iy = self.screen_to_image(x, y)
                self.offset_x += old_ix - new_ix
                self.offset_y += old_iy - new_iy
            
            self.update_display()
            return
        
        # Right button to pan
        if event == cv2.EVENT_RBUTTONDOWN:
            self.panning = True
            self.pan_start = (x, y)
            return
        
        if event == cv2.EVENT_RBUTTONUP:
            self.panning = False
            return
        
        if event == cv2.EVENT_MOUSEMOVE and self.panning:
            dx = (self.pan_start[0] - x) / self.zoom_level
            dy = (self.pan_start[1] - y) / self.zoom_level
            self.offset_x += dx
            self.offset_y += dy
            self.pan_start = (x, y)
            self.update_display()
            return
        
        # Left button to draw boxes
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            # Convert screen coords to image coords
            ix, iy = self.screen_to_image(x, y)
            self.start_point = (ix, iy)
            
        elif event == cv2.EVENT_MOUSEMOVE:
            if self.drawing:
                temp = self.display.copy()
                color = CLASSES[self.current_class][1]
                # Convert start point to screen coords
                sx1, sy1 = self.image_to_screen(*self.start_point)
                cv2.rectangle(temp, (sx1, sy1), (x, y), color, 2)
                cv2.imshow("Label Tool", temp)
                
        elif event == cv2.EVENT_LBUTTONUP:
            if self.drawing:
                self.drawing = False
                ix, iy = self.screen_to_image(x, y)
                x1, y1 = self.start_point
                x2, y2 = ix, iy
                
                # Ensure x1 < x2, y1 < y2
                if x1 > x2: x1, x2 = x2, x1
                if y1 > y2: y1, y2 = y2, y1
                
                # Clamp to image bounds
                x1 = max(0, min(x1, self.w))
                y1 = max(0, min(y1, self.h))
                x2 = max(0, min(x2, self.w))
                y2 = max(0, min(y2, self.h))
                
                # Minimum size check
                if x2 - x1 > 5 and y2 - y1 > 5:
                    self.boxes.append((self.current_class, x1, y1, x2, y2))
                
                self.update_display()
    
    def run(self):
        cv2.namedWindow("Label Tool")
        cv2.setMouseCallback("Label Tool", self.mouse_callback)
        
        print("\n=== Label Tool Started ===")
        print("1=Head, 2=Body, N=Next, P=Prev, D=Delete, S=Save&Next, Q=Quit")
        print("Scroll to zoom, Middle-click+drag to pan, R to reset zoom")
        
        while True:
            self.update_display()
            key = cv2.waitKey(1) & 0xFF
            
            if key == ord('1'):
                self.current_class = 0  # Head
                print("Class: HEAD")
                
            elif key == ord('2'):
                self.current_class = 1  # Body
                print("Class: BODY")
                
            elif key == ord('n'):
                if self.current_idx < len(self.images) - 1:
                    self.current_idx += 1
                    self.load_current()
                    
            elif key == ord('p'):
                if self.current_idx > 0:
                    self.current_idx -= 1
                    self.load_current()
                    
            elif key == ord('d'):
                if self.boxes:
                    self.boxes.pop()
                    self.update_display()
                    
            elif key == ord('s'):
                self.save_labels()
                if self.current_idx < len(self.images) - 1:
                    self.current_idx += 1
                    self.load_current()
                    
            elif key == ord('r'):
                # Reset zoom
                self.zoom_level = 1.0
                self.offset_x = 0
                self.offset_y = 0
                self.update_display()
                print("Zoom reset")
                    
            elif key == ord('q'):
                break
        
        cv2.destroyAllWindows()
        print(f"\nLabeling complete!")
        print(f"Labels saved to: {LABEL_DIR}/")

if __name__ == "__main__":
    tool = LabelTool()
    if tool.images:
        tool.run()
