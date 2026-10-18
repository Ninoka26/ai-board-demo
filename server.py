import base64, ctypes, ctypes.wintypes, json, os, pathlib, secrets, threading, time, urllib.request, urllib.error, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE=pathlib.Path(__file__).resolve().parent
KEY=pathlib.Path(os.environ['LOCALAPPDATA'])/'AI_Board'/'gigachat_key.dpapi'
TOKEN=None
EXPIRY=0
LOCK=threading.Lock()
class BLOB(ctypes.Structure):
    _fields_=[('cbData',ctypes.wintypes.DWORD),('pbData',ctypes.POINTER(ctypes.c_byte))]
def unprotect(data):
    buf=ctypes.create_string_buffer(data)
    src=BLOB(len(data),ctypes.cast(buf,ctypes.POINTER(ctypes.c_byte)))
    dst=BLOB()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src),None,None,None,None,0,ctypes.byref(dst)):
        raise OSError('Windows could not decrypt the saved key')
    try: return ctypes.string_at(dst.pbData,dst.cbData).decode('utf-8')
    finally: ctypes.windll.kernel32.LocalFree(dst.pbData)
def post(url,headers,payload):
    request=urllib.request.Request(url,data=payload,headers=headers,method='POST')
    with urllib.request.urlopen(request,timeout=35) as response:
        return json.load(response)
def get_token():
    global TOKEN,EXPIRY
    with LOCK:
        if TOKEN and time.time()<EXPIRY-90: return TOKEN
        key=unprotect(KEY.read_bytes())
        body=b'scope=GIGACHAT_API_PERS'
        response=post('https://ngw.devices.sberbank.ru:9443/api/v2/oauth',{'Authorization':'Basic '+key,'RqUID':str(__import__('uuid').uuid4()),'Content-Type':'application/x-www-form-urlencoded'},body)
        TOKEN=response['access_token']
        EXPIRY=time.time()+1700
        return TOKEN
