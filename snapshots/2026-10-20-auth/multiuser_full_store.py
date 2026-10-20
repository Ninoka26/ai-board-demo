"""Isolated full-v1.3 multiuser storage prototype. No real user DB access.
Optimistic revisions cover notes AND connections. No legacy data migration here.
"""
import hashlib,hmac,json,sqlite3,pathlib

def canonical(data):return json.dumps(data,ensure_ascii=False,separators=(',',':'))
def revision(data):return hashlib.sha256(canonical(data).encode('utf-8')).hexdigest()
def validate(data):
 if not isinstance(data,dict) or set(data)!={'notes','connections'}:raise ValueError('Expected notes and connections')
 notes=data['notes'];links=data['connections']
 if not isinstance(notes,list) or len(notes)>1000 or not isinstance(links,list) or len(links)>3000:raise ValueError('Invalid collections')
 ids=set()
 for n in notes:
  if not isinstance(n,dict) or not isinstance(n.get('id'),str) or not isinstance(n.get('title',''),str) or not isinstance(n.get('text',''),str):raise ValueError('Invalid note')
  if n['id'] in ids:raise ValueError('Duplicate ID')
  ids.add(n['id'])
  if len(n.get('text',''))>100000:raise ValueError('Note too long')
  a=n.get('attachment')
  if a is not None and (not isinstance(a,dict) or not isinstance(a.get('data'),str) or not isinstance(a.get('type'),str) or len(a['data'])>3000000):raise ValueError('Invalid attachment')
 for link in links:
  if not isinstance(link,list) or len(link)!=2 or not all(isinstance(x,str) and x in ids for x in link):raise ValueError('Invalid connection')
 if len(canonical(data).encode('utf-8'))>5000000:raise ValueError('Board too large')
 return data

class Store:
 def __init__(self,path):
  self.path=pathlib.Path(path)
  db=self.connect()
  try:
   db.execute('CREATE TABLE IF NOT EXISTS full_boards(uid INTEGER NOT NULL,bid TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(uid,bid))');db.commit()
  finally:db.close()
 def connect(self):return sqlite3.connect(self.path,timeout=10)
 def create(self,uid,bid,payload=None):
  data=validate(payload if payload is not None else {'notes':[],'connections':[]})
  db=self.connect()
  try:
   db.execute('INSERT INTO full_boards VALUES(?,?,?)',(uid,bid,canonical(data)));db.commit()
  finally:db.close()
 def read(self,uid,bid):
  db=self.connect()
  try:row=db.execute('SELECT payload FROM full_boards WHERE uid=? AND bid=?',(uid,bid)).fetchone()
  finally:db.close()
  if row is None:return None
  data=json.loads(row[0]);return {'data':data,'revision':revision(data)}
 def save(self,uid,bid,data,expected_revision):
  validate(data)
  if not isinstance(expected_revision,str) or len(expected_revision)!=64:return 428
  db=self.connect()
  try:
   db.execute('BEGIN IMMEDIATE')
   row=db.execute('SELECT payload FROM full_boards WHERE uid=? AND bid=?',(uid,bid)).fetchone()
   if row is None:return 404
   old=json.loads(row[0])
   if not hmac.compare_digest(revision(old),expected_revision):return 409
   db.execute('UPDATE full_boards SET payload=? WHERE uid=? AND bid=?',(canonical(data),uid,bid));db.commit();return 200
  finally:db.close()