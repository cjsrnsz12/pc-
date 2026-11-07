import sys
if __name__=='__main__' and '--apply-update' in sys.argv:
    from installer import apply_plan
    raise SystemExit(apply_plan(sys.argv[sys.argv.index('--apply-update')+1]))

"""Abyss Helper desktop application (Windows; packaged with --windowed)."""
if __name__=='__main__' and '--test-update-owner' in sys.argv:
    from installer import integration_owner
    integration_owner(sys.argv[sys.argv.index('--test-update-owner')+1])
    raise SystemExit(0)
if __name__=='__main__' and '--updater-self-test' in sys.argv:
    from installer import integration_self_test
    raise SystemExit(integration_self_test(sys.argv[sys.argv.index('--report')+1]))

from windows import dpi_aware
dpi_aware()
import json
import logging
from log_retention import DailyRetentionHandler
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
import uuid
import shutil
import cv2
import mss
import numpy as np
from PIL import Image, ImageTk
from engine import Controller, Observation, State
from raid import RaidController,RaidVision,RAID_DIFFICULTIES
from recognition_timing import poll_interval, same_detection
from list_centering import ListCentering,RaidEntryCentering
from capture_guard import CapturePause, within_desktop
from window_sizing import supported_client
from failure_diagnostics import save_failure,create_bundle,LOG_FILENAME
from startup_notes import needs_notice, installed_release, mark_shown
from vision import Vision, DUNGEONS, DIFFICULTIES
from windows import Windows, WindowError
from privileges import permission_advice, relaunch_admin, process_elevated
from updates import check_update, release_url, download_release, DownloadCancelled
from version import VERSION, REPOSITORY
from installer import prepare_install, launch_installer, cleanup_updates
from update_notice import UpdateNotice
from ui_controls import SmoothCheckbutton, smooth_buttons,RoundScrollbar
from ui_theme import LauncherHeader, app_icon
from choice_control import SmoothChoice, DIFFICULTY_COLORS, PLAY_MODES, CONTENT_TYPES
from update_prompt import UpdatePrompt

BASE = Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
DATA = Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'AbyssHelper'
DATA.mkdir(parents=True,exist_ok=True)
cleanup_updates(DATA/'updates')
LOG = logging.getLogger('abyss')
LOG.setLevel(logging.INFO)
if not (DATA/LOG_FILENAME).exists() and (DATA/'app.log').is_file():
    try:shutil.copyfile(DATA/'app.log',DATA/LOG_FILENAME)
    except OSError:pass
_handler = DailyRetentionHandler(DATA)
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
        self.resize_target=(800,1000)
        self.closing = False
        self.update_busy = False
        self.seen_updates = set()
        self.download_cancels = set()
        self.download_workers = []
        self.update_dialog = None
        self.update_notice = None
        self.installed_notice = None
        self.update_prompt = None
        self.install_owner = None
        self.latest_release = None
        self.update_manual_requested = False
        self.permission_dialog = None
        self.installing = False
        self.previous_keys = (False,False)
        self.windows = []
        self.settings_path = DATA/'settings.json'
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (ValueError,OSError):
            self.settings = {}
        root.title('어비스 헬퍼 · PC')
        try:
            _,work=self.win.monitor_info(self.win.u.GetAncestor(root.winfo_id(),2))
        except Exception:work=(0,0,root.winfo_screenwidth(),root.winfo_screenheight())
        width=min(820,max(600,work[2]-work[0]-48));height=min(950,max(480,work[3]-work[1]-56))
        root.geometry(f'{width}x{height}+{work[0]+24}+{work[1]+12}')
        root.minsize(min(760,width),min(640,height))
        root.configure(bg=BG)
        self._window_icon=ImageTk.PhotoImage(app_icon(64),master=root)
        root.iconphoto(True,self._window_icon)
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.report_callback_exception = self.callback_error
        self.style()
        self.build()
        self.refresh()
        self.log('v'+VERSION+' / 앱 관리자 권한: '+str(process_elevated()))
        self.log('게임 창 자동 맞추기 또는 시작을 누르면 필요한 권한을 확인합니다. 권한 확인 버튼으로도 볼 수 있습니다.')
        root.after(100,self.pump)
        root.after(min(1000,_handler.next_cleanup_ms()),self.maintain_logs)
        root.after(1600,self.update_check)
        if '--smoke-test' not in sys.argv:root.after(700,self.show_installed_changes)
        if '--update-ready' in sys.argv:
            ready=Path(sys.argv[sys.argv.index('--update-ready')+1]).resolve()
            if ready.parent.parent==(DATA/'updates').resolve() and ready.parent.name.startswith('session-'):
                root.after(300,lambda:ready.write_text(json.dumps({'ok':True,'version':VERSION}),encoding='utf-8'))
                if '--update-test-exit' in sys.argv:root.after(1200,self.close)

    def style(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('.',font=('맑은 고딕',10),background=BG,foreground=TEXT)
        s.configure('TFrame',background=BG)
        s.configure('Card.TFrame',background=PANEL,relief='solid',borderwidth=1,bordercolor='#304565',lightcolor='#243750',darkcolor='#152238')
        s.configure('TLabel',background=BG,foreground=TEXT)
        s.configure('Muted.TLabel',foreground=MUTED)
        s.configure('Title.TLabel',font=('맑은 고딕',24,'bold'))
        s.configure('Card.TLabel',background=PANEL)
        s.configure('Big.Card.TLabel',background=PANEL,font=('맑은 고딕',16,'bold'),foreground=ACCENT)
        s.configure('TButton',padding=(13,9),background='#263550',foreground=TEXT,borderwidth=0)
        s.map('TButton',background=[('disabled','#172239'),('pressed','#30435f'),('active','#354b6e')],foreground=[('disabled','#8190aa'),('!disabled',TEXT)],bordercolor=[('!disabled','#263550')],lightcolor=[('!disabled','#263550')],darkcolor=[('!disabled','#263550')])
        s.configure('Start.TButton',background=ACCENT,foreground='#05271e',font=('맑은 고딕',12,'bold'))
        s.map('Start.TButton',background=[('disabled','#23483e'),('active','#7cecc8')],foreground=[('disabled','#8190aa'),('!disabled','#05271e')])
        s.configure('Stop.TButton',foreground='#ffacb5')
        s.configure('TCombobox',fieldbackground='#263550',background='#263550',foreground=TEXT,padding=7,arrowcolor=TEXT)
        s.map('TCombobox',fieldbackground=[('disabled','#182237'),('readonly','#263550'),('active','#263550')],background=[('disabled','#182237'),('active','#30425e'),('!disabled','#263550')],foreground=[('disabled',MUTED),('readonly',TEXT)],bordercolor=[('focus','#7dd9cf'),('active','#7a6fc2'),('!disabled','#455577')],lightcolor=[('!disabled','#263550')],darkcolor=[('!disabled','#263550')],selectbackground=[('!disabled','#354e73')],selectforeground=[('!disabled',TEXT)])
        s.configure('Horizontal.TProgressbar',background=ACCENT,troughcolor='#162136',bordercolor='#162136',lightcolor=ACCENT,darkcolor=ACCENT,borderwidth=0,thickness=7)
        s.configure('Vertical.TScrollbar',background='#314660',troughcolor=BG,bordercolor=BG,arrowcolor=MUTED,lightcolor='#314660',darkcolor='#314660',borderwidth=0,width=12)
        s.map('Vertical.TScrollbar',background=[('pressed','#5e8aa8'),('active','#426381')],lightcolor=[('!disabled','#314660')],darkcolor=[('!disabled','#314660')],bordercolor=[('!disabled',BG)],arrowcolor=[('!disabled',MUTED)])
        s.configure('TCheckbutton',background=BG,foreground=TEXT,padding=5)
        s.map('TCheckbutton',background=[('disabled',BG),('active',BG),('!disabled',BG)],foreground=[('disabled','#8190aa'),('!disabled',TEXT)])
        root=self.root
        root.option_add('*TCombobox*Listbox.background','#263550')
        root.option_add('*TCombobox*Listbox.foreground',TEXT)

    def build(self):
        self.footer=ttk.Frame(self.root,padding=(24,10,24,14));self.footer.pack(side='bottom',fill='x')
        content=ttk.Frame(self.root);content.pack(fill='both',expand=True)
        self.page_canvas=tk.Canvas(content,bg=BG,highlightthickness=0,bd=0)
        scrollbar=RoundScrollbar(content,command=self.page_canvas.yview)
        scrollbar.pack(side='right',fill='y');self.page_canvas.pack(side='left',fill='both',expand=True)
        self.page_canvas.configure(yscrollcommand=scrollbar.set)
        page=ttk.Frame(self.page_canvas,padding=(24,24,14,18))
        window=self.page_canvas.create_window(0,0,anchor='nw',window=page)
        page.bind('<Configure>',lambda _:self.page_canvas.configure(scrollregion=self.page_canvas.bbox('all')))
        self.page_canvas.bind('<Configure>',lambda e:self.page_canvas.itemconfigure(window,width=e.width))
        self.root.bind('<MouseWheel>',self.scroll_page,add='+')
        self.header=LauncherHeader(page,VERSION);self.header.pack(fill='x',pady=(0,18))
        card=ttk.Frame(page,style='Card.TFrame',padding=18);card.pack(fill='x')
        ttk.Label(card,text='●  CURRENT STATUS  /  현재 상태',style='Card.TLabel').pack(anchor='w')
        self.status=tk.StringVar(value='시작 대기')
        ttk.Label(card,textvariable=self.status,style='Big.Card.TLabel').pack(anchor='w',pady=(6,2))
        self.detail=tk.StringVar(value='게임 화면 기준 800 × 1000  ·  정지 확인 4초')
        ttk.Label(card,textvariable=self.detail,style='Card.TLabel',wraplength=620).pack(anchor='w')
        ttk.Label(page,text='게임 창',font=('맑은 고딕',11,'bold')).pack(anchor='w',pady=(18,7))
        row=ttk.Frame(page);row.pack(fill='x')
        self.window_choice=tk.StringVar()
        self.window_box=ttk.Combobox(row,textvariable=self.window_choice,state='readonly');self.window_box.pack(side='left',fill='x',expand=True)
        self.refresh_button=ttk.Button(row,text='↻ 새로고침',command=self.refresh);self.refresh_button.pack(side='left',padx=(8,0))
        self.resize_button=ttk.Button(row,text='▣ 게임 창 자동 맞추기',command=self.resize);self.resize_button.pack(side='left',padx=(8,0))
        destination_section=ttk.Frame(page);destination_section.pack(fill='x',pady=(15,8))
        ttk.Label(destination_section,text='콘텐츠').pack(anchor='w',pady=(0,5))
        self.content=tk.StringVar(value=self.settings.get('content','어비스'))
        if self.content.get() not in CONTENT_TYPES:self.content.set('어비스')
        self.content_box=SmoothChoice(destination_section,textvariable=self.content,values=CONTENT_TYPES);self.content_box.pack(fill='x')
        self.content_hint=ttk.Label(destination_section,text='레이드 · 보상 확인·배 복귀·재출항 반복',foreground='#ffc454',padding=(0,12),wraplength=650)
        options=self.destination_options=ttk.Frame(destination_section);options.pack(fill='x',pady=(12,0))
        options.columnconfigure(0,weight=1);options.columnconfigure(1,weight=1)
        ttk.Label(options,text='목적지').grid(row=0,column=0,sticky='w',pady=(0,5))
        ttk.Label(options,text='난이도').grid(row=0,column=1,sticky='w',padx=(12,0),pady=(0,5))
        self.dungeon=tk.StringVar(value=self.settings.get('abyss_dungeon',self.settings.get('dungeon','허상의 정박지')))
        if self.dungeon.get() not in DUNGEONS:self.dungeon.set('허상의 정박지')
        self.difficulty=tk.StringVar(value=self.settings.get('abyss_difficulty',self.settings.get('difficulty','매우 어려움')))
        if self.difficulty.get() not in DIFFICULTIES:self.difficulty.set('매우 어려움')
        self.dungeon_box=SmoothChoice(options,textvariable=self.dungeon,values=list(DUNGEONS),command=self.destination_changed);self.dungeon_box.grid(row=1,column=0,sticky='ew')
        self.difficulty_box=SmoothChoice(options,textvariable=self.difficulty,values=DIFFICULTIES,colors=DIFFICULTY_COLORS);self.difficulty_box.grid(row=1,column=1,sticky='ew',padx=(12,0))
        self.repeat=tk.BooleanVar(value=bool(self.settings.get('repeat',True)))
        self.food=tk.BooleanVar(value=bool(self.settings.get('food',True)))
        self.play_mode=tk.StringVar(value=self.settings.get('play_mode',PLAY_MODES[0]).removesuffix(' · 준비 중'))
        if self.play_mode.get() not in PLAY_MODES:self.play_mode.set(PLAY_MODES[0])
        self.play_mode.trace_add('write',self.play_mode_changed)
        self.repeat.set(True)
        ttk.Label(page,text='플레이 모드').pack(anchor='w',pady=(6,4))
        self.mode_box=SmoothChoice(page,textvariable=self.play_mode,values=PLAY_MODES);self.mode_box.pack(fill='x',pady=(0,4))
        self.mode_hint=tk.StringVar(value='솔로: 다시 하기 · 파티: 다른 던전 가기 → 목적지 선택 → 입장하기')
        ttk.Label(page,textvariable=self.mode_hint,style='Muted.TLabel').pack(anchor='w')
        self.entry_hint=tk.StringVar(value='입장 조건: 함께하기 · 선택한 난이도 · 우연한 만남 ON')
        self.food_check=SmoothCheckbutton(page,text='음식 아이콘이 나타나면 한 번 클릭',variable=self.food);self.food_check.pack(anchor='w')
        ttk.Label(page,textvariable=self.entry_hint,style='Muted.TLabel').pack(anchor='w',pady=(4,10))
        controls=ttk.Frame(page);controls.pack(fill='x',pady=(0,10))
        self.start_button=ttk.Button(controls,text='▶  시작   F8',style='Start.TButton',command=self.start);self.start_button.pack(side='left',fill='x',expand=True)
        self.stop_button=ttk.Button(controls,text='■  중지   F9',style='Stop.TButton',command=self.stop,state='disabled');self.stop_button.pack(side='left',fill='x',expand=True,padx=(10,0))
        ttk.Label(page,text='시작 후 게임 창을 클릭하세요. 다른 창을 사용하면 자동으로 대기합니다.',style='Muted.TLabel',wraplength=650).pack(anchor='w',pady=(0,12))
        log_header=ttk.Frame(page);log_header.pack(fill='x')
        ttk.Label(log_header,text='✦ 진행 기록',font=('맑은 고딕',11,'bold')).pack(side='left')
        ttk.Button(log_header,text='로그 파일 저장',command=self.export_logs).pack(side='right',padx=(8,0))
        ttk.Button(log_header,text='기록 폴더',command=lambda:os.startfile(DATA)).pack(side='right')
        self.log_box=tk.Text(page,height=8,background='#09101b',foreground='#b9cbea',font=('맑은 고딕',9),relief='flat',padx=12,pady=10,wrap='word',state='disabled')
        self.log_box.pack(fill='both',expand=True,pady=(8,12))
        bottom=self.footer
        self.update_text=tk.StringVar(value='GitHub 업데이트 안내 연결됨')
        ttk.Label(bottom,textvariable=self.update_text,style='Muted.TLabel').pack(side='left')
        self.update_button=ttk.Button(bottom,text='업데이트 소식',command=self.open_update_notice);self.update_button.pack(side='right')
        ttk.Button(bottom,text='권한 확인',command=self.check_permissions).pack(side='right',padx=(0,8))
        self._active_content='어비스'
        self._content_values={'어비스':(self.dungeon.get(),self.difficulty.get()),'레이드':('카브락',self.settings.get('raid_difficulty','입문'))}
        if self._content_values['레이드'][1] not in RAID_DIFFICULTIES:self._content_values['레이드']=('카브락','입문')
        self.content.trace_add('write',self.content_changed)
        self.content_changed()
        smooth_buttons(self.root)

    def maintain_logs(self):
        if self.closing:return
        try:_handler.purge()
        except OSError:pass
        self.root.after(_handler.next_cleanup_ms(),self.maintain_logs)

    def export_logs(self):
        destination=filedialog.asksaveasfilename(parent=self.root,title='로그 파일과 오류 화면 함께 저장',initialfile='로그 파일.zip',defaultextension='.zip',filetypes=[('로그 묶음','*.zip')])
        if not destination:return
        try:
            _handler.flush();create_bundle(DATA,destination)
            messagebox.showinfo('로그 파일','로그 파일과 저장된 오류 화면을 ZIP으로 묶었습니다. 이 대화에 첨부해 주세요.',parent=self.root)
        except OSError as error:messagebox.showerror('로그 파일 저장 실패',str(error),parent=self.root)

    def save_problem(self,frame,metadata):
        save_failure(DATA/'diagnostics',frame,metadata)
        LOG.info('오류 화면·진단 정보 저장 완료. 로그 파일.zip을 보내 주세요.')
        _handler.flush();create_bundle(DATA)

    def scroll_page(self,event):
        if not isinstance(event.widget,tk.Misc):return
        if event.widget.winfo_toplevel() is not self.root:return
        if isinstance(event.widget,(tk.Text,ttk.Combobox)):return
        self.page_canvas.yview_scroll(-int(event.delta/120),'units')

    def collect_settings(self):
        self._content_values[self._active_content]=(self.dungeon.get(),self.difficulty.get())
        abyss=self._content_values['어비스'];raid=self._content_values['레이드']
        return dict(self.settings,dungeon=self.dungeon.get(),difficulty=self.difficulty.get(),repeat=self.repeat.get(),
                    food=self.food.get(),play_mode=self.play_mode.get(),content=self.content.get(),
                    abyss_dungeon=abyss[0],abyss_difficulty=abyss[1],raid_difficulty=raid[1])

    def content_changed(self,*_):
        self._content_values[self._active_content]=(self.dungeon.get(),self.difficulty.get())
        self._active_content=self.content.get()
        raid=self._active_content=='레이드'
        self.dungeon_box.dismiss();self.difficulty_box.dismiss()
        self.mode_box.values=[PLAY_MODES[0]] if raid else PLAY_MODES
        if raid:self.play_mode.set(PLAY_MODES[0])
        self.dungeon_box.values=['카브락'] if raid else list(DUNGEONS)
        self.difficulty_box.values=RAID_DIFFICULTIES if raid else DIFFICULTIES
        destination,difficulty=self._content_values[self._active_content]
        self.dungeon.set(destination);self.difficulty.set(difficulty)
        self.destination_options.pack(fill='x',pady=(12,0))
        if raid:
            self.content_hint.configure(text='레이드 · 보상 확인·배 복귀·재출항 반복')
            self.content_hint.pack(fill='x')
        else:self.content_hint.pack_forget()
        self.entry_hint.set('레이드 조건: 카브락 · 혼자하기 · 입문/어려움 · 지역 도착 후 출항' if raid else '입장 조건: 함께하기 · 선택한 난이도 · 우연한 만남 ON')
        if _:
            self.settings=self.collect_settings()
            try:self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError as error:self.log('콘텐츠 선택 저장 실패: '+str(error))
        self.play_mode_changed()

    def destination_changed(self,_=None):
        if self.content.get()=='레이드':return
        self.difficulty.set({'허상의 정박지':'매우 어려움','광기의 동굴':'어려움','흩어진 물길':'입문'}[self.dungeon.get()])
        self.log('목적지 변경: '+self.dungeon.get()+' — 화면의 실제 던전 이름과 선택 조건을 다시 확인합니다.')

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

    def check_permissions(self):
        hwnd=None
        try:
            self.refresh();hwnd=self.selected()
        except WindowError:pass
        self.show_permission_notice('게임 조작',hwnd=hwnd)

    def show_permission_notice(self,operation,error=None,hwnd=None,file_access=False):
        if self.permission_dialog and self.permission_dialog.winfo_exists():
            self.permission_dialog.lift();return
        rights=getattr(error,'rights',None)
        if rights is None:
            try:rights=self.win.permission_status(hwnd)
            except Exception:rights={'app_admin':process_elevated(),'game_admin':None}
        code=getattr(error,'winerror',None)
        advice=permission_advice(operation,rights['app_admin'],rights['game_admin'],code,file_access)
        self.log('권한 안내: '+advice['levels']+' / '+operation+((' / '+str(error)) if error else ''))
        dialog=tk.Toplevel(self.root);self.permission_dialog=dialog
        dialog.title(advice['title']);dialog.geometry('630x510');dialog.configure(bg=BG);dialog.transient(self.root)
        frame=ttk.Frame(dialog,padding=24);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text=advice['title'],font=('맑은 고딕',18,'bold')).pack(anchor='w')
        ttk.Label(frame,text=advice['levels'],foreground=ACCENT).pack(anchor='w',pady=(12,10))
        text=tk.Text(frame,bg='#09101b',fg=TEXT,relief='flat',wrap='word',font=('맑은 고딕',10),padx=12,pady=12)
        text.insert('1.0',advice['message'])
        if error:text.insert('end','\n\n작업: '+operation+'\n오류: '+str(error))
        text.configure(state='disabled');text.pack(fill='both',expand=True,pady=(0,15))
        row=ttk.Frame(frame);row.pack(fill='x')
        if advice['can_elevate'] and getattr(sys,'frozen',False):
            ttk.Button(row,text='관리자 권한으로 다시 실행',style='Start.TButton',command=self.restart_as_admin).pack(side='left')
        ttk.Button(row,text='기록 폴더 열기',command=lambda:os.startfile(DATA)).pack(side='left',padx=8)
        ttk.Button(row,text='닫기',command=dialog.destroy).pack(side='right')
        smooth_buttons(dialog);dialog.lift()

    def show_operation_error(self,title,error,hwnd=None):
        if getattr(error,'winerror',None)==5:
            self.show_permission_notice(title,error,hwnd)
        elif isinstance(error,PermissionError):
            self.show_permission_notice(title,error,hwnd,file_access=True)
        else:
            messagebox.showerror(title,str(error)+'\n\n상세 정보는 기록 폴더의 로그 파일.log를 확인하세요.',parent=self.root)

    def restart_as_admin(self):
        if not getattr(sys,'frozen',False):return
        try:
            if process_elevated() is True:
                messagebox.showinfo('권한 확인','현재 앱은 이미 관리자 권한입니다.',parent=self.root);return
            self.stop()
            self.settings=self.collect_settings()
            self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
            if relaunch_admin(sys.executable):
                self.log('Windows 관리자 권한 재실행이 승인되어 현재 앱을 종료합니다.');self.close()
            else:
                self.log('사용자가 Windows 권한 승인을 취소했습니다. 현재 앱을 유지합니다.')
                messagebox.showinfo('권한 요청 취소','Windows 권한 승인이 취소되어 현재 앱을 그대로 유지합니다.',parent=self.root)
        except OSError as e:
            self.log('관리자 권한 재실행 실패: '+str(e))
            messagebox.showerror('재실행 실패',str(e)+'\n앱 EXE를 우클릭 → 관리자 권한으로 실행을 선택해 주세요.',parent=self.root)

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
        self.show_operation_error('자동 창 맞추기',error,hwnd)

    def resize(self):
        if self.running or self.sizing_busy or self.installing or self.closing:return
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
            if info['fullscreen_like'] or (int(info['style'],16)&0x00C00000)!=0x00C00000:
                self.win.make_windowed(hwnd)
                self.log('테두리 없는 창/고정 창의 스타일을 보정했습니다.')
            self.resize_target=self.win.resize(hwnd)
            self.detail.set(f'{self.resize_target[0]}×{self.resize_target[1]} 적용 후 실제 화면 크기 확인 중…')
            self.root.after(600,lambda:self.verify_size(hwnd))
        except WindowError as e:self.sizing_error(hwnd,e)

    def verify_size(self,hwnd,attempt=0):
        if self.closing:return
        try:
            self.win.ensure_game(hwnd)
            left,top,w,h=self.win.rect(hwnd)
            self.log(f'창 맞춤 검증 {attempt+1}: 실제 게임 영역 {w}×{h}')
            if (int(self.win.diagnostics(hwnd)['style'],16)&0x00C00000)!=0x00C00000:
                raise WindowError('게임이 제목 표시줄을 다시 숨겼습니다. 제목 표시줄을 유지할 수 있는 화면 모드인지 확인하세요.')
            if (w,h)!=self.resize_target:
                if attempt<3:
                    self.resize_target=self.win.resize(hwnd,correction=True)
                    self.root.after(650,lambda:self.verify_size(hwnd,attempt+1));return
                raise WindowError(f'실제 화면이 {w}×{h}로 유지됩니다. 게임이 전체 화면/고정 해상도로 되돌리거나 크기 변경을 제한하고 있습니다. 자동 전환이 지원되지 않으면 게임 설정에서 디스플레이 모드를 변경해야 합니다.')
            _,work=self.win.monitor_info(hwnd)
            if left<work[0] or top<work[1] or left+w>work[2] or top+h>work[3]:
                if attempt<3:
                    self.resize_target=self.win.resize(hwnd,correction=True)
                    self.root.after(650,lambda:self.verify_size(hwnd,attempt+1));return
                raise WindowError('제목 표시줄은 유지했지만 게임 화면 일부가 작업 표시줄이나 화면 경계에 가려집니다. 화면 해상도 또는 작업 표시줄 자동 숨김 설정을 확인하세요.')
            self.refresh();self.sizing_finished()
            self.log(f'자동 창 맞추기 완료: 제목 표시줄 유지 + 실제 게임 화면 {w}×{h} / 인식 기준 800×1000.')
            self.log('창 맞춤 결과: '+json.dumps(self.win.diagnostics(hwnd),ensure_ascii=False))
            self.detail.set(f'게임 화면 {w} × {h} · 인식/클릭 좌표 자동 변환')
        except WindowError as e:self.sizing_error(hwnd,e)

    def lock_controls(self,running):
        for w in (self.window_box,self.content_box,self.dungeon_box,self.difficulty_box,self.mode_box):w.configure(state='disabled' if running else 'readonly')
        for w in (self.refresh_button,self.resize_button,self.start_button,self.food_check):w.configure(state='disabled' if running else 'normal')
        self.stop_button.configure(state='normal' if running else 'disabled')
        if self.installing:self.start_button.configure(state='disabled')

    def play_mode_changed(self,*_):
        party=self.play_mode.get()==PLAY_MODES[1]
        raid=self.content.get()=='레이드'
        self.repeat.set(True)
        if hasattr(self,'mode_hint'):
            self.mode_hint.set('레이드: 혼자하기 · 배 출항 · 장면 넘기기 · 빵 아이콘 확인 · 토벌 후 배 복귀·재출항' if raid else '파티: 다른 던전 가기 → 목적지 선택 → 입장하기' if party else '솔로: 다시 하기 · 파티: 다른 던전 가기 → 목적지 선택 → 입장하기')
            self.status.set('레이드 시작 대기' if raid else '파티 플레이 시작 대기' if party else '시작 대기')
            self.start_button.configure(state='disabled' if self.running or self.installing else 'normal')

    def start(self):
        if self.running or self.sizing_busy or self.installing or self.closing:return
        try:
            self.refresh()
            hwnd=self.selected()
            self.win.require_control_permission(hwnd)
            _,_,w,h=self.win.rect(hwnd)
            if not supported_client((w,h)):raise WindowError(f'실제 화면이 {w}×{h}입니다. 먼저 게임 창 자동 맞추기를 누르세요.')
        except WindowError as e:
            self.show_operation_error('매크로 시작',e,locals().get('hwnd'));return
        self.settings=self.collect_settings()
        self.settings_path.write_text(json.dumps(self.settings,ensure_ascii=False,indent=2),encoding='utf-8')
        self.running=True;self.stop_event.clear();self.lock_controls(True)
        self.status.set('게임 창을 클릭하세요')
        self.log('시작: '+self.dungeon.get()+' / '+self.difficulty.get()+' / '+self.play_mode.get()+' — 게임 창이 앞에 있을 때만 인식·클릭합니다.')
        self.worker=threading.Thread(target=self.run,args=(hwnd,dict(self.settings)),daemon=True);self.worker.start()

    def stop(self):
        self.stop_event.set()
        if self.running:
            self.status.set('중지 중…')

    def run(self,hwnd,config):
        try:
            raid=config.get('content')=='레이드'
            detector=RaidVision(BASE/'assets.json') if raid else Vision(BASE/'assets.json')
            controller=RaidController(config['difficulty']) if raid else Controller(config['dungeon'],config['difficulty'],config['repeat'],party=config.get('play_mode')==PLAY_MODES[1])
            last_screen,streak,food_streak='',0,0
            previous_observation=None
            list_center=ListCentering();raid_center=RaidEntryCentering()
            pause=CapturePause();last_status=None;unknown_since=None;warned=False
            diagnostics_saved=False
            self.events.put(('log','실행 환경: '+json.dumps(self.win.diagnostics(hwnd),ensure_ascii=False)))
            motion_log_state=None;motion_log_at=-999.
            with mss.mss() as capture:
                while not self.stop_event.is_set():
                    now=time.monotonic()
                    if not self.win.active(hwnd):
                        if pause.hold('inactive',now):
                            detector.stillness.reset();controller.still_since=None
                            self.events.put(('status',('게임 창 활성화 대기','게임 창을 앞에 두면 진행을 이어갑니다.')))
                        self.stop_event.wait(.25);continue
                    self.win.ensure_game(hwnd)
                    left,top,width,height=self.win.rect(hwnd)
                    if not supported_client((width,height)):raise WindowError('게임 화면 비율이 바뀌었습니다. 자동 맞추기를 다시 누르세요.')
                    bounds=self.win.desktop_bounds()
                    if not within_desktop((left,top,width,height),bounds):
                        if pause.hold('offscreen',now):
                            detector.stillness.reset();controller.still_since=None
                            self.events.put(('log',f'게임 화면 일부가 모니터 밖에 있어 대기: 게임 {(left,top,width,height)} / 화면 {bounds}'))
                            self.events.put(('status',('게임 창 위치 대기','게임 화면 전체를 모니터 안으로 옮기면 자동으로 이어갑니다.')))
                        self.stop_event.wait(.25);continue
                    elapsed=pause.resume(now)
                    if elapsed is not None:
                        if controller.entered_at is not None:controller.entered_at+=elapsed
                        last_status=None;last_screen='';streak=0;previous_observation=None
                        unknown_since=None;warned=False;food_streak=0
                        self.events.put(('log','게임 창 확인 완료 → 현재 화면을 새로 확인해 진행을 이어갑니다.'))
                    frame=np.array(capture.grab({'left':left,'top':top,'width':width,'height':height}))[:,:,:3]
                    frame=cv2.resize(frame,(800,1000))
                    observation=detector.observe(frame,config['dungeon'],config['difficulty'],after_clear=controller.clear_clicked)
                    if raid and raid_center.observe(observation.screen,entered=controller.phase=='inside'):
                        self.events.put(('status',('카브락 보스방 입장 확인','게임 화면 중앙으로 마우스를 부드럽게 이동합니다.')))
                        if self.win.center_raid_pointer(hwnd,self.stop_event):
                            raid_center.completed()
                            self.events.put(('log','레이드 보스방: 중앙 (400, 500)으로 부드럽게 이동 완료 → 화면 새로 캡처·재인식'))
                        previous_observation=None;streak=0;food_streak=0;last_screen='';last_status=None
                        self.stop_event.wait(.10)
                        continue
                    center_due=list_center.observe(observation.screen)
                    if center_due and (not controller.combat_latched or controller.clear_clicked):
                        self.events.put(('status',('어비스 목록 확인','게임 화면 중앙보다 위로 마우스 이동 후 새 화면을 확인합니다.')))
                        if self.win.center_list_pointer(hwnd,self.stop_event):
                            list_center.completed()
                            self.events.put(('log','어비스 목록: 중앙 위 (400, 350)로 부드럽게 이동 완료 → 화면 새로 캡처·이름 재확인'))
                        # Never reuse the pre-move image or its click coordinates.
                        previous_observation=None;streak=0;last_screen='';last_status=None
                        self.stop_event.wait(.10)
                        continue

                    food_streak=food_streak+1 if observation.food else 0
                    if not config['food'] or food_streak<2:
                        from dataclasses import replace
                        observation=replace(observation,food=False)
                    streak=streak+1 if same_detection(previous_observation,observation) else 1
                    previous_observation=observation
                    if observation.screen=='list' and last_screen!='list':
                        self.events.put(('log','어비스 목록 이름 인식: '+config['dungeon']+' / 현재 화면 연속 확인 중'))
                    last_screen=observation.screen
                    result_stalled=controller.clear_seen_at is not None and now-controller.clear_seen_at>15 and observation.screen not in ('reward','matching','loading')
                    if observation.screen=='unknown' or result_stalled:
                        controller.still_since=None
                        if unknown_since is None:unknown_since=now
                        if (now-unknown_since>15 or result_stalled) and not warned:
                            self.events.put(('log','화면을 인식하지 못하고 있습니다. 팝업·가려진 화면·UI 배율을 확인하세요.'))
                            if not diagnostics_saved and self.win.active(hwnd):
                                try:
                                    metadata={'version':VERSION,'time':time.strftime('%Y-%m-%d %H:%M:%S'),'requested':config,
                                              'client_rect':[left,top,width,height],'desktop_bounds':bounds,
                                              'window':self.win.diagnostics(hwnd),'controller_state':controller.state.value,
                                              'last_action':controller.last_key,'template_scores':dict(detector.scores)}
                                    self.save_problem(frame,metadata)
                                    diagnostics_saved=True
                                    self.events.put(('log','진단 저장: 기록 폴더의 로그 파일.zip에 로그와 오류 화면을 함께 담았습니다. 자동 전송하지 않습니다.'))
                                except Exception as error:
                                    self.events.put(('log','진단 저장 실패: '+str(error)))

                            warned=True
                    else:unknown_since=None;warned=False
                    action=controller.step(observation,now) if streak>=2 else None
                    status=(controller.state.value,controller.reason or ('감지: '+{'unknown':'화면 확인 중','dead':'행동 불능·여기서 부활 확인','field':'일반 화면','combat':'전투','detail':'입장 설정','matching':'우연한 만남 대기','loading':'로딩','cutscene':'보스 연출','reward':'보상','mission':'협동 미션','clear':'던전 클리어','menu':'메뉴','list':'어비스 목록','raid_menu':'레이드 메뉴','raid_list':'카브락 목록','raid_detail':'레이드 설정','raid_travel':'레이드 지역 이동','raid_boat':'배 탑승·퀘스트 출항','raid_cutscene':'출항 장면','raid_inside':'카브락 입장·음식 확인','raid_weekend':'주말 레이드 퀘스트 보상','raid_reward':'카브락 처치 완료 보상','raid_return':'토벌 완료·우상단 나가기','raid_return_dialog':'출항선으로 이동 확인'}.get(observation.screen,observation.screen)))
                    if observation.screen=='field' and controller.state==State.IDLE:
                        status=(status[0],status[1]+' / '+observation.motion_note)
                        motion_mode=observation.motion_note.split('(')[0]
                        if motion_mode!=motion_log_state and now-motion_log_at>2:
                            self.events.put(('log','시작 전 정지 판정: '+observation.motion_note))
                            motion_log_state=motion_mode;motion_log_at=now
                    if status!=last_status:self.events.put(('status',status));last_status=status
                    if action and not self.stop_event.is_set():
                        self.win.click(hwnd,action.point)
                        self.events.put(('log',action.message+(f' / 찾은 버튼 위치 {action.point}' if action.key in ('abyss','dungeon') else '')))
                    if controller.state==State.BLOCKED:
                        self.events.put(('log',controller.reason))
                        try:
                            if self.win.active(hwnd):self.save_problem(frame,{'version':VERSION,'reason':controller.reason,'screen':observation.screen,'template_scores':dict(detector.scores)})
                        except Exception:LOG.exception('오류 화면 저장 실패')
                        break
                    self.stop_event.wait(poll_interval(observation.screen))
        except Exception as e:
            LOG.exception('Worker stopped')
            try:
                if self.win.active(hwnd):
                    x,y,w,h=self.win.rect(hwnd)
                    if supported_client((w,h)) and within_desktop((x,y,w,h),self.win.desktop_bounds()):
                        with mss.mss() as failed_capture:
                            failed_frame=np.array(failed_capture.grab({'left':x,'top':y,'width':w,'height':h}))[:,:,:3]
                        if self.win.active(hwnd):self.save_problem(cv2.resize(failed_frame,(800,1000)),{'version':VERSION,'reason':str(e),'window':self.win.diagnostics(hwnd)})
            except Exception:LOG.exception('오류 진단 저장 실패')
            self.events.put(('error',(e,hwnd)))
        finally:self.events.put(('stopped',None))

    def open_update_notice(self):
        if self.update_notice and not self.update_notice.closed and self.update_notice.phase in ('downloading','preparing','installing'):
            self.update_notice.show();return
        self.show_update_prompt(None)
        self.update_check(True)

    def show_installed_changes(self,state_path=None):
        if self.closing:return False
        path=state_path if state_path is not None else DATA/'release-notice.json'
        if not needs_notice(path,VERSION):return False
        try:
            release=installed_release(BASE/'release_notes.md',VERSION)
            self.installed_notice=UpdateNotice(self,release)
            self.installed_notice.dialog.update_idletasks()
            mark_shown(path,VERSION)
            return True
        except (OSError,ValueError) as error:
            self.log('업데이트 내용 자동 안내 실패: '+str(error))
            return False

    def update_check(self,manual=False):
        self.update_manual_requested=self.update_manual_requested or manual
        if manual:
            self.show_update_prompt(None)
            self.update_prompt.set_loading()
        if self.update_busy:
            if self.update_prompt and not self.update_prompt.closed:self.update_prompt.status.set('업데이트 정보를 확인 중입니다. 잠시 기다려 주세요.')
            return
        self.update_busy=True;self.update_text.set('업데이트 확인 중…')
        def check():
            try:self.events.put(('update',(check_update(include_current=True),None)))
            except Exception as e:self.events.put(('update',(None,str(e))))
        threading.Thread(target=check,daemon=True).start()
        if not manual:self.root.after(5*60*1000,self.update_check)

    def show_update_prompt(self,result=None):
        if self.update_prompt and not self.update_prompt.closed:
            if result:self.update_prompt.set_release(result)
            self.update_prompt.show();return
        self.update_prompt=UpdatePrompt(self,result)

    def update_from_prompt(self,release):
        self.show_update(release)
        self.update_notice.begin()
        return self.update_notice.phase in ('downloading','preparing','installing')

    @property
    def data_path(self):
        return DATA

    def show_update(self,result=None):
        if self.update_notice and not self.update_notice.closed:
            if result:self.update_notice.set_release(result)
            self.update_notice.show();return
        self.update_notice=UpdateNotice(self,result)
        self.update_dialog=self.update_notice.dialog

    def pump(self):
        if self.closing:return
        for _ in range(100):
            try:kind,value=self.events.get_nowait()
            except queue.Empty:break
            if kind=='log':self.log(value)
            elif kind=='status':self.status.set(value[0]);self.detail.set(value[1])
            elif kind=='error':
                error,hwnd=value;self.log(str(error));self.show_operation_error('게임 조작',error,hwnd)
            elif kind=='stopped':
                self.running=False;self.lock_controls(False)
                if self.status.get()!='확인 필요':self.status.set('중지됨')
            elif kind=='update':
                self.update_busy=False;result,error=value
                manual=self.update_manual_requested;self.update_manual_requested=False
                notice=self.update_notice if self.update_notice and not self.update_notice.closed else None
                prompt=self.update_prompt if self.update_prompt and not self.update_prompt.closed else None
                if error:
                    self.update_text.set('업데이트 연결 실패 · 다시 확인 가능')
                    if manual:
                        if prompt is None:self.show_update_prompt(None);prompt=self.update_prompt
                        prompt.set_check_error(error)
                elif result:
                    self.latest_release=result
                    newer=result.get('is_new',True)
                    self.update_text.set(result['version']+(' 업데이트 필요' if newer else ' 최신 버전 사용 중'))
                    if notice:notice.set_release(result)
                    if prompt:prompt.set_release(result)
                    if manual or (newer and result['version'] not in self.seen_updates):
                        self.seen_updates.add(result['version']);self.show_update_prompt(result)
                else:
                    self.update_text.set('등록된 최신 배포를 찾지 못했습니다.')
                    if manual:
                        if prompt is None:self.show_update_prompt(None);prompt=self.update_prompt
                        prompt.set_no_release()
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
        messagebox.showerror('오류','작업을 중지했습니다. 기록 폴더의 로그 파일.log를 확인하세요.\n'+str(value),parent=self.root)

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
        app.update_notice.close()
        app.show_permission_notice('게임 조작')
        root.update_idletasks();app.permission_dialog.destroy()
        from ui_update_test import exercise_update_buttons
        update_ui_report=exercise_update_buttons(app)
        from ui_style_test import exercise_style_controls
        style_report=exercise_style_controls(app,sys.argv[sys.argv.index('--report')+1])
        from ui_dialog_test import exercise_update_dialogs
        dialog_report=exercise_update_dialogs(app,sys.argv[sys.argv.index('--report')+1])
        report={'ok':True,'version':VERSION,'templates':len(detector.data),'ui':'created','platform':sys.platform,'update_ui':update_ui_report,'style_ui':style_report,'dialog_ui':dialog_report}
        out=Path(sys.argv[sys.argv.index('--report')+1])
        out.write_text(json.dumps(report),encoding='utf-8')
        app.closing=True;root.destroy()
    else:
        main()
