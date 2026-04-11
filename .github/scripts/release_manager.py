import os
import json
import subprocess

def run_command(command):
    """Executes a shell command and returns the output."""
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    return result.stdout.strip()

def main():
    # 1. Load the existing registry to preserve 'core_app' and other plugins
    with open('registry.json', 'r') as f:
        registry = json.load(f)

    # Ensure 'plugins' dictionary exists
    if "plugins" not in registry:
        registry["plugins"] = {}

    # 2. Find out which root folders changed in the latest push
    changed_files = run_command("git diff --name-only HEAD^ HEAD")
    changed_dirs = {line.split('/')[0] for line in changed_files.split('\n') if '/' in line}

    new_releases = []

    # 3. Iterate through all folders looking for BioPro modules
    for module_id in os.listdir('.'):
        if os.path.isdir(module_id) and os.path.exists(os.path.join(module_id, 'manifest.json')):
            with open(os.path.join(module_id, 'manifest.json'), 'r') as f:
                manifest = json.load(f)

            # 4. If this module folder had code changes, check for a new version
            if module_id in changed_dirs:
                version = manifest['version']
                tag_name = f"{module_id}/v{version}"
                
                existing_tags = run_command("git tag -l")
                
                # If this tag doesn't exist yet, we need to release it
                if tag_name not in existing_tags:
                    new_releases.append((module_id, tag_name, manifest))
                    
                    # Safely update this specific plugin in the registry
                    registry["plugins"][module_id] = {
                        "name": manifest.get("name", module_id),
                        "version": version,
                        "min_core_version": manifest.get("min_core_version", "1.0.0"),
                        "description": manifest.get("description", ""),
                        "author": manifest.get("author", "BioPro Team"),
                        # Automatically construct the correct GitHub release asset URL
                        "download_url": f"https://github.com/KalaimaranB/BioPro-Plugins/releases/download/{tag_name}/{module_id}.zip"
                    }

    # 5. If we have updates, process them
    if new_releases:
        # Save the updated registry.json locally
        with open('registry.json', 'w') as f:
            json.dump(registry, f, indent=2)

        for module_id, tag_name, manifest in new_releases:
            module_name = manifest.get('name', module_id)
            version = manifest.get('version')
            print(f"Creating release for {module_name} at {tag_name}...")
            
            # Zip the module folder directly
            zip_name = f"{module_id}.zip"
            run_command(f"zip -r {zip_name} {module_id}/")
            
            # Extract custom release notes from manifest, or use a default
            notes = manifest.get('release_notes', f'Automated release for {module_name} v{version}')
            with open("temp_notes.txt", "w") as notes_file:
                notes_file.write(notes)
            
            # Create the GitHub Release using the GitHub CLI
            release_cmd = (f"gh release create {tag_name} {zip_name} "
                           f"--title '{module_name} v{version}' "
                           f"--notes-file temp_notes.txt")
            run_command(release_cmd)
            
            # Cleanup temp file
            os.remove("temp_notes.txt")

        # 6. Commit the updated registry.json back to the main branch
        run_command("git config user.name 'github-actions[bot]'")
        run_command("git config user.email 'github-actions[bot]@users.noreply.github.com'")
        run_command("git add registry.json")
        # [skip ci] is crucial: it prevents this commit from triggering another action run
        run_command("git commit -m 'chore: auto-update registry.json [skip ci]'")
        run_command("git push")

if __name__ == "__main__":
    main()