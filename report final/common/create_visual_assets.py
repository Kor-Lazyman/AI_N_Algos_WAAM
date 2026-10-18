from __future__ import annotations

import csv
from pathlib import Path
import math
import trimesh

ROOT = Path(__file__).resolve().parents[1]
COLORS = {"T": "#2878B5", "D": "#2B9348", "W": "#F4A261"}


def mesh_svg(source: Path, target: Path, max_faces: int = 4500) -> None:
    mesh = trimesh.load(source, force="mesh", process=False)
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        return
    ids = list(range(len(mesh.faces)))
    if len(ids) > max_faces:
        stride = len(ids) / max_faces
        ids = [min(len(mesh.faces)-1, int(i*stride)) for i in range(max_faces)]
    az, el = math.radians(45), math.radians(33)
    ca, sa, ce, se = math.cos(az), math.sin(az), math.cos(el), math.sin(el)
    vertices = mesh.vertices
    projected = [(x*ca-y*sa, x*sa*se+y*ca*se-z*ce, x*sa*ce+y*ca*ce+z*se) for x,y,z in vertices]
    points = [projected[i] for face_id in ids for i in mesh.faces[face_id]]
    xmin=min(p[0] for p in points); xmax=max(p[0] for p in points)
    ymin=min(p[1] for p in points); ymax=max(p[1] for p in points)
    width,height,pad=900,620,42
    scale=min((width-2*pad)/max(xmax-xmin,1e-9),(height-2*pad)/max(ymax-ymin,1e-9))
    def xy(p): return (pad+(p[0]-xmin)*scale, height-pad-(p[1]-ymin)*scale)
    face_normals=mesh.face_normals
    light=(0.35,-0.3,0.88)
    norm=math.sqrt(sum(v*v for v in light)); light=tuple(v/norm for v in light)
    polys=[]
    for fid in ids:
        face=mesh.faces[fid]; pts=[xy(projected[int(i)]) for i in face]
        n=face_normals[fid]; dot=max(0.,float(n[0]*light[0]+n[1]*light[1]+n[2]*light[2]))
        shade=int(128+95*dot)
        color=f"#{max(0,shade-20):02x}{min(255,shade+2):02x}{min(255,shade+18):02x}"
        depth=sum(projected[int(i)][2] for i in face)/3
        polys.append((depth,pts,color))
    polys.sort(key=lambda x:x[0])
    label=source.name
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="#fbfcfe"/><text x="36" y="30" font-family="Arial" font-size="18" fill="#17233b">{label}</text><g stroke="#345" stroke-width="0.18">']
    for _,pts,color in polys:
        coords=" ".join(f"{x:.2f},{y:.2f}" for x,y in pts)
        svg.append(f'<polygon points="{coords}" fill="{color}"/>')
    svg.append('</g></svg>')
    target.parent.mkdir(parents=True,exist_ok=True); target.write_text(''.join(svg),encoding='utf-8')


def gantt_svg(trajectory: Path, target: Path, title: str) -> None:
    robots={1:[],2:[],3:[]}
    with trajectory.open(newline='',encoding='utf-8-sig') as f:
        for row in csv.DictReader(f): robots[int(row['robot_id'])].append((float(row['time_s']),row['mode']))
    max_time=max((pts[-1][0] for pts in robots.values() if pts),default=1.)
    width,height,left,right,top=1300,260,110,28,56
    plotw=width-left-right
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/><text x="{left}" y="27" font-family="Arial" font-size="19">{title} Gantt - {max_time:.2f}s</text>']
    for i,robot in enumerate((1,2,3)):
        y=top+i*58;svg.append(f'<text x="16" y="{y+20}" font-family="Arial" font-size="15">Robot {robot}</text>')
        pts=robots[robot]
        if len(pts)>1600:
            buckets=1600; step=max_time/buckets; sampled=[]
            j=0
            for b in range(buckets):
                a=b*step; z=(b+1)*step; mid=(a+z)/2
                while j+1<len(pts) and pts[j+1][0]<=mid:j+=1
                mode=pts[j][1]
                if sampled and sampled[-1][2]==mode:sampled[-1]=(sampled[-1][0],z,mode)
                else:sampled.append((a,z,mode))
            segs=sampled
        else:
            segs=[(a[0],b[0],a[1]) for a,b in zip(pts,pts[1:]) if b[0]>a[0]]
        for a,b,mode in segs:
            if mode in COLORS and b>a:
                x=left+a/max_time*plotw;w=(b-a)/max_time*plotw
                svg.append(f'<rect x="{x:.2f}" y="{y}" width="{max(w,0.25):.2f}" height="26" fill="{COLORS[mode]}"/>')
    legend=[('T','Travel'),('D','Deposition'),('W','Wait')]
    x=left
    for mode,label in legend:
        svg.append(f'<rect x="{x}" y="239" width="14" height="11" fill="{COLORS[mode]}"/><text x="{x+20}" y="249" font-family="Arial" font-size="12">{label}</text>');x+=115
    svg.append('</svg>');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(''.join(svg),encoding='utf-8')


