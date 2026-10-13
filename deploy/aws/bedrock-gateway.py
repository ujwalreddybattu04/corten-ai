"""Host-only regional Bedrock gateway; peer credentials and a durable spend guard.

No app AWS credentials, network listener, model-created tool calls, or prompt logs.
Price ceilings exceed Sydney standard Nova rates verified 2026-10-10:
https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonBedrock/current/ap-southeast-2/index.json
"""
import datetime, json, os, socket, socketserver, sqlite3, struct, subprocess, threading, uuid
from http.server import BaseHTTPRequestHandler
from pathlib import Path

REGION="ap-southeast-2"
# Nanodollars per token, padded above the verified standard on-demand prices.
MODELS={"amazon.nova-pro-v1:0":(1000,4000),"amazon.nova-lite-v1:0":(80,320)}
MAX_BYTES=128*1024


class BudgetExceeded(RuntimeError):pass
class DailyBudgetExceeded(RuntimeError):pass


class Ledger:
    def __init__(self,path,limit=25_000_000_000):
        self.path=str(path);self.limit=limit
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS requests(id TEXT PRIMARY KEY, month TEXT NOT NULL, day TEXT NOT NULL, charge INTEGER NOT NULL CHECK(charge>=0), settled INTEGER NOT NULL DEFAULT 0)")
    def connect(self):return sqlite3.connect(self.path,timeout=10)
    def reserve(self,amount,month=None):
        if not isinstance(amount,int) or not 0<amount<=self.limit:raise ValueError("Invalid reservation")
        month=month or datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m')
        day=datetime.datetime.now(datetime.timezone.utc).date().isoformat()
        identifier=uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            used=db.execute("SELECT COALESCE(SUM(charge),0) FROM requests WHERE month=?",(month,)).fetchone()[0]
            # Keep a small allowance for the separately measured pre-deployment evaluations.
            if used+amount+50_000_000>self.limit:raise BudgetExceeded("Monthly Pharma inference budget reached")
            if db.execute("SELECT count(*) FROM requests WHERE day=?",(day,)).fetchone()[0]>=100:raise DailyBudgetExceeded("Daily Pharma generation cap reached")
            db.execute("INSERT INTO requests(id,month,day,charge) VALUES(?,?,?,?)",(identifier,month,day,amount))
        return identifier
    def settle(self,identifier,actual):
        if not isinstance(actual,int) or actual<0:raise ValueError("Invalid measured charge")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row=db.execute("SELECT charge,settled FROM requests WHERE id=?",(identifier,)).fetchone()
            if not row or row[1]:return
            if actual>row[0]:raise ValueError("Measured charge exceeds its reservation")
            db.execute("UPDATE requests SET charge=?,settled=1 WHERE id=?",(actual,identifier))


def validated_request(value):
    if not isinstance(value,dict) or set(value)-{"modelId","system","messages","inferenceConfig"}:raise ValueError("Unsupported request fields")
    model=value.get("modelId")
    if model not in MODELS:raise ValueError("Unsupported regional model")
    config=value.get("inferenceConfig") or {}
    tokens=config.get("maxTokens")
    if type(tokens) is not int or not 1<=tokens<=1536:raise ValueError("Invalid output limit")
    system=value.get("system",[]);messages=value.get("messages")
    if not isinstance(system,list) or len(system)>4 or not isinstance(messages,list) or not 1<=len(messages)<=80:raise ValueError("Invalid messages")
    blocks=[*system]
    for message in messages:
        if not isinstance(message,dict) or message.get("role") not in ("user","assistant") or not isinstance(message.get("content"),list):raise ValueError("Invalid message")
        if not message["content"] or len(message["content"])>4:raise ValueError("Invalid content blocks")
        blocks.extend(message["content"])
    if messages[0]["role"]!="user" or messages[-1]["role"]!="user":raise ValueError("Conversation must begin and end with a user turn")
    for block in blocks:
        if not isinstance(block,dict) or set(block)!={"text"} or not isinstance(block["text"],str) or not block["text"].strip():raise ValueError("Only text content is allowed")
    if len(json.dumps(value,ensure_ascii=False).encode())>MAX_BYTES:raise ValueError("Prompt exceeds limit")
    return {"modelId":model,"system":system,"messages":messages,"inferenceConfig":{"maxTokens":tokens,"temperature":0.1}}


