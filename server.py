import os, json, sqlite3, secrets, time, hashlib, hmac, threading, io, base64, re
from decimal import Decimal, InvalidOperation
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
import requests, qrcode
ROOT=Path(__file__).parent
DB=os.getenv('DB_PATH',str(ROOT/'swap.db'))
KEY=os.getenv('CHANGENOW_API_KEY','')
BASE='https://api.changenow.io/v2'
ADMIN=os.getenv('ADMIN_PASSWORD','')
SECRET=os.getenv('ADMIN_TOTP_SECRET','')
LIVE=os.getenv('ENABLE_SWAPS','0')=='1'
FIXED=os.getenv('ENABLE_FIXED','0')=='1'
lock=threading.Lock(); cache={}; sessions={}; limits={}
def db():
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row; return c
def init():
 with db() as c: c.executescript((ROOT/'schema.sql').read_text())
def request(path,params=None,body=None):
 r=requests.request('POST' if body is not None else 'GET',BASE+path,params=params,json=body,headers={'x-changenow-api-key':KEY},timeout=15); r.raise_for_status(); return r.json()
def cached(key,ttl,fn):
 with lock:
  if key in cache and time.time()-cache[key][0]<ttl:return cache[key][1]
  val=fn();cache[key]=(time.time(),val);return val
def assets():
 if not KEY:return []
 def get():
  data=request('/exchange/currencies',{'active':'true','flow':'standard'});return [dict(ticker=x['ticker'],network=x['network'],name=x.get('name',x['ticker']),image=x.get('image',''),buy=x.get('isAvailable',True) and x.get('isAvailableForBuy',True),sell=x.get('isAvailable',True) and x.get('isAvailableForSell',True),memo=x.get('hasExtraId',False)) for x in data if not x.get('isFiat') and x.get('ticker') and x.get('network')]
 with db() as c: disabled={r[0] for r in c.execute('select asset from disabled')}
 return [x for x in cached('assets',120,get) if x['ticker']+':'+x['network'] not in disabled]
def market():
 def get():
  r=requests.get('https://data-api.binance.vision/api/v3/ticker/price',timeout=10);r.raise_for_status();return {'prices':{x['symbol']:x['price'] for x in r.json()},'updated':int(time.time())}
 return cached('market',30,get)
def quote(p):
 a={x['ticker']+':'+x['network']:x for x in assets()}; f=a.get(p.get('from'));t=a.get(p.get('to'))
 if not f or not t or f==t or not f['sell'] or not t['buy']:raise ValueError('Select an available exchange pair.')
 amount=Decimal(str(p.get('amount','0')))
 if not amount.is_finite() or amount<=0 or amount>Decimal('1000000000000'):raise ValueError('Enter a valid positive amount.')
 flow='fixed-rate' if p.get('fixed') else 'standard'
 if flow=='fixed-rate' and not FIXED:raise ValueError('Fixed rates are not enabled.')
 args=dict(fromCurrency=f['ticker'],toCurrency=t['ticker'],fromNetwork=f['network'],toNetwork=t['network'],fromAmount=str(amount),flow=flow,type='direct')
 q=request('/exchange/estimated-amount',args)
 if not q.get('toAmount'):raise ValueError('No executable quote available.')
 return args,q

def validate(t,n,address):
 if not isinstance(address,str) or not 10<=len(address)<=250 or re.search(r'\s',address):raise ValueError('Invalid wallet address.')
 v=request('/validate/address',{'currency':t,'network':n,'address':address})
 if v.get('result') is not True:raise ValueError('Provider could not validate this wallet/network.')
def public(row):
 return json.loads(row['data'])|{'id':row['id'],'created':row['created'],'status':row['status']}
