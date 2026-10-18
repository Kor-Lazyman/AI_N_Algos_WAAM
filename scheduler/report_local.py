"""Summarize completed local-repair training alongside both previous baselines."""
import argparse
import html
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--previous',type=Path,required=True);a=p.parse_args()
    read=lambda path:json.loads(path.read_text(encoding='utf-8'))
    meta=read(a.run/'training.json')
    if meta['status']!='completed':raise ValueError('Training and validation must be complete')
    before=read(a.run/'validation_before/evaluation.json')['jobs']
    after=read(a.run/'validation_after/evaluation.json')['jobs']
    old={j['id']:j for j in read(a.previous/'validation_after/evaluation.json')['jobs']}
    bmap={j['id']:j for j in before}
    original=sum(j['baseline_makespan_s'] for j in after)
    prev=sum(old[j['id']]['makespan_s'] for j in after)
    initial=sum(j['makespan_s'] for j in before);final=sum(j['makespan_s'] for j in after)
    lines=['# 충돌 예측·국소 대피 scheduler 학습 결과','',
        f"CUDA {meta['completed_updates']} rollout 업데이트, {meta['actual_timesteps']:,} step. Early stopping 없음. 완료 학습 에피소드 {meta['completed_training_episodes']}개. 학습과 학습 전후 검증을 합한 실행 시간 {meta['wall_time_s']:.1f}초.",'',
        'minor_2 적층 모델은 고정했다. scheduler만 새 action/observation에 맞게 학습했다. 작업을 마치면 현재 위치에 머물고, 다음 후보와 충돌이 예상될 때 유휴 로봇의 국소 대피를 제안한다. 대피 경로와 이후 작업을 재검사하며, 안전하지 않은 후보는 선택하지 못한다. 실행 중인 비드는 중단하지 않고 다음 이벤트에서 재검토한다.','',
        '| STL | minor_2 (초) | 이전 scheduler (초) | 새 학습 전 (초) | 새 학습 후 (초) | Validator |','|---|---:|---:|---:|---:|---|']
    for j in after:
        lines.append(f"| {j['id']} | {j['baseline_makespan_s']:.2f} | {old[j['id']]['makespan_s']:.2f} | {bmap[j['id']]['makespan_s']:.2f} | {j['makespan_s']:.2f} | {j['validator']} |")
    lines += [f'| 합계 | {original:.2f} | {prev:.2f} | {initial:.2f} | {final:.2f} | |','',
        f'최종 모델의 makespan 감소율: minor_2 대비 {100*(1-final/original):+.2f}%, 이전 scheduler 대비 {100*(1-final/prev):+.2f}%, 동일한 새 환경의 학습 전 정책 대비 {100*(1-final/initial):+.2f}%. 양수는 단축, 음수는 증가다. 구조 개선 효과와 학습 효과를 구분해서 비교해야 한다.','',
        '| STL | R1 적층 활용률 | R2 적층 활용률 | R3 적층 활용률 | 국소 대피 수 | 대피 거리 합 (mm) | 대피용 home 복귀 | 동시 적층 (초) |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for j in after:
        u=[r['D']/j['makespan_s']*100 for r in j['robots']]
        lines.append(f"| {j['id']} | {u[0]:.2f}% | {u[1]:.2f}% | {u[2]:.2f}% | {j['local_yields']} | {j['yield_distance_mm']:.1f} | {j['home_fallbacks']} | {j['deposition_2plus_s']:.2f} |")
    lines+=['','활용률은 D/makespan이다. 이동 T를 포함한 가동률 및 로봇별 T/D/W는 각 metrics.json에 있다. home 복귀 수는 대피 후보의 최후 대안으로 선택한 횟수이며 정상 레이어 종료 복귀는 제외한다.','',
        '이 validation STL들은 최대 XY 거리가 250 mm보다 작아서 현재 팔 외피 기준에서 동시 적층이 불가능하다. 기대하는 개선은 반복 home 왕복 감소와 안전한 이동 구간 겹침이다. 짧은 40-update 단일 seed 실험이므로 일반화·수렴이나 전체 학습 STL 성능을 보장하지 않는다.','',
        '모든 전체 STL 결과는 minor_2와 적층 선분 및 담당 로봇 multiset을 대조한 후 기존 공식 Validator로 검사했다. 후보 검사 가속화 코드와 별개로 전체 레이어에도 공식 충돌 검사를 수행했다.','',
        '## 저장 파일','',
        '- [최종 scheduler 모델](scheduler_final.zip)',
        '- [학습 전후 비교 JSON](comparison.json)',
        '- [학습 정보](training.json)',
        '- [전체 Gantt 모음](gantt_index.html)',
        '- `validation_after/job_XX/input/trajectory.csv`: 최종 경로',
        '- `validation_after/job_XX/scheduler_trace.json`: 충돌 예측 및 반복 대피/재검사 기록',
        '- `validation_after/job_XX/validation/summary.json`: 공식 Validator 결과',
        '- `tensorboard/`: 학습 로그','']
    old_t=sum(r['T'] for j in after for r in old[j['id']]['robots'])
    new_t=sum(r['T'] for j in after for r in j['robots'])
    lines+=['## 이동 비용 확인','',
        f'이전 scheduler의 로봇 이동시간 합은 {old_t:.2f} 로봇·초, 새 최종 scheduler는 {new_t:.2f} 로봇·초다. 이동시간 합과 makespan은 다르며, 로봇들이 동시에 이동하면 이동시간 합 일부가 겹친다.','',
        'trace의 predicted_conflict.robots는 내부 인덱스 0/1/2이며 실제 로봇 번호는 +1이다. repairs.robot와 DISPATCH의 robot은 실제 번호 1/2/3이다. predicted_conflict.time_s는 해당 제안 start 기준 상대 시각이다.','']
    (a.run/'RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    body=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>Local repair scheduler Gantt</title>',
          '<style>body{font:18px system-ui;max-width:1000px;margin:40px auto}li{margin:16px}a{margin-right:20px}</style>',
          '<h1>충돌 예측·국소 대피 scheduler</h1><p>각 형상의 학습 전후 Gantt와 충돌 수정 기록</p><ul>']
    for i,j in enumerate(after):
        folder=f'job_{i:02d}'
        body.append(f'<li>{html.escape(j["id"])}: {j["makespan_s"]:.2f}s ({html.escape(j["validator"])})<br>'
                    f'<a href="validation_before/{folder}/gantt.html">학습 전 Gantt</a>'
                    f'<a href="validation_after/{folder}/gantt.html">학습 후 Gantt</a>'
                    f'<a href="validation_after/{folder}/scheduler_trace.json">충돌 수정 기록</a></li>')
    body+=['</ul></html>'];(a.run/'gantt_index.html').write_text('\n'.join(body),encoding='utf-8')
    print(json.dumps(dict(minor2=original,previous_scheduler=prev,new_initial=initial,new_final=final,
        pass_count=sum(j['validator']=='PASS' for j in after),home_fallbacks=sum(j['home_fallbacks'] for j in after)),indent=2))

if __name__=='__main__':main()
