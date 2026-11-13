"""Offline photo-to-sticker editing. No network clients or credentials."""
from io import BytesIO
import os
from pathlib import Path
import textwrap

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

MAX_INPUT = 15 * 1024 * 1024


def load_image(path):
    path = Path(path)
    if path.stat().st_size > MAX_INPUT:
        raise ValueError('15MB 이하의 사진을 선택해 주세요.')
    with Image.open(path) as opened:
        if opened.width * opened.height > 40_000_000:
            raise ValueError('사진 해상도가 너무 큽니다. 줄인 사진을 사용해 주세요.')
        return ImageOps.exif_transpose(opened).convert('RGBA')


def png_bytes(image, max_side=1536):
    image = image.copy().convert('RGBA')
    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    stream = BytesIO(); image.save(stream, 'PNG')
    return stream.getvalue()


def compact_png(canvas):
    output = BytesIO(); canvas.save(output, 'PNG', optimize=True)
    data = output.getvalue()
    for colors in (256, 192, 128, 96, 64):
        if len(data) <= 150_000:break
        output = BytesIO()
        canvas.quantize(colors=colors, method=Image.Quantize.FASTOCTREE).save(output, 'PNG', optimize=True)
        data = output.getvalue()
    if len(data) > 150_000:raise ValueError('파일 용량을 맞추지 못했습니다. 다른 이미지를 사용해 주세요.')
    return data


def sticker_bytes(raw):
    with Image.open(BytesIO(raw)) as source:
        image = ImageOps.exif_transpose(source).convert('RGBA')
        image.thumbnail((332, 332), Image.Resampling.LANCZOS)
        canvas = Image.new('RGBA', (360, 360))
        canvas.alpha_composite(image, ((360-image.width)//2, (360-image.height)//2))
    return compact_png(canvas)


def remove_edge_background(image, tolerance=30):
    """Remove only edge-connected pixels near the dominant opaque edge colour."""
    rgba = np.array(image.convert('RGBA')).copy()
    rgb = rgba[:, :, :3].astype(np.int16)
    edges = np.concatenate((rgba[0], rgba[-1], rgba[:, 0], rgba[:, -1]))
    opaque = edges[edges[:, 3] > 240, :3]
    if not len(opaque):return image.copy()
    # Quantization tolerates JPEG noise without averaging two unrelated colours.
    keys = (opaque.astype(np.int32)//16) @ np.array([256,16,1])
    values, counts = np.unique(keys, return_counts=True)
    background = np.median(opaque[keys == values[np.argmax(counts)]], axis=0)
    near = (np.max(np.abs(rgb-background), axis=2) <= max(0,min(100,int(tolerance)))) | (rgba[:,:,3]==0)
    _, labels = cv2.connectedComponents(near.astype(np.uint8), connectivity=4)
    connected = np.unique(np.concatenate((labels[0],labels[-1],labels[:,0],labels[:,-1])))
    connected = connected[connected != 0]
    rgba[np.isin(labels, connected), 3] = 0
    return Image.fromarray(rgba)


def caption_font(size, path=None):
    candidates = [Path(path)] if path else []
    candidates += [Path(os.getenv('WINDIR','C:/Windows'))/'Fonts'/n for n in ('malgunbd.ttf','malgun.ttf')]
    candidates += [Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'),Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')]
    for candidate in candidates:
        if candidate.is_file():
            try:return ImageFont.truetype(str(candidate),size)
            except OSError:pass
    raise ValueError('한글 글꼴을 찾지 못했습니다. ‘글꼴 선택’에서 TTF·OTF 글꼴을 선택해 주세요.')


def edit_sticker(image, caption='', remove_bg=False, tolerance=30, mirror=False, outline=True, font_path=None):
    caption = str(caption).strip()
    if len(caption)>40:raise ValueError('문구는 40자 이내로 입력해 주세요.')
    source = image.copy().convert('RGBA')
    source.thumbnail((1536,1536),Image.Resampling.LANCZOS)
    if remove_bg:source=remove_edge_background(source,tolerance)
    bbox=source.getchannel('A').getbbox()
    if not bbox:raise ValueError('배경을 지운 뒤 남은 부분이 없습니다. 허용 범위를 낮추거나 배경 지우기를 꺼 주세요.')
    source=source.crop(bbox)
    if mirror:source=ImageOps.mirror(source)
    scale=2;canvas=Image.new('RGBA',(360*scale,360*scale))
    text='\n'.join(textwrap.wrap(caption,width=12,replace_whitespace=False))
    text_height=0;font=None
    if text:
        draw=ImageDraw.Draw(canvas)
        for size in range(64,23,-2):
            font=caption_font(size,font_path)
            bounds=draw.multiline_textbbox((0,0),text,font=font,spacing=2,stroke_width=4)
            if bounds[2]-bounds[0]<=328*scale and bounds[3]-bounds[1]<=100*scale:break
        text_height=bounds[3]-bounds[1]+12*scale
    available_height=332*scale-text_height
    source=ImageOps.contain(source,(320*scale,max(20,available_height-12*scale)),Image.Resampling.LANCZOS)
    picture=Image.new('RGBA',canvas.size)
    picture.alpha_composite(source,((canvas.width-source.width)//2,14*scale+(available_height-source.height)//2))
    if outline:
        alpha=picture.getchannel('A').filter(ImageFilter.MaxFilter(13))
        white=Image.new('RGBA',canvas.size,'white');white.putalpha(alpha)
        canvas=Image.alpha_composite(canvas,white)
    canvas=Image.alpha_composite(canvas,picture)
    if text:
        draw=ImageDraw.Draw(canvas)
        x=(canvas.width-(bounds[2]-bounds[0]))//2-bounds[0]
        y=canvas.height-14*scale-(bounds[3]-bounds[1])-bounds[1]
        draw.multiline_text((x,y),text,font=font,fill='#20334f',stroke_width=4,stroke_fill='white',spacing=2,align='center')
    return compact_png(canvas.resize((360,360),Image.Resampling.LANCZOS))