def sync(row):
 d=json.loads(row['data']); s=request('/exchange/by-id',{'id':d['providerId']}); status=s.get('status',row['status']);
 for k in ('payinHash','payoutHash','amountFrom','amountTo','updatedAt','expectedAmountTo','status'): 
  if s.get(k) is not None:d[k]=s[k]
 with db() as c:c.execute('update orders set status=?,data=?,updated=? where id=?',(status,json.dumps(d),int(time.time()),row['id']))
 return d|{'id':row['id'],'status':status,'created':row['created']}
def worker():
 while True:
  time.sleep(25)
  if not KEY:continue
  with db() as c: rows=c.execute("select * from orders where status not in ('finished','refunded','failed','expired') order by updated limit 50").fetchall()
  for row in rows:
   try:sync(row)
   except Exception:pass

def totp(code):
 if not SECRET:return False
 try:
  key=base64.b32decode(SECRET.upper()+'='*((-len(SECRET))%8)); now=int(time.time())//30
  for t in (now-1,now,now+1):
   d=hmac.new(key,t.to_bytes(8,'big'),hashlib.sha1).digest();i=d[-1]&15;v=(int.from_bytes(d[i:i+4],'big')&0x7fffffff)%1000000
   if hmac.compare_digest(str(v).zfill(6),str(code)):return True
 except Exception:pass
 return False
