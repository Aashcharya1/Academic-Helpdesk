"""Explicit synthetic fixtures, isolated from every real source and index."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openpyxl import Workbook
from helpdesk.config import ROOT
from helpdesk.importers import ingest,snapshot

dest=ROOT/'data/demo_import';dest.mkdir(parents=True,exist_ok=True)
(dest/'DEMO synthetic handbook.txt').write_text('DEMO ONLY. Fictional testing university. EXM1000 Introduction to Examples has no prerequisites. This synthetic course carries 2 credits. These facts are not IIT Jodhpur rules.',encoding='utf-8')
w=Workbook();s=w.active;s.title='Classroom Allocation'
s.append(['Code','Subject','L-T-P','Credit','Slot','Department','Instructor','Co-Instructor','Registered','Classroom'])
s.append(['EXM1000','Introduction to Examples','2-0-0',2,'A','DEMO','Example Teacher',None,10,'DEMO room'])
s=w.create_sheet('Time Table Committee Members');s.append(['Synthetic contacts']);s.append(['No','Department','Name','eMail']);s.append([1,'DEMO','Example Teacher','demo@example.invalid'])
# Dummy address is deliberately documented as synthetic and never available to REAL.
w.save(dest/'DEMO Finalized courses list.xlsx')
result=ingest('demo',dest)
p=snapshot('demo',True)
manifest=__import__('csv').DictReader((p/'manifest.csv').open(encoding='utf-8-sig'))
review={'approved':[r['doc_id'] for r in manifest],'metadata':{},'note':'Generated synthetic fixtures. All addresses and people in DEMO are fictional.'}
(p/'review.json').write_text(json.dumps(review,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
