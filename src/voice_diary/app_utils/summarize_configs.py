#!/usr/bin/env python
import json
import os
import glob
import re
from pathlib import Path
from collections import defaultdict


def find_config_files():
    """Find all JSON config files in the project."""
    base_dir = Path(__file__).resolve().parent.parent.parent  # voice_diary directory
    config_files = []
    
    # New dedicated config directory
    project_fallback_configs_dir = base_dir / "voice_diary" / "project_fallback_configs"
    
    # Search patterns for config files
    patterns = [
        str(project_fallback_configs_dir / "**" / "*.json"),
        "**/config/**/*.json",
        "**/*config*.json",
    ]
    
    for pattern in patterns:
        if pattern.startswith(str(project_fallback_configs_dir)):
            # Use Path.glob for absolute paths
            config_files.extend(list(Path(pattern[:pattern.index("**")]).glob(pattern[pattern.index("**"):])))
        else:
            # Use base_dir.glob for relative patterns
            config_files.extend(list(base_dir.glob(pattern)))
    
    # Remove duplicates
    return list(set(config_files))


def is_valid_file_path(value, key=""):
    """Check if a string is likely to be a file path and not an API endpoint, database URL, or date."""
    if not isinstance(value, str):
        return False
    
    # Skip specific keys
    if key.endswith('.message') or key == 'message' or key.endswith('.email.message'):
        return False
    
    # Path must contain separators
    if '/' not in value and '\\' not in value:
        return False
    
    # Skip API endpoints
    if value.startswith(('http://', 'https://', 'ftp://')):
        return False
    
    # Skip database connection strings
    if re.search(r'(postgres|mysql|sqlite|mongodb|jdbc|odbc):', value, re.IGNORECASE):
        return False
    
    # Skip dates or timestamps
    if re.match(r'\d{4}-\d{2}-\d{2}T', value):
        return False
    
    # Skip long text/email content
    if len(value) > 100 and '\n' in value:
        return False
    
    # Must contain a directory or filename pattern
    file_path_pattern = re.compile(r'([A-Za-z]:\\|/|\\\\|\.\.?/).*\.(json|txt|py|log|csv|[a-z]{2,4})$', re.IGNORECASE)
    directory_pattern = re.compile(r'([A-Za-z]:\\|/|\\\\|\.\.?/).*(/|\\)$', re.IGNORECASE)
    
    # Check if it looks like a file or directory path
    if file_path_pattern.search(value) or directory_pattern.search(value) or ':\\' in value:
        return True
    
    # For paths that don't have extensions but have a proper structure
    if ('/' in value or '\\' in value) and not value.startswith(('http', 'ftp', 'ws:')):
        parts = re.split(r'[/\\]', value)
        # Valid paths should have reasonable component lengths
        if len(parts) >= 2 and all(1 <= len(part) <= 64 for part in parts if part):
            return True
    
    return False


def extract_path_fields(config_data, parent_key="", path_fields=None):
    """Recursively extract all path fields from config data."""
    if path_fields is None:
        path_fields = {}
    
    if isinstance(config_data, dict):
        for key, value in config_data.items():
            current_key = f"{parent_key}.{key}" if parent_key else key
            
            # Check if value is a likely file or directory path
            if is_valid_file_path(value, current_key):
                path_fields[current_key] = value
            
            # Recursively process dictionaries
            if isinstance(value, (dict, list)):
                extract_path_fields(value, current_key, path_fields)
    
    elif isinstance(config_data, list):
        for i, item in enumerate(config_data):
            current_key = f"{parent_key}[{i}]"
            if isinstance(item, (dict, list)):
                extract_path_fields(item, current_key, path_fields)
    
    return path_fields


# Add colored terminal output support
def colorize(text, color_code):
    """Add color to terminal output."""
    # Only use colors if we're not in a CI environment and terminal supports it
    if os.isatty(1):  # Check if stdout is a terminal
        return f"\033[{color_code}m{text}\033[0m"
    return text


