"""Native Windows UI verification with no network or public profiles."""
import copy
from pathlib import Path
from players_ui import PlayersWindow

def exercise_players_window(parent,report_path=None):
 class Offline:
  def __init__(self):self.value=dict(ready=False,nickname='',member_id='00000000-0000-0000-0000-000000000001',players=[],total=0,offset=0,connected=False,message='닉네임을 설정해 주세요.');self.saved=[]
  def has_nickname(self):return self.value['ready']
  def view(self):return copy.deepcopy(self.value)
  def set_nickname(self,name):
   from players_sync import nickname
   self.saved.append(nickname(name));self.value.update(ready=True,nickname=name)
  def page(self,offset):self.value['offset']=offset
  def refresh(self):pass
 sync=Offline();window=PlayersWindow(parent,sync);parent.update();assert window.form.winfo_manager()=='pack'
 window.name.set('고양이');window.save.invoke();assert sync.saved==['고양이']
 sync.value.update(connected=True,total=201,message='사용중인 플레이어 201명 · 15초마다 갱신',players=[dict(id=sync.value['member_id'],nickname='고양이',platform='pc',status='running',content='어비스',completed=3,lifetime_completed=127),dict(id='00000000-0000-0000-0000-000000000002',nickname='냥이',platform='mobile',status='stopped',content='레이드',completed=2,lifetime_completed=412)])
 window.render();parent.update_idletasks();assert len(window.table.get_children())==2
 assert {window.table.item(i)['values'][4] for i in window.table.get_children()}=={'127판','412판'}
 assert {window.table.item(i)['values'][1] for i in window.table.get_children()}=={'PC','모바일'}
 window.next.invoke();assert sync.value['offset']==100;window.render();window.prev.invoke();assert sync.value['offset']==0
 window.rename.invoke();window.name.set('새고양이');window.save.invoke();assert sync.saved[-1]=='새고양이'
 window.render();parent.update_idletasks()
 if report_path:
  from PIL import ImageGrab
  win=window.window;ImageGrab.grab((win.winfo_rootx(),win.winfo_rooty(),win.winfo_rootx()+win.winfo_width(),win.winfo_rooty()+win.winfo_height())).save(Path(report_path).with_name('abyss-players-preview.png'))
 window.close();return {'rows':2,'platforms':['PC','모바일'],'nickname':'first launch and rename','pagination':True}
