"""Build the Autorouter with its isolated loading window and bundled OCR."""
import subprocess
import sys
from build_with_loader import main

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as exc:
        print(f"Build failed (exit code {exc.returncode}). See the output above.")
        sys.exit(exc.returncode)
