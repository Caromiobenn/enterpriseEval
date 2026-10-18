import argparse
import json
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root/'evidence'/'recovery-study-20261016'/'code'))
import recovery_study as study

p=argparse.ArgumentParser()
p.add_argument('--case',choices=['rescue','regression','remaining_failure'],default='rescue')
p.add_argument('--arm',choices=study.ARMS,default='raw')
args=p.parse_args()
record=json.loads((root/'cases'/(args.case+'.json')).read_text(encoding='utf-8'))[args.arm]
grade,observed=study.replay(record)
print(json.dumps({'cell':record['cell'],'grade':grade,'initial_and_final_observed':observed,
                  'termination':record['termination']},ensure_ascii=False,indent=2))