class H(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def sendj(self,obj,status=200,cookie=None):
  b=json.dumps(obj).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');
  if cookie:self.send_header('Set-Cookie',cookie)
  self.end_headers();self.wfile.write(b)
 def auth(self):
  token=next((x.strip()[4:] for x in self.headers.get('Cookie','').split(';') if x.strip().startswith('sid=')),'');return token if sessions.get(token,0)>time.time() else None
 def do_GET(self):self.handle_req(False)
 def do_POST(self):self.handle_req(True)
 def handle_req(self,post):
  u=urlparse(self.path);path=u.path
  try:
   if not path.startswith('/api/'):
    if post:return self.sendj({'error':'Not found'},404)
    f=ROOT/'public'/({'/style.css':'style.css','/app.js':'app.js'}.get(path,'index.html'));self.send_response(200);self.send_header('Content-Type',{' .css':'text/css','.css':'text/css','.js':'application/javascript','.html':'text/html; charset=utf-8'}[f.suffix]);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(f.read_bytes());return
   ip=self.client_address[0];now=int(time.time())//60;k=(ip,now,path=='/api/login');
   with lock:
    if len(limits)>10000:limits.clear()
    limits[k]=limits.get(k,0)+1
    if limits[k]>(5 if path=='/api/login' else 100):return self.sendj({'error':'Rate limit exceeded'},429)
   p={}
   if post:
    if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.sendj({'error':'JSON required'},415)
    origin=self.headers.get('Origin'); expected=os.getenv('PUBLIC_ORIGIN','http://localhost:8000')
    if origin and origin!=expected:return self.sendj({'error':'Origin rejected'},403)
    n=int(self.headers.get('Content-Length','0'))
    if not 0<n<=20000:return self.sendj({'error':'Invalid body'},400)
    p=json.loads(self.rfile.read(n))
   if path=='/api/config':return self.sendj({'connected':bool(KEY),'live':LIVE and bool(KEY),'fixed':FIXED})
   if path=='/api/assets':return self.sendj(assets())
   if path=='/api/market':return self.sendj(market())
   if path=='/api/quote' and post:
    args,q=quote(p);return self.sendj({'amount':q['toAmount'],'rateId':q.get('rateId'),'validUntil':q.get('validUntil'),'flow':args['flow']})
   if path=='/api/create' and post:
    if not LIVE or not KEY:raise ValueError('Live swaps are disabled until provider setup and approval.')
    args,q=quote(p);address=p.get('address','');validate(args['toCurrency'],args['toNetwork'],address)
    refund=p.get('refund','');
    if refund:validate(args['fromCurrency'],args['fromNetwork'],refund)
    if p.get('accepted') is not True:raise ValueError('Confirm exchange terms.')
    nonce=p.get('nonce','');
    if not re.fullmatch('[a-f0-9-]{36}',nonce):raise ValueError('Invalid request ID.')
    oid=secrets.token_urlsafe(24)
    with db() as c:
     try:c.execute('insert into attempts values(?,?,?)',(nonce,oid,int(time.time())))
     except sqlite3.IntegrityError:raise ValueError('Request already submitted; contact support if no order appeared.')
    body=args|{'address':address,'refundAddress':refund,'extraId':str(p.get('memo','')),'refundExtraId':str(p.get('refundMemo','')),'rateId':q.get('rateId') or '','userId':oid}
    v=request('/exchange',body=body)
    if not v.get('id') or not v.get('payinAddress'):raise ValueError('Provider did not return deposit instructions. Do not send funds.')
    d={k:v.get(k) for k in ('payinAddress','payinExtraId','fromAmount','toAmount','validUntil','payinHash','payoutHash')};d.update(args);d.update(providerId=v['id'],address=address,refund=refund,expectedAmountTo=v.get('toAmount') or q['toAmount'],fromAmount=v.get('fromAmount') or args['fromAmount'])
    buf=io.BytesIO();qrcode.make(d['payinAddress']).save(buf,format='PNG');d['qr']='data:image/png;base64,'+base64.b64encode(buf.getvalue()).decode()
    with db() as c:c.execute('insert into orders values(?,?,?,?,?)',(oid,v.get('status','new'),json.dumps(d),int(time.time()),int(time.time())))
    return self.sendj({'id':oid})
   if path=='/api/order':
    oid=parse_qs(u.query).get('id',[''])[0]
    with db() as c: row=c.execute('select * from orders where id=?',(oid,)).fetchone()
    if not row:return self.sendj({'error':'Order not found'},404)
    return self.sendj(public(row))
   if path=='/api/login' and post:
    if not ADMIN or len(ADMIN)<16 or not hmac.compare_digest(str(p.get('password','')),ADMIN) or not totp(p.get('code','')):return self.sendj({'error':'Invalid credentials or admin not configured'},401)
    token=secrets.token_urlsafe(32);sessions[token]=time.time()+3600;return self.sendj({'ok':True},cookie='sid='+token+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=3600'+('; Secure' if os.getenv('PUBLIC_ORIGIN','').startswith('https:') else ''))
   if path.startswith('/api/admin'):
    if not self.auth():return self.sendj({'error':'Sign in required'},401)
    if path=='/api/admin/logout' and post:sessions.pop(self.auth(),None);return self.sendj({'ok':True},cookie='sid=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict')
    if path=='/api/admin/assets' and post:
     asset=str(p.get('asset','')); 
     with db() as c:
      if p.get('disabled'):c.execute('insert or ignore into disabled values(?)',(asset,))
      else:c.execute('delete from disabled where asset=?',(asset,))
      c.execute('insert into audit values(?,?)',(int(time.time()),'Asset setting '+asset))
     return self.sendj({'ok':True})
    with db() as c:
     rows=[public(r) for r in c.execute('select * from orders order by created desc limit 1000')];disabled=[r[0] for r in c.execute('select asset from disabled')];audit=[dict(r) for r in c.execute('select * from audit order by at desc limit 100')]
    return self.sendj({'orders':rows,'disabled':disabled,'audit':audit,'connected':bool(KEY),'live':LIVE})
   return self.sendj({'error':'Not found'},404)
  except (ValueError,InvalidOperation) as e:return self.sendj({'error':str(e)},400)
  except requests.RequestException:return self.sendj({'error':'External provider unavailable or rejected request. No payment should be made without confirmed instructions.'},503)
  except Exception:return self.sendj({'error':'Unexpected server error. Contact support before retrying any order.'},500)
if __name__=='__main__':
 init();threading.Thread(target=worker,daemon=True).start();print('NovaSwap running on http://localhost:8000');ThreadingHTTPServer((os.getenv('HOST','127.0.0.1'),int(os.getenv('PORT','8000'))),H).serve_forever()
