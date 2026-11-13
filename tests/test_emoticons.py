import base64
from email import policy
from email.parser import BytesParser
from io import BytesIO
import json
from pathlib import Path
import urllib.error

from PIL import Image
import pytest

from emoticon_core import ENDPOINT, MODEL, build_prompt, generate, multipart, png_bytes, sticker_bytes


def test_generated_png_keeps_alpha_and_fits_size_limit():
    image=Image.new('RGBA',(800,1400));image.paste((15,180,220,255),(150,250,650,1150))
    raw=sticker_bytes(png_bytes(image))
    with Image.open(BytesIO(raw)) as result:
        assert result.size==(360,360)
        rgba=result.convert('RGBA')
        assert rgba.getpixel((0,0))[3]==0
        assert rgba.getpixel((180,180))[3]==255
    assert len(raw)<=150_000


def test_request_sends_identity_then_pose_and_transparency():
    body,kind=multipart(b'identity',b'pose','keep my character')
    message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+kind+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+body)
    fields={};images=[]
    for part in message.iter_parts():
        name=part.get_param('name',header='content-disposition')
        if name=='image[]':images.append(part.get_payload(decode=True))
        else:fields[name]=part.get_payload(decode=True).decode()
    assert images==[b'identity',b'pose']
    assert fields['model']==MODEL and fields['n']=='1'
    assert fields['background']=='transparent' and fields['output_format']=='png'


def test_real_request_contract_and_result_conversion_with_fake_server():
    raw=png_bytes(Image.new('RGBA',(1024,1024),(0,100,200,255)))
    response=BytesIO(json.dumps({'data':[{'b64_json':base64.b64encode(raw).decode()}]}).encode())
    def fake(request,timeout):
        assert request.full_url==ENDPOINT and request.get_method()=='POST'
        assert request.headers['Authorization']=='Bearer test-only-key'
        assert timeout==360
        return response
    result=generate('test-only-key',Image.new('RGBA',(10,10)),Image.new('RGBA',(10,10)),'pose',opener=fake)
    assert Image.open(BytesIO(result)).size==(360,360)


@pytest.mark.parametrize('code',[400,401,403,429,500])
def test_api_failures_do_not_retry_or_expose_credentials(code):
    calls=[]
    def fake(request,timeout):
        calls.append(request)
        raise urllib.error.HTTPError(ENDPOINT,code,'error',{},BytesIO(b'sensitive server response'))
    with pytest.raises(ValueError) as error:
        generate('test-only-key',Image.new('RGBA',(10,10)),Image.new('RGBA',(10,10)),'pose',opener=fake)
    assert len(calls)==1
    assert 'test-only-key' not in str(error.value) and 'sensitive' not in str(error.value)


def test_empty_key_makes_no_network_call():
    def fake(*a,**kw):raise AssertionError('unexpected request')
    with pytest.raises(ValueError):generate('',None,None,'',opener=fake)


def test_pack_is_eight_individual_transparent_images():
    folder=Path(__file__).resolve().parents[1]/'emoticons'
    pack=json.loads((folder/'pack.json').read_text(encoding='utf-8'))
    assert len(pack)==8 and len({p['name'] for p in pack})==8
    for item in pack:
        path=folder/item['file']
        with Image.open(path) as image:
            assert image.size==(360,360)
            alpha=image.convert('RGBA').getchannel('A')
            low,high=alpha.getextrema()
            assert low==0 and high>=240
        assert path.stat().st_size<=150_000


def test_prompt_preserves_roles_and_exact_caption():
    prompt=build_prompt('sky-blue hair and red eyes','빼꼼','문 뒤에서')
    assert 'Image 1' in prompt and 'Image 2' in prompt
    assert '빼꼼' in prompt and 'five fingers' in prompt
    assert 'No text' in build_prompt('character','','')
