import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def run_command(args):
    return subprocess.run([sys.executable, str(ROOT / 'main.py'), *args], capture_output=True, text=True, cwd=ROOT)


def test_atlas_pipes():
    result = run_command(['--file', 'data/atlas.txt', 'atlas', 'pipes'])
    assert result.returncode == 0
    assert 'heart' in result.stdout
    assert 'left-middle-top' in result.stdout
    assert '13 pipes' in result.stdout or '13 pipes' in result.stdout


def test_show_area():
    result = run_command(['--file', 'data/atlas.txt', 'atlas', 'show', 'speaking'])
    assert result.returncode == 0
    assert 'Area: speaking' in result.stdout
    assert 'What it does:   Turns thoughts into words' in result.stdout
    assert 'If it stops:    cannot-speak' in result.stdout


def test_find_keyword():
    result = run_command(['--file', 'data/atlas.txt', 'atlas', 'find', 'arm'])
    assert result.returncode == 0
    assert 'areas match "arm"' in result.stdout
    assert 'right-arm-face' in result.stdout
    assert 'left-arm-face' in result.stdout


def test_missing_name_error():
    result = run_command(['--file', 'data/atlas.txt', 'atlas', 'show', 'missing'])
    assert result.returncode == 0
    assert 'ERROR: No pipe or area called "missing".' in result.stdout


def test_invalid_file_error():
    temp = ROOT / 'data' / 'atlas2.txt'
    if temp.exists():
        temp.unlink()
    result = run_command(['--file', 'data/atlas2.txt', 'atlas', 'pipes'])
    assert result.returncode == 1
    assert 'ERROR: File not found:' in result.stdout
