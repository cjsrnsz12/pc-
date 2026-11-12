"""Windows GUI regression check for dark hover, ticks and transition lifecycle."""
import time
from tkinter import ttk
from pathlib import Path
import ctypes as C
from ctypes import wintypes as W
from PIL import Image
from ui_controls import BG,SmoothCheckbutton


def exercise_style_controls(app,report_path):
    import mss
    root=app.root;root.deiconify();root.update()
    from branding import APP_NAME,APP_TITLE
    assert root.title()==APP_TITLE
    def settle(seconds=.23):
        end=time.monotonic()+seconds
        while time.monotonic()<end:root.update();time.sleep(.01)
    check=app.food_check
    assert isinstance(check,SmoothCheckbutton)
    original=bool(app.food.get())
    app.food.set(False);settle()
    assert APP_NAME in [app.header.itemcget(i,'text') for i in app.header.find_all() if app.header.type(i)=='text']
    check.invoke();settle()
    assert app.food.get() and check.selected>.99
    check.event_generate('<Enter>');settle()
    assert check.cget('background')==BG and check.label.cget('background')==BG
    check.configure(state='disabled');check.event_generate('<Enter>');settle()
    previous=app.food.get();check.invoke();assert app.food.get()==previous
    assert check.label.cget('background')==BG
    check.configure(state='normal');app.food.set(original);settle()
    from choice_control import PLAY_MODES,DIFFICULTY_COLORS
    from choice_control import SmoothChoice,CONTENT_TYPES
    from vision import DUNGEONS
    assert isinstance(app.content_box,SmoothChoice) and isinstance(app.dungeon_box,SmoothChoice)
    assert app.content_box.values==CONTENT_TYPES and app.dungeon_box.values==list(DUNGEONS)
    app.content.set('어비스');root.update()
    for choice in (app.content_box,app.dungeon_box):
        choice.open();settle()
        assert choice.popup and choice.popup.winfo_height()>60
        choice.dismiss()
    saved_destination=app.dungeon.get();saved_difficulty=app.difficulty.get()
    app.content_box.choose('레이드');root.update()
    import json
    assert json.loads(app.settings_path.read_text(encoding='utf-8'))['content']=='레이드'
    assert app.content_hint.winfo_ismapped() and app.destination_options.winfo_ismapped()
    assert str(app.start_button['state'])=='normal' and '레이드' in app.status.get()
    assert app.dungeon_box.values==['카브락'] and app.difficulty_box.values==['입문','어려움']
    app.content_box.choose('어비스');root.update()
    assert app.destination_options.winfo_ismapped() and not app.content_hint.winfo_ismapped()
    assert app.dungeon.get()==saved_destination and app.difficulty.get()==saved_difficulty
    assert str(app.start_button['state'])=='normal'
    for dungeon in DUNGEONS:
        app.dungeon_box.choose(dungeon);root.update()
        assert app.dungeon.get()==dungeon
    app.dungeon.set(saved_destination);app.difficulty.set(saved_difficulty)

    app.play_mode.set(PLAY_MODES[1]);root.update()
    assert '다른 던전 가기' in app.mode_hint.get() and str(app.start_button['state'])=='normal'
    assert app.repeat.get()
    app.play_mode.set(PLAY_MODES[0]);root.update()
    assert str(app.start_button['state'])=='normal'
    for title,color in DIFFICULTY_COLORS.items():
        app.difficulty.set(title);root.update()
        assert app.difficulty_box.label.cget('fg')==color
        app.difficulty_box.open();settle()
        popup=app.difficulty_box.popup
        assert popup and popup.winfo_height()>80
        app.difficulty_box.dismiss();assert app.difficulty_box.popup is None
    app.difficulty.set('매우 어려움')
    button=app.resize_button;button.event_generate('<Enter>');settle()
    color=ttk.Style(root).lookup(button.cget('style'),'background',('active',))
    assert color.lower() not in ('white','#ffffff','#fff','#d9d9d9')
    button.configure(state='disabled');settle()
    disabled=ttk.Style(root).lookup(button.cget('style'),'background',('disabled','active'))
    assert disabled.lower() not in ('white','#ffffff','#fff','#d9d9d9')
    button.configure(state='normal');button.event_generate('<Leave>');settle()
    # Capture only this test app, for visual inspection of the native layout.
    hwnd=app.win.u.GetAncestor(root.winfo_id(),2);rect=W.RECT();origin=W.POINT()
    app.win.u.GetClientRect(hwnd,C.byref(rect));app.win.u.ClientToScreen(hwnd,C.byref(origin))
    assert app.footer.winfo_rooty()+app.footer.winfo_height()<=origin.y+rect.bottom+1
    for button in (app.start_button,app.stop_button):
        assert button.winfo_viewable()
        assert app.footer.winfo_rooty()<=button.winfo_rooty()
        assert button.winfo_rooty()+button.winfo_height()<=origin.y+rect.bottom
    screenshot=Path(report_path).with_suffix('.png')
    with mss.mss() as capture:
        shot=capture.grab({'left':origin.x,'top':origin.y,'width':rect.right,'height':rect.bottom})
        Image.frombytes('RGB',shot.size,shot.rgb).save(screenshot)
    return {'hover_stays_dark':True,'check_mark':'tick','disabled_click_ignored':True,'button_transition':True,'native_preview':str(screenshot),'footer_visible':True}
