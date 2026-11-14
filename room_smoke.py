"""Native Tk smoke check. Exercises create/join/leave UI with an offline manager."""
from pathlib import Path
import copy
import tkinter as tk
from room_ui import RoomWindow

def exercise_room_window(parent,report_path=None):
    class Offline:
        def __init__(self):self.value=dict(joined=False,busy=False,nickname='',room_code='',member_id='00000000-0000-0000-0000-000000000001',members=[],connected=False,message='방에 참여하면 현황이 공유됩니다.');self.calls=[]
        def view(self):return copy.deepcopy(self.value)
        def join(self,name,code=None):self.calls.append(('join',name,code))
        def leave(self):self.calls.append(('leave',));self.value.update(joined=False,members=[])
        def refresh(self):self.calls.append(('refresh',))
    sync=Offline();window=RoomWindow(parent,sync);parent.update_idletasks()
    window.name.set('고양이');window.create.invoke();assert sync.calls[-1]==('join','고양이',None)
    window.code.set('ABCDEF0123456789ABCD');window.join_button.invoke();assert sync.calls[-1][2]=='ABCDEF0123456789ABCD'
    sync.value.update(joined=True,connected=True,room_code='ABCDEF0123456789ABCD',members=[dict(id=sync.value['member_id'],nickname='고양이',platform='pc',status='running',content='어비스',completed=27),dict(id='00000000-0000-0000-0000-000000000002',nickname='냥이',platform='mobile',status='stopped',content='레이드',completed=12)])
    window.refresh();parent.update_idletasks();assert len(window.table.get_children())==2
    rows=[window.table.item(i)['values'] for i in window.table.get_children()];assert {r[1] for r in rows}=={'PC','모바일'}
    if report_path:
        try:
            from PIL import ImageGrab
            win=window.window;win.update();ImageGrab.grab((win.winfo_rootx(),win.winfo_rooty(),win.winfo_rootx()+win.winfo_width(),win.winfo_rooty()+win.winfo_height())).save(Path(report_path).with_name('abyss-room-preview.png'))
        except OSError:pass
    window.leave.invoke();window.refresh();assert sync.calls[-1]==('leave',);window.close()
    return {'rows':2,'platforms':['PC','모바일'],'controls':'create/join/leave','network':'offline fixture'}
