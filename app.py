"""Abyss Helper desktop application (Windows; packaged with --windowed)."""
from windows import dpi_aware
dpi_aware()
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
import cv2
import mss
import numpy as np
from PIL import Image, ImageTk
from engine import Controller, Observation, State
from vision import Vision, DUNGEONS, DIFFICULTIES
from windows import Windows, WindowError
from updates import check_update, release_url, download_release, DownloadCancelled
from version import VERSION, REPOSITORY

BASE = Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
DATA = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'AbyssHelper'
DATA.mkdir(parents=True,exist_ok=True)
LOG = logging.getLogger('abyss')
LOG.setLevel(logging.INFO)
_handler = RotatingFileHandler(DATA/'app.log',maxBytes=1_000_000,backupCount=3,encoding='utf-8')
_handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
LOG.addHandler(_handler)
BG, PANEL, TEXT, MUTED, ACCENT = '#0c1220','#162136','#edf2ff','#9caccc','#51dfb0'


class App:
    def __init__(self, root):
        self.root = root
        self.win = Windows()
        self.events = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.running = False
        self.sizing_busy = False
        self.closing = False
        self.update_busy = False
        self.seen_updates = set()
        self.download_cancels = set()
        self.download_workers = []
        self.update_dialog = None
        self.previous_keys = (False,False)
        self.windows = []
        self.settings_path = DATA/'settings.json'
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (ValueError,OSError):
            self.settings = {}
        root.title('어비스 헬퍼 · PC')
        root.geometry('750x860')
        root.minsize(680,770)
        root.configure(bg=BG)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.report_callback_exception = self.callback_error
        self.style()
        self.build()
        self.refresh()
        self.log('마비노기 모바일을 창 모드로 실행하고 게임 창 자동 맞추기를 누르세요. F9를 누르면 즉시 중지합니다.')
        root.after(100,self.pump)
        root.after(1600,self.update_check)

    def style(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('.',font=('맑은 고딕',10),background=BG,foreground=TEXT)
        s.configure('TFrame',background=BG)
        s.configure('Card.TFrame',background=PANEL)
        s.configure('TLabel',background=BG,foreground=TEXT)
        s.configure('Muted.TLabel',foreground=MUTED)
        s.configure('Title.TLabel',font=('맑은 고딕',24,'bold'))
        s.configure('Card.TLabel',background=PANEL)
        s.configure('Big.Card.TLabel',background=PANEL,font=('맑은 고딕',16,'bold'),foreground=ACCENT)
        s.configure('TButton',padding=(13,9),background='#263550',foreground=TEXT,borderwidth=0)
        s.map('TButton',background=[('active','#354b6e'),('disabled','#172239')],foreground=[('disabled','#62718e')])
        s.configure('Start.TButton',background=ACCENT,foreground='#05271e',font=('맑은 고딕',12,'bold'))
        s.map('Start.TButton',background=[('active','#7cecc8'),('disabled','#23483e')])
        s.configure('Stop.TButton',foreground='#ffacb5')
        s.configure('TCombobox',fieldbackground='#263550',background='#263550',foreground=TEXT,padding=7,arrowcolor=TEXT)
        s.map('TCombobox',fieldbackground=[('readonly','#263550')],foreground=[('readonly',TEXT),('disabled',MUTED)])
        s.configure('TCheckbutton',background=BG,foreground=TEXT,padding=5)
        root=self.root
        root.option_add('*TCombobox*Listbox.background','#263550')
        root.option_add('*TCombobox*Listbox.foreground',TEXT)

    def build(self):
        page=ttk.Frame(self.root,padding=24);page.pack(fill='both',expand=True)
        top=ttk.Frame(page);top.pack(fill='x')
        ttk.Label(top,text='ABYSS HELPER',style='Muted.TLabel').pack(anchor='w')
        ttk.Label(top,text='어비스 헬퍼',style='Title.TLabel').pack(side='left')
        ttk.Label(top,text='PC  /  v'+VERSION,style='Muted.TLabel').pack(side='right',pady=14)
        ttk.Label(page,text='화면을 확인하고, 정해진 순서대로.',style='Muted.TLabel').pack(anchor='w',pady=(2,18))
        card=ttk.Frame(page,style='Card.TFrame',padding=18);card.pack(fill='x')
        ttk.Label(card,text='현재 상태',style='Card.TLabel').pack(anchor='w')
        self.status=tk.StringVar(value='시작 대기')
        ttk.Label(card,textvariable=self.status,style='Big.Card.TLabel').pack(anchor='w',pady=(6,2))
        self.detail=tk.StringVar(value='게임 화면 기준 800 × 1000  ·  정지 확인 4초')
        ttk.Label(card,textvariable=self.detail,style='Card.TLabel',wraplength=620).pack(anchor='w')
        ttk.Label(page,text='게임 창',font=('맑은 고딕',11,'bold')).pack(anchor='w',pady=(18,7))
        row=ttk.Frame(page);row.pack(fill='x')
        self.window_choice=tk.StringVar()
        self.window_box=ttk.Combobox(row,textvariable=self.window_choice,state='readonly');self.window_box.pack(side='left',fill='x',expand=True)
        self.refresh_button=ttk.Button(row,text='새로고침',command=self.refresh);self.refresh_button.pack(side='left',padx=(8,0))
        self.resize_button=ttk.Button(row,text='게임 창 자동 맞추기',command=self.resize);self.resize_button.pack(side='left',padx=(8,0))
        options=ttk.Frame(page);options.pack(fill='x',pady=(15,8))
        options.columnconfigure(0,weight=1);options.columnconfigure(1,weight=1)
        ttk.Label(options,text='목적지').grid(row=0,column=0,sticky='w',pady=(0,5))
        ttk.Label(options,text='난이도').grid(row=0,column=1,sticky='w',padx=(12,0),pady=(0,5))
        self.dungeon=tk.StringVar(value=self.settings.get('dungeon','허상의 정박지'))
        if self.dungeon.get() not in DUNGEONS:self.dungeon.set('허상의 정박지')
        self.difficulty=tk.StringVar(value=self.settings.get('difficulty','매우 어려움'))
        if self.difficulty.get() not in DIFFICULTIES:self.difficulty.set('매우 어려움')
        self.dungeon_box=ttk.Combobox(options,textvariable=self.dungeon,values=list(DUNGEONS),state='readonly');self.dungeon_box.grid(row=1,column=0,sticky='ew')
        self.difficulty_box=ttk.Combobox(options,textvariable=self.difficulty,values=DIFFICULTIES,state='readonly');self.difficulty_box.grid(row=1,column=1,sticky='ew',padx=(12,0))
        self.dungeon_box.bind('<<ComboboxSelected>>',self.destination_changed)
        self.repeat=tk.BooleanVar(value=bool(self.settings.get('repeat',True)))
        self.food=tk.BooleanVar(value=bool(self.settings.get('food',True)))
        self.repeat_check=ttk.Checkbutton(page,text='솔로 플레이: 보상 화면에서 다시 하기',variable=self.repeat);self.repeat_check.pack(anchor='w')
        self.food_check=ttk.Checkbutton(page,text='음식 아이콘이 나타나면 한 번 클릭',variable=self.food);self.food_check.pack(anchor='w')
        ttk.Label(page,text='입장 조건: 함께하기 · 선택한 난이도 · 우연한 만남 ON',style='Muted.TLabel').pack(anchor='w',pady=(4,10))
        controls=ttk.Frame(page);controls.pack(fill='x',pady=(0,10))
        self.start_button=ttk.Button(controls,text='▶  시작   F8',style='Start.TButton',command=self.start);self.start_button.pack(side='left',fill='x',expand=True)
        self.stop_button=ttk.Button(controls,text='■  중지   F9',style='Stop.TButton',command=self.stop,state='disabled');self.stop_button.pack(side='left',fill='x',expand=True,padx=(10,0))
        ttk.Label(page,text='시작 후 게임 창을 클릭하세요. 다른 창을 사용하면 자동으로 대기합니다.',style='Muted.TLabel',wraplength=650).pack(anchor='w',pady=(0,12))
        log_header=ttk.Frame(page);log_header.pack(fill='x')
        ttk.Label(log_header,text='진행 기록',font=('맑은 고딕',11,'bold')).pack(side='left')
        ttk.Button(log_header,text='기록 폴더',command=lambda:os.startfile(DATA)).pack(side='right')
        self.log_box=tk.Text(page,height=8,background='#09101b',foreground='#b9cbea',font=('맑은 고딕',9),relief='flat',padx=12,pady=10,wrap='word',state='disabled')
        self.log_box.pack(fill='both',expand=True,pady=(8,12))
        bottom=ttk.Frame(page);bottom.pack(fill='x')
        self.update_text=tk.StringVar(value='GitHub 업데이트 안내 연결됨')
        ttk.Label(bottom,textvariable=self.update_text,style='Muted.TLabel').pack(side='left')
        self.update_button=ttk.Button(bottom,text='업데이트 확인',command=lambda:self.update_check(True));self.update_button.pack(side='right')

    def destination_changed(self,_=None):
        self.difficulty.set({'허상의 정박지':'매우 어려움','광기의 동굴':'어려움','흩어진 물길':'입문'}[self.dungeon.get()])
        if self.dungeon.get() != '허상의 정박지':
            self.log('이 던전의 상세·전투 화면은 실게임 확인이 필요합니다. 이름·조건을 확인하지 못하면 입장을 보류합니다.')

    def log(self,message):
        LOG.info(message)
        self.log_box.configure(state='normal')
        self.log_box.insert('end',time.strftime('%H:%M:%S')+'  '+message+'\n')
        if int(self.log_box.index('end-1c').split('.')[0])>500:
            self.log_box.delete('1.0','100.0')
        self.log_box.see('end');self.log_box.configure(state='disabled')

    def refresh(self):
        if self.running:return
        previous = None
        index = self.window_box.current()
        if 0 <= index < len(self.windows):previous=self.windows[index][0]
        self.windows=self.win.list_windows()
        self.window_box['values']=[f'{title}  [{width}×{height}]' for _,title,width,height in self.windows]
        if self.windows:
            preferred=next((i for i,w in enumerate(self.windows) if w[0]==previous),None)
            if preferred is None:preferred=next((i for i,w in enumerate(self.windows) if self.win.active(w[0])),0)
            self.window_box.current(preferred)
        else:self.window_choice.set('마비노기 모바일을 실행해 주세요')

    def selected(self):
        index=self.window_box.current()
        if index<0 or index>=len(self.windows):raise WindowError('마비노기 모바일 게임 창을 찾지 못했습니다. 게임을 실행하세요.')
        hwnd=self.windows[index][0]
        self.win.ensure_game(hwnd)
        return hwnd

    def sizing_finished(self):
        self.sizing_busy=False
        self.resize_button.configure(state='normal')
        self.start_button.configure(state='normal')

    def sizing_error(self,hwnd,error):
        try:self.log('창 맞춤 진단: '+json.dumps(self.win.diagnostics(hwnd),ensure_ascii=False))
        except Exception:LOG.exception('Window diagnostics failed')
        self.log('창 맞춤 실패: '+str(error))
        self.detail.set('창 맞추기 실패 — 기록에서 원인을 확인하세요.')
        self.sizing_finished()
        messagebox.showerror('자동 창 맞추기 진단',str(error)+'\n\n상세 정보는 기록 폴더의 app.log에 저장했습니다.',parent=self.root)

    def resize(self):
        if self.running or self.sizing_busy:return
        hwnd=None
        try:
            self.refresh();hwnd=self.selected()
            self.log('창 맞춤 시작: '+json.dumps(self.win.diagnostics(hwnd),ensure_ascii=False))
            self.sizing_busy=True
            self.resize_button.configure(state='disabled');self.start_button.configure(state='disabled')
            info=self.win.prepare_resize(hwnd)
            if info['fullscreen_like'] and info['client'] != [800,1000]:
                self.detail.set('전체 화면 감지 → 게임 활성화 및 창 모드 전환 중…')
                self.root.after(300,lambda:self.exit_fullscreen(hwnd))
            else:self.apply_resize(hwnd)
        except WindowError as e:
            if hwnd is None:
                messagebox.showerror('게임 창 확인',str(e),parent=self.root)
            else:self.sizing_error(hwnd,e)

    def exit_fullscreen(self,hwnd):
        if self.closing:return
        try:
            self.win.toggle_fullscreen(hwnd)
            self.log('전체 화면 전환: 게임에 Alt+Enter를 한 번 전달했습니다.')
            self.root.after(1400,lambda:self.apply_resize(hwnd))
        except WindowError as e:self.sizing_error(hwnd,e)

    def apply_resize(self,hwnd):
        if self.closing:return
        try:
            info=self.win.diagnostics(hwnd)
            # Persistent borderless or fixed-style windows require a real frame change.
            if info['fullscreen_like'] or not (int(info['style'],16)&0x00C00000):
                self.win.make_windowed(hwnd)
                self.log('테두리 없는 창/고정 창의 스타일을 보정했습니다.')
            self.win.resize(hwnd)
            self.detail.set('800×1000 적용 후 실제 화면 크기 확인 중…')
            self.root.after(600,lambda:self.verify_size(hwnd))
        except WindowError as e:self.sizing_error(hwnd,e)

    def verify_size(self,hwnd,attempt=0):
        if self.closing:return
        try:
            self.win.ensure_game(hwnd)
            _,_,w,h=self.win.rect(hwnd)
            self.log(f'창 맞춤 검증 {attempt+1}: 실제 게임 영역 {w}×{h}')
            if (w,h)!=(800,1000):
                if attempt<3:
                    self.win.resize(hwnd,correction=True)
                    self.root.after(650,lambda:self.verify_size(hwnd,attempt+1));return
                raise WindowError(f'실제 화면이 {w}×{h}로 유지됩니다. 게임이 전체 화면/고정 해상도로 되돌리거나 크기 변경을 제한하고 있습니다. 자동 전환이 지원되지 않으면 게임 설정에서 디스플레이 모드를 변경해야 합니다.')
            self.refresh();self.sizing_finished()
            self.log('자동 창 맞추기 완료: 실제 게임 화면 800×1000 확인.')
            self.log('창 맞춤 결과: '+json.dumps(self.win.diagnostics(hwnd),ensure_ascii=False))
            self.detail.set('게임 화면 800 × 1000 확인 완료')
        except WindowError as e:self.sizing_error(hwnd,e)

    def lock_controls(self,running):
        for w in (self.window_box,self.dungeon_box,self.difficulty_box):w.configure(state='disabled' if running else 'readonly')
        for w in (self.refresh_button,self.resize_button,self.start_button,self.repeat_check,self.food_check):w.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running else 'disabled')

    def start(self):
        if self.running or self.sizing_busy:return
        try:
            self.refresh()
            hwnd=self.selected()
            _,_,w,h=self.win.rect(hwnd)
            if (w,h)!=(800,1000):raise WindowError(f'실제 화면이 {w}×{h}입니다. 먼저 게임 창 자동 맞추기를 누르세요.')
        except WindowError as e:
            messagebox.showerror('시작할 수 없음',str(e),parent=self.root);return
        self.settings={'dungeon':self.dungeon.get(),'difficulty':self.difficulty.get(),'repeat':self.repeat.get(),'food':self.food.get()}
        self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
        self.running=True;self.stop_event.clear();self.lock_controls(True)
        self.status.set('게임 창을 클릭하세요')
        self.log('시작: '+self.dungeon.get()+' / '+self.difficulty.get()+' — 게임 창이 앞에 있을 때만 인식·클릭합니다.')
        self.worker=threading.Thread(target=self.run,args=(hwnd,dict(self.settings)),daemon=True);self.worker.start()

    def stop(self):
        self.stop_event.set()
        if self.running:
            self.status.set('중지 중…')

    def run(self,hwnd,config):
        try:
            detector=Vision(BASE/'assets.json')
            controller=Controller(config['dungeon'],config['difficulty'],config['repeat'])
            last_screen,streak,food_streak='',0,0
            paused_at=None;last_status=None;unknown_since=None;warned=False
            with mss.mss() as capture:
                while not self.stop_event.is_set():
                    now=time.monotonic()
                    if not self.win.active(hwnd):
                        if paused_at is None:
                            paused_at=now;detector.stillness.reset();controller.still_since=None
                            self.events.put(('status',('게임 창 활성화 대기','게임 창을 앞에 두면 진행을 이어갑니다.')))
                        self.stop_event.wait(.25);continue
                    if paused_at is not None:
                        if controller.entered_at is not None:controller.entered_at+=now-paused_at
                        paused_at=None;last_status=None;last_screen='';streak=0
                    self.win.ensure_game(hwnd)
                    left,top,width,height=self.win.rect(hwnd)
                    if (width,height)!=(800,1000):raise WindowError('화면 크기가 바뀌어 중지했습니다. 800×1000으로 다시 맞추세요.')
                    monitor=capture.monitors[0]
                    if left<monitor['left'] or top<monitor['top'] or left+width>monitor['left']+monitor['width'] or top+height>monitor['top']+monitor['height']:
                        raise WindowError('게임 화면 전체가 모니터 안에 보이도록 창을 옮기세요.')
                    frame=np.array(capture.grab({'left':left,'top':top,'width':width,'height':height}))[:,:,:3]
                    observation=detector.observe(frame,config['dungeon'],config['difficulty'])
                    food_streak=food_streak+1 if observation.food else 0
                    if not config['food'] or food_streak<2:
                        from dataclasses import replace
                        observation=replace(observation,food=False)
                    streak=streak+1 if last_screen==observation.screen else 1
                    last_screen=observation.screen
                    if observation.screen=='unknown':
                        controller.still_since=None
                        if unknown_since is None:unknown_since=now
                        if now-unknown_since>15 and not warned:
                            self.events.put(('log','화면을 인식하지 못하고 있습니다. 팝업·가려진 화면·UI 배율을 확인하세요.'))
                            warned=True
                    else:unknown_since=None;warned=False
                    action=controller.step(observation,now) if streak>=2 else None
                    status=(controller.state.value,controller.reason or ('감지: '+{'unknown':'화면 확인 중','field':'일반 화면','combat':'전투','detail':'입장 설정','matching':'우연한 만남 대기','loading':'로딩','cutscene':'보스 연출','reward':'보상','mission':'협동 미션','clear':'던전 클리어','menu':'메뉴','list':'어비스 목록'}.get(observation.screen,observation.screen)))
                    if status!=last_status:self.events.put(('status',status));last_status=status
                    if action and not self.stop_event.is_set():
                        self.win.click(hwnd,action.point)
                        self.events.put(('log',action.message))
                    if controller.state==State.BLOCKED:
                        self.events.put(('log',controller.reason));break
                    self.stop_event.wait(.25)
        except Exception as e:
            LOG.exception('Worker stopped')
            self.events.put(('error',str(e)))
        finally:self.events.put(('stopped',None))

    def update_check(self,manual=False):
        if self.update_busy:return
        self.update_busy=True;self.update_text.set('업데이트 확인 중…')
        def check():
            try:self.events.put(('update',(check_update(),manual,None)))
            except Exception as e:self.events.put(('update',(None,manual,str(e))))
        threading.Thread(target=check,daemon=True).start()
        if not manual:self.root.after(30*60*1000,self.update_check)

    def show_update(self,result):
        if self.update_dialog and self.update_dialog.winfo_exists():
            self.update_dialog.lift();return
        dialog=tk.Toplevel(self.root);dialog.title('새 업데이트 다운로드');dialog.geometry('620x600');dialog.configure(bg=BG)
        self.update_dialog=dialog
        dialog.transient(self.root)
        frame=ttk.Frame(dialog,padding=24);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='새 버전이 도착했어요',font=('맑은 고딕',20,'bold')).pack(anchor='w')
        ttk.Label(frame,text=f"현재 v{VERSION}  →  {result['version']}",foreground=ACCENT).pack(anchor='w',pady=12)
        text=tk.Text(frame,bg='#09101b',fg=TEXT,relief='flat',wrap='word',font=('맑은 고딕',10),padx=12,pady=12)
        text.insert('1.0',result['notes']);text.configure(state='disabled');text.pack(fill='both',expand=True,pady=(0,12))
        progress=ttk.Progressbar(frame,mode='determinate',maximum=100);progress.pack(fill='x')
        status=tk.StringVar(value='새 버전을 앱에서 바로 다운로드할 수 있습니다.')
        ttk.Label(frame,textvariable=status,wraplength=560).pack(anchor='w',pady=(6,8))
        ttk.Label(frame,text='저장 후 현재 앱을 종료하고 새 실행 파일을 실행하세요.',style='Muted.TLabel').pack(anchor='w')
        row=ttk.Frame(frame);row.pack(fill='x',pady=(15,0))
        events=queue.Queue()
        cancel=threading.Event()
        state={'busy':False,'saved':None}
        def close_dialog():
            cancel.set();dialog.destroy()
        dialog.protocol('WM_DELETE_WINDOW',close_dialog)
        def start_download():
            if state['busy']:return
            downloads=Path.home()/'Downloads'
            initial=downloads if downloads.is_dir() else Path.home()
            filename=filedialog.asksaveasfilename(parent=dialog,title='새 버전 저장',initialdir=str(initial),
                initialfile='AbyssHelper-'+result['version']+'.exe',defaultextension='.exe',filetypes=[('Windows 실행 파일','*.exe')])
            if not filename:return
            destination=Path(filename)
            if getattr(sys,'frozen',False) and destination.resolve()==Path(sys.executable).resolve():
                messagebox.showinfo('저장 위치','실행 중인 앱과 다른 파일명으로 저장하세요.',parent=dialog);return
            cancel.clear();state['busy']=True;self.download_cancels.add(cancel)
            download_button.configure(state='disabled');cancel_button.configure(state='normal')
            folder_button.configure(state='disabled');progress['value']=0
            status.set('다운로드 연결 중…')
            def worker():
                last=0.
                def report(done,total):
                    nonlocal last
                    now=time.monotonic()
                    if now-last>.1 or done==total:
                        events.put(('progress',(done,total)));last=now
                try:
                    path=download_release(result,destination,report,cancel)
                    events.put(('done',path))
                except DownloadCancelled:events.put(('cancelled',None))
                except Exception as e:
                    LOG.exception('Update download failed');events.put(('error',str(e)))
            self.download_workers=[t for t in self.download_workers if t.is_alive()]
            thread=threading.Thread(target=worker,daemon=True)
            self.download_workers.append(thread);thread.start()
        def poll():
            if not dialog.winfo_exists():
                self.download_cancels.discard(cancel);return
            for _ in range(100):
                try:kind,value=events.get_nowait()
                except queue.Empty:break
                if kind=='progress':
                    done,total=value;progress['value']=100*done/total
                    status.set(f'{100*done/total:.0f}%  ·  {done/1048576:.1f} / {total/1048576:.1f} MB')
                else:
                    state['busy']=False;self.download_cancels.discard(cancel)
                    download_button.configure(state='normal');cancel_button.configure(state='disabled')
                    if kind=='done':
                        state['saved']=value;progress['value']=100
                        status.set('다운로드 완료: '+str(value));folder_button.configure(state='normal')
                        self.log('새 버전 다운로드 완료: '+str(value))
                    elif kind=='cancelled':status.set('다운로드를 취소했습니다. 다시 시도할 수 있습니다.')
                    else:status.set('다운로드 실패: '+value)
            dialog.after(100,poll)
        download_button=ttk.Button(row,text='새 버전 다운로드',style='Start.TButton',command=start_download);download_button.pack(side='left')
        folder_button=ttk.Button(row,text='저장 폴더 열기',state='disabled',command=lambda:os.startfile(state['saved'].parent));folder_button.pack(side='left',padx=8)
        cancel_button=ttk.Button(row,text='취소',state='disabled',command=cancel.set);cancel_button.pack(side='left')
        ttk.Button(row,text='닫기',command=close_dialog).pack(side='right')
        ttk.Button(frame,text='GitHub 배포 페이지',command=lambda:webbrowser.open(result['url']) if release_url(result['url']) else None).pack(anchor='w',pady=(8,0))
        dialog.after(100,poll)

    def pump(self):
        if self.closing:return
        for _ in range(100):
            try:kind,value=self.events.get_nowait()
            except queue.Empty:break
            if kind=='log':self.log(value)
            elif kind=='status':self.status.set(value[0]);self.detail.set(value[1])
            elif kind=='error':self.log(value);messagebox.showerror('실행 중지',value,parent=self.root)
            elif kind=='stopped':
                self.running=False;self.lock_controls(False)
                if self.status.get()!='확인 필요':self.status.set('중지됨')
            elif kind=='update':
                self.update_busy=False;result,manual,error=value
                if error:
                    self.update_text.set('업데이트 연결 실패 · 재시도 가능')
                    if manual:messagebox.showinfo('업데이트 확인','연결을 확인하고 다시 시도하세요.\n'+error,parent=self.root)
                elif result:
                    self.update_text.set(result['version']+' 업데이트 있음')
                    if manual or result['version'] not in self.seen_updates:
                        self.seen_updates.add(result['version']);self.show_update(result)
                else:
                    self.update_text.set('현재 배포 버전 확인 완료 · v'+VERSION)
                    if manual:messagebox.showinfo('업데이트 확인','현재 버전보다 새로운 정식 배포가 없습니다.',parent=self.root)
        keys=self.win.keys()
        if keys[1] and not self.previous_keys[1]:self.stop()
        elif keys[0] and not self.previous_keys[0]:
            if self.running:self.stop()
            else:self.start()
        self.previous_keys=keys
        self.root.after(100,self.pump)

    def callback_error(self,typ,value,tb):
        LOG.error('UI error',exc_info=(typ,value,tb))
        self.stop()
        messagebox.showerror('오류','작업을 중지했습니다. 기록 폴더의 app.log를 확인하세요.\n'+str(value),parent=self.root)

    def close(self):
        self.closing=True;self.stop_event.set()
        for cancel in self.download_cancels:cancel.set()
        self.root.after(100,self.wait_close)

    def wait_close(self):
        if (self.worker and self.worker.is_alive()) or any(t.is_alive() for t in self.download_workers):self.root.after(100,self.wait_close)
        else:self.root.destroy()


def main():
    root=tk.Tk()
    try:
        App(root)
    except Exception as e:
        LOG.exception('Startup failed')
        messagebox.showerror('시작 오류',str(e),parent=root);root.destroy();return
    root.mainloop()


if __name__=='__main__':
    if '--smoke-test' in sys.argv:
        # Windows build validation: imports, packaged templates, native API and Tk UI.
        root=tk.Tk();root.withdraw()
        app=App(root)
        root.update_idletasks()
        detector=Vision(BASE/'assets.json')
        app.show_update({'version':'v99.0.0','url':'https://github.com/'+REPOSITORY+'/releases/tag/v99.0.0','notes':'업데이트 다운로드 UI 검사','asset':{}})
        root.update_idletasks()
        app.update_dialog.destroy()
        report={'ok':True,'version':VERSION,'templates':len(detector.data),'ui':'created','platform':sys.platform}
        out=Path(sys.argv[sys.argv.index('--report')+1])
        out.write_text(json.dumps(report),encoding='utf-8')
        app.closing=True;root.destroy()
    else:
        main()