VOICE_LOCK=threading.Lock()
VOICE_MODEL=None
def transcribe_audio(raw):
    global VOICE_MODEL
    import tempfile, subprocess, shutil as sh
    from faster_whisper import WhisperModel
    with VOICE_LOCK:
        if VOICE_MODEL is None:
            VOICE_MODEL=WhisperModel('small',device='cpu',compute_type='int8',local_files_only=True)
        with tempfile.TemporaryDirectory() as folder:
            src=pathlib.Path(folder)/'audio.webm'
            wav=pathlib.Path(folder)/'audio.wav'
            src.write_bytes(raw)
            subprocess.run([sh.which('ffmpeg') or 'ffmpeg','-nostdin','-loglevel','error','-y','-i',str(src),'-ar','16000','-ac','1',str(wav)],check=True,timeout=30,capture_output=True)
            segments,_=VOICE_MODEL.transcribe(str(wav),language='ru',beam_size=3,vad_filter=True)
            return ' '.join(x.text.strip() for x in segments).strip()
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def reply(self,status,obj):
        raw=json.dumps(obj,ensure_ascii=False).encode('utf-8')
        self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path!='/': return self.reply(404,{'error':'Not found'})
        raw=(BASE/'board.html').read_bytes()
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        if self.path=='/api/transcribe':
            try:
                length=int(self.headers.get('Content-Length','0'))
                if length<100 or length>12000000: return self.reply(413,{'error':'Audio size must be under 12 MB'})
                result=transcribe_audio(self.rfile.read(length))
                return self.reply(200,{'text':result})
            except Exception as e:
                return self.reply(502,{'error':'Offline recognition: '+type(e).__name__})
        if self.path!='/api/analyze': return self.reply(404,{'error':'Not found'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if length<2 or length>80000: return self.reply(413,{'error':'Too much text'})
            data=json.loads(self.rfile.read(length))
            notes=data.get('notes',[])
            if not isinstance(notes,list) or not notes or len(notes)>40: return self.reply(400,{'error':'Select 1 to 40 notes'})
            lines=[]
            for n in notes:
                title=str(n.get('title',''))[:150]
                body=str(n.get('text',''))[:1800]
                lines.append(title+'\n'+body)
            prompt="\u0422\u044b \u043f\u043e\u043c\u043e\u0449\u043d\u0438\u043a \u043f\u043e \u0430\u043d\u0430\u043b\u0438\u0437\u0443 \u0437\u0430\u043c\u0435\u0442\u043e\u043a \u043d\u0430 \u0434\u043e\u0441\u043a\u0435. \u041f\u0438\u0448\u0438 \u0442\u043e\u043b\u044c\u043a\u043e \u043d\u0430 \u0440\u0443\u0441\u0441\u043a\u043e\u043c \u044f\u0437\u044b\u043a\u0435. \u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 \u0442\u043e\u043b\u044c\u043a\u043e \u0444\u0430\u043a\u0442\u044b \u0438\u0437 \u0437\u0430\u043c\u0435\u0442\u043e\u043a. \u041d\u0435 \u0432\u044b\u0434\u0443\u043c\u044b\u0432\u0430\u0439 \u0441\u0432\u0435\u0434\u0435\u043d\u0438\u0439, \u0441\u043e\u0432\u0435\u0442\u043e\u0432 \u0438 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0438\u0445 \u0448\u0430\u0433\u043e\u0432. \u0415\u0441\u043b\u0438 \u0437\u0430\u043c\u0435\u0442\u043a\u0438 \u043d\u0430 \u0440\u0430\u0437\u043d\u044b\u0435 \u0442\u0435\u043c\u044b, \u0440\u0430\u0437\u0434\u0435\u043b\u044f\u0439 \u0442\u0435\u043c\u044b. \u0423\u043a\u0430\u0436\u0438 \u043f\u043e\u0434\u0442\u0432\u0435\u0440\u0436\u0434\u0435\u043d\u043d\u044b\u0435 \u0441\u0432\u044f\u0437\u0438, \u0430 \u0435\u0441\u043b\u0438 \u0438\u0445 \u043d\u0435\u0442, \u043d\u0430\u043f\u0438\u0448\u0438: \u0421\u0432\u044f\u0437\u044c \u043d\u0435 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u043b\u0435\u043d\u0430. \u041d\u0435 \u0438\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439 Markdown, \u0441\u0438\u043c\u0432\u043e\u043b\u044b \u0440\u0435\u0448\u0435\u0442\u043a\u0438 \u0438 \u0437\u0432\u0435\u0437\u0434\u043e\u0447\u043a\u0438. \u0417\u0430\u043c\u0435\u0442\u043a\u0438:"+'\n\n---\n\n'.join(lines)
            payload=json.dumps({'model':'GigaChat','messages':[{'role':'user','content':prompt}],'max_tokens':700,'temperature':0.3},ensure_ascii=False).encode('utf-8')
            response=post('https://gigachat.devices.sberbank.ru/api/v1/chat/completions',{'Authorization':'Bearer '+get_token(),'Content-Type':'application/json'},payload)
            result=response['choices'][0]['message']['content']
            import re
            result=re.sub(r'(?m)^\s{0,3}#{1,6}\s*','',result)
            result=re.sub(r'\*\*(.*?)\*\*',r'\1',result)
            result=re.sub(r'(?m)^\s*---+\s*$','',result)
            return self.reply(200,{'text':result})
        except urllib.error.HTTPError as e: return self.reply(502,{'error':'GigaChat HTTP '+str(e.code)})
        except Exception as e: return self.reply(502,{'error':'Connection error: '+type(e).__name__})
def main():
    server=ThreadingHTTPServer(('127.0.0.1',8765),Handler)
    print('AI_BOARD_READY http://127.0.0.1:8765',flush=True)
    webbrowser.open('http://127.0.0.1:8765')
    server.serve_forever()
if __name__=='__main__': main()