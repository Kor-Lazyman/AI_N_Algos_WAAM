"""Version 1.0.2 entry point."""
import sys
from evaluate_layers import main

if __name__ == "__main__":
    main(["--eval-source", "stl", *sys.argv[1:]])
