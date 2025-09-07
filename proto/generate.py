# Script to generate gRPC code from proto
import subprocess
import sys
import os
from pathlib import Path

def generate():
    """Generate Python protobuf and gRPC files"""
    
    # Get directories
    current_dir = Path(__file__).parent
    project_root = current_dir.parent
    
    print(f"📁 Proto directory: {current_dir}")
    print(f"📁 Project root: {project_root}")
    
    # Check if arena.proto exists
    proto_file = current_dir / "arena.proto"
    if not proto_file.exists():
        print(f"❌ arena.proto not found at {proto_file}")
        sys.exit(1)
    
    # Change to project root for relative imports
    os.chdir(project_root)
    
    # Command to generate protobuf files
    cmd = [
        sys.executable, "-m", "grpc_tools.protoc",
        f"--proto_path=proto",
        f"--python_out=proto", 
        f"--grpc_python_out=proto",
        "proto/arena.proto"
    ]
    
    print("🔨 Generating protobuf files...")
    print(f"Command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Protobuf files generated successfully!")
        
        # List generated files
        generated_files = [
            current_dir / "arena_pb2.py",
            current_dir / "arena_pb2_grpc.py"
        ]
        
        print("📄 Generated files:")
        for file_path in generated_files:
            if file_path.exists():
                size_kb = file_path.stat().st_size / 1024
                print(f"  ✅ {file_path.name} ({size_kb:.1f} KB)")
            else:
                print(f"  ❌ Missing: {file_path.name}")
        
        # Add __init__.py if not exists
        init_file = current_dir / "__init__.py"
        if not init_file.exists():
            init_file.write_text("# Proto package\n")
            print(f"  📝 Created {init_file.name}")
                
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate protobuf files:")
        print(f"Error: {e}")
        if e.stdout:
            print(f"Stdout: {e.stdout}")
        if e.stderr:
            print(f"Stderr: {e.stderr}")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ grpc_tools not found.")
        print("Install with: pip install grpcio-tools")
        sys.exit(1)

if __name__ == "__main__":
    generate()