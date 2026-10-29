import { ApiError, requestData } from '../../lib/api';

export interface Offering { id:string;term_id:string;title:string;section:string;source_kind:'DEMO' }
export interface Policy { offering_id:string;term_id:string;revision:number;completion_steps:number;max_attempts:number;require_all_answers:boolean;source_kind:'DEMO' }
export interface Step { id:string;text:string }
export interface Unit { id:string;offering_id:string;title:string;steps:Step[];revision:number;status:'published';opens_at:string;closes_at:string;source_kind:'DEMO' }
export interface Progress { unit_id:string;completed_steps:string[];revision:number;state:'IN_PROGRESS'|'DEMO_COMPLETED'|'STALE_DEMO';evidence:'SELF_REPORTED_DEMO';official_attendance:'BLOCKED';source_kind:'DEMO' }
export interface ExamSummary { id:string;title:string;revision:number;opens_at:string;closes_at:string;open_for_demo:boolean;source_kind:'DEMO' }
export interface Question { id:string;prompt:string;options:{id:string;text:string}[] }
export interface Exam extends ExamSummary {questions:Question[]}
export interface Attempt { id:string;exam_id:string;exam_revision:number;state:'in_progress'|'submitted';revision:number;started_at:string;submitted_at:string|null;source_kind:'DEMO';evaluation:'NOT_GRADED';official_grade:'BLOCKED' }
export interface Workspace {offering:Offering;policy:Policy;units:Unit[];progress:Progress[];exams:ExamSummary[];attempts:Attempt[];source_kind:'DEMO'}
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const only=(v:Record<string,unknown>,keys:string[])=>Object.keys(v).every(k=>keys.includes(k));
// Pydantic string limits count Unicode code points, not UTF-16 code units.
const text=(v:unknown,max:number):v is string=>typeof v==='string'&&v.length<=max*2&&v.trim().length>0&&Array.from(v).length<=max;
const uuid=(v:unknown):v is string=>typeof v==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(v);
const int=(v:unknown,min=1,max=1000000):v is number=>Number.isInteger(v)&&Number(v)>=min&&Number(v)<=max;
const date=(v:unknown):v is string=>typeof v==='string'&&/T.*(?:Z|[+-]\d\d:\d\d)$/.test(v)&&Number.isFinite(Date.parse(v));
const list=<T>(v:unknown,max:number,guard:(x:unknown)=>x is T):v is T[]=>Array.isArray(v)&&v.length<=max&&v.every(guard);
const unique=(xs:string[])=>new Set(xs).size===xs.length;
export function isOffering(v:unknown):v is Offering {return object(v)&&only(v,['id','term_id','title','section','source_kind'])&&uuid(v.id)&&uuid(v.term_id)&&text(v.title,160)&&text(v.section,40)&&v.source_kind==='DEMO';}
function isPolicy(v:unknown):v is Policy {return object(v)&&only(v,['offering_id','term_id','revision','completion_steps','max_attempts','require_all_answers','source_kind'])&&uuid(v.offering_id)&&uuid(v.term_id)&&int(v.revision)&&int(v.completion_steps,1,20)&&int(v.max_attempts,1,10)&&typeof v.require_all_answers==='boolean'&&v.source_kind==='DEMO';}
function isStep(v:unknown):v is Step{return object(v)&&only(v,['id','text'])&&uuid(v.id)&&text(v.text,2000);}
function isUnit(v:unknown):v is Unit {return object(v)&&only(v,['id','offering_id','title','steps','revision','status','opens_at','closes_at','source_kind'])&&uuid(v.id)&&uuid(v.offering_id)&&text(v.title,160)&&list(v.steps,20,isStep)&&v.steps.length>0&&unique(v.steps.map(s=>s.id))&&int(v.revision)&&v.status==='published'&&date(v.opens_at)&&date(v.closes_at)&&Date.parse(v.closes_at)>Date.parse(v.opens_at)&&v.source_kind==='DEMO';}
export function isProgress(v:unknown):v is Progress {return object(v)&&only(v,['unit_id','completed_steps','revision','state','evidence','official_attendance','source_kind'])&&uuid(v.unit_id)&&list(v.completed_steps,20,uuid)&&unique(v.completed_steps)&&int(v.revision,0)&&['IN_PROGRESS','DEMO_COMPLETED','STALE_DEMO'].includes(String(v.state))&&v.evidence==='SELF_REPORTED_DEMO'&&v.official_attendance==='BLOCKED'&&v.source_kind==='DEMO';}
const summaryKeys=['id','title','revision','opens_at','closes_at','open_for_demo','source_kind'];
function summary(v:unknown):v is ExamSummary {return object(v)&&uuid(v.id)&&text(v.title,160)&&int(v.revision)&&date(v.opens_at)&&date(v.closes_at)&&Date.parse(v.closes_at)>Date.parse(v.opens_at)&&typeof v.open_for_demo==='boolean'&&v.source_kind==='DEMO';}
function isSummary(v:unknown):v is ExamSummary{return object(v)&&only(v,summaryKeys)&&summary(v);}
function isQuestion(v:unknown):v is Question {return object(v)&&only(v,['id','prompt','options'])&&uuid(v.id)&&text(v.prompt,1000)&&list(v.options,8,(x):x is {id:string;text:string}=>object(x)&&only(x,['id','text'])&&uuid(x.id)&&text(x.text,400))&&v.options.length>=2&&unique(v.options.map(o=>o.id));}
export function isExam(v:unknown):v is Exam {return object(v)&&only(v,[...summaryKeys,'questions'])&&summary(v)&&list(v.questions,20,isQuestion)&&v.questions.length>0&&unique(v.questions.map(q=>q.id));}
export function isAttempt(v:unknown):v is Attempt {return object(v)&&only(v,['id','exam_id','exam_revision','state','revision','started_at','submitted_at','source_kind','evaluation','official_grade'])&&uuid(v.id)&&uuid(v.exam_id)&&int(v.exam_revision)&&int(v.revision)&&['in_progress','submitted'].includes(String(v.state))&&date(v.started_at)&&(v.state==='submitted'?date(v.submitted_at)&&Date.parse(v.submitted_at)>=Date.parse(v.started_at):v.submitted_at===null)&&v.source_kind==='DEMO'&&v.evaluation==='NOT_GRADED'&&v.official_grade==='BLOCKED';}
export function isWorkspace(v:unknown):v is Workspace {
 if(!object(v)||!only(v,['offering','policy','units','progress','exams','attempts','source_kind'])||!isOffering(v.offering)||!isPolicy(v.policy)||!list(v.units,50,isUnit)||!list(v.progress,50,isProgress)||!list(v.exams,30,isSummary)||!list(v.attempts,100,isAttempt)||v.source_kind!=='DEMO')return false;
 const {offering,policy,units,progress,exams,attempts}=v;
 return policy.offering_id===offering.id&&policy.term_id===offering.term_id&&units.every(u=>u.offering_id===offering.id)
  &&progress.every(p=>units.some(u=>u.id===p.unit_id&&p.completed_steps.every(s=>u.steps.some(step=>step.id===s))))
  &&attempts.every(a=>exams.some(e=>e.id===a.exam_id))
  &&[units,progress,exams,attempts].every(xs=>unique(xs.map(x=>'unit_id' in x?x.unit_id:x.id)));
}
async function checked<T>(path:string,guard:(v:unknown)=>v is T,init?:RequestInit){const value=await requestData<unknown>(path,{cache:'no-store',...init});if(!guard(value))throw new ApiError('INVALID_RESPONSE',200);return value;}
export const loadOfferings=(signal?:AbortSignal)=>checked('/online-learning?limit=20',(v):v is Offering[]=>list(v,20,isOffering)&&unique(v.map(o=>o.id)),{signal});
export const loadWorkspace=(id:string,signal?:AbortSignal)=>checked(`/online-learning/${id}`,(v):v is Workspace=>isWorkspace(v)&&v.offering.id===id,{signal});
export const loadExam=(offering:string,id:string,signal?:AbortSignal)=>checked(`/online-learning/${offering}/exams/${id}`,(v):v is Exam=>isExam(v)&&v.id===id,{signal});
export const writeProgress=(offering:string,unit:string,body:object,key:string)=>checked(`/online-learning/${offering}/units/${unit}/progress`,(v):v is Progress=>isProgress(v)&&v.unit_id===unit,{method:'PUT',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(body)});
export const writeAttempt=(path:string,exam:string,body:object,key:string)=>checked(path,(v):v is Attempt=>isAttempt(v)&&v.exam_id===exam,{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(body)});
export function intentTracker(generate:()=>string=()=>crypto.randomUUID()){const keys=new Map<string,{body:string;key:string}>();return {key(path:string,body:object){const serialized=JSON.stringify(body);const prior=keys.get(path);const value=prior?.body===serialized?prior:{body:serialized,key:generate()};keys.set(path,value);return value.key;},done(path:string){keys.delete(path);}};}
