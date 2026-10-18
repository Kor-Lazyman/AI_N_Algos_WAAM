"""Report both trained policies and makespan-only evaluation without PASS labels."""
import argparse
import html
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args()
    read=lambda n:json.loads((a.run/n).read_text(encoding='utf-8'))
    meta=read('training.json');rows=read('comparison.json');after=read('validation_after/evaluation.json')
    if meta['status']!='completed':raise ValueError('Run is not completed')
    lines=['# minor3 공동 학습 결과','',
        f"CUDA 교대 업데이트 {meta['completed_updates']}회. 경로 PPO {meta['path_timesteps']} layer step, 대피 PPO {meta['avoidance_timesteps']} repair step. Early stopping 없음. 준비·학습·학습 전후 평가 시간 {meta['wall_time_s']:.1f}초.",'',
        f"경로 정책 가중치 변경: {meta['path_weights_changed']}. 대피 정책 가중치 변경: {meta['avoidance_weights_changed']}. 경로 정책은 minor_2로 초기화 후 추가 학습했다.",'',
        '한 경로 action으로 전체 레이어를 생성한다. 충돌 때 작업을 재분할하지 않고, 충돌 직전 위치에서 정지·대피·복귀 후 같은 선분을 계속 그린다. 로봇별 원래 적층 순서와 선분 완성을 확인하고 새 충돌을 반복 검사한다. 두 정책 모두 makespan 비용만 받는다.','',
        '**IoU 및 전체 Validator는 실행하지 않았다. 아래 완료 여부는 적층 경로 보존과 설정된 샘플 기반 충돌 모델 기준이며, Validator PASS나 형상 품질 통과를 의미하지 않는다.** 경로 자체도 재학습하므로 기준 minor_2와 동일 품질을 보장하는 시간 비교는 아니다.','',
        '| STL | 기존 minor_2 (초) | minor3 학습 전 (초) | minor3 학습 후 (초) | 완료 / 충돌 없음 |','|---|---:|---:|---:|---|']
    fmt=lambda n:'미완료' if n is None else f'{n:.2f}'
    for r in rows:lines.append(f"| {r['id']} | {r['minor2_s']:.2f} | {fmt(r['before_s'])} | {fmt(r['after_s'])} | {r['after_complete']} |")
    if all(r['before_complete'] and r['after_complete'] for r in rows):
        b=sum(r['before_s'] for r in rows);c=sum(r['after_s'] for r in rows);original=sum(r['minor2_s'] for r in rows)
        lines+=[f'| 합계 | {original:.2f} | {b:.2f} | {c:.2f} | |','',
                f'학습 전 대비 makespan 변화 {100*(c/b-1):+.2f}%. 기존 minor_2 대비 {100*(c/original-1):+.2f}%. 양수는 증가, 음수는 단축.']
    lines+=['','| STL | 충돌 수정 횟수 | D 선분 중간 중단 횟수 | 대피 왕복 거리 합 (mm) |','|---|---:|---:|---:|']
    for j in after:lines.append(f"| {j['id']} | {j['repairs']} | {j['interrupted_D']} | {j['detour_distance_mm']:.1f} |")
    lines+=['','D 중간 중단이 0인 형상은 그 평가에서 충돌이 접근 T 구간에서 발생했거나, 접근 단계의 대피·대기로 이후 충돌까지 해소된 경우다. 대피 선택에는 제자리 대기도 포함되며 거리 0이면 이동 없이 기다린 것이다.','',
        '미완성 계획은 실제 완료 makespan으로 비교하지 않는다. 학습에서는 큰 시간 목적 비용을 주며 출력은 실패로 남긴다. 학습 데이터는 6개 STL의 18개 선택 레이어, 평가는 별도 6개 STL 전체 레이어이다. 짧은 시험 학습이며 수렴이나 형상 품질을 주장하지 않는다.','',
        '## 파일','',
        '- [경로 정책](path_final.zip)',
        '- [대피 정책](avoidance_final.zip)',
        '- [Gantt 모음](gantt_index.html)',
        '- [학습 메타데이터](training.json)',
        '- `validation_after/job_XX/input/trajectory.csv`: 완성된 경로',
        '- `validation_after/job_XX/repair_trace.json`: 충돌 시각·양보 로봇·중단 좌표·대피 좌표·복귀 시각',
        '- `path_episodes.json`, `avoidance_episodes.json`: 두 정책 학습 에피소드',
        '- `tensorboard/`: 경로와 대피 학습 로그','']
    lines+=['## 학습 중 제약 실패','',
            '| 정책 | 종료된 에피소드 | 미해결/실패 에피소드 | D 중간 중단 합계 |','|---|---:|---:|---:|']
    for label in ('path','avoidance'):
        records=read(label+'_episodes.json')
        lines.append(f"| {label} | {len(records)} | {sum(bool(r['failed']) for r in records)} | {sum(r['interrupted_D'] for r in records)} |")
    lines+=['','위 에피소드 수는 종료된 에피소드 전체이며 실패도 포함한다. 실패한 계획은 실제 완료 makespan으로 인정하지 않는다. 예를 들어 `repair_limit`은 32회 수정 한계를 넘었다는 뜻이다.','']
    lines+=['## 로봇별 활용률','',
            '적층 활용률은 D 시간 / 전체 makespan이다. 이동(T)을 적층 활용률에 포함하지 않는다. 대기율은 W 시간 / 전체 makespan이다.', '',
            '| STL | 시점 | R1 적층 | R2 적층 | R3 적층 | 평균 적층 | 평균 대기 |',
            '|---|---|---:|---:|---:|---:|---:|']
    for phase,label in [('before','학습 전'),('after','학습 후')]:
        for job in read('validation_'+phase+'/evaluation.json'):
            if not job['complete']:
                lines.append(f"| {job['id']} | {label} | 미완료 | | | | |")
                continue
            robots=job['robots'];util=[r['D_util'] for r in robots]
            mean_wait=sum(r['W']/job['makespan_s'] for r in robots)/len(robots)
            lines.append(f"| {job['id']} | {label} | {util[0]:.1%} | {util[1]:.1%} | {util[2]:.1%} | {sum(util)/len(util):.1%} | {mean_wait:.1%} |")
    example=a.run/'mid_stroke_example'/'details.json'
    if example.exists():
        details=json.loads(example.read_text(encoding='utf-8'))
        lines+=['','## 적층선 중간 대피 예시','',
                f"학습 STL {details['shape']}, layer {details['layer']} 한 층의 최종 두 정책 재실행이다. 전체 STL 또는 별도 검증 결과가 아니다. 충돌 수정 {details['repairs']}회, D 중간 중단 {details['interrupted_D']}회.",'',
                (f"**미해결: {details['failure_reason']}.** 그림은 실패한 수정 과정의 진단용이며 완성 경로가 아니다. 중간 계획 시간은 실제 완료 makespan으로 비교하지 않는다."
                 if details['failed'] else f"완료 makespan {details['makespan_s']:.2f}초. 설정된 충돌 모델에서 충돌 없음."),'',
                '- [XY 대피·복귀 경로](mid_stroke_example/xy_detours.html)',
                '- [대피 좌표와 시각](mid_stroke_example/details.json)','']
    (a.run/'RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    page=['<!doctype html><html lang="ko"><meta charset="utf-8"><title>minor3 Gantt</title>',
          '<style>body{font:18px system-ui;max-width:1000px;margin:40px auto}li{margin:20px}a{margin-right:20px}</style>',
          '<h1>minor3 학습 전후 Gantt</h1><p>makespan 및 충돌 검사만 수행. IoU·전체 Validator 미실행.</p><ul>']
    for i,r in enumerate(rows):
        page.append('<li>'+html.escape(r['id'])+'<br>')
        for key,label in [('before','학습 전'),('after','학습 후')]:
            if r[key+'_complete']:page.append(f'<a href="validation_{key}/job_{i:02d}/gantt.html">{label}: {r[key+"_s"]:.2f}s</a>')
        page.append(f'<a href="validation_after/job_{i:02d}/repair_trace.json">대피 기록</a></li>')
    page+=['</ul></html>'];(a.run/'gantt_index.html').write_text('\n'.join(page),encoding='utf-8')
    print(json.dumps(dict(completed=meta['complete_validation'],path_weights_changed=meta['path_weights_changed'],
        avoidance_weights_changed=meta['avoidance_weights_changed'],
        before=sum(r['before_s'] for r in rows) if all(r['before_complete'] for r in rows) else None,
        after=sum(r['after_s'] for r in rows) if all(r['after_complete'] for r in rows) else None),indent=2))

if __name__=='__main__':main()