def aws(operation,body,timeout):
    # An anonymous RAM file supports CLI file loading without
    # putting prompts in shell syntax, process arguments or persistent files.
    descriptor=os.memfd_create("corten-bedrock-request",flags=os.MFD_CLOEXEC)
    try:
        with os.fdopen(os.dup(descriptor),"wb") as stream:
            stream.write(json.dumps(body,ensure_ascii=False).encode("utf-8"))
        os.lseek(descriptor,0,os.SEEK_SET)
        completed=subprocess.run(["aws","bedrock-runtime",operation,"--region",REGION,"--cli-input-json",f"file:///proc/self/fd/{descriptor}",
            "--cli-connect-timeout","5","--cli-read-timeout",str(timeout),"--output","json"],
            pass_fds=(descriptor,),capture_output=True,text=True,timeout=timeout+10,
            env={**os.environ,"AWS_MAX_ATTEMPTS":"1","AWS_RETRY_MODE":"standard","AWS_PAGER":"","AWS_CLI_FILE_ENCODING":"UTF-8"})
    finally:os.close(descriptor)
    if completed.returncode:raise RuntimeError("Bedrock operation unavailable")
    value=json.loads(completed.stdout)
    if not isinstance(value,dict):raise ValueError("Invalid provider response")
    return value


def complete(request,ledger):
    request=validated_request(request);model=request['modelId'];input_rate,output_rate=MODELS[model]
    count_body={"modelId":model,"input":{"converse":{"system":request['system'],"messages":request['messages']}}}
    try:
        counted=aws('count-tokens',count_body,8)['inputTokens']
        if type(counted) is not int or not 0<counted<200000:raise ValueError("Invalid token count")
    except (RuntimeError,ValueError,subprocess.TimeoutExpired):
        # Conservative UTF-8 byte bound plus framing allowance if CountTokens is unsupported.
        counted=len(json.dumps(count_body,ensure_ascii=False).encode())+1024
    reservation=ledger.reserve(counted*input_rate+request['inferenceConfig']['maxTokens']*output_rate)
    # Failed/uncertain invocations retain the reservation: never refund an unknown bill.
    result=aws('converse',request,85)
    usage=result.get('usage') or {}
    incoming,outgoing=usage.get('inputTokens'),usage.get('outputTokens')
    if type(incoming) is not int or type(outgoing) is not int or incoming<0 or outgoing<0:raise ValueError("Invalid usage report")
    ledger.settle(reservation,incoming*input_rate+outgoing*output_rate)
    if result.get('stopReason')!='end_turn':raise ValueError("Incomplete or refused answer")
    text=''.join(block.get('text','') for block in result.get('output',{}).get('message',{}).get('content',[]) if isinstance(block,dict))
    if not text.strip() or len(text)>16000:raise ValueError("Invalid answer size")
    return {'text':text,'model':model,'usage':{'inputTokens':incoming,'outputTokens':outgoing},'stop_reason':'end_turn'}


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def reply(self,status,value):
        body=json.dumps(value).encode();self.send_response(status)
        self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
    def do_POST(self):
        self.connection.settimeout(10)
        _,uid,_=struct.unpack('3i',self.connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if uid not in (0,10001) or self.path!='/complete':return self.reply(403,{'error':'not_allowed'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=MAX_BYTES:return self.reply(413,{'error':'prompt_too_large'})
            request=json.loads(self.rfile.read(length))
            if not self.server.slots.acquire(blocking=False):return self.reply(429,{'error':'busy'})
            try:value=complete(request,self.server.ledger)
            finally:self.server.slots.release()
            self.reply(200,value)
        except BudgetExceeded:self.reply(429,{'error':'monthly_budget_reached'})
        except DailyBudgetExceeded:self.reply(429,{'error':'daily_budget_reached'})
        except ValueError:self.reply(422,{'error':'invalid_or_incomplete_answer'})
        except (RuntimeError,subprocess.TimeoutExpired):self.reply(503,{'error':'model_unavailable'})


if hasattr(socketserver,"UnixStreamServer"):
    class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):
        daemon_threads=True
        def handle_error(self,*args):print('Bedrock gateway request failed',flush=True)


def main():
    if not hasattr(socket,"SO_PEERCRED") or not hasattr(socketserver,"UnixStreamServer"):
        raise RuntimeError("This protected gateway requires Linux peer credentials")
    os.umask(0o077)
    socket_path=Path('/run/corten-bedrock/gateway.sock');socket_path.parent.mkdir(parents=True,exist_ok=True)
    if socket_path.exists():socket_path.unlink()
    with Server(str(socket_path),Handler) as server:
        os.chown(socket_path,0,10001);socket_path.chmod(0o660)
        private=Path('/opt/corten/private/bedrock');private.mkdir(mode=0o700,exist_ok=True)
        server.ledger=Ledger(private/'usage.sqlite3');server.slots=threading.BoundedSemaphore(2)
        server.serve_forever()

if __name__=='__main__':main()
