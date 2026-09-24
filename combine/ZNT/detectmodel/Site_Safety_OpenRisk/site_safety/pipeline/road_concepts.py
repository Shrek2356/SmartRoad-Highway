"""Road concept execution and scene annotation, separate from risk confirmation."""
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from site_safety.schemas import SAM3Task
from site_safety.utils.image import mask_box, save_binary_mask, image_font


def execute_road_concepts(sam3, risks, scene_elements, output_dir, min_score, max_tasks=48):
    # Round-robin gives every risk a turn before one risk consumes the budget.
    tasks=[]
    for index in range(max((len(r.sam3_tasks) for r in risks),default=0)):
        tasks.extend(r.sam3_tasks[index] for r in risks if index<len(r.sam3_tasks))
    context=[]
    for concept in dict.fromkeys(scene_elements):
        if concept in {'road','traffic_sign','guardrail'}:
            context.append(SAM3Task(task_id='context_'+concept,role='region',
                                   prompt=concept.replace('_',' '),expected_count=128))
    by_task={};cache={};trace=[];calls=0
    for task in tasks+context:
        key=task.prompt.strip().lower()
        record={'task_id':task.task_id,'prompt':task.prompt,'role':task.role}
        try:
            if key not in cache:
                if calls>=max_tasks:
                    record['status']='budget_exceeded';trace.append(record);continue
                calls+=1
                # Cache all instances of the concept; role and risk IDs are rebound below.
                cache[key]=sam3.segment(task.model_copy(update={'expected_count':128}))
                record['cache_hit']=False
            else:
                record['cache_hit']=True
            threshold=max(min_score,task.min_score or min_score)
            items=[replace(x,task_id=task.task_id,role=task.role,prompt=task.prompt)
                   for x in cache[key] if x.score>=threshold]
            by_task[task.task_id]=items
            record.update(status='ok',instances=len(items))
        except Exception as exc:
            by_task[task.task_id]=[]
            record.update(status='error',error=f'{type(exc).__name__}: {exc}')
        trace.append(record)
    for risk in risks:
        unfinished=[t['task_id'] for t in trace if t['status']!='ok' and t['task_id'] in {x.task_id for x in risk.sam3_tasks}]
        if unfinished:
            risk.uncertainties.append('定位任务未完成：'+','.join(unfinished))
            risk.localization_plan_status='partial_execution'
    Path(output_dir,'sam3_task_trace.json').write_text(json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8')
    return by_task,context


def write_scene_annotation(image, output_dir, report, by_task, context_tasks):
    output_dir=Path(output_dir)
    normal=report.assessment_quality.get('result_status')=='no_visible_anomaly'
    overlay=image.copy();draw=ImageDraw.Draw(overlay);font=image_font(17)
    records=[]
    for task in context_tasks:
        concept=task.task_id.removeprefix('context_')
        items=by_task.get(task.task_id,[])
        if not items:
            continue
        mask=np.zeros((image.height,image.width),dtype=np.uint8)
        for item in items:
            if item.mask.shape!=mask.shape:
                raise ValueError('Scene context mask does not match the input image')
            mask=np.maximum(mask,(item.mask>0).astype(np.uint8))
        name=f'scene_mask_{concept}.png';save_binary_mask(mask,output_dir/name)
        color=(28,175,83) if concept=='road' and normal else (44,127,208)
        if concept=='road':
            tint=Image.new('RGB',image.size,color)
            overlay=Image.composite(tint,overlay,Image.fromarray((mask*64).astype(np.uint8)))
            draw=ImageDraw.Draw(overlay)
        text={'road':'路面：未见可见异常' if normal else '道路区域（场景对象）',
              'traffic_sign':'路牌（场景对象）','guardrail':'护栏（场景对象）'}[concept]
        # A single road union box avoids labeling every asphalt patch as a new road.
        boxes=[mask_box(mask)] if concept=='road' else [mask_box(x.mask) for x in items]
        boxes=[b for b in boxes if b]
        # Guardrail proposals are retained as masks/metadata; dense long boxes
        # obscure the requested road/sign overview, so do not draw them here.
        visible_boxes=[] if concept=='guardrail' else boxes
        for box in visible_boxes:
            x1,y1,x2,y2=box
            draw.rectangle((x1,y1,x2-1,y2-1),outline=color,width=3)
        if visible_boxes:
            x,y=visible_boxes[0][0],max(34,visible_boxes[0][1]-25)
            rect=draw.textbbox((x,y),text,font=font)
            draw.rectangle(rect,fill=(255,255,255));draw.text((x,y),text,fill=color,font=font)
        records.append(dict(concept=concept,mask_path=name,instances=len(items),boxes=boxes,
                            color='green' if concept=='road' and normal else 'blue',is_risk=False,
                            displayed_in_overview=concept!='guardrail'))
    banner='未见可见异常 · 绿色为道路掩码与框' if normal else '蓝色为场景对象 · 风险见逐项叠加图'
    draw.rectangle((0,0,image.width,31),fill=(20,35,52));draw.text((8,4),banner,fill='white',font=font)
    overlay.save(output_dir/'scene_annotation.png')
    metadata=dict(result_status=report.assessment_quality.get('result_status'),
                  meaning='Green road box: no visible anomaly in this image, not a guarantee of safety. Blue: context object, not damage.',
                  items=records)
    (output_dir/'scene_annotation.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    report.assessment_quality['scene_annotation']='scene_annotation.png'
    report.assessment_quality['normal_road_box']=bool(normal and any(x['concept']=='road' for x in records))
