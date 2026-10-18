#!/usr/bin/env python3
"""Build the small fbdev sprite atlas (Pillow is needed only on the build host)."""
import argparse
import io
import math
from pathlib import Path
import zipfile
from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 3
BG = '#080d16'


def build(output, latin, cjk, preview=None):
    def canvas(w, h):
        return Image.new('RGBA', (w*S, h*S), (0, 0, 0, 0))

    def text(draw, xy, value, size, fill, chinese=False):
        font = ImageFont.truetype(str(cjk if chinese else latin), size*S)
        draw.text((xy[0]*S, xy[1]*S), value, font=font, fill=fill, anchor='mm')

    sprites = {}
    def save(name, image):
        sprites[name] = image.resize((image.width//S, image.height//S), Image.Resampling.LANCZOS)

    for lang in ['zh', 'en']:
        base = Image.new('RGBA', (320*S, 480*S), BG)
        glow = canvas(320,480)
        d = ImageDraw.Draw(glow)
        d.ellipse((75*S, 104*S, 245*S, 274*S), fill=(50,190,163,24))
        base = Image.alpha_composite(base,glow.filter(ImageFilter.GaussianBlur(36*S)))
        d = ImageDraw.Draw(base)
        d.ellipse((62*S, 89*S, 258*S, 285*S), outline=(68,121,116,45), width=S)
        d.line((142*S,397*S,178*S,397*S),fill='#30434c',width=S)
        text(d,(160,424),'短按查看电量' if lang=='zh' else 'Press to check charge',12,'#778792',lang=='zh')
        text(d,(160,447),'长按电源键开机' if lang=='zh' else 'Hold power to start',12,'#a6b6bf',lang=='zh')
        save('base-'+lang,base)
        for state,label in [('charging','正在充电' if lang=='zh' else 'Charging'),
                            ('full','充电完成' if lang=='zh' else 'Fully charged'),
                            ('paused','充电已暂停' if lang=='zh' else 'Charging paused')]:
            im=canvas(320,32);d=ImageDraw.Draw(im)
            text(d,(160,16),label,14,'#76d9c5' if state!='paused' else '#e4bc7e',lang=='zh')
            save('status-'+lang+'-'+state,im)
    for cap in range(101):
        im=canvas(96,148);d=ImageDraw.Draw(im)
        d.rounded_rectangle((35*S,0,61*S,7*S),radius=3*S,fill='#718b91')
        d.rounded_rectangle((5*S,10*S,91*S,145*S),radius=20*S,fill='#111f28',outline='#719c9b',width=2*S)
        if cap:
            fill=canvas(96,148);fd=ImageDraw.Draw(fill)
            color='#70dfbf' if cap>15 else '#edb779'
            fd.rectangle((11*S,(139-123*cap/100)*S,85*S,139*S),fill=color)
            mask=Image.new('L',im.size,0)
            ImageDraw.Draw(mask).rounded_rectangle((11*S,16*S,85*S,139*S),radius=14*S,fill=255)
            fill.putalpha(Image.composite(fill.getchannel('A'),Image.new('L',im.size,0),mask))
            im=Image.alpha_composite(im,fill)
        save('battery-'+str(cap),im)
        digits=canvas(320,76);d=ImageDraw.Draw(digits)
        text(d,(160,38),str(cap)+'%',46,'#ecf5f4')
        save('number-'+str(cap),digits)
    for n in range(16):
        im=canvas(44,64);d=ImageDraw.Draw(im)
        strength=(1-math.cos(n*2*math.pi/16))/2
        value=int(188+67*strength)
        d.polygon([(25*S,3*S),(8*S,34*S),(21*S,34*S),(17*S,61*S),(37*S,25*S),(24*S,25*S)],
                  fill=(value,value,255,255))
        save('bolt-'+str(n),im)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,im in sprites.items():
            z.writestr(name+'.rgba',im.tobytes())
    if preview:
        im=sprites['base-zh'].copy()
        for name,xy in [('battery-73',(112,113)),('number-73',(0,291)),
                        ('status-zh-charging',(0,363)),('bolt-8',(138,158))]:
            im.alpha_composite(sprites[name],xy)
        im.save(preview)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--latin',type=Path,required=True)
    ap.add_argument('--cjk',type=Path,required=True)
    ap.add_argument('--output',type=Path,default=Path(__file__).with_name('charge-art.zip'))
    ap.add_argument('--preview',type=Path)
    a=ap.parse_args();build(a.output,a.latin,a.cjk,a.preview)
