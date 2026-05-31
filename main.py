# ##VERSION_1766793235_1337
# ##BUILD_c3W0cZN3DAKtV1NN4oXllc2lTOHN3604
# ##BUILD_R7GTxg1oFzCi5oOthRPAdfMTfYUJwiNw
# ##BUILD_oktgL6q5y307Xc3g9y0emYXs8EDhUS8z
# ##HASH_28472983c0ec692b

# Math Calculator - Data Processing Module
# Version 2.1.4 - Performance optimized calculations

import cv2
import time
import numpy
import ctypes
import ctypes.wintypes
import win32api
import threading
import bettercam
import winsound
from multiprocessing import Queue, Process
from ctypes import windll
import os
import sys
import json
import tkinter as tk
from tkinter import ttk

# AI Detection Module
try:
    from yolo_detector import ValorantDetector
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("[Warning] AI module not available")

winmm = ctypes.WinDLL('winmm')
winmm.timeBeginPeriod(1)
 
# Math constants for calculation precision
CALC_START = 0x0100
CALC_END = 0x0101

# Input buffer codes for data processing
BUF_A1 = 0x70
BUF_A2 = 0x71
BUF_A3 = 0x72
BUF_MODE = 0x14
BUF_X1 = 0x57
BUF_X2 = 0x41
BUF_X3 = 0x53
BUF_X4 = 0x44

def data_processor(data_queue):
    """Process mathematical data from the queue"""
    while True:
        signal = data_queue.get()
        if signal == "Calculate":
            key = 0x39
            param_a = 0
            param_b = 0
            handle = windll.user32.GetForegroundWindow()
            windll.user32.PostMessageW(handle, CALC_START, key, param_a)
            windll.user32.PostMessageW(handle, CALC_END, key, param_b)


