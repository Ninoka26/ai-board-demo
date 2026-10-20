"""Isolated authenticated full v1.3 bridge, localhost only. Never deploy publicly."""
import json,pathlib,sqlite3,secrets,hashlib,hmac,time,os
from http.server import ThreadingHTTPServer
from http.cookies import SimpleCookie
import server as original
from multiuser_full_store import Store
ROOT=pathlib.Path(__file__).resolve().parent
store=Store(ROOT/'full_board_auth_test.sqlite3')
DB=ROOT/'full_board_auth_users.sqlite3'
def connect():return sqlite3.connect(DB,timeout=10)
with connect() as db:
 db.execute('CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT UNIQUE, salt BLOB, password_hash BLOB)')
 db.execute('CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, uid INTEGER, expires INTEGER)')
 db.commit()
def password_hash(password,salt):return hashlib.pbkdf2_hmac('sha256',password.encode(),salt,240000)
def register(name,password):
 if not isinstance(name,str) or not (3<=len(name)<=40) or not isinstance(password,str) or len(password)!=4 or not password.isascii() or not password.isdecimal():raise ValueError('Invalid credentials')
 salt=os.urandom(16)
 with connect() as db:
  uid=db.execute('INSERT INTO users(name,salt,password_hash) VALUES(?,?,?)',(name,salt,password_hash(password,salt))).lastrowid
  db.commit()
 store.create(uid,'main')
 return uid
class Handler(original.Handler):
 def reply(self,status,obj,cookie=None):
  raw=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status)
  self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
  if cookie:self.send_header('Set-Cookie',cookie)
  self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def uid(self):
  try:
   c=SimpleCookie();c.load(self.headers.get('Cookie',''));token=c['session'].value
   with connect() as db:row=db.execute('SELECT uid FROM sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(token.encode()).hexdigest(),time.time())).fetchone()
   return row[0] if row else None
  except:return None
 def do_GET(self):
  if self.path=='/':
   raw=(ROOT/'board.html').read_text(encoding='utf-8').replace('</body>','<script src="/full_board_bridge.js"></script></body>').encode()
   self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
  if self.path=='/full_board_bridge.js':
   raw=(ROOT/'full_board_bridge.js').read_bytes();self.send_response(200);self.send_header('Content-Type','application/javascript');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
  uid=self.uid()
  if not uid:return self.reply(401,{'error':'Требуется вход'})
  if self.path=='/api/full/boards':
   with connect() as db:pass
   with store.connect() as db:ids=[x[0] for x in db.execute('SELECT bid FROM full_boards WHERE uid=?',(uid,))]
   return self.reply(200,{'boards':[{'id':bid,**store.read(uid,bid)} for bid in ids]})
  return self.reply(404,{'error':'Не найдено'})
 def do_POST(self):
  if self.headers.get('Origin') not in (None,'http://127.0.0.1:8786','http://localhost:8786'):return self.reply(403,{'error':'Недопустимый источник'})
  if self.path in ('/api/full/login','/api/full/register'):
   try:
    length=int(self.headers.get('Content-Length','0'))
    if length<2 or length>3000:return self.reply(400,{'error':'Invalid request'})
    data=json.loads(self.rfile.read(length));name=data.get('name','');password=data.get('password','')
    if not isinstance(name,str) or not isinstance(password,str):return self.reply(400,{'error':'Неверный формат'})
    if self.path=='/api/full/register':
     try:uid=register(name,password)
     except sqlite3.IntegrityError:return self.reply(409,{'error':'Логин уже занят'})
     except ValueError:return self.reply(400,{'error':'Логин от 3 до 40 символов, ПИН — ровно 4 цифры'})
    else:
     with connect() as db:row=db.execute('SELECT id,salt,password_hash FROM users WHERE name=?',(name,)).fetchone()
     if not row or not hmac.compare_digest(password_hash(password,row[1]),row[2]):return self.reply(401,{'error':'Неверный логин или пароль'})
     uid=row[0]
    token=secrets.token_urlsafe(32)
    with connect() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),uid,int(time.time())+86400));db.commit()
    return self.reply(200,{'ok':True},'session='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=86400')
   except (ValueError,TypeError,AttributeError):return self.reply(400,{'error':'Invalid request'})
  uid=self.uid()
  if not uid:return self.reply(401,{'error':'Требуется вход'})
  if self.path=='/api/full/logout':
   c=SimpleCookie();c.load(self.headers.get('Cookie',''))
   if 'session' in c:
    token_hash=hashlib.sha256(c['session'].value.encode()).hexdigest()
    with connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=? AND uid=?',(token_hash,uid));db.commit()
   return self.reply(200,{'ok':True},'session=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0')
  if self.path in ('/api/transcribe','/api/analyze'):
   return super().do_POST()
  if self.path=='/api/full/create':
   try:
    length=int(self.headers.get('Content-Length','0'))
    if length<2 or length>500:return self.reply(400,{'error':'Invalid request'})
    data=json.loads(self.rfile.read(length));bid=data.get('id');name=data.get('name')
    if not isinstance(bid,str) or len(bid)!=36 or not isinstance(name,str) or not (1<=len(name.strip())<=70):return self.reply(400,{'error':'Invalid name or ID'})
    store.create(uid,bid)
    return self.reply(201,{'revision':store.read(uid,bid)['revision']})
   except sqlite3.IntegrityError:return self.reply(409,{'error':'Already exists'})
   except (ValueError,TypeError,AttributeError):return self.reply(400,{'error':'Invalid data'})
  if self.path=='/api/full/save':
   try:
    length=int(self.headers.get('Content-Length','0'))
    if length<2 or length>5500000:return self.reply(413,{'error':'Too large'})
    data=json.loads(self.rfile.read(length));bid=str(data.get('id',''))
    code=store.save(uid,bid,data['data'],data.get('revision'))
    if code!=200:return self.reply(code,{'error':'Conflict or invalid revision'})
    return self.reply(200,{'revision':store.read(uid,bid)['revision']})
   except (ValueError,KeyError,TypeError) as e:return self.reply(400,{'error':str(e)[:120]})
  return self.reply(404,{'error':'Not found'})
if __name__=='__main__':
 import sys
 if len(sys.argv)==3 and sys.argv[1]=='add-user':
  import getpass
  print('CREATED',register(sys.argv[2],getpass.getpass('Password: ')))
 else:
  print('AUTH TEST http://127.0.0.1:8786',flush=True)
  ThreadingHTTPServer(('127.0.0.1',8786),Handler).serve_forever()