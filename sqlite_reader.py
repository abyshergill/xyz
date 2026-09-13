import os
import subprocess
import sys


def launch_database_browser(db_path: str, port: int = 8001):
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found.")
        sys.exit(1)

    print(f"Starting Datasette for: {db_path}")
    print(f"Open your browser at: http://127.0.0.1:{port}\n")

    # Clean command without missing plugins-dir flag
    cmd = [
        sys.executable,
        "-m",
        "datasette",
        "serve",
        db_path,
        "-p",
        str(port),
    ]

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    DATABASE_FILE = "db.sqlite3"  # Make sure this path is correct
    launch_database_browser(DATABASE_FILE)