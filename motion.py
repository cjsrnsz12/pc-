"""Crowd-tolerant scene motion: balanced background tracks and a minimap veto."""
import cv2
import numpy as np


class Stillness:
    def __init__(self):self.reset()

    def reset(self):
        self.previous=None;self.previous_mask=None;self.previous_map_mask=None
        self.note='배경 움직임 확인 중';self.stable_tiles=0;self.valid_tiles=0

    @staticmethod
    def background_mask(frame):
        h,w=frame.shape[:2]
        mask=np.zeros((h,w),np.uint8)
        mask[180:810,8:792]=255
        # HUD, quest list, chat and the main character/crowd centre are not anchors.
        mask[230:670,615:]=0
        mask[620:,0:300]=0
        mask[340:735,235:565]=0
        hsv=cv2.cvtColor(frame,cv2.COLOR_BGR2HSV)
        hue,saturation,value=cv2.split(hsv)
        labels=((hue>=115)&(saturation>35)&(value>105))|((value>170)&(saturation<65))|((saturation>110)&(value>175))
        labels=cv2.dilate(labels.astype(np.uint8),np.ones((5,5),np.uint8))
        mask[labels>0]=0
        return mask

    @staticmethod
    def tracks(previous,current,mask,current_mask):
        points=[];sectors=[]
        for row,y in enumerate(range(180,810,158)):
            for col,x in enumerate(range(0,800,160)):
                local=mask[y:min(y+158,810),x:min(x+160,800)]
                if np.count_nonzero(local)<150:continue
                detected=cv2.goodFeaturesToTrack(previous[y:y+local.shape[0],x:x+local.shape[1]],maxCorners=14,qualityLevel=.025,minDistance=8,mask=local,blockSize=5)
                if detected is not None:
                    for p in detected.reshape(-1,2):points.append(p+[x,y]);sectors.append((row,col))
        if len(points)<12:return []
        p=np.float32(points).reshape(-1,1,2)
        q,ok,error=cv2.calcOpticalFlowPyrLK(previous,current,p,None,winSize=(21,21),maxLevel=3,criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,25,.01))
        if q is None:return []
        back,ok_back,_=cv2.calcOpticalFlowPyrLK(current,previous,q,None,winSize=(21,21),maxLevel=3,criteria=(cv2.TERM_CRITERIA_EPS|cv2.TERM_CRITERIA_COUNT,25,.01))
        if back is None:return []
        good=(ok.ravel()>0)&(ok_back.ravel()>0)&(error.ravel()<22)&(np.linalg.norm(back-p,axis=2).ravel()<.65)
        groups={}
        for i in np.flatnonzero(good):
            x,y=q[i,0];ix,iy=round(float(x)),round(float(y))
            if 0<=ix<800 and 0<=iy<1000 and current_mask[iy,ix]:
                groups.setdefault(sectors[i],[]).append(q[i,0]-p[i,0])
        return [(sector,np.median(vectors,axis=0)) for sector,vectors in groups.items() if len(vectors)>=3]

    @staticmethod
    def minimap_mask(frame):
        roi=frame[118:214,676:774]
        hsv=cv2.cvtColor(roi,cv2.COLOR_BGR2HSV)
        yy,xx=np.indices(roi.shape[:2])
        mask=(((xx-48)**2+(yy-46)**2)<43**2).astype(np.uint8)*255
        markers=(hsv[:,:,1]>125)|((hsv[:,:,2]>210)&(hsv[:,:,1]<65))
        mask[cv2.dilate(markers.astype(np.uint8),np.ones((3,3),np.uint8))>0]=0
        return mask

    @staticmethod
    def minimap_moving(previous,current,old_mask,current_mask):
        # Track map terrain, excluding colored player/NPC dots and white markers.
        a,b=previous[118:214,676:774],current[118:214,676:774]
        if min(a.shape)<20 or float(a.std())<12:return False
        p=cv2.goodFeaturesToTrack(a,maxCorners=28,qualityLevel=.04,minDistance=6,mask=old_mask)
        if p is None or len(p)<6:return False
        q,ok,err=cv2.calcOpticalFlowPyrLK(a,b,p,None,winSize=(15,15),maxLevel=2)
        if q is None:return False
        good=(ok.ravel()>0)&(err.ravel()<18)
        if np.count_nonzero(good)<6:return False
        for i in np.flatnonzero(good):
            x,y=np.rint(q[i,0]).astype(int)
            if not (0<=x<b.shape[1] and 0<=y<b.shape[0] and current_mask[y,x]):good[i]=False
        if np.count_nonzero(good)<6:return False
        vectors=(q-p).reshape(-1,2)[good]
        median=np.median(vectors,axis=0)
        agreement=np.linalg.norm(vectors-median,axis=1)<.75
        return bool(np.linalg.norm(median)>.5 and np.mean(agreement)>.65)

    def update(self,frame):
        frame=cv2.resize(frame,(800,1000))
        gray=cv2.GaussianBlur(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),(3,3),0)
        mask=self.background_mask(frame)
        map_mask=self.minimap_mask(frame)
        previous,old_mask,old_map=self.previous,self.previous_mask,self.previous_map_mask
        self.previous,self.previous_mask,self.previous_map_mask=gray,mask,map_mask
        if previous is None:
            self.note='배경 기준 화면 확보 중';return False
        if self.minimap_moving(previous,gray,old_map,map_mask):
            self.note='미니맵 이동 감지 — 정지 대기';return False
        tracks=self.tracks(previous,gray,old_mask,mask)
        self.valid_tiles=len(tracks)
        stationary=[sector for sector,vector in tracks if np.linalg.norm(vector)<=.55]
        self.stable_tiles=len(stationary)
        if len(tracks)<4:
            self.note='고정 배경 근거 부족 — 화면 확인 중';return False
        vectors=np.array([v for _,v in tracks]);median=np.median(vectors,axis=0)
        coherent=np.linalg.norm(vectors-median,axis=1)<.8
        if np.linalg.norm(median)>.45 and np.mean(coherent)>=.55:
            self.note='배경 이동 감지 — 정지 대기';return False
        spread=len({s[0] for s in stationary})>=2 and len({s[1] for s in stationary})>=2
        stable=len(stationary)>=4 and len(stationary)/len(tracks)>=.55 and spread
        self.note=('주변 변화 제외 · 배경 정지 확인' if stable else '배경 이동/가림 확인 중')+f' ({len(stationary)}/{len(tracks)}영역)'
        return stable