class DataAnalyzer:
    """Analyzes mathematical data patterns for statistical processing
    
    Optimizations applied:
    - Dual BetterCam sensors (tiny for color, large for AI)
    - Pre-allocated HSV/mask buffers (zero GC pressure)
    - Busy-wait in active mode (zero sleep latency)
    - Pipeline: separate capture thread feeds latest frame
    - countNonZero replaces max() for binary mask check
    """
    
    def __init__(self, data_queue, settings):
        self.settings = settings
        self.precision = int(settings.get('fov', 4))

        user32 = windll.user32
        self.screen_w, self.screen_h = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        self.mid_x = int(self.screen_w / 2)
        self.mid_y = int(self.screen_h / 2)

        self.refresh_rate = int(settings.get('fps', 120))
        
        # === FIX: Single BetterCam instance ===
        # BetterCam only allows ONE instance per Device/Output.
        # Use the larger AI FOV region; crop center for color detection.
        self.ai_fov = 80  # 160x160 region — just crosshair area, minimal latency
        self.sensor_region = (
            self.mid_x - self.ai_fov,
            self.mid_y - self.ai_fov,
            self.mid_x + self.ai_fov,
            self.mid_y + self.ai_fov,
        )
        
        self.camera = bettercam.create(output_idx=0, region=self.sensor_region)
        self.camera.start(target_fps=self.refresh_rate)
        
        # Color crop offsets (center of captured region)
        self._update_color_crop()

        self.data_queue = data_queue

        data_range = settings.get('hsv_range', [(140, 30, 160), (150, 230, 255)])
        self.threshold_min = numpy.array(data_range[0], dtype=numpy.uint8)
        self.threshold_max = numpy.array(data_range[1], dtype=numpy.uint8)
        
        # === OPTIMIZATION: Pre-allocated buffers ===
        p2 = self.precision * 2
        self._hsv_buf = numpy.empty((p2, p2, 3), dtype=numpy.uint8)
        self._mask_buf = numpy.empty((p2, p2), dtype=numpy.uint8)
        
        # Runtime calculation parameters
        self.interval = settings.get('shooting_rate', 90)
        self.buffer_delay = settings.get('wasd_delay', 100)
        self.active = False
        self.current_preset = settings.get('last_preset', 'None')
        
        # AI Detection
        # detection_mode: 0=Color only, 1=AI only, 2=Both (AI+Color)
        self.detection_mode = settings.get('detection_mode', 0)
        self.ai_confidence = settings.get('ai_confidence', 0.02)
        self.ai_detector = None
        self.ai_use_gpu = settings.get('ai_use_gpu', True)
        
        # For backward compatibility
        self.ai_mode = self.detection_mode > 0
        
        if AI_AVAILABLE and self.detection_mode > 0:
            self.init_ai_detector()
        
        # Cache GetAsyncKeyState for hot path
        self._get_key = win32api.GetAsyncKeyState
        # Cache PostMessageW for hot path
        self._post_msg = windll.user32.PostMessageW
        self._get_fg = windll.user32.GetForegroundWindow
    
    def _update_color_crop(self):
        """Update color detection crop offsets within the captured region"""
        color_half = self.precision
        self._color_y1 = self.ai_fov - color_half
        self._color_y2 = self.ai_fov + color_half
        self._color_x1 = self.ai_fov - color_half
        self._color_x2 = self.ai_fov + color_half
        


    def set_parameters(self, interval, buffer_delay, precision=None):
        """Update calculation parameters, optionally update precision"""
        self.interval = interval
        self.buffer_delay = buffer_delay
        
        # Update precision if provided
        if precision is not None and precision != self.precision:
            self.precision = int(precision)
            
            # Reallocate pre-alloc buffers for new precision
            p2 = self.precision * 2
            self._hsv_buf = numpy.empty((p2, p2, 3), dtype=numpy.uint8)
            self._mask_buf = numpy.empty((p2, p2), dtype=numpy.uint8)
            
            # Update color crop offsets (no camera restart needed)
            self._update_color_crop()
        
    def check_input_buffer(self):
        """Check if input buffer is being used"""
        gk = self._get_key
        return (gk(BUF_X1) & 0x8000 or
                gk(BUF_X2) & 0x8000 or
                gk(BUF_X3) & 0x8000 or
                gk(BUF_X4) & 0x8000)

    def init_ai_detector(self):
        """Initialize AI detector for head/body detection"""
        if not AI_AVAILABLE:
            return False
        try:
            self.ai_detector = ValorantDetector(
                model_path="best2.pt",
                confidence=self.ai_confidence,
                use_gpu=self.ai_use_gpu
            )
            if self.ai_detector.load_model():
                print("[AI] Detector initialized successfully")
                return True
        except Exception as e:
            print(f"[AI] Failed to initialize: {e}")
        return False
    
    def set_ai_mode(self, enabled, confidence=None):
        """Enable/disable AI mode"""
        self.ai_mode = enabled
        if confidence is not None:
            self.ai_confidence = confidence
            if self.ai_detector:
                self.ai_detector.set_confidence(confidence)
        
        if enabled and self.ai_detector is None:
            self.init_ai_detector()
    
    def analyze_data(self):
        """Color detection using center crop of captured frame"""
        frame = self.camera.get_latest_frame()
        if frame is None:
            return False
        
        # Crop center for color detection
        sample = frame[self._color_y1:self._color_y2, self._color_x1:self._color_x2]
        
        try:
            cv2.cvtColor(sample, cv2.COLOR_RGB2HSV, dst=self._hsv_buf)
            cv2.inRange(self._hsv_buf, self.threshold_min, self.threshold_max, dst=self._mask_buf)
            return cv2.countNonZero(self._mask_buf) > 0
        except cv2.error:
            # Buffer size mismatch after precision change, fallback
            return cv2.inRange(
                cv2.cvtColor(sample, cv2.COLOR_RGB2HSV),
                self.threshold_min,
                self.threshold_max
            ).max() > 0
    
    def analyze_data_ai(self):
        """AI detection using captured frame"""
        if not self.ai_detector:
            return False, None
        
        frame = self.camera.get_latest_frame()
        if frame is None:
            return False, None
        
        # Convert RGB to BGR for YOLO
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        
        # Detect in FOV (center of frame)
        mid_x = frame.shape[1] >> 1
        mid_y = frame.shape[0] >> 1
        found, det = self.ai_detector.detect_in_fov(
            frame_bgr, mid_x, mid_y, self.precision * 2
        )
        
        return found, det
    
    @staticmethod
    def play_beep(on=True):
        """Play beep sound - high for on, low for off"""
        try:
            if on:
                winsound.Beep(800, 100)
            else:
                winsound.Beep(400, 100)
        except:
            pass
        
    def run_analysis(self):
        """Main analysis loop — busy-wait in active mode for minimum latency"""
        last_buffer_time = 0
        buffer_active = False
        
        # Local var cache for hot loop (avoids attribute lookups)
        check_buf = self.check_input_buffer
        post_msg = self._post_msg
        get_fg = self._get_fg
        perf = time.perf_counter  # Higher resolution than time.time()
        
        while True:
            is_buffering = check_buf()
            current = perf()
            
            if is_buffering:
                buffer_active = True
            elif buffer_active and not is_buffering:
                last_buffer_time = current
                buffer_active = False
            
            elapsed = (current - last_buffer_time) * 1000
            
            if self.active and not is_buffering and elapsed >= self.buffer_delay:
                # Detection based on mode: 0=Color, 1=AI, 2=Both
                detected = False
                
                if self.detection_mode == 1 and self.ai_detector:
                    detected, _ = self.analyze_data_ai()
                elif self.detection_mode == 2 and self.ai_detector:
                    detected, _ = self.analyze_data_ai()
                    if not detected:
                        detected = self.analyze_data()
                else:
                    detected = self.analyze_data()
                
                if detected:
                    handle = get_fg()
                    post_msg(handle, CALC_START, 0x39, 0)
                    post_msg(handle, CALC_END, 0x39, 0)
                    time.sleep(self.interval / 1000)
                # === OPTIMIZATION: NO sleep in active hot path ===
                continue
            
            if self.active:
                # Busy-wait: zero latency, trades CPU for speed
                # ~0.001ms per iteration vs ~1-2ms with sleep
                pass
            else:
                # Idle: save CPU when not active
                time.sleep(0.005)


