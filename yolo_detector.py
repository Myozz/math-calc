"""
YOLO Detector - Optimized for maximum speed
Supports PyTorch (.pt), ONNX (.onnx), and TensorRT (.engine) backends
GPU-accelerated inference with FP16 precision
"""

from ultralytics import YOLO
import numpy as np
import cv2
import torch
import os

class ValorantDetector:
    # Engine file path (pre-exported TensorRT model)
    ENGINE_PATH = "best2.engine"
    PT_PATH = "best2.pt"
    
    def __init__(self, model_path="best2.pt", confidence=0.02, use_gpu=True):
        """
        Initialize YOLO detector with automatic backend selection.
        Priority: TensorRT .engine > PyTorch .pt
        
        Args:
            model_path: Path to trained model (.pt or .engine)
            confidence: Minimum confidence threshold
            use_gpu: Use GPU if available
        """
        self.confidence = confidence
        self.model = None
        self.class_names = {0: 'head', 1: 'body'}
        self.use_gpu = use_gpu
        self.device = self._get_device()
        
        # Auto-select best backend
        if os.path.exists(self.ENGINE_PATH) and self.device == 0:
            self.model_path = self.ENGINE_PATH
            self._backend = "TensorRT"
        else:
            self.model_path = model_path
            self._backend = "PyTorch"
        
        # Inference settings optimized for speed
        self._imgsz = 160  # Match 160x160 capture region — no resize needed
        self._use_half = self.device == 0  # FP16 only on GPU
        
    def _get_device(self):
        """Determine device to use"""
        if self.use_gpu and torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            print(f"[AI] GPU available: {device_name}")
            return 0  # GPU
        else:
            if self.use_gpu:
                print("[AI] GPU requested but not available, using CPU")
            else:
                print("[AI] Using CPU mode")
            return 'cpu'
        
    def load_model(self):
        """Load the YOLO model with warmup"""
        try:
            self.model = YOLO(self.model_path, task='detect')
            self.class_names = self.model.names
            
            print(f"[AI] Backend: {self._backend}")
            print(f"[AI] Loaded: {self.model_path} on {'GPU' if self.device == 0 else 'CPU'}")
            print(f"[AI] Classes: {self.class_names}")
            print(f"[AI] imgsz={self._imgsz}, half={self._use_half}")
            
            # Warmup: first inference is slow, do it now
            self._warmup()
            
            return True
        except Exception as e:
            print(f"[AI] Failed to load model: {e}")
            # Fallback to PyTorch if TensorRT fails
            if self._backend == "TensorRT":
                print("[AI] Falling back to PyTorch backend...")
                self.model_path = self.PT_PATH
                self._backend = "PyTorch"
                try:
                    self.model = YOLO(self.model_path, task='detect')
                    self.class_names = self.model.names
                    self._warmup()
                    return True
                except Exception as e2:
                    print(f"[AI] Fallback also failed: {e2}")
            return False
    
    def _warmup(self):
        """Run dummy inference to warm up the model (CUDA kernel compilation, etc.)"""
        if self.model is None:
            return
        dummy = np.zeros((self._imgsz, self._imgsz, 3), dtype=np.uint8)
        for _ in range(3):  # 3 warmup passes
            self.model.predict(
                dummy,
                conf=self.confidence,
                verbose=False,
                device=self.device,
                imgsz=self._imgsz,
                half=self._use_half,
            )
        print("[AI] Warmup complete")
    
    def is_loaded(self):
        """Check if model is loaded"""
        return self.model is not None
    
    def set_device(self, use_gpu):
        """Switch between CPU and GPU"""
        self.use_gpu = use_gpu
        self.device = self._get_device()
        self._use_half = self.device == 0
        return self.device != 'cpu'
    
    def detect(self, frame):
        """
        Detect head/body in frame - optimized for minimal latency
        Returns: list of detection dicts
        """
        if self.model is None:
            return []
        
        # Run inference (speed-optimized settings)
        results = self.model.predict(
            frame, 
            conf=self.confidence, 
            verbose=False,
            device=self.device,
            imgsz=self._imgsz,
            half=self._use_half,
            agnostic_nms=True,
            max_det=10,  # Limit max detections for speed
        )
        
        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is None or len(boxes) == 0:
                continue
                
            # Batch extract all values at once (faster than per-box loop)
            cls_all = boxes.cls.int().tolist()
            conf_all = boxes.conf.tolist()
            xyxy_all = boxes.xyxy.int().tolist()
            
            for cls, conf, (x1, y1, x2, y2) in zip(cls_all, conf_all, xyxy_all):
                detections.append({
                    'class_id': cls,
                    'class_name': self.class_names[cls],
                    'confidence': conf,
                    'x': x1,
                    'y': y1,
                    'w': x2 - x1,
                    'h': y2 - y1,
                    'center_x': (x1 + x2) >> 1,  # Bitshift for speed
                    'center_y': (y1 + y2) >> 1,
                })
        
        # Sort by priority: head first, then by confidence
        detections.sort(key=lambda d: (d['class_id'], -d['confidence']))
        
        return detections
    
    def detect_in_fov(self, frame, fov_x, fov_y, fov_size):
        """
        Check if there's a detection within FOV (for triggerbot)
        Returns: (bool, detection_dict or None)
        """
        detections = self.detect(frame)
        
        if not detections:
            return False, None
        
        for det in detections:
            cx, cy = det['center_x'], det['center_y']
            if (abs(cx - fov_x) <= fov_size and 
                abs(cy - fov_y) <= fov_size):
                return True, det
        
        return False, None
    
    def set_confidence(self, confidence):
        """Update confidence threshold"""
        self.confidence = confidence
    
    def get_device_info(self):
        """Get current device info"""
        backend = f" [{self._backend}]" if self._backend else ""
        if self.device == 0:
            return f"GPU ({torch.cuda.get_device_name(0)}){backend}"
        return f"CPU{backend}"
