"""Run the test suite in throwaway data folders: python tests/run_tests.py"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
base = Path(tempfile.mkdtemp(prefix="emliq-tests-"))
try:
    gmail_home, ollama_home = base / "gmail", base / "ollama"
    gmail_home.mkdir()
    for script, home in [("test_fake_gmail.py", gmail_home), ("test_fake_ollama.py", ollama_home)]:
        if script == "test_fake_ollama.py":
            shutil.copytree(gmail_home, ollama_home)
        print(f"== {script}", flush=True)
        result = subprocess.run([sys.executable, str(HERE / script), str(home)])
        if result.returncode:
            sys.exit(f"{script} failed")
    print("All tests passed.")
finally:
    shutil.rmtree(base, ignore_errors=True)
