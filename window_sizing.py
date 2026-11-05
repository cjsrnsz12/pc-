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
