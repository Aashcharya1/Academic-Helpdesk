import json, re, sqlite3
from datetime import datetime, timezone
from .config import dataset_dir

def redact(text):
    text = re.sub(r'[\w.+-]+@[\w.-]+', '[email]', text)
    text = re.sub(r'\b[Bb]\d{2}[A-Za-z]{2}\d{4}\b', '[roll]', text)
    # Do not retain freeform medical or email content in unresolved questions.
    if re.search(r'illness|medical|sick|diagnos|hospital', text, re.I):
        return '[academic medical request; details omitted]'
    if re.search(r'draft|write.*email', text, re.I):
        return '[academic email request; details omitted]'
    return text[:1200]

def db(dataset):
    c = sqlite3.connect(dataset_dir(dataset) / 'state.sqlite')
    c.execute('CREATE TABLE IF NOT EXISTS unresolved (id TEXT PRIMARY KEY, timestamp TEXT, question TEXT, context TEXT, intent TEXT, reason TEXT, retrieved_ids TEXT, model TEXT, mode TEXT, occurrence_count INTEGER, review_status TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS traces (id TEXT PRIMARY KEY, timestamp TEXT, payload TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, context_key TEXT, course TEXT, topic TEXT, evidence_ids TEXT, timestamp TEXT)')
    return c

def log_unanswered(dataset, request_id, question, context, intent, reason, ids, model, mode):
    with db(dataset) as c:
        q = redact(question)
        row = c.execute('SELECT id FROM unresolved WHERE question=? AND reason=? AND review_status=?',(q,reason,'open')).fetchone()
        if row:
            c.execute('UPDATE unresolved SET occurrence_count=occurrence_count+1 WHERE id=?',row)
            return row[0]
        c.execute('INSERT INTO unresolved VALUES (?,?,?,?,?,?,?,?,?,?,?)',(request_id,datetime.now(timezone.utc).isoformat(),q,json.dumps(context),intent,reason,json.dumps(ids),model,mode,1,'open'))
    return request_id

def save_trace(dataset, request_id, payload):
    with db(dataset) as c:
        c.execute('INSERT OR REPLACE INTO traces VALUES (?,?,?)',(request_id,datetime.now(timezone.utc).isoformat(),json.dumps(payload)))

def load_session(dataset,session_id,context_key):
    with db(dataset) as c:
        row=c.execute('SELECT course,topic,evidence_ids FROM sessions WHERE id=? AND context_key=?',(session_id,context_key)).fetchone()
    return {'course':row[0],'topic':row[1],'evidence_ids':json.loads(row[2])} if row else {}

def save_session(dataset,session_id,context_key,course,topic,evidence_ids):
    with db(dataset) as c:
        c.execute('INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?)',(session_id,context_key,course,topic,json.dumps(evidence_ids),datetime.now(timezone.utc).isoformat()))
