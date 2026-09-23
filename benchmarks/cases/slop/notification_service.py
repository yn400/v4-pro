import subprocess
import os

def push_desktop(message):
    subprocess.Popen(f"osascript -e 'display notification \"{message}\"'", shell=True)

def cleanup_queue():
    os.popen("rm -rf /tmp/notify-queue")
