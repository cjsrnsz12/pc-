"""Strict game-title matching. Browser pages and launchers are not game windows."""
from pathlib import PureWindowsPath
import re

BLOCKED = {'chrome.exe','msedge.exe','firefox.exe','brave.exe','opera.exe','iexplore.exe',
           'explorer.exe','notepad.exe','cmd.exe','powershell.exe','pwsh.exe',
           'windowsterminal.exe','applicationframehost.exe','nexonlauncher.exe',
           'nexonplug.exe','ngm.exe','abysshelper.exe','python.exe','pythonw.exe'}


def is_game_window(title, executable):
    title = re.sub(r'\s+','',title).casefold()
    name = PureWindowsPath(executable).name.casefold()
    return title in {'마비노기모바일','mabinogimobile'} and bool(name) and name.endswith('.exe') and name not in BLOCKED