def normalize_path(path):
    """Normalize path for display and checking existence."""
    # Convert to forward slashes for display consistency
    normalized = path.replace("\\", "/")
    return normalized


def get_module_name(config_file):
    """Extract module name from config file path."""
    path_parts = config_file.parts
    
    # Extract from the new config directory structure
    if 'project_fallback_configs' in path_parts:
        config_dir_index = path_parts.index('project_fallback_configs')
        # Check if the directory starts with 'config_' followed by the module name
        if len(path_parts) > config_dir_index + 1:
            module_dir = path_parts[config_dir_index + 1]
            if module_dir.startswith('config_'):
                return module_dir[7:]  # Remove 'config_' prefix
            return module_dir
    
    # Legacy method: Find 'voice_diary' in the path
    if 'voice_diary' in path_parts:
        voice_diary_index = path_parts.index('voice_diary')
        # Get the next part after voice_diary as the module name
        if len(path_parts) > voice_diary_index + 1:
            return path_parts[voice_diary_index + 1]
    
    # Fallback: use the parent directory name
    return config_file.parent.name


def truncate_path(path, max_length=80):
    """Truncate path for display if it's too long."""
    if len(path) <= max_length:
        return path
    
    # Keep the first part of the path
    first_part = path[:40]
    
    # Keep the last part of the path
    last_part = path[-(max_length - 43):]
    
    return f"{first_part}...{last_part}"


def get_ordered_modules(module_configs):
    """Return modules in the specified processing order."""
    # Define the order of modules based on the workflow
    module_order = [
        "dwnload_files",     # 1. Download from Gmail
        "transcribe_raw_audio", # 2. Transcribe
        "file_utils",        # 3. Move to target paths
        "agent_summarize_day", # 4. Summarize
        "send_email",        # 5. Send email
        # Any remaining modules will be appended at the end
    ]
    
    # First add modules in the defined order
    ordered_modules = []
    for module in module_order:
        if module.lower() in module_configs:
            ordered_modules.append(module.lower())
    
    # Then add any remaining modules alphabetically
    for module in sorted(module_configs.keys()):
        if module.lower() not in ordered_modules:
            ordered_modules.append(module.lower())
    
    return ordered_modules


def summarize_configurations():
    """Generate a summary of all config paths grouped by module."""
    config_files = find_config_files()
    
    # Skip test configuration files
    config_files = [file for file in config_files if "test" not in str(file).lower()]
    
    if not config_files:
        print(colorize("No configuration files found.", "31"))  # Red
        return None
    
    # Group configs by module
    module_configs = defaultdict(list)
    all_paths = []
    path_exists_count = 0
    path_not_found_count = 0
    
    for config_file in config_files:
        try:
            module_name = get_module_name(config_file)
            
            # Get relative path in a way that works for both old and new structures
            try:
                relative_path = config_file.relative_to(config_file.parent.parent.parent.parent)
            except ValueError:
                # For the new config structure
                base_dir = Path(__file__).resolve().parent.parent.parent
                relative_path = config_file.relative_to(base_dir)
            
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            path_fields = extract_path_fields(config_data)
            
            if path_fields:
                module_configs[module_name.lower()].append({
                    'file': str(relative_path),
                    'paths': path_fields
                })
                
                for path in path_fields.values():
                    all_paths.append(path)
                    # Check if path exists
                    display_path = normalize_path(path)
                    exists = os.path.exists(path) or os.path.exists(Path(display_path))
                    if exists:
                        path_exists_count += 1
                    else:
                        path_not_found_count += 1
        except Exception as e:
            print(colorize(f"Error processing {config_file}: {e}", "31"))  # Red
    
    # Print summary
    print(colorize("\n===== CONFIGURATION PATHS SUMMARY =====", "1;36"))  # Bold Cyan
    print(colorize(f"Found {len(config_files)} configuration files with {len(all_paths)} path settings", "1;37"))
    print(colorize(f"Paths status: {path_exists_count} exist, {path_not_found_count} not found", "1;37"))
    
    # Get modules in defined order
    ordered_modules = get_ordered_modules(module_configs)
    
    # Create summary sections by module in the defined order
    for module_name in ordered_modules:
        configs = module_configs[module_name]
        print(colorize(f"\n[{module_name.upper()}]", "1;33"))  # Bold Yellow
        
        for config in configs:
            print(colorize(f"  {config['file']}", "1;36"))  # Bold Cyan
            
            for key, path in config['paths'].items():
                # Check if path exists
                display_path = normalize_path(path)
                display_path = truncate_path(display_path, 80)
                
                exists = os.path.exists(path) or os.path.exists(Path(normalize_path(path)))
                existence_marker = colorize("[✓]", "32") if exists else colorize("[✗]", "31")
                
                print(f"    {colorize(key, '36')}: {display_path} {existence_marker}")
    
    print(colorize("\n===== END OF SUMMARY =====\n", "1;36"))  # Bold Cyan
    
    return module_configs


