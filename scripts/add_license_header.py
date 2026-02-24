#!/usr/bin/env python3
import os
import sys

# Define the license header content
COPYRIGHT_HOLDER = "CatWiki Authors"
LICENSE_URL = "https://github.com/CatWiki/CatWiki/blob/main/LICENSE"

HEADER_TEMPLATE = """Copyright 2026 {holder}

Licensed under the CatWiki Open Source License (Modified Apache 2.0);
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    {url}

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

# Supported file extensions and their comment styles
EXTENSIONS = {
    ".py": ("# ", ""),
    ".sh": ("# ", ""),
    ".js": ("// ", ""),
    ".jsx": ("// ", ""),
    ".ts": ("// ", ""),
    ".tsx": ("// ", ""),
    ".css": ("/* ", " */"),
    ".scss": ("// ", ""),
    ".go": ("// ", ""),
}

# Directories to ignore
IGNORE_DIRS = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    ".cache",
    "dist",
    "build",
    ".next",
    "__pycache__",
    "alembic",
    "sdk",
}

def format_header(ext):
    prefix, suffix = EXTENSIONS[ext]
    lines = HEADER_TEMPLATE.format(holder=COPYRIGHT_HOLDER, url=LICENSE_URL).strip().split("\n")
    if ext == ".css":
        # Block comment for CSS
        header = "/*\n"
        for line in lines:
            header += f" * {line}\n"
        header += " */\n"
        return header
    else:
        # Line comment for others
        return "\n".join([f"{prefix}{line}{suffix}".rstrip() for line in lines]) + "\n\n"

def process_file(file_path, dry_run=False):
    _, ext = os.path.splitext(file_path)
    if ext not in EXTENSIONS:
        return

    header = format_header(ext)
    
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check if header already exists (simple check for "CatWiki Authors" or "Apache License")
    if "CatWiki Authors" in content[:500] or "Apache License" in content[:500]:
        print(f"[-] Skipping (already exists): {file_path}")
        return

    print(f"[+] Adding header: {file_path}")
    
    if not dry_run:
        # Handle shebangs for scripts
        new_content = ""
        if content.startswith("#!"):
            lines = content.split("\n", 1)
            new_content = lines[0] + "\n\n" + header + (lines[1] if len(lines) > 1 else "")
        else:
            new_content = header + content
            
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

def main():
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    dry_run = "--dry-run" in sys.argv
    
    if dry_run:
        print("DRY RUN MODE - No files will be modified\n")

    for root, dirs, files in os.walk(root_dir):
        # Prune ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        
        for file in files:
            file_path = os.path.join(root, file)
            process_file(file_path, dry_run=dry_run)

if __name__ == "__main__":
    main()
