from game_identity import is_game_window


def test_game_titles_with_verified_process_path():
    assert is_game_window('마비노기 모바일',r'C:\Nexon\game\Game-Win64-Shipping.exe')
    assert is_game_window('Mabinogi Mobile',r'C:\Nexon\MabinogiMobile.exe')
    assert is_game_window('마비노기모바일',r'C:\Nexon\Game.exe')


def test_browser_launcher_and_other_games_are_excluded():
    for title in ['마비노기','마비노기 모바일 - Google Chrome','마비노기 모바일 공략','NEXON Launcher','어비스 헬퍼 · PC','냐크로 · PC','']:
        assert not is_game_window(title,r'C:\Game.exe')
    for exe in ['chrome.exe','msedge.exe','firefox.exe','notepad.exe','cmd.exe','NexonLauncher.exe','AbyssHelper.exe','Nyacro.exe','냐크로.exe','']:
        assert not is_game_window('마비노기 모바일',exe)
