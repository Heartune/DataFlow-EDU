import os
import sys


def print_progress_bar(iteration, total, prefix='', suffix='', length=50, fill='█'):
    """
    Call this function in a loop to create a terminal progress bar.
    :param iteration: Current iteration (int)
    :param total: Total iterations (int)
    :param prefix: Prefix string (str)
    :param suffix: Suffix string (str)
    :param length: Character length of the bar (int)
    :param fill: Bar fill character (str)
    """
    percent = f"{100 * (iteration / float(total)):.1f}"
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)

    sys.stdout.write(f'\r{prefix} |{bar}| {percent}% {suffix}')
    sys.stdout.flush()

    if iteration == total:
        print()


def escape_gitignore_entry(path):
    """
    Escape special characters in a file path for .gitignore.
    
    Specifically, this function:
      - Escapes '[' and ']' by prefixing them with a backslash.
      - Escapes a leading '#' or '!' if present.
      
    This ensures that such characters are taken literally in .gitignore.
    """
    if path.startswith('#'):
        path = '\\' + path
    if path.startswith('!'):
        path = '\\' + path
    path = path.replace('[', '\\[').replace(']', '\\]')
    return path


def main():
    # Define size threshold: 100 MB in bytes.
    SIZE_THRESHOLD = 100 * 1024 * 1024

    base_dir = os.getcwd()
    gitignore_path = os.path.join(base_dir, ".gitignore")

    # Read existing entries from .gitignore (if it exists).
    existing_entries = set()
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r", encoding="utf-8") as gitignore_file:
            for line in gitignore_file:
                cleaned_line = line.strip()
                # Ignore empty lines and comment lines.
                if cleaned_line and not cleaned_line.startswith('#'):
                    existing_entries.add(cleaned_line)

    # Gather all files (excluding the .git folder and the .gitignore file itself).
    all_files = []
    for root, dirs, files in os.walk(base_dir):
        if '.git' in dirs:
            dirs.remove('.git')
        for filename in files:
            file_path = os.path.join(root, filename)
            if file_path != gitignore_path:
                all_files.append(file_path)

    total_files = len(all_files)
    large_files = []

    # Scan files and update progress bar.
    for i, file_path in enumerate(all_files, start=1):
        print_progress_bar(i, total_files, prefix='Scanning', suffix='Complete', length=40)

        try:
            if os.path.getsize(file_path) > SIZE_THRESHOLD:
                # Generate a relative path.
                relative_path = os.path.relpath(file_path, base_dir)
                # Convert Windows backslashes to forward slashes.
                relative_path = relative_path.replace("\\", "/")
                # Escape any special characters for .gitignore.
                escaped_path = escape_gitignore_entry(relative_path)
                large_files.append(escaped_path)
        except (FileNotFoundError, PermissionError):
            # Skip files that can't be accessed.
            pass

    # Determine which entries are new.
    new_entries = [entry for entry in large_files if entry not in existing_entries]

    if new_entries:
        with open(gitignore_path, "a", encoding="utf-8") as gitignore_file:
            gitignore_file.write("\n# Files over 100 MB (Automatically added)\n")
            for entry in new_entries:
                gitignore_file.write(entry + "\n")

        print("\nAdded these files to .gitignore:")
        for entry in new_entries:
            print(f"  {entry}")
    else:
        print("\nNo new large files found or all are already in .gitignore.")


if __name__ == "__main__":
    main()
