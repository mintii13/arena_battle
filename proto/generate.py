#!/usr/bin/env python3
"""
Generate Protocol Buffer files for Arena Battle Game
Run this from project root: python proto/generate.py
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    # Get paths
    project_root = Path(__file__).parent.parent
    proto_dir = project_root / "proto"
    proto_file = proto_dir / "arena.proto"
    
    print("🔧 Arena Battle - Protocol Buffer Generator")
    print("=" * 50)
    print(f"📁 Project root: {project_root}")
    print(f"📁 Proto directory: {proto_dir}")
    print(f"📄 Proto file: {proto_file}")
    
    # Check if proto file exists
    if not proto_file.exists():
        print(f"❌ ERROR: {proto_file} not found!")
        print("Please ensure arena.proto file exists in proto/ directory")
        return 1
    
    # Check if protoc is available
    try:
        result = subprocess.run(['protoc', '--version'], 
                              capture_output=True, text=True, check=True)
        print(f"✅ Found protoc: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("❌ ERROR: protoc not found!")
        print("Please install Protocol Buffers compiler:")
        print("  - Windows: Download from https://github.com/protocolbuffers/protobuf/releases")
        print("  - Ubuntu: sudo apt install protobuf-compiler")
        print("  - macOS: brew install protobuf")
        return 1
    
    # Check Python grpcio-tools
    try:
        import grpc_tools.protoc
        print("✅ Found grpcio-tools")
    except ImportError:
        print("❌ ERROR: grpcio-tools not found!")
        print("Install with: pip install grpcio-tools")
        return 1
    
    # Change to project root for generation
    original_cwd = os.getcwd()
    os.chdir(project_root)
    
    try:
        print("\n🚀 Generating Python files...")
        
        # Generate using grpc_tools.protoc
        command = [
            'python', '-m', 'grpc_tools.protoc',
            '--proto_path=proto',
            '--python_out=proto',
            '--grpc_python_out=proto',
            'arena.proto'
        ]
        
        print(f"🔧 Running: {' '.join(command)}")
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("❌ Generation failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            return 1
        
        # Check generated files
        generated_files = [
            proto_dir / "arena_pb2.py",
            proto_dir / "arena_pb2_grpc.py"
        ]
        
        print("\n📦 Generated files:")
        for file_path in generated_files:
            if file_path.exists():
                size = file_path.stat().st_size
                print(f"  ✅ {file_path.name} ({size} bytes)")
            else:
                print(f"  ❌ {file_path.name} (missing)")
                return 1
        
        # Create __init__.py if it doesn't exist
        init_file = proto_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("# Proto package\n")
            print(f"  ✅ Created {init_file.name}")
        
        print("\n🎉 Protocol Buffer generation completed successfully!")
        print("📁 Files ready in proto/ directory")
        return 0
        
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1
    finally:
        os.chdir(original_cwd)

if __name__ == "__main__":
    sys.exit(main())