"""Pure resize planning; native calls live in windows.py."""
TARGET=(800,1000)


def covers_monitor(window, monitor):
    l,t,r,b=window;ml,mt,mr,mb=monitor
    return l<=ml+3 and t<=mt+3 and r>=mr-3 and b>=mb-3


def fit_position(window, size, work):
    width,height=size;left,top,right,bottom=work
    if width>right-left or height>bottom-top:
        raise ValueError(f'모니터 작업 영역 {right-left}×{bottom-top}보다 필요한 창 크기 {width}×{height}가 큽니다. 화면 해상도를 높이거나 세로 공간이 더 큰 모니터를 사용하세요.')
    return max(left,min(window[0],right-width)),max(top,min(window[1],bottom-height))


def fit_framed_position(window,size,work,monitor,insets,client=TARGET):
    """Keep caption and client inside the work area; only bottom/right frame may cross it."""
    width,height=size;wl,wt,wr,wb=work;ml,mt,mr,mb=monitor
    left,top,_,_=insets;cw,ch=client
    min_x,min_y=max(ml,wl),max(mt,wt)
    max_x=min(mr-width,wr-left-cw)
    max_y=min(mb-height,wb-top-ch)
    if max_x<min_x or max_y<min_y:
        raise ValueError(f'제목 표시줄을 유지한 채 맞추려면 게임 영역 {cw}×{ch}와 위쪽 여백 {top}px가 필요합니다. 현재 작업 영역은 {wr-wl}×{wb-wt}, 모니터는 {mr-ml}×{mb-mt}입니다. 제목 표시줄을 숨기지 않고 작업을 보류했습니다. 화면 해상도나 작업 표시줄 자동 숨김 설정을 확인하세요.')
    return max(min_x,min(window[0],max_x)),max(min_y,min(window[1],max_y))


def fitted_client(work,monitor,insets):
    left,top,right,bottom=insets
    available_w=min(work[2]-work[0]-left,monitor[2]-monitor[0]-left-right)
    available_h=min(work[3]-work[1]-top,monitor[3]-monitor[1]-top-bottom)
    units=min(200,int(available_w//4),int(available_h//5))
    if units<160:
        raise ValueError('제목 표시줄을 유지할 작업 영역이 부족합니다. 인식 가능한 최소 게임 영역은 640×800입니다. 작업 표시줄 자동 숨김이나 화면 해상도를 확인하세요.')
    return units*4,units*5


def supported_client(size):
    width,height=size
    return 640<=width<=800 and 800<=height<=1000 and abs(width*1000-height*800)<=1000


def client_point(point,size):
    if not supported_client(size):raise ValueError('지원하는 게임 화면 비율이 아닙니다. 자동 맞추기를 사용하세요.')
    x,y=point
    if not (0<=x<800 and 0<=y<1000):raise ValueError('화면 밖 클릭을 차단했습니다.')
    w,h=size
    return min(w-1,round(x*w/800)),min(h-1,round(y*h/1000))
