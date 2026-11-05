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
