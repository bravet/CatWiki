#!/usr/bin/env python3
import os
import re
import sys
import json

def update_file(file_path, pattern, replacement):
    if not os.path.exists(file_path):
        # Silently skip missing optional files
        return False
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    new_content = re.sub(pattern, replacement, content)
    
    if content == new_content:
        return False
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    # print(f"✅ Updated: {file_path}") # Suppress noisy logs
    return True

def get_current_version():
    config_path = 'backend/app/core/infra/config.py'
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            content = f.read()
            match = re.search(r'VERSION: str = "([^"]+)"', content)
            if match:
                return match.group(1)
    return "unknown"

def set_version(version):
    v_tag = f"v{version}" if not version.startswith('v') else version
    v_num = version.lstrip('v')

    print(f"🚀 Aligning project version to {v_num} (Docker tag: {v_tag})")

    # 1. backend/app/core/infra/config.py
    update_file(
        'backend/app/core/infra/config.py',
        r'VERSION: str = "[^"]+"',
        f'VERSION: str = "{v_num}"'
    )

    # 2. backend/pyproject.toml
    update_file(
        'backend/pyproject.toml',
        r'(?m)^version = "[^"]+"',
        f'version = "{v_num}"'
    )

    # 3. frontend package.json files (Target specific project files)
    pkg_files = [
        'frontend/admin/package.json',
        'frontend/client/package.json',
        'frontend/docs/package.json',
        'frontend/website/package.json'
    ]
    for pkg_path in pkg_files:
        if os.path.exists(pkg_path):
            try:
                with open(pkg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if 'version' in data and data.get('version') != v_num:
                    data['version'] = v_num
                    with open(pkg_path, 'w', encoding='utf-8') as f_out:
                        json.dump(data, f_out, indent=2)
                        f_out.write('\n')
                    print(f"✅ Updated: {pkg_path}")
            except Exception as e:
                print(f"❌ Error updating {pkg_path}: {e}")

    # 4. .env files
    env_files = [
        '.env',
        'backend/.env',
        'backend/.env.example',
        'deploy/docker/.env'
    ]
    for env_f in env_files:
        # Match VERSION=x.x.x or VERSION="x.x.x"
        update_file(env_f, r'VERSION=[^\s#]+', f'VERSION={v_num}')
        update_file(env_f, r'VERSION="[^"]+"', f'VERSION="{v_num}"')

    # 5. docker-compose files
    compose_files = [
        'deploy/docker/docker-compose.yml',
        'docker-compose.dev.yml'
    ]
    for compose_path in compose_files:
        update_file(
            compose_path,
            r'(image: bulolo/catwiki-[^:]+):[^\s]+',
            r'\1:' + v_tag
        )

if __name__ == "__main__":
    if len(sys.argv) < 2:
        curr = get_current_version()
        print(f"Current project version is: {curr}")
        print("Usage: make set-version v=<version>")
        sys.exit(0)
    
    new_version = sys.argv[1]
    set_version(new_version)
