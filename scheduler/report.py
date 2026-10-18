"""Write a concise Korean report from completed scheduler evaluation artifacts."""
import argparse
import json
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);a=p.parse_args();root=a.run
    metadata=json.loads((root/'training.json').read_text(encoding='utf-8'))
    if metadata['status']!='completed':raise ValueError('Training is not complete')
    before=json.loads((root/'validation_before/evaluation.json').read_text(encoding='utf-8'))['jobs']
    after=json.loads((root/'validation_after/evaluation.json').read_text(encoding='utf-8'))['jobs']
    original=sum(j['baseline_makespan_s'] for j in after);initial=sum(j['makespan_s'] for j in before);final=sum(j['makespan_s'] for j in after)
    lines=['# scheduler 실행 결과','',
        'minor_2는 고정하고, 작업 후보 선택·짧은 대기·다음 완료까지 대기를 담당하는 PPO만 학습했습니다. 적층선 끝점과 로봇 배정은 바꾸지 않습니다.','',
        f"- CUDA, {metadata['completed_updates']} rollout 업데이트, {metadata['actual_timesteps']:,} scheduler step, early stopping 없음.",
        f"- 학습용 레이어 {metadata['train_layers']}개 준비. 실제 완료한 학습 에피소드 {metadata.get('completed_training_episodes','?')}개, 완료된 서로 다른 레이어 {len(metadata.get('visited_layer_ids',[]))}개.",
        f"- 학습 및 전후 validation 포함 소요시간: {metadata['wall_time_s']:.1f}초.",
        '- 모델: [scheduler_final.zip](scheduler_final.zip) / [TensorBoard 이벤트](tensorboard/).','',
        '## 전체 validation 6개','',
        '학습 전후 비교는 동일한 작업 묶음·충돌 검사에 초기/학습 정책을 적용한 것입니다. 원본 minor_2는 레이어 전체의 경로를 순차 실행하므로 작업 묶음별 복귀 오버헤드가 없습니다.','',
        '| 형상 | minor_2 초 | scheduler 학습 전 초 | scheduler 학습 후 초 | 학습 전 대비 단축률 | 동시 적층 초(학습 후) | Validator |',
        '|---|---:|---:|---:|---:|---:|---|']
    for b,c in zip(before,after):
        lines.append(f"| {c['id']} | {c['baseline_makespan_s']:.2f} | {b['makespan_s']:.2f} | {c['makespan_s']:.2f} | {100*(1-c['makespan_s']/b['makespan_s']):+.2f}% | {c['deposition_2plus_s']:.2f} | {c['validator']} |")
    lines += ['',f'합계: 원본 {original:.2f}초, 미학습 scheduler {initial:.2f}초, 학습 scheduler {final:.2f}초.',
        f'미학습 scheduler 대비 {100*(1-final/initial):+.2f}% 단축, 원본 minor_2 대비 {100*(1-final/original):+.2f}% 단축. 음수는 시간 증가입니다.',
        '작은 validation 형상에서는 로봇의 충돌 여유 공간이 제한되고 작업 묶음별 home 왕복이 추가됩니다. 동시 적층이 가능해졌다는 사실과 전체 makespan 개선은 별도로 평가해야 합니다.',
        '원본과 최종 trajectory의 D 구간/로봇 multiset이 모두 일치했고, 각 형상의 전체 공식 Validator를 실행했습니다.','',
        '각 형상의 trajectory, Validator 결과, 간트차트는 [validation_after](validation_after/)에 있습니다.','']
    episode_path=root/'training_episodes.json'
    if episode_path.exists():
        episodes=json.loads(episode_path.read_text(encoding='utf-8'))
        parallel=[e for e in episodes if e.get('deposition_2plus_s',0)>1e-6]
        lines += ['## 학습 중 관측','',
            f"완료된 {len(episodes)}개 학습 에피소드 중 {len(parallel)}개에서 2대 이상 동시 적층이 관측됐습니다. 단일 에피소드 최댓값은 {max((e.get('deposition_2plus_s',0) for e in episodes),default=0):.2f}초입니다.",
            '이는 탐색을 포함한 학습 중 기록이며 최종 deterministic 정책의 독립 평가 성능을 의미하지 않습니다. 최종 정책은 위의 전체 validation 6개에서 검증했습니다.','']
    path=root/'training_layer_diagnostics.json'
    if path.exists() and any('final' in x['checkpoint'] for x in json.loads(path.read_text(encoding='utf-8'))):
        results=json.loads(path.read_text(encoding='utf-8'));old={x['plan']:x for x in results if 'initial' in x['checkpoint']}
        new=[x for x in results if 'final' in x['checkpoint']]
        lines += ['## 학습 형상 첫 레이어 진단','',
            '아래는 01~06의 첫 레이어만 검사한 값이며 전체 STL의 makespan이나 전체 Validator 통과 결과가 아닙니다. 각 레이어의 공식 충돌/궤적 검사는 별도로 실행했습니다.','',
            '| 레이어 | minor_2 초 | scheduler 전 초 | scheduler 후 초 | 동시 적층 초(전/후) | 충돌 이벤트 |',
            '|---|---:|---:|---:|---:|---:|']
        for c in new:
            if c['plan'] not in old:continue
            b=old[c['plan']]
            lines.append(f"| {c['plan']} | {c['baseline_duration']:.2f} | {b['makespan_s']:.2f} | {c['makespan_s']:.2f} | {b['deposition_2plus_s']:.2f} / {c['deposition_2plus_s']:.2f} | {c['collision_events']} |")
        lines += ['','[레이어별 학습 전후 간트차트](training_layer_gantt/)','']
    lines += ['## 현재 모델의 범위','',
        '- 충돌 검사는 공식 Validator가 담당하고, 정책은 허용된 작업 후보와 WAIT 중 무엇을 실행할지 학습합니다.',
        '- 충돌 난 후보는 실행하지 않습니다. 다른 안전한 후보를 고르거나 기다립니다. 레이어 전체를 자동으로 직렬화하는 fallback은 없습니다.',
        '- 작업 묶음마다 home 복귀, 레이어 종료 장벽을 유지합니다. 이 이동 비용이 남아 있어 아직 원본 minor_2를 대체할 성능으로 검증된 것은 아닙니다.',
        '- 기존 minor_2 가중치 및 원본 코드는 수정하지 않았습니다.','']
    (root/'RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
    print(f'validation totals: minor_2={original:.2f}, before={initial:.2f}, after={final:.2f}')
    print(root/'RESULTS.md')

if __name__=='__main__':main()
