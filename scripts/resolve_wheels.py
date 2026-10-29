"""Export pip's resolved wheel links before its sequential download phase.

This process-only hook does not alter pip or install anything. The subsequent
standard pip install still checks dependency compatibility from local wheels.
"""
import json
from pathlib import Path
from pip._internal.operations.prepare import RequirementPreparer
from pip._internal.cli.main import main
root=Path(__file__).resolve().parents[1]
def export_links(self,requirements):
    rows=[]
    for req in requirements:
        link=req.link
        if link is None:continue
        if link.hash_name!='sha256' or not link.hash:raise ValueError('Missing SHA-256 from package index')
        rows.append({'download_info':{'url':link.url_without_fragment,'archive_info':{'hashes':{'sha256':link.hash}}}})
    (root/'.cache/requirements-plan.json').write_text(json.dumps({'install':rows},indent=2))
    print(f'Exported {len(rows)} resolved SHA-256 wheel links',flush=True)
    raise SystemExit(0)
RequirementPreparer.prepare_linked_requirements_more=export_links
main(['install','--dry-run','--only-binary=:all:','-r',str(root/'requirements.txt'),'--disable-pip-version-check','--progress-bar','off'])
