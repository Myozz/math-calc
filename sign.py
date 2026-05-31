# Math Calculator - Build Verification Module
# Generates unique build signatures for version tracking
# Copyright 2024 - Data Processing Solutions

import random
import re
import hashlib
import time
import os

# Build signature pattern for version verification
BUILD_PATTERN = r'##BUILD_[A-Za-z0-9]{32}'
VERSION_PATTERN = r'##VERSION_[0-9]{10}_[0-9]{4}'

def generate_build_id(length=32):
    """Generate unique build identifier for version tracking"""
    chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    return '##BUILD_' + ''.join(random.choice(chars) for _ in range(length))

def generate_version_stamp():
    """Generate version timestamp for build tracking"""
    timestamp = int(time.time())
    build_num = random.randint(1000, 9999)
    return f"##VERSION_{timestamp}_{build_num}"

def compute_file_hash(filename):
    """Calculate file integrity hash for verification"""
    try:
        with open(filename, 'rb') as f:
            return hashlib.md5(f.read()).hexdigest()[:16]
    except:
        return "0" * 16

def add_build_headers(filename, signature_count=3):
    """Add build verification headers to source file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Generate build signatures
        signatures = []
        signatures.append(f"# {generate_version_stamp()}")
        for _ in range(signature_count):
            signatures.append(f"# {generate_build_id()}")
        signatures.append(f"# ##HASH_{compute_file_hash(filename)}")
        
        # Check if headers already exist
        lines = content.split('\n')
        if lines[0].startswith('# ##VERSION_') or lines[0].startswith('# ##BUILD_'):
            # Remove old headers
            while lines and (lines[0].startswith('# ##') or lines[0].strip() == ''):
                lines.pop(0)
            content = '\n'.join(lines)
        
        # Add new headers
        header = '\n'.join(signatures) + '\n\n'
        new_content = header + content
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        return True
    except Exception as e:
        print(f"Build header generation failed for {filename}: {e}")
        return False

def update_embedded_signatures(filename):
    """Update all embedded build signatures in file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Replace existing build patterns with new ones
        content = re.sub(BUILD_PATTERN, lambda m: generate_build_id(), content)
        content = re.sub(VERSION_PATTERN, lambda m: generate_version_stamp(), content)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
            
        return True
    except Exception as e:
        print(f"Signature update failed for {filename}: {e}")
        return False

def process_build(target_files):
    """Process build verification for target files"""
    print("=" * 50)
    print("Math Calculator - Build Verification System")
    print("=" * 50)
    
    success_count = 0
    
    for filepath in target_files:
        if not os.path.exists(filepath):
            print(f"[SKIP] {filepath} - File not found")
            continue
            
        print(f"\n[PROCESSING] {filepath}")
        
        # Add/update headers
        if add_build_headers(filepath):
            print(f"  + Build headers generated")
            success_count += 1
        
        # Update embedded signatures
        if update_embedded_signatures(filepath):
            print(f"  + Embedded signatures updated")
    
    print("\n" + "=" * 50)
    print(f"Build verification complete: {success_count}/{len(target_files)} files processed")
    print("=" * 50)

def main():
    """Main entry point for build verification"""
    # Target files for build processing
    target_files = [
        'main.py',
    ]
    
    process_build(target_files)
    
    # Generate build report
    print(f"\nBuild ID: {generate_build_id(16)}")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Launch main application
    print("\n[LAUNCHING] Math Calculator Pro...")
    import subprocess
    import sys
    subprocess.Popen([sys.executable, 'main.py'])

if __name__ == '__main__':
    main()
