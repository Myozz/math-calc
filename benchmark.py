"""
Performance Benchmark - measures latency for each detection path
Run this to verify optimizations are working correctly
"""

import time
import numpy as np
import cv2
import sys

def benchmark_color_detection():
    """Benchmark HSV color detection with pre-allocated buffers"""
    print("\n=== Color Detection Benchmark ===")
    
    # Simulate a small frame (8x8 = precision*2)
    precision = 4
    p2 = precision * 2
    frame = np.random.randint(0, 255, (p2, p2, 3), dtype=np.uint8)
    
    threshold_min = np.array([140, 30, 160], dtype=np.uint8)
    threshold_max = np.array([150, 230, 255], dtype=np.uint8)
    
    # Pre-allocated buffers
    hsv_buf = np.empty((p2, p2, 3), dtype=np.uint8)
    mask_buf = np.empty((p2, p2), dtype=np.uint8)
    
    iterations = 10000
    
    # Method 1: Original (allocate each time + max())
    start = time.perf_counter()
    for _ in range(iterations):
        result = cv2.inRange(
            cv2.cvtColor(frame, cv2.COLOR_RGB2HSV),
            threshold_min,
            threshold_max
        ).max() > 0
    old_time = (time.perf_counter() - start) / iterations * 1000
    
    # Method 2: Optimized (pre-alloc + countNonZero)
    start = time.perf_counter()
    for _ in range(iterations):
        cv2.cvtColor(frame, cv2.COLOR_RGB2HSV, dst=hsv_buf)
        cv2.inRange(hsv_buf, threshold_min, threshold_max, dst=mask_buf)
        result = cv2.countNonZero(mask_buf) > 0
    new_time = (time.perf_counter() - start) / iterations * 1000
    
    print(f"  Original (alloc+max):     {old_time:.4f} ms/iter")
    print(f"  Optimized (prealloc+cnz): {new_time:.4f} ms/iter")
    print(f"  Speedup: {old_time/new_time:.2f}x ({(old_time-new_time)*1000:.1f} us saved)")


def benchmark_timer_resolution():
    """Benchmark time.time() vs time.perf_counter()"""
    print("\n=== Timer Resolution Benchmark ===")
    
    iterations = 100000
    
    start = time.perf_counter()
    for _ in range(iterations):
        t = time.time()
    time_time = (time.perf_counter() - start) / iterations * 1000000  # nanoseconds
    
    start = time.perf_counter()
    for _ in range(iterations):
        t = time.perf_counter()
    perf_time = (time.perf_counter() - start) / iterations * 1000000  # nanoseconds
    
    print(f"  time.time():         {time_time:.1f} ns/call")
    print(f"  time.perf_counter(): {perf_time:.1f} ns/call")


def benchmark_sleep_accuracy():
    """Benchmark actual sleep durations"""
    print("\n=== Sleep Accuracy Benchmark ===")
    
    for target_ms in [0.5, 1.0, 5.0, 10.0]:
        times = []
        for _ in range(100):
            start = time.perf_counter()
            time.sleep(target_ms / 1000)
            actual = (time.perf_counter() - start) * 1000
            times.append(actual)
        avg = sum(times) / len(times)
        print(f"  sleep({target_ms}ms): actual avg = {avg:.2f}ms (overhead: +{avg-target_ms:.2f}ms)")
    
    # Busy-wait benchmark
    times = []
    for _ in range(100):
        start = time.perf_counter()
        while (time.perf_counter() - start) < 0.0005:
            pass
        actual = (time.perf_counter() - start) * 1000
        times.append(actual)
    avg = sum(times) / len(times)
    print(f"  busy-wait(0.5ms): actual avg = {avg:.4f}ms")


def benchmark_yolo_inference():
    """Benchmark YOLO inference speed (PT vs TensorRT)"""
    print("\n=== YOLO Inference Benchmark ===")
    
    try:
        import torch
        if not torch.cuda.is_available():
            print("  [SKIP] CUDA not available")
            return
        print(f"  GPU: {torch.cuda.get_device_name(0)}")
    except ImportError:
        print("  [SKIP] PyTorch not installed")
        return
    
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  [SKIP] Ultralytics not installed")
        return
    
    import os
    
    # Test frame (300x300 like AI sensor region)
    test_frame = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)
    warmup = 5
    iterations = 50
    
    # Benchmark each available model
    models_to_test = []
    if os.path.exists("best2.pt"):
        models_to_test.append(("PyTorch (.pt)", "best2.pt"))
    if os.path.exists("best2.engine"):
        models_to_test.append(("TensorRT (.engine)", "best2.engine"))
    
    for name, path in models_to_test:
        print(f"\n  --- {name}: {path} ---")
        model = YOLO(path)
        
        # Warmup
        for _ in range(warmup):
            model.predict(test_frame, conf=0.02, verbose=False, device=0, imgsz=160, half=True)
        
        # Benchmark
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            model.predict(test_frame, conf=0.02, verbose=False, device=0, imgsz=160, half=True, agnostic_nms=True, max_det=10)
            elapsed = (time.perf_counter() - start) * 1000
            times.append(elapsed)
        
        avg = sum(times) / len(times)
        min_t = min(times)
        max_t = max(times)
        p95 = sorted(times)[int(0.95 * len(times))]
        
        print(f"  Avg:  {avg:.2f} ms")
        print(f"  Min:  {min_t:.2f} ms")
        print(f"  Max:  {max_t:.2f} ms")
        print(f"  P95:  {p95:.2f} ms")
        print(f"  FPS:  {1000/avg:.0f}")


def benchmark_getasynckeystate():
    """Benchmark GetAsyncKeyState call patterns"""
    print("\n=== GetAsyncKeyState Benchmark ===")
    
    try:
        import win32api
    except ImportError:
        print("  [SKIP] pywin32 not installed")
        return
    
    keys = [0x57, 0x41, 0x53, 0x44]
    iterations = 100000
    
    # Direct calls
    start = time.perf_counter()
    for _ in range(iterations):
        for k in keys:
            win32api.GetAsyncKeyState(k) & 0x8000
    direct_time = (time.perf_counter() - start) / iterations * 1000000
    
    # Cached function reference 
    gk = win32api.GetAsyncKeyState
    start = time.perf_counter()
    for _ in range(iterations):
        gk(keys[0]) & 0x8000 or gk(keys[1]) & 0x8000 or gk(keys[2]) & 0x8000 or gk(keys[3]) & 0x8000
    cached_time = (time.perf_counter() - start) / iterations * 1000000
    
    print(f"  Direct (win32api.GetAsyncKeyState x4): {direct_time:.1f} ns/call")
    print(f"  Cached (gk x4, short-circuit):         {cached_time:.1f} ns/call")
    print(f"  Speedup: {direct_time/cached_time:.2f}x")


if __name__ == "__main__":
    print("=" * 60)
    print("Performance Benchmark Suite")
    print("=" * 60)
    
    benchmark_color_detection()
    benchmark_timer_resolution()
    benchmark_sleep_accuracy()
    benchmark_getasynckeystate()
    benchmark_yolo_inference()
    
    print("\n" + "=" * 60)
    print("Benchmark complete!")
    print("=" * 60)
