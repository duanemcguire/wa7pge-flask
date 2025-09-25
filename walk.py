from pathlib import Path
import sys
import os

def find_first_file_starting_with(root_path, prefix):
    root = Path(root_path)
    for p in root.rglob(f"{prefix}*"):
        if p.is_file():
            return p
    return None


# Example usage
current_file = os.path.abspath(__file__)
current_dir = os.path.dirname(current_file)
os.chdir(current_dir)
start_with = f"{current_dir}/pages/POTA/"
print(start_with)
result = find_first_file_starting_with(start_with, sys.argv[1])
if result:
    print("Found:", result)
else:
    print("No matching file found.")
