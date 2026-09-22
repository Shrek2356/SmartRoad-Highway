"""Create a traceable diagnostic subset, not an unbiased evaluation split."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import Window
from PIL import Image, ImageDraw


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'inputs').mkdir(exist_ok=True)
    (args.out/'references').mkdir(exist_ok=True)
    # Selection is fixed before inference; all results including failures are retained.
    choices=[('20230830-SteinhatcheeRiver.geo.tif','polygons',i) for i in [0,2,3,7,1]]
    choices += [('20211215-Russelville-Middle.geo.tif','polygons',1),
                ('05-08-2020-MussettBayouFire-NorthOf98.geo.tif','road_lines',0)]
    entries=[]
    for index,(name,kind,ordinal) in enumerate(choices,1):
        sid=f'S{index:02d}'
        source=args.data/'test/imagery/UAS'/name
        annotation=args.data/'test/annotations/UAS/road_damage_assessment'/(name+'.json')
        payload=json.loads(annotation.read_text(encoding='utf-8'))
        if kind not in payload:
            raise ValueError(f'{annotation}: expected {kind}, found {list(payload)}')
        target=payload[kind][ordinal]
        xs=[p['x'] for p in target['pixels']];ys=[p['y'] for p in target['pixels']]
        span=max(max(xs)-min(xs),max(ys)-min(ys))
        side=int(min(1536,max(512,span*1.6)))
        with rasterio.open(source) as raster:
            x=max(0,min(raster.width-side,int((min(xs)+max(xs)-side)/2)))
            y=max(0,min(raster.height-side,int((min(ys)+max(ys)-side)/2)))
            data=raster.read([1,2,3],window=Window(x,y,side,side))
        image=Image.fromarray(np.moveaxis(data,0,-1).astype('uint8'))
        image.save(args.out/'inputs'/f'{sid}.png')
        reference=image.copy();draw=ImageDraw.Draw(reference)
        coords=[(p['x']-x,p['y']-y) for p in target['pixels']]
        draw.line(coords+([coords[0]] if kind=='polygons' else []),fill='red',width=3)
        reference.save(args.out/'references'/f'{sid}.png')
        entries.append(dict(sample_id=sid,input=f'inputs/{sid}.png',source=str(source),
            source_size=source.stat().st_size,annotation=str(annotation),
            annotation_sha256=hashlib.sha256(annotation.read_bytes()).hexdigest(),
            input_sha256=hashlib.sha256((args.out/'inputs'/f'{sid}.png').read_bytes()).hexdigest(),
            split='official_test_used_for_development_diagnostics',annotation_kind=kind,
            annotation_index=ordinal,label=target['label'],window_xywh=[x,y,side,side],
            focal_polygon=coords,official_target=target,
            caveat='Road Line means road geometry only, not a verified negative' if kind!='polygons' else 'Label applies to focal polygon, not necessarily entire crop'))
    manifest=dict(purpose='selected diagnostic examples; no training and no unbiased benchmark claims',
                  labels_provided_to_model=False,items=entries)
    (args.out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    thumbs=[]
    for e in entries:
        im=Image.open(args.out/e['input']).convert('RGB');im.thumbnail((340,310))
        tile=Image.new('RGB',(360,360),'white');tile.paste(im,((360-im.width)//2,30));
        ImageDraw.Draw(tile).text((10,8),e['sample_id']+' | '+e['label'],fill='black');thumbs.append(tile)
    sheet=Image.new('RGB',(360*4,360*2),'#dddddd')
    for i,im in enumerate(thumbs):sheet.paste(im,((i%4)*360,(i//4)*360))
    sheet.save(args.out/'contact_sheet.jpg')
    print(json.dumps([{'id':e['sample_id'],'label':e['label'],'window':e['window_xywh']} for e in entries]))

if __name__=='__main__':main()
