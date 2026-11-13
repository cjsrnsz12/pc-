"""Native UI + mocked generation integration check; no external API calls."""
import json
from pathlib import Path
import tempfile
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageGrab
import emoticon_ui
from emoticon_core import png_bytes

root=tk.Tk();root.geometry('1000x950+0+0');root.configure(bg='#0c1220')
style=ttk.Style();style.theme_use('clam');style.configure('.',background='#0c1220',foreground='#edf2ff',font=('맑은 고딕',10));style.configure('TButton',padding=8,background='#263550');style.configure('Muted.TLabel',foreground='#9caccc')
data=Path(tempfile.mkdtemp(prefix='nyacro-emoticon-smoke-'))
view=emoticon_ui.EmoticonWindow(root,Path(__file__).parent,data)
view.window.geometry('850x850+30+30')
view.make();assert not view.busy
view.key.set('test-only-key')
emoticon_ui.generate=lambda *args,**kwargs:(Path(__file__).parent/'emoticons/01_nyar_peek.png').read_bytes()
view.make()
deadline=time.monotonic()+10
while time.monotonic()<deadline and view.busy:root.update();time.sleep(.03)
assert not view.busy and view.result and len(list((data/'emoticons').glob('*.png')))==1
root.update()
target=Path(tempfile.gettempdir())/'abyss-emoticon-ui.png'
ImageGrab.grab().save(target)
view.close();assert view.key.get()==''
root.destroy()
print(json.dumps({'ok':True,'basic_stickers':8,'mock_generation_saved':True,'api_key_cleared':True,'preview':str(target)}))
