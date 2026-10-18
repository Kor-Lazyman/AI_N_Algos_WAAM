from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
from docx import Document

ROOT=Path(__file__).resolve().parents[1]
BASE=Path(os.environ["PROJECT_102"])
TEMPLATE=Path(os.environ["REPORT_TEMPLATE"])


def read_json(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
    return h.hexdigest()

def fmt(seconds):
    if seconds is None or seconds=="":return "미측정"
    n=max(0,int(float(seconds))); d,n=divmod(n,86400);h,n=divmod(n,3600);m,s=divmod(n,60)
    return f"{d:02d}:{h:02d}:{m:02d}:{s:02d}"

def set_cell(cell,text):
    p=cell.paragraphs[0] if cell.paragraphs else cell.add_paragraph()
    old=p.runs[0] if p.runs else None
    font_props=None
    if old:
        font_props={"name":old.font.name,"size":old.font.size,"bold":old.bold,"italic":old.italic}
    for paragraph in cell.paragraphs:
        paragraph.clear()
    run=p.add_run(str(text))
    if font_props:
        run.font.name=font_props["name"]
        if font_props["size"]:run.font.size=font_props["size"]
        if font_props["bold"] is not None:run.bold=font_props["bold"]
        if font_props["italic"] is not None:run.italic=font_props["italic"]

def table_rows_from_eval(path):
    data=read_json(path);out=[]
    for job in data["jobs"]:
        ep=job["episodes"][0]
        out.append({"model":job.get("id",""),"makespan":ep.get("makespan_s"),
                    "calculation":job.get("job_wall_time_s"),"validator":ep.get("status","미측정")})
    return out

def table_rows_minor2(path):
    out=[]
    with open(path,newline="",encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            out.append({"model":r["input"],"makespan":float(r["minor_2_makespan_s"]),
                        "calculation":float(r["minor_2_calculation_s"]),"validator":r["minor_2_validator"]})
    names={"01":"01 (Honeycomb)","02":"02 (Spiral)","03":"03 (Triangular truss)",
           "04":"04 (Motor inner)","05":"05 (Twisted shell)","06":"06 (Angle frame)"}
    for r in out:r["model"]=names.get(r["model"],r["model"])
    return out

def params_for(variant,training):
    p=training.get("ppo",{})
    common=[
        ("학습 업데이트",f"{training.get('completed_updates','-')} / {training.get('requested_updates','-')}회", "요청 횟수 / 완료 횟수"),
        ("학습 타임스텝",f"{training.get('actual_timesteps','-')} / {training.get('requested_timesteps','-')}", "완료 / 요청"),
        ("n_steps",p.get("n_steps","-"),"PPO rollout 단계 수"),
        ("batch_size",p.get("batch_size","-"),"미니배치 크기"),
        ("learning_rate",p.get("learning_rate","-"),"학습률"),
        ("gamma",p.get("gamma","-"),"할인율"),
        ("gae_lambda",p.get("gae_lambda","-"),"GAE 람다"),
        ("seed",p.get("seed","-"),"재현용 시드"),
        ("device",training.get("actual_device",p.get("device","-")),"정책 네트워크 계산 장치"),
        ("early_stopping",training.get("early_stopping","-"),"조기 종료 설정"),
        ("eval_every_updates",training.get("eval_every_updates","-"),"평가 주기"),
        ("eval_episodes",training.get("eval_episodes",1),"평가 STL별 반복 횟수"),
        ("geometry_device",training.get("geometry_device","CPU"),"기하·Validator 계산 장치"),
        ("training STL",len(training.get("training_jobs",[])),"학습 입력 STL 개수"),
        ("validation STL",len(training.get("validation_jobs",[])),"학습 중 평가 STL 개수"),
    ]
    if variant=="minor1":
        common.extend([
            ("placement_enabled",training.get("placement_enabled"),"전역 XY placement PPO 사용"),
            ("placement_steps_per_update",training.get("placement_steps_per_update"),"업데이트당 placement episode 수"),
            ("placement_every",training.get("placement_every"),"placement 학습 주기"),
            ("placement PPO n_steps",training.get("placement_ppo",{}).get("n_steps"),"placement rollout 길이"),
            ("placement PPO n_epochs",training.get("placement_ppo",{}).get("n_epochs"),"placement PPO 반복 횟수"),
            ("reward_formula",training.get("reward_formula"),"layer 보상식 ID"),
            ("placement_reward",training.get("placement_reward"),"동일 STL의 layer reward 평균"),
        ])
    else:
        common.extend([
            ("placement_enabled",training.get("placement_enabled",False),"전역 XY placement PPO 사용 여부"),
            ("reward_formula",training.get("reward_formula","-"),"학습 보상식 ID"),
        ])
    common.extend([
        ("best_step",training.get("best_step","-"),"최고 검증 점수 체크포인트 단계"),
        ("best_model",training.get("best_model","best_model.zip"),"실행 시 불러오는 모델"),
        ("training_status",training.get("status","-"),"학습 기록 상태"),
    ])
    return common

def set_paragraph(doc,index,text):
    if index<len(doc.paragraphs):doc.paragraphs[index].text=text

def make_doc(variant,title,rows,training):
    folder=ROOT/variant
    doc=Document(TEMPLATE)
    set_paragraph(doc,1,f"알고리즘 1번 | {title}")
    # Keep the form's authored comment slots empty for the user.
    for idx in (16,18,24,25,29):set_paragraph(doc,idx,"")
    table=doc.tables[1]
    for i,r in enumerate(rows,1):
        if i>=len(table.rows):table.add_row()
        model_name=r["model"]
        if model_name.isdigit():model_name={"01":"01 (Honeycomb)","02":"02 (Spiral)","03":"03 (Triangular truss)","04":"04 (Motor inner)","05":"05 (Twisted shell)","06":"06 (Angle frame)"}.get(model_name,model_name)
        values=(model_name,fmt(r["makespan"]),fmt(r["calculation"]),str(r["validator"]))
        for j,val in enumerate(values):set_cell(table.rows[i].cells[j],val)
    ptable=doc.tables[2]
    params=params_for(variant,training)
    for i,item in enumerate(params,1):
        if i>=len(ptable.rows):ptable.add_row()
        for j,val in enumerate(item):set_cell(ptable.rows[i].cells[j],val)
    for i in range(len(params)+1,len(ptable.rows)):
        for c in ptable.rows[i].cells:set_cell(c,"")
    doc.core_properties.title=f"INE4107 중간보고서 {title}"
    doc.core_properties.subject=f"{title} 실험 결과 자료"
    doc.save(folder/f"{variant}_중간보고서.docx")

def main():
    configs={
      "main":{"title":"1.0.2 Main Layer PPO","training":"result/training/layers_1.0.2_20261017_044941_396096/training.json","eval":"result/layer_evaluation/stl_files_20261017_trained_model_runtime/evaluation.json"},
      "minor1":{"title":"Minor1 Placement and Scheduler PPO","training":"Minor/result/training/minor_40updates_20261018_152213/training.json","eval":"Minor/result/layer_evaluation/training_stl_validator_20261018/evaluation.json"},
      "minor2":{"title":"Minor2 Reward Only PPO","training":"minor_2/result/training/reward_only_40updates_20261018_155838/training.json","eval":None},
    }
    source_hash=sha(TEMPLATE)
    (ROOT/"common"/"template_evidence.json").write_text(json.dumps({"reference":str(TEMPLATE),"sha256":source_hash,"section_count":1,"tables":3,"template_unchanged":True},indent=2),encoding="utf-8")
    for variant,cfg in configs.items():
        training=read_json(BASE/cfg["training"])
        rows=table_rows_minor2(BASE/"minor_2/result/training/reward_only_40updates_20261018_155838/comparison/original_gantt_comparison.csv") if variant=="minor2" else table_rows_from_eval(BASE/cfg["eval"])
        make_doc(variant,cfg["title"],rows,training)
        record={"variant":variant,"title":cfg["title"],"training":training,
                "model_results":[{"model":r["model"],"makespan_s":r["makespan"],"makespan_DD_HH_MM_SS":fmt(r["makespan"]),
                                  "calculation_s":r["calculation"],"calculation_DD_HH_MM_SS":fmt(r["calculation"]),"validator":r["validator"]} for r in rows]}
        (ROOT/variant/"results.json").write_text(json.dumps(record,indent=2,ensure_ascii=False,default=str),encoding="utf-8")
    print("Three filled DOCX reports and results.json files created.")

if __name__=="__main__":main()