def save_summary_to_file():
    """Save the configuration summary to a file."""
    config_files = find_config_files()
    config_files = [file for file in config_files if "test" not in str(file).lower()]
    
    if not config_files:
        print("No configuration files found.")
        return
    
    # Group configs by module
    module_configs = defaultdict(list)
    all_paths = []
    path_exists_count = 0
    path_not_found_count = 0
    
    for config_file in config_files:
        try:
            module_name = get_module_name(config_file)
            
            # Get relative path in a way that works for both old and new structures
            try:
                relative_path = config_file.relative_to(config_file.parent.parent.parent.parent)
            except ValueError:
                # For the new config structure
                base_dir = Path(__file__).resolve().parent.parent.parent
                relative_path = config_file.relative_to(base_dir)
            
            with open(config_file, 'r') as f:
                config_data = json.load(f)
            
            path_fields = extract_path_fields(config_data)
            
            if path_fields:
                module_configs[module_name.lower()].append({
                    'file': str(relative_path),
                    'paths': path_fields
                })
                
                for path in path_fields.values():
                    all_paths.append(path)
                    # Check if path exists
                    display_path = normalize_path(path)
                    exists = os.path.exists(path) or os.path.exists(Path(display_path))
                    if exists:
                        path_exists_count += 1
                    else:
                        path_not_found_count += 1
        except Exception as e:
            print(f"Error processing {config_file}: {e}")
    
    # Generate summary text
    summary = []
    summary.append("===== CONFIGURATION PATHS SUMMARY =====")
    summary.append(f"Found {len(config_files)} configuration files with {len(all_paths)} path settings")
    summary.append(f"Paths status: {path_exists_count} exist, {path_not_found_count} not found")
    summary.append("")
    
    # Get modules in defined order
    ordered_modules = get_ordered_modules(module_configs)
    
    # Create summary sections by module in the defined order
    for module_name in ordered_modules:
        configs = module_configs[module_name]
        summary.append(f"[{module_name.upper()}]")
        
        for config in configs:
            summary.append(f"  {config['file']}")
            
            for key, path in config['paths'].items():
                display_path = normalize_path(path)
                display_path = truncate_path(display_path, 80)
                
                exists = os.path.exists(path) or os.path.exists(Path(normalize_path(path)))
                status = "EXISTS" if exists else "NOT FOUND"
                summary.append(f"    {key}: {display_path} [{status}]")
        
        summary.append("")
    
    summary.append("===== END OF SUMMARY =====")
    
    # Create reports directory if it doesn't exist
    output_dir = Path(__file__).parent / "reports"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / "config_paths_summary.txt"
    
    with open(output_file, "w") as f:
        f.write("\n".join(summary))
    
    print(f"Summary saved to {output_file}")
    return output_file


if __name__ == "__main__":
    summarize_configurations()
    save_summary_to_file() 