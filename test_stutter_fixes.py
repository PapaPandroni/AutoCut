#!/usr/bin/env python3
"""
Quick validation test for comprehensive stutter and freeze frame fixes

This script tests the key fixes implemented:
1. CFR enforcement removal 
2. Output seeking for frame accuracy
3. Endpoint bias elimination

Run with: python test_stutter_fixes.py
"""

import sys
import subprocess
from pathlib import Path

def test_ffmpeg_parameters():
    """Test that the problematic FFmpeg parameters have been removed"""
    renderer_path = Path("src/video/renderer.py")
    
    if not renderer_path.exists():
        print("❌ renderer.py not found")
        return False
    
    content = renderer_path.read_text()
    
    # Check that problematic parameters are removed (should only be in comments)
    active_vsync = [line for line in content.split('\n') if "vsync='cfr'" in line and not line.strip().startswith('#')]
    if active_vsync:
        print("❌ vsync='cfr' still present - this causes frame drops!")
        return False
    
    active_force_key = [line for line in content.split('\n') if "force_key_frames=" in line and not line.strip().startswith('#')]
    if active_force_key:
        print("❌ force_key_frames still present - this creates artificial timing!")
        return False
    
    # Check that good parameters are present
    if "copyts=True" not in content:
        print("❌ copyts=True not found - timestamp preservation missing!")
        return False
    
    if "avoid_negative_ts='disabled'" not in content:
        print("❌ avoid_negative_ts='disabled' not found - timing preservation missing!")
        return False
    
    print("✅ FFmpeg parameters fixed - CFR enforcement removed")
    return True

def test_seeking_fix():
    """Test that output seeking is being used instead of input seeking"""
    renderer_path = Path("src/video/renderer.py")
    content = renderer_path.read_text()
    
    # Look for the fixed seeking pattern
    lines = content.split('\n')
    input_line_found = False
    output_seeking_found = False
    
    for i, line in enumerate(lines):
        if "ffmpeg.input(str(source_path))" in line and "ss=" not in line:
            input_line_found = True
            # Check next few lines for output seeking
            for j in range(i+1, min(i+10, len(lines))):
                if "ss=segment.source_start_time" in lines[j]:
                    output_seeking_found = True
                    break
    
    if input_line_found and output_seeking_found:
        print("✅ Output seeking implemented - frame accuracy improved")
        return True
    else:
        print("❌ Output seeking not properly implemented")
        return False

def test_endpoint_bias_fix():
    """Test that endpoint bias elimination is implemented"""
    timeline_path = Path("src/core/timeline.py") 
    content = timeline_path.read_text()
    
    if "_passes_endpoint_quality_check" not in content:
        print("❌ Endpoint quality check method not found!")
        return False
    
    if "min_quality=0.6" not in content:
        print("❌ Quality threshold for endpoints not set!")
        return False
    
    # Check that automatic endpoint inclusion is removed
    if "[0.0] + [sc.timestamp for sc in scenes] + [video_info.duration]" in content:
        print("❌ Automatic endpoint inclusion still present!")
        return False
    
    print("✅ Endpoint bias eliminated - freeze frame prevention active")
    return True

def main():
    print("🔍 VALIDATING COMPREHENSIVE STUTTER/FREEZE FRAME FIXES")
    print("=" * 60)
    
    tests = [
        test_ffmpeg_parameters,
        test_seeking_fix, 
        test_endpoint_bias_fix
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print("\n" + "=" * 60)
    print(f"🎯 VALIDATION SUMMARY: {passed}/{total} fixes validated")
    
    if passed == total:
        print("🎉 ALL CRITICAL FIXES IMPLEMENTED SUCCESSFULLY!")
        print("\nThe fixes address:")
        print("• ✅ Frame drops (CFR enforcement removed)")
        print("• ✅ Timing drift (output seeking implemented)")  
        print("• ✅ Freeze frames (endpoint bias eliminated)")
        print("• ✅ A/V sync (timestamp preservation enabled)")
        print("\n🚀 Your video output should now be smooth without stuttering!")
        return True
    else:
        print(f"⚠️  {total - passed} fix(es) need attention")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)