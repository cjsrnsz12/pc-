from io import BytesIO
import json
from pathlib import Path
import urllib.request

from PIL import Image,ImageDraw
import pytest

from emoticon_core import edit_sticker,load_image,png_bytes,sticker_bytes,remove_edge_background


def test_offline_edit_never_connects_and_keeps_source_unchanged(monkeypatch):
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**kw:pytest.fail('Network access'))
    image=Image.new('RGBA',(800,1400));image.paste((15,180,220,255),(150,250,650,1150))
    original=image.tobytes()
    raw=edit_sticker(image,'안녕!')
    assert image.tobytes()==original
    with Image.open(BytesIO(raw)) as result:
        assert result.size==(360,360)
        assert result.convert('RGBA').getpixel((0,0))[3]==0
    assert len(raw)<=150_000


def test_background_removal_preserves_enclosed_white_details():
    image=Image.new('RGBA',(100,100),'white');d=ImageDraw.Draw(image)
    d.rectangle((20,20,80,80),fill='red');d.ellipse((40,40,60,60),fill='white')
    result=remove_edge_background(image,20)
    assert result.getpixel((0,0))[3]==0
    assert result.getpixel((50,50))==(255,255,255,255)
    assert result.getpixel((30,30))==(255,0,0,255)


def test_transparent_input_is_retained():
    image=Image.new('RGBA',(100,100));image.paste('red',(30,30,70,70))
    assert remove_edge_background(image).tobytes()==image.tobytes()
    raw=edit_sticker(image,outline=False)
    result=Image.open(BytesIO(raw)).convert('RGBA')
    assert result.getpixel((180,180))==(255,0,0,255)


def test_all_background_and_long_caption_have_actionable_errors():
    with pytest.raises(ValueError,match='남은 부분'):edit_sticker(Image.new('RGBA',(100,100),'white'),remove_bg=True)
    with pytest.raises(ValueError,match='40자'):edit_sticker(Image.new('RGBA',(100,100),'red'),'가'*41)


def test_long_korean_caption_and_portrait_fit_inside_transparent_margins():
    raw=edit_sticker(Image.new('RGBA',(60,500),'red'),'수고하셨습니다 오늘도 즐거운 하루 보내세요')
    image=Image.open(BytesIO(raw)).convert('RGBA');box=image.getchannel('A').getbbox()
    assert image.size==(360,360) and len(raw)<=150_000
    assert box[0]>0 and box[1]>0 and box[2]<360 and box[3]<360


def test_mirror_changes_direction_without_changing_output_size():
    image=Image.new('RGBA',(100,100),'blue');image.paste('red',(0,0,50,100))
    normal=Image.open(BytesIO(edit_sticker(image,outline=False))).convert('RGBA')
    mirrored=Image.open(BytesIO(edit_sticker(image,mirror=True,outline=False))).convert('RGBA')
    assert normal.getpixel((100,180))[:3]==(255,0,0)
    assert mirrored.getpixel((100,180))[:3]==(0,0,255)


def test_photo_load_respects_orientation_and_file_limit(tmp_path):
    path=tmp_path/'photo.jpg';image=Image.new('RGB',(50,80),'blue')
    exif=image.getexif();exif[274]=6;image.save(path,exif=exif)
    assert load_image(path).size==(80,50)
    path=tmp_path/'large.png'
    with path.open('wb') as out:out.truncate(16*1024*1024)
    with pytest.raises(ValueError,match='15MB'):load_image(path)


def test_generated_png_keeps_alpha_and_fits_size_limit():
    image=Image.new('RGBA',(800,1400));image.paste((15,180,220,255),(150,250,650,1150))
    raw=sticker_bytes(png_bytes(image))
    assert Image.open(BytesIO(raw)).size==(360,360) and len(raw)<=150_000


def test_pack_is_eight_individual_transparent_images():
    folder=Path(__file__).resolve().parents[1]/'emoticons'
    pack=json.loads((folder/'pack.json').read_text(encoding='utf-8'))
    assert len(pack)==8 and len({p['name'] for p in pack})==8
    for item in pack:
        path=folder/item['file']
        with Image.open(path) as image:
            assert image.size==(360,360)
            low,high=image.convert('RGBA').getchannel('A').getextrema()
            assert low==0 and high>=240
        assert path.stat().st_size<=150_000