def process_tree(folder: Path, kind: str) -> int:
    jobs=0
    for stl in folder.rglob('target.stl'):
        if kind=='validation' and '/job_' not in str(stl).replace('\\','/'): continue
        episode=stl.parent
        traj=episode/'trajectory.csv'
        if not traj.is_file():
            # Evaluation outputs keep the input pair under episode/input.
            traj=episode/'input'/'trajectory.csv'
        if not traj.is_file(): continue
        rel=episode.relative_to(folder)
        name='_'.join(rel.parts) or stl.stem
        image_dir=folder/'images';chart_dir=folder/'gantt_images'
        mesh_svg(stl,image_dir/f'{name}_target.svg')
        gantt_svg(traj,chart_dir/f'{name}_gantt.svg',name)
        jobs+=1
    return jobs


def main():
    for variant in ('main','minor1','minor2'):
        for kind,folder in [('stl_files',ROOT/variant/'stl_files'),('validation',ROOT/variant/'validation_data')]:
            count=process_tree(folder,kind)
            print(f'{variant}/{kind}: {count} STL target and trajectory images')
    # Main experiment pseudocode flowchart, as an editable vector image.
    path=ROOT/'main'/'pseudocode'/'algorithm.svg'
    path.write_text('''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="640" viewBox="0 0 900 640"><rect width="100%" height="100%" fill="white"/><style>text{font-family:Arial,sans-serif;fill:#17233b;font-size:18px}.box{fill:#f2f6fb;stroke:#2563eb;stroke-width:2;rx:12}.arrow{stroke:#53657d;stroke-width:2;marker-end:url(#m)}</style><defs><marker id="m" markerWidth="10" markerHeight="8" refX="8" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#53657d"/></marker></defs><text x="450" y="38" text-anchor="middle" font-size="24">1.0.2 Layer PPO</text><rect class="box" x="275" y="65" width="350" height="56"/><text x="450" y="100" text-anchor="middle">STL and process config</text><path class="arrow" d="M450 121v34"/><rect class="box" x="275" y="155" width="350" height="56"/><text x="450" y="190" text-anchor="middle">Slice target into layers</text><path class="arrow" d="M450 211v34"/><rect class="box" x="235" y="245" width="430" height="66"/><text x="450" y="274" text-anchor="middle">For each layer, PPO selects hatch</text><text x="450" y="297" text-anchor="middle">angle, spacing, corner, robot partition</text><path class="arrow" d="M450 311v34"/><rect class="box" x="275" y="345" width="350" height="56"/><text x="450" y="380" text-anchor="middle">Generate routes and schedule 3 robots</text><path class="arrow" d="M450 401v34"/><rect class="box" x="275" y="435" width="350" height="56"/><text x="450" y="470" text-anchor="middle">Collision and geometry checks</text><path class="arrow" d="M450 491v34"/><rect class="box" x="275" y="525" width="350" height="56"/><text x="450" y="560" text-anchor="middle">Full WAAM Validator; save trajectory</text></svg>''',encoding='utf-8')

if __name__=='__main__':main()
