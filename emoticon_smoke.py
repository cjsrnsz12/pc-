"""Exercise the offline editor and real save/export handlers. No network."""
import json
from pathlib import Path
import os
import tempfile
import time
import tkinter as tk
from tkinter import ttk
import urllib.request
import zipfile
from PIL import Image, ImageGrab
import emoticon_ui

urllib.request.urlopen=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Offline editor made a network call'))
root=tk.Tk();root.geometry('1000x950+0+0');root.configure(bg='#0c1220')
style=ttk.Style();style.theme_use('clam');style.configure('.',background='#0c1220',foreground='#edf2ff',font=('맑은 고딕',10));style.configure('TButton',padding=8,background='#263550');style.configure('Muted.TLabel',foreground='#9caccc')
data=Path(tempfile.mkdtemp(prefix='nyacro-emoticon-smoke-'))
view=emoticon_ui.EmoticonWindow(root,Path(__file__).parent,data)
view.window.geometry('710x650+30+30');root.update()
assert not hasattr(view,'key')
view.caption.set('안녕!');view.make()
deadline=time.monotonic()+10
while time.monotonic()<deadline and view.busy:root.update();time.sleep(.03)
assert not view.busy and view.result and len(list((data/'emoticons').glob('*.png')))==1
root.update();view.window.lift();root.update()
assert view.generate_button.winfo_viewable()
assert view.generate_button.winfo_rooty()+view.generate_button.winfo_height()<=view.window.winfo_rooty()+view.window.winfo_height()
# Test handlers, rather than just writing their in-memory output.
target_png=data/'export.png';target_zip=data/'pack.zip'
emoticon_ui.filedialog.asksaveasfilename=lambda **kw:str(target_png)
view.save_result();assert target_png.read_bytes()==view.result
emoticon_ui.filedialog.asksaveasfilename=lambda **kw:str(target_zip)
view.export_pack()
with zipfile.ZipFile(target_zip) as archive:assert len(archive.namelist())==8
with Image.open(target_png) as image:assert image.size==(360,360)
assert target_png.stat().st_size<=150_000
# Keep CI screenshots scoped to this app when a display is available.
preview=Path(tempfile.gettempdir())/'abyss-emoticon-ui.png'
view.window.lift();root.update();time.sleep(.15);root.update();box=(view.window.winfo_rootx(),view.window.winfo_rooty(),view.window.winfo_rootx()+view.window.winfo_width(),view.window.winfo_rooty()+view.window.winfo_height())
ImageGrab.grab(xdisplay=os.getenv('DISPLAY') if os.name!='nt' else None).crop(box).save(preview)
view.close();root.destroy()
print(json.dumps({'ok':True,'basic_stickers':8,'offline_edit_saved':True,'png_zip_handlers':True,'small_window_actions_visible':True,'preview':str(preview)}))
