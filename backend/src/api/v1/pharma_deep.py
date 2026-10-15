"""Authenticated Deep research plans, durable progress and owner-scoped report exports."""
import asyncio
from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Response
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy.exc import SQLAlchemyError
from src.api.deps import get_current_user_id
from src.config.settings import settings
from src.services.pharma_deep_plan import DeepPlan,make_plan,TOPICS,CHECKLISTS
from src.services import pharma_deep_store as store,pharma_deep_exports as exports
from src.services.llm_runtime import LLMProviderError

def enabled():
    if not settings.PHARMA_INTELLIGENCE_ENABLED or not settings.PHARMA_DEEP_RESEARCH_ENABLED:raise HTTPException(404,'Deep research is not enabled.')

class DeepRoute(APIRoute):
    def get_route_handler(self):
        handler=super().get_route_handler()
        async def bounded(request):
            if request.method in ('POST','PATCH','PUT'):
                body=bytearray()
                async for part in request.stream():
                    body.extend(part)
                    if len(body)>24576:raise HTTPException(413,'Deep research requests must be no larger than 24 KB.')
                request._body=bytes(body)
            try:response=await handler(request)
            except SQLAlchemyError:raise HTTPException(503,'Research storage is temporarily unavailable. Please retry shortly.',headers={'Retry-After':'10','Cache-Control':'no-store'}) from None
            response.headers['Cache-Control']='private, no-store'
            return response
        return bounded

router=APIRouter(dependencies=[Depends(enabled)],route_class=DeepRoute)

class PlanRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    query:str=Field(min_length=5,max_length=4000)
    private:bool=False
    @field_validator('query')
    @classmethod
    def nonempty(cls,value):
        value=value.strip()
        if len(value)<5:raise ValueError('Enter a Pharma research question.')
        return value

class StartRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    plan:DeepPlan
    revision:int=Field(ge=1)
    private:bool=False

@router.get('/options')
async def options():
    return {'topics':[{'id':key,'label':value[0],'description':value[1]} for key,value in TOPICS.items()],
        'checklists':CHECKLISTS,'limits':{'rounds':3,'documents':12,'lookups':30,'reports_per_day':settings.PHARMA_DEEP_DAILY_REPORTS}}

@router.post('/plan',status_code=201)
async def prepare(request:PlanRequest,response:Response,owner:str=Depends(get_current_user_id)):
    if request.private:raise HTTPException(422,'Deep research saves reports to your account. Leave Private mode before starting.')
    response.headers['Cache-Control']='private, no-store'
    try:
        async with asyncio.timeout(140):plan=await make_plan(request.query)
        return await store.create(owner,request.query,plan.model_dump())
    except LLMProviderError as exc:raise HTTPException(503,str(exc)) from None
    except TimeoutError:raise HTTPException(504,'The plan could not be prepared in time. Please retry.') from None
    except ValueError:raise HTTPException(422,'Please use specific medicine, company or study names in the question.') from None
    except SQLAlchemyError:raise HTTPException(503,'Research storage is temporarily unavailable. Please retry.') from None

@router.get('')
async def history(response:Response,owner:str=Depends(get_current_user_id)):
    response.headers['Cache-Control']='private, no-store'
    return {'items':await store.recent(owner)}

@router.get('/{identifier}')
async def report(identifier:UUID,response:Response,owner:str=Depends(get_current_user_id)):
    response.headers['Cache-Control']='private, no-store'
    return await store.get(str(identifier),owner)

@router.post('/{identifier}/start',status_code=202)
async def start(identifier:UUID,request:StartRequest,owner:str=Depends(get_current_user_id)):
    if request.private:raise HTTPException(422,'Deep research saves reports to your account. Leave Private mode before starting.')
    return await store.start(str(identifier),owner,request.plan.model_dump(),request.revision)

@router.post('/{identifier}/cancel')
async def cancel(identifier:UUID,owner:str=Depends(get_current_user_id)):
    return await store.cancel(str(identifier),owner)

@router.post('/{identifier}/retry',status_code=202)
async def retry(identifier:UUID,owner:str=Depends(get_current_user_id)):
    return await store.retry(str(identifier),owner)

@router.get('/{identifier}/download/{format}')
async def download(identifier:UUID,format:Literal['docx','pdf','xlsx'],owner:str=Depends(get_current_user_id)):
    job=await store.get(str(identifier),owner)
    if job['status'] not in store.TERMINAL or not job.get('report'):raise HTTPException(409,'The report is not ready to download.')
    builder,mime={'docx':(exports.word,'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
        'pdf':(exports.pdf,'application/pdf'),'xlsx':(exports.excel,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}[format]
    try:body=await asyncio.to_thread(builder,job['report'])
    except (ValueError,KeyError,TypeError):raise HTTPException(503,'The download could not be created. Please retry.') from None
    return Response(body,media_type=mime,headers={'Content-Disposition':f'attachment; filename="corten-pharma-{identifier}.{format}"',
        'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'})
