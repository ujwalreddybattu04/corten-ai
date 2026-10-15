"""Bounded public document reading. No credentials, arbitrary hosts, JavaScript or XML execution."""
import asyncio,hashlib,ipaddress,json,re,socket,sys
from datetime import datetime,timezone
from html.parser import HTMLParser
from urllib.parse import urljoin,urlsplit
import httpx
from src.services.pharma_research_tools import DOMAINS

HOSTS=tuple(sorted({host for hosts in DOMAINS.values() for host in hosts}|{'clinicaltrials.gov','ncbi.nlm.nih.gov','europepmc.org','ebi.ac.uk','dailymed.nlm.nih.gov'}))
MAX_BYTES=8_000_000
MAX_TEXT=120_000
PDF_SLOTS=asyncio.Semaphore(1)

def document_url(value):
    try:
        url=urlsplit(value)
        return (len(value)<=2048 and url.scheme=='https' and not url.username and not url.password and url.port in (None,443)
            and url.hostname and any(url.hostname==host or url.hostname.endswith('.'+host) for host in HOSTS))
    except (ValueError,TypeError):return False

async def public_host(url):
    if not document_url(url):raise ValueError('Document host is not an approved public source')
    host=urlsplit(url).hostname
    addresses=await asyncio.get_running_loop().getaddrinfo(host,443,type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('Non-public document address')

class ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[];self.links=[];self.skip=0;self.size=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style','noscript','svg','nav','footer'}:self.skip+=1
        if not self.skip and tag in {'p','div','section','h1','h2','h3','h4','li','tr','br'}:self.parts.append('\n')
        if tag=='a' and not self.skip:
            values=dict(attrs)
            if values.get('href'):self.links.append(values['href'])
    def handle_endtag(self,tag):
        if tag in {'script','style','noscript','svg','nav','footer'}:self.skip=max(0,self.skip-1)
        if not self.skip and tag in {'p','div','section','h1','h2','h3','h4','li','tr'}:self.parts.append('\n')
    def handle_data(self,data):
        if not self.skip and self.size<MAX_TEXT*2:
            self.parts.append(data);self.size+=len(data)
    def text(self):return '\n'.join(re.sub(r'\s+',' ',p).strip() for p in ''.join(self.parts).splitlines() if p.strip())

PDF_PROGRAM=r'''
import io,json,sys
try:
 import resource
 resource.setrlimit(resource.RLIMIT_CPU,(8,8))
 resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
except ImportError:pass
from pypdf import PdfReader
reader=PdfReader(io.BytesIO(sys.stdin.buffer.read(8000001)),strict=False)
if reader.is_encrypted:raise ValueError('Encrypted PDF')
pages=[];size=0;total=len(reader.pages)
for i,page in enumerate(reader.pages):
 if i>=100 or size>=120000:break
 text=page.extract_text() or '';pages.append(text[:120000-size]);size+=len(text)
print(json.dumps({'text':'\n'.join(pages),'pages_read':len(pages),'total_pages':total,'truncated':len(pages)<total or size>120000}))
'''

async def pdf_text(content):
    async with PDF_SLOTS:return await _pdf_text(content)

async def _pdf_text(content):
    process=await asyncio.create_subprocess_exec(sys.executable,'-I','-c',PDF_PROGRAM,
        stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
    try:
        stdout,_=await asyncio.wait_for(process.communicate(content),15)
        if process.returncode or len(stdout)>900_000:raise ValueError('PDF text could not be safely extracted')
        return json.loads(stdout)
    finally:
        if process.returncode is None:process.kill();await process.wait()

async def read_document(url,*,client=None,resolve=public_host):
    original=url;owned=client is None
    if owned:client=httpx.AsyncClient(timeout=httpx.Timeout(15,connect=5),follow_redirects=False,trust_env=False,
        headers={'User-Agent':'CortenResearch/1.0 (public pharmaceutical source review)','Accept':'text/html,application/pdf,text/plain'})
    try:
        async with asyncio.timeout(22):
            for redirect in range(4):
                await resolve(url)
                async with client.stream('GET',url) as response:
                    if response.is_redirect:
                        if redirect==3:raise ValueError('Document redirect limit')
                        url=urljoin(url,response.headers.get('location',''));continue
                    response.raise_for_status()
                    mime=response.headers.get('content-type','').split(';')[0].lower()
                    if mime not in {'text/html','application/xhtml+xml','application/pdf','text/plain'}:raise ValueError('Unsupported document format')
                    length=response.headers.get('content-length','')
                    if length.isdigit() and int(length)>MAX_BYTES:raise ValueError('Document exceeds download limit')
                    content=bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content)>MAX_BYTES:raise ValueError('Document exceeds download limit')
                links=[];metadata={}
                if mime=='application/pdf' or content.startswith(b'%PDF'):
                    parsed=await pdf_text(bytes(content));text=re.sub(r'\s+',' ',parsed.pop('text')).strip();metadata=parsed
                else:
                    body=bytes(content).decode('utf-8',errors='replace')
                    if 'html' in mime:
                        parser=ReadableHTML();parser.feed(body);text=parser.text()
                        links=list(dict.fromkeys(urljoin(url,link) for link in parser.links if document_url(urljoin(url,link))))[:150]
                        metadata['truncated']=parser.size>=MAX_TEXT*2 or len(text)>MAX_TEXT
                    else:text=body;metadata['truncated']=len(text)>MAX_TEXT
                text='\n'.join(re.sub(r'[\t \r]+',' ',line).strip() for line in text.splitlines() if line.strip())[:MAX_TEXT]
                if len(text.strip())<50:raise ValueError('No usable document text')
                return {'url':url,'requested_url':original,'text':text,'links':links,'sha256':hashlib.sha256(content).hexdigest(),
                    'retrieved_at':datetime.now(timezone.utc).isoformat(),'read_method':'pdf_text' if mime=='application/pdf' else 'document_text',**metadata}
            raise ValueError('Document unavailable')
    finally:
        if owned:await client.aclose()

def relevant_quotes(text,query,*,limit=4,word_budget=180):
    """Return exact passages from the normalized document, never generated quotations."""
    terms={v.casefold() for v in re.findall(r'[\w-]{4,}',query)}-{'what','which','research','profile','about','please','compare','current'}
    blocks=[]
    for line in text.splitlines():
        if len(line)<35 or re.search(r'cookies|all rights reserved|forward.looking statements|subscribe to|privacy policy|legal disclaimer',line,re.I):continue
        for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z])',line):
            if 35<=len(sentence)<=900:
                score=sum(term in sentence.casefold() for term in terms)+bool(re.search(r'\b(?:results|approved|warning|endpoint|randomized|patent|recall)\b',sentence,re.I))
                if score:blocks.append((score,sentence))
    output=[];words=0
    for _,quote in sorted(blocks,key=lambda v:-v[0]):
        count=len(quote.split())
        if quote in output or words+count>word_budget:continue
        assert quote in text
        output.append(quote);words+=count
        if len(output)>=limit:break
    return output