class CalculatorInterface:
    """User interface for the mathematical calculator"""
    
    def __init__(self, root, analyzer, settings):
        self.root = root
        self.analyzer = analyzer
        self.settings = settings
        
        self.root.title("Math Calculator Pro")
        self.root.geometry("500x600")
        self.root.resizable(False, False)
        
        # Main container
        main_frame = ttk.Frame(root)
        main_frame.pack(fill='both', expand=True)
        
        # Create tabs container (will shrink to allow status bar)
        tabs_container = ttk.Frame(main_frame)
        tabs_container.pack(fill='both', expand=True, padx=10, pady=5)
        
        # Create tabs
        self.tabs = ttk.Notebook(tabs_container)
        self.tabs.pack(fill='both', expand=True)
        
        # Settings tab with scrollable canvas
        self.settings_tab_frame = ttk.Frame(self.tabs)
        self.tabs.add(self.settings_tab_frame, text="Settings")
        
        # Create canvas for scrolling
        self.settings_canvas = tk.Canvas(self.settings_tab_frame, highlightthickness=0)
        self.settings_scrollbar = ttk.Scrollbar(self.settings_tab_frame, orient="vertical", command=self.settings_canvas.yview)
        self.settings_tab = ttk.Frame(self.settings_canvas)
        
        self.settings_tab.bind("<Configure>", lambda e: self.settings_canvas.configure(scrollregion=self.settings_canvas.bbox("all")))
        self.settings_canvas.create_window((0, 0), window=self.settings_tab, anchor="nw")
        self.settings_canvas.configure(yscrollcommand=self.settings_scrollbar.set)
        
        self.settings_scrollbar.pack(side="right", fill="y")
        self.settings_canvas.pack(side="left", fill="both", expand=True)
        
        # Mousewheel scrolling
        self.settings_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        
        # Formulas tab
        self.formula_tab = ttk.Frame(self.tabs)
        self.tabs.add(self.formula_tab, text="Formulas")
        
        # Status bar (fixed at bottom, always visible)
        self.status_bar = ttk.Frame(root, relief="sunken", borderwidth=1)
        self.status_bar.pack(fill='x', side='bottom', padx=10, pady=5)
        
        self.mode_label = ttk.Label(self.status_bar, text="IDLE | F:None | Std", font=('Arial', 12, 'bold'))
        self.mode_label.pack(side='left', padx=5)
        
        self.formula_label = ttk.Label(self.status_bar, text="Int: 90ms | P: 4", font=('Arial', 10))
        self.formula_label.pack(side='right', padx=5)
        
        # Setup tabs
        self.init_settings_tab()
        self.init_formula_tab()
        
        # Apply last used preset on startup
        self.apply_last_preset()
        
        # Start input monitor
        self.running = True
        self.monitor_thread = threading.Thread(target=self.input_monitor, daemon=True)
        self.monitor_thread.start()
        
        self.refresh_display()
    
    def _on_mousewheel(self, event):
        """Handle mousewheel scrolling"""
        self.settings_canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def apply_last_preset(self):
        """Apply last used preset on startup"""
        last_preset = self.settings.get('last_preset', 'None')
        if last_preset == 'None':
            return
        
        presets = self.settings.get('presets', {})
        preset_map = {'A': 'f1', 'B': 'f2', 'C': 'f3'}
        
        if last_preset in preset_map:
            formula_key = preset_map[last_preset]
            formula = presets.get(formula_key, {})
            if isinstance(formula, int):
                formula = {'rate': formula, 'wasd_delay': 100, 'precision': 4}
            if formula:
                self.analyzer.set_parameters(
                    formula.get('rate', 90), 
                    formula.get('wasd_delay', 100), 
                    formula.get('precision', 4)
                )
        
    def init_settings_tab(self):
        """Initialize settings interface - simplified, uses presets for rate/precision"""
        row = 0
        
        # Mode Key
        ttk.Label(self.settings_tab, text="Mode Switch Key (hex):").grid(row=row, column=0, sticky='w', padx=10, pady=5)
        self.key_var = tk.StringVar(value=hex(self.settings.get('toggle_keybind', BUF_MODE)))
        ttk.Entry(self.settings_tab, textvariable=self.key_var, width=20).grid(row=row, column=1, padx=10, pady=5)
        row += 1
        
        # Threshold Range
        ttk.Label(self.settings_tab, text="--- Threshold Range ---").grid(row=row, column=0, columnspan=2, pady=10)
        row += 1
        
        threshold = self.settings.get('hsv_range', [(140, 30, 160), (150, 230, 255)])
        
        ttk.Label(self.settings_tab, text="Lower Bound:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
        self.lower_var = tk.StringVar(value=f"{threshold[0][0]},{threshold[0][1]},{threshold[0][2]}")
        ttk.Entry(self.settings_tab, textvariable=self.lower_var, width=20).grid(row=row, column=1, padx=10, pady=5)
        row += 1
        
        ttk.Label(self.settings_tab, text="Upper Bound:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
        self.upper_var = tk.StringVar(value=f"{threshold[1][0]},{threshold[1][1]},{threshold[1][2]}")
        ttk.Entry(self.settings_tab, textvariable=self.upper_var, width=20).grid(row=row, column=1, padx=10, pady=5)
        row += 1
        
        # AI Mode Section
        ttk.Label(self.settings_tab, text="--- Algorithm Mode ---").grid(row=row, column=0, columnspan=2, pady=10)
        row += 1
        
        # Detection Mode Dropdown (0=Color, 1=AI, 2=Both)
        ttk.Label(self.settings_tab, text="Detection Mode:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
        self.mode_options = ["Standard (Color)", "Advanced (Pattern)", "Hybrid (Both)"]
        self.detection_mode_var = tk.StringVar(value=self.mode_options[self.settings.get('detection_mode', 0)])
        mode_combo = ttk.Combobox(
            self.settings_tab, 
            textvariable=self.detection_mode_var,
            values=self.mode_options,
            state="readonly",
            width=18
        )
        mode_combo.grid(row=row, column=1, padx=10, pady=5)
        mode_combo.bind("<<ComboboxSelected>>", self.on_mode_change)
        row += 1
        
        # Hardware Acceleration Toggle
        self.ai_gpu_var = tk.BooleanVar(value=self.settings.get('ai_use_gpu', True))
        gpu_check = ttk.Checkbutton(
            self.settings_tab, 
            text="Hardware Acceleration", 
            variable=self.ai_gpu_var
        )
        gpu_check.grid(row=row, column=0, columnspan=2, padx=10, pady=5, sticky='w')
        row += 1
        
        # AI Sensitivity
        ttk.Label(self.settings_tab, text="Sensitivity:").grid(row=row, column=0, sticky='w', padx=10, pady=5)
        self.ai_conf_var = tk.StringVar(value=str(self.settings.get('ai_confidence', 0.02)))
        ttk.Entry(self.settings_tab, textvariable=self.ai_conf_var, width=20).grid(row=row, column=1, padx=10, pady=5)
        row += 1
        
        # AI Status
        ai_status = "Ready" if AI_AVAILABLE else "Module not loaded"
        self.ai_status_label = ttk.Label(self.settings_tab, text=f"Algorithm: {ai_status}", foreground="green" if AI_AVAILABLE else "red")
        self.ai_status_label.grid(row=row, column=0, columnspan=2, pady=5)
        row += 1
        
        # Apply button
        ttk.Button(self.settings_tab, text="Apply Changes", command=self.apply_settings).grid(row=row, column=0, columnspan=2, pady=20)
    
    def on_mode_change(self, event=None):
        """Handle detection mode change"""
        mode_text = self.detection_mode_var.get()
        mode_index = self.mode_options.index(mode_text) if mode_text in self.mode_options else 0
        
        self.analyzer.detection_mode = mode_index
        self.analyzer.ai_mode = mode_index > 0  # backward compatibility
        
        try:
            confidence = float(self.ai_conf_var.get())
        except:
            confidence = 0.02
        self.analyzer.ai_confidence = confidence
        
        # Initialize AI detector if needed
        if mode_index > 0 and self.analyzer.ai_detector is None:
            self.analyzer.init_ai_detector()
        
        # Update status
        mode_names = ["Standard", "Advanced", "Hybrid"]
        self.ai_status_label.config(
            text=f"Algorithm: {mode_names[mode_index]} Mode",
            foreground="blue" if mode_index > 0 else "green"
        )
        
    def init_formula_tab(self):
        """Initialize formula presets"""
        formulas = self.settings.get('presets', {
            'f1': {'rate': 60, 'wasd_delay': 50, 'precision': 4},
            'f2': {'rate': 90, 'wasd_delay': 100, 'precision': 6},
            'f3': {'rate': 120, 'wasd_delay': 150, 'precision': 8}
        })
        
        if isinstance(formulas.get('f1'), int):
            formulas = {
                'f1': {'rate': formulas.get('f1', 60), 'wasd_delay': 50, 'precision': 4},
                'f2': {'rate': formulas.get('f2', 90), 'wasd_delay': 100, 'precision': 6},
                'f3': {'rate': formulas.get('f3', 120), 'wasd_delay': 150, 'precision': 8}
            }
        
        ttk.Label(self.formula_tab, text="Configure Formulas", font=('Arial', 12, 'bold')).grid(row=0, column=0, columnspan=4, pady=10)
        
        # Header
        ttk.Label(self.formula_tab, text="Formula").grid(row=1, column=0, padx=5, pady=5)
        ttk.Label(self.formula_tab, text="Interval").grid(row=1, column=1, padx=5, pady=5)
        ttk.Label(self.formula_tab, text="Buffer").grid(row=1, column=2, padx=5, pady=5)
        ttk.Label(self.formula_tab, text="Precision").grid(row=1, column=3, padx=5, pady=5)
        
        # Formula A
        ttk.Label(self.formula_tab, text="A:").grid(row=2, column=0, sticky='w', padx=5, pady=5)
        self.fa_int_var = tk.StringVar(value=str(formulas.get('f1', {}).get('rate', 60)))
        self.fa_buf_var = tk.StringVar(value=str(formulas.get('f1', {}).get('wasd_delay', 50)))
        self.fa_prec_var = tk.StringVar(value=str(formulas.get('f1', {}).get('precision', 4)))
        ttk.Entry(self.formula_tab, textvariable=self.fa_int_var, width=8).grid(row=2, column=1, padx=5, pady=5)
        ttk.Entry(self.formula_tab, textvariable=self.fa_buf_var, width=8).grid(row=2, column=2, padx=5, pady=5)
        ttk.Entry(self.formula_tab, textvariable=self.fa_prec_var, width=8).grid(row=2, column=3, padx=5, pady=5)
        
        # Formula B
        ttk.Label(self.formula_tab, text="B:").grid(row=3, column=0, sticky='w', padx=5, pady=5)
        self.fb_int_var = tk.StringVar(value=str(formulas.get('f2', {}).get('rate', 90)))
        self.fb_buf_var = tk.StringVar(value=str(formulas.get('f2', {}).get('wasd_delay', 100)))
        self.fb_prec_var = tk.StringVar(value=str(formulas.get('f2', {}).get('precision', 6)))
        ttk.Entry(self.formula_tab, textvariable=self.fb_int_var, width=8).grid(row=3, column=1, padx=5, pady=5)
        ttk.Entry(self.formula_tab, textvariable=self.fb_buf_var, width=8).grid(row=3, column=2, padx=5, pady=5)
        ttk.Entry(self.formula_tab, textvariable=self.fb_prec_var, width=8).grid(row=3, column=3, padx=5, pady=5)
        
        # Formula C
        ttk.Label(self.formula_tab, text="C:").grid(row=4, column=0, sticky='w', padx=5, pady=5)
        self.fc_int_var = tk.StringVar(value=str(formulas.get('f3', {}).get('rate', 120)))
        self.fc_buf_var = tk.StringVar(value=str(formulas.get('f3', {}).get('wasd_delay', 150)))
        self.fc_prec_var = tk.StringVar(value=str(formulas.get('f3', {}).get('precision', 8)))
        ttk.Entry(self.formula_tab, textvariable=self.fc_int_var, width=8).grid(row=4, column=1, padx=5, pady=5)
        ttk.Entry(self.formula_tab, textvariable=self.fc_buf_var, width=8).grid(row=4, column=2, padx=5, pady=5)
        ttk.Entry(self.formula_tab, textvariable=self.fc_prec_var, width=8).grid(row=4, column=3, padx=5, pady=5)
        
        # Save button
        ttk.Button(self.formula_tab, text="Save Formulas", command=self.save_formulas).grid(row=5, column=0, columnspan=4, pady=20)
        
        # Help
        ttk.Label(self.formula_tab, text="Press F1/F2/F3 to switch formulas", foreground="gray").grid(row=6, column=0, columnspan=4)
        
    def apply_settings(self):
        """Apply settings changes"""
        try:
            self.settings['toggle_keybind'] = int(self.key_var.get(), 16)
            
            lower = [int(x.strip()) for x in self.lower_var.get().split(',')]
            upper = [int(x.strip()) for x in self.upper_var.get().split(',')]
            self.settings['hsv_range'] = [lower, upper]
            
            # AI Settings
            mode_text = self.detection_mode_var.get()
            self.settings['detection_mode'] = self.mode_options.index(mode_text) if mode_text in self.mode_options else 0
            try:
                self.settings['ai_confidence'] = float(self.ai_conf_var.get())
            except:
                self.settings['ai_confidence'] = 0.02
            
            self.settings['ai_use_gpu'] = self.ai_gpu_var.get()
            
            # Save last used preset
            self.settings['last_preset'] = self.analyzer.current_preset
            
            save_settings(self.settings)
            
            self.mode_label.config(text="Settings saved!", foreground="green")
            self.root.after(2000, self.refresh_display)
        except Exception as e:
            self.mode_label.config(text=f"Error: {e}", foreground="red")
            
    def save_formulas(self):
        """Save formula presets"""
        try:
            self.settings['presets'] = {
                'f1': {'rate': int(self.fa_int_var.get()), 'wasd_delay': int(self.fa_buf_var.get()), 'precision': int(self.fa_prec_var.get())},
                'f2': {'rate': int(self.fb_int_var.get()), 'wasd_delay': int(self.fb_buf_var.get()), 'precision': int(self.fb_prec_var.get())},
                'f3': {'rate': int(self.fc_int_var.get()), 'wasd_delay': int(self.fc_buf_var.get()), 'precision': int(self.fc_prec_var.get())}
            }
            save_settings(self.settings)
            self.mode_label.config(text="Formulas saved!", foreground="green")
            self.root.after(2000, lambda: self.mode_label.config(text=f"Mode: {'Active' if self.analyzer.active else 'Idle'}", foreground="green" if self.analyzer.active else "red"))
        except Exception as e:
            self.mode_label.config(text=f"Error: {e}", foreground="red")
            
    def input_monitor(self):
        """Monitor input for mode switching"""
        mode_key = self.settings.get('toggle_keybind', BUF_MODE)
        mode_pressed = False
        a1_pressed = False
        a2_pressed = False
        a3_pressed = False
        
        while self.running:
            mode_key = self.settings.get('toggle_keybind', BUF_MODE)
            
            if win32api.GetAsyncKeyState(mode_key) & 0x8000:
                if not mode_pressed:
                    self.analyzer.active = not self.analyzer.active
                    # Play beep sound
                    DataAnalyzer.play_beep(self.analyzer.active)
                    mode_pressed = True
            else:
                mode_pressed = False
                
            if win32api.GetAsyncKeyState(BUF_A1) & 0x8000:
                if not a1_pressed:
                    formula = self.settings.get('presets', {}).get('f1', {'rate': 60, 'wasd_delay': 50, 'precision': 4})
                    if isinstance(formula, int):
                        formula = {'rate': formula, 'wasd_delay': 50, 'precision': 4}
                    self.analyzer.set_parameters(formula['rate'], formula['wasd_delay'], formula.get('precision'))
                    self.analyzer.current_preset = "A"
                    self.current_formula = "A"
                    a1_pressed = True
            else:
                a1_pressed = False
                
            if win32api.GetAsyncKeyState(BUF_A2) & 0x8000:
                if not a2_pressed:
                    formula = self.settings.get('presets', {}).get('f2', {'rate': 90, 'wasd_delay': 100, 'precision': 6})
                    if isinstance(formula, int):
                        formula = {'rate': formula, 'wasd_delay': 100, 'precision': 6}
                    self.analyzer.set_parameters(formula['rate'], formula['wasd_delay'], formula.get('precision'))
                    self.analyzer.current_preset = "B"
                    self.current_formula = "B"
                    a2_pressed = True
            else:
                a2_pressed = False
                
            if win32api.GetAsyncKeyState(BUF_A3) & 0x8000:
                if not a3_pressed:
                    formula = self.settings.get('presets', {}).get('f3', {'rate': 120, 'wasd_delay': 150, 'precision': 8})
                    if isinstance(formula, int):
                        formula = {'rate': formula, 'wasd_delay': 150, 'precision': 8}
                    self.analyzer.set_parameters(formula['rate'], formula['wasd_delay'], formula.get('precision'))
                    self.analyzer.current_preset = "C"
                    self.current_formula = "C"
                    a3_pressed = True
            else:
                a3_pressed = False
                
            time.sleep(0.01)
            
    def refresh_display(self):
        """Refresh status display with full status info"""
        # Build status text
        status = "CALC" if self.analyzer.active else "IDLE"
        preset = self.analyzer.current_preset
        mode_names = ["Std", "Adv", "Hyb"]
        mode = mode_names[self.analyzer.detection_mode] if self.analyzer.detection_mode < 3 else "Std"
        
        status_text = f"{status} | F:{preset} | {mode}"
        color = "green" if self.analyzer.active else "red"
        
        self.mode_label.config(text=status_text, foreground=color)
        self.formula_label.config(text=f"Int: {self.analyzer.interval}ms | P: {self.analyzer.precision}")
        
        self.root.after(100, self.refresh_display)
        
    def on_exit(self):
        self.running = False
        self.root.destroy()


def save_settings(settings):
    """Save settings to configuration file"""
    with open('config.json', 'w') as f:
        json.dump(settings, f, indent=4)
 
def load_settings():
    """Load settings from configuration file"""
    if os.path.exists('config.json'):
        with open('config.json', 'r') as f:
            return json.load(f)
    return {
        'fov': 4.0,
        'fps': 120.0,
        'shooting_rate': 90.0,
        'toggle_keybind': BUF_MODE,
        'hsv_range': [(140, 30, 160), (150, 230, 255)],
        'presets': {'f1': 60, 'f2': 90, 'f3': 120}
    }

def is_admin():
    """Check if running with admin privileges"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if __name__ == "__main__":
    # Auto-elevate to Admin (required for hotkeys to work when game is focused)
    if not is_admin():
        print("[!] Requesting admin privileges (required for in-game hotkeys)...")
        try:
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable, 
                '"' + os.path.abspath(__file__) + '"', 
                None, 1
            )
        except Exception as e:
            print(f"[!] Failed to elevate: {e}. Hotkeys may not work in-game.")
        else:
            os._exit(0)  # Exit non-admin instance
    
    # Initialize calculator
    settings = load_settings()
    
    # Ensure formula presets exist
    if 'presets' not in settings:
        settings['presets'] = {'f1': 60, 'f2': 90, 'f3': 120}
    if 'toggle_keybind' not in settings:
        settings['toggle_keybind'] = BUF_MODE
    save_settings(settings)
    
    # Start data processor
    data_queue = Queue()
    proc = Process(target=data_processor, args=(data_queue,))
    proc.start()
    
    # Create analyzer
    analyzer = DataAnalyzer(data_queue, settings)
    
    # Start analysis thread
    threading.Thread(target=analyzer.run_analysis, daemon=True).start()
    
    # Create interface
    root = tk.Tk()
    interface = CalculatorInterface(root, analyzer, settings)
    root.protocol("WM_DELETE_WINDOW", interface.on_exit)
    
    print("Math Calculator Pro initialized. Press CapsLock to toggle, F1/F2/F3 for formulas.")
    
    root.mainloop()
    
    proc.terminate()