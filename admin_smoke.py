"""Native Windows administrator UI test with deterministic local sample records."""
import time,uuid
from pathlib import Path
from admin_ui import AdminWindow

def exercise_admin_window(parent,report_path):
 class Sync:
  def identity_body(self):return dict(member_id=str(uuid.UUID(int=1)),token='b'*64)
 class Store:
  key=''
  def load(self):return self.key
  def save(self,key):self.key=key;return True
  def clear(self):self.key='';return True
 class API:
  def call(self,op,key,offset=0,unread=False,report_id=None):
   assert key=='a'*64
   if op=='admin_list_errors':return dict(ok=True,offset=offset,total=1,reports=[dict(id=str(uuid.UUID(int=2)),nickname='미리보기 고양이',device_type='tablet',stop_reason='터치 결과 확인 지연',read=False)])
   if op=='admin_read_error':return dict(ok=True,report=dict(id=report_id,nickname='미리보기 고양이',device_type='tablet',device_model='Galaxy Tab S7',screen='1600x2560',app_version='1.2.41',content='어비스',stop_reason='터치 결과 확인 지연',logs='오류 보관함 UI 검사'))
   return dict(ok=True)
 def wait(check):
  end=time.monotonic()+5
  while not check():
   if time.monotonic()>end:raise AssertionError('Administrator window timed out')
   parent.update();time.sleep(.01)
 store=Store();window=AdminWindow(parent,Sync(),'unused-private-key-path',api=API(),store=store);parent.update();window.key.set('a'*64);window.authenticate.invoke();wait(lambda:len(window.table.get_children())==1)
 assert store.key=='a'*64;window.table.selection_set(window.table.get_children()[0]);window.open_button.invoke();wait(lambda:bool(window.detail_text));assert 'Galaxy Tab S7' in window.detail_text;window.copy();assert window.window.clipboard_get()==window.detail_text
 from PIL import ImageGrab
 win=window.window;parent.update();ImageGrab.grab((win.winfo_rootx(),win.winfo_rooty(),win.winfo_rootx()+win.winfo_width(),win.winfo_rooty()+win.winfo_height())).save(Path(report_path).with_name('abyss-admin-preview.png'))
 window.close();assert store.key=='a'*64
 restored=AdminWindow(parent,Sync(),'unused-private-key-path',api=API(),store=store);wait(lambda:len(restored.table.get_children())==1);restored.logout_button.invoke();assert not store.key;restored.close()
 return dict(authenticated=True,remembered_after_close=True,logout=True,detail_copy=True,network=False)
