import { ApiError, requestData } from '../../lib/api';

export const KINDS = { dorm:'생활관 가상 신청', inquiry:'일반 안내 가상 민원', volunteer:'가상 봉사 참여' };
export type Kind = keyof typeof KINDS;
export const CHOICES = { demo_dorm_a:'가상 생활관 선택 A', demo_dorm_b:'가상 생활관 선택 B', process_information:'가상 절차 안내 문의', facility_information:'가상 시설 안내 문의', demo_volunteer_a:'가상 봉사 활동 A', demo_volunteer_b:'가상 봉사 활동 B' };
export type Choice = keyof typeof CHOICES;
const choiceKinds: Record<Kind, Choice[]> = {dorm:['demo_dorm_a','demo_dorm_b'], inquiry:['process_information','facility_information'], volunteer:['demo_volunteer_a','demo_volunteer_b']};
export const STATES = {requested:'가상 신청됨',processing:'가상 처리 상태',answered:'가상 안내 답변 상태',participating:'가상 참여 상태',completed:'가상 완료 상태',cancelled:'가상 취소됨'};
const stateKinds: Record<Kind, string[]> = {dorm:['requested','processing','cancelled'],inquiry:['requested','processing','answered','cancelled'],volunteer:['requested','participating','completed','cancelled']};
export interface Guide {id:string;category:'dorm'|'disability'|'volunteer'|'general_inquiry'|'protected_help';title:string;summary:string;revision:number;source_kind:'OFFICIAL_PUBLIC'|'UNKNOWN'|'DEMO';source_url:string|null;checked_at:string|null;}
export interface GuidePage {items:Guide[];offset:number;has_more:boolean;}
export interface Policy {program_id:string;kind:Kind;name:string;revision:number;allowed_choices:Choice[];opens_at:string;closes_at:string;cancel_until:string|null;max_per_user:number;capacity:number;source_kind:'DEMO';}
export interface LifeRequest {id:string;program_id:string;kind:Kind;choice:Choice;state:keyof typeof STATES;answer_code:'demo_information_referred'|'demo_information_checked'|null;revision:number;policy_revision:number;created_at:string;updated_at:string;source_kind:'DEMO';official_effect:false;}
export interface Badge {id:string;title:'가상 참여 확인'|'가상 학습 확인';state:'DEMO_ISSUED'|'DEMO_REVOKED';recorded_at:string;source_kind:'DEMO';official_effect:false;verification:'NOT_OFFICIALLY_VERIFIABLE';}
export interface Overview {requests:LifeRequest[];badges:Badge[];policies:Policy[];source_kind:'DEMO';sensitive_support:'BLOCKED';}
const object = (v:unknown):v is Record<string,unknown> => !!v && typeof v === 'object' && !Array.isArray(v) && !('owner_id' in v);
const text = (v:unknown,max:number):v is string => typeof v === 'string' && !!v.trim() && v.length <= max;
const uuid = (v:unknown):v is string => typeof v === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v);
const int = (v:unknown,min=1,max=100000) => Number.isInteger(v) && Number(v)>=min && Number(v)<=max;
const date = (v:unknown):v is string => typeof v === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(v) && Number.isFinite(Date.parse(v));
const list = <T,>(v:unknown,max:number,guard:(v:unknown)=>v is T):v is T[] => Array.isArray(v) && v.length<=max && v.every(guard);
export function officialUrl(v:unknown):v is string { if (!text(v,2048) || /[\s\u0000-\u001f\u007f\\]|[^\x00-\x7f]/.test(v)) return false; try {const u=new URL(v);return u.protocol==='https:' && u.host==='www.dit.ac.kr' && !u.username && !u.password;}catch{return false;} }
export function isGuide(v:unknown):v is Guide { return object(v) && uuid(v.id) && ['dorm','disability','volunteer','general_inquiry','protected_help'].includes(String(v.category)) && text(v.title,200) && text(v.summary,1000) && int(v.revision) && (v.source_kind==='OFFICIAL_PUBLIC' ? officialUrl(v.source_url) && date(v.checked_at) : ['UNKNOWN','DEMO'].includes(String(v.source_kind)) && v.source_url===null && v.checked_at===null); }
export function isGuidePage(v:unknown):v is GuidePage { return object(v) && list(v.items,50,isGuide) && int(v.offset,0) && typeof v.has_more==='boolean'; }
function isPolicy(v:unknown):v is Policy { if (!object(v) || !Object.hasOwn(KINDS,String(v.kind))) return false; const kind=v.kind as Kind; return uuid(v.program_id) && text(v.name,100) && int(v.revision) && list(v.allowed_choices,6,(c):c is Choice=>choiceKinds[kind].includes(c as Choice)) && v.allowed_choices.length>0 && date(v.opens_at) && date(v.closes_at) && Date.parse(v.closes_at)>Date.parse(v.opens_at) && (v.cancel_until===null || date(v.cancel_until)) && int(v.max_per_user,1,10) && int(v.capacity,1,1000) && v.source_kind==='DEMO'; }
export function isRequest(v:unknown):v is LifeRequest { if (!object(v) || !Object.hasOwn(KINDS,String(v.kind))) return false;const kind=v.kind as Kind; return uuid(v.id) && uuid(v.program_id) && choiceKinds[kind].includes(v.choice as Choice) && stateKinds[kind].includes(String(v.state)) && (kind==='inquiry' && v.state==='answered' ? ['demo_information_referred','demo_information_checked'].includes(String(v.answer_code)) : v.answer_code===null) && int(v.revision) && int(v.policy_revision) && date(v.created_at) && date(v.updated_at) && v.source_kind==='DEMO' && v.official_effect===false; }
function isBadge(v:unknown):v is Badge { return object(v) && uuid(v.id) && ['가상 참여 확인','가상 학습 확인'].includes(String(v.title)) && ['DEMO_ISSUED','DEMO_REVOKED'].includes(String(v.state)) && date(v.recorded_at) && v.source_kind==='DEMO' && v.official_effect===false && v.verification==='NOT_OFFICIALLY_VERIFIABLE'; }
export function isOverview(v:unknown):v is Overview { return object(v) && list(v.requests,100,isRequest) && list(v.badges,100,isBadge) && list(v.policies,20,isPolicy) && v.source_kind==='DEMO' && v.sensitive_support==='BLOCKED'; }
async function checked<T>(path:string,guard:(v:unknown)=>v is T,init?:RequestInit) {const data=await requestData<unknown>(path,init);if(!guard(data))throw new ApiError('INVALID_RESPONSE',200);return data;}
export const loadGuides=(signal?:AbortSignal)=>checked('/student-life/guides?limit=20',isGuidePage,{signal});
export const loadMe=(signal?:AbortSignal)=>checked('/student-life/me',isOverview,{signal});
export const writeRequest=(path:string,body:object,key:string,method='POST')=>checked(path,isRequest,{method,headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(body)});
export function intentTracker(generate:()=>string=()=>crypto.randomUUID()) {const map=new Map<string,{body:string;key:string}>();return {key(path:string,body:object){const serialized=JSON.stringify(body);const old=map.get(path);const next=old?.body===serialized?old:{body:serialized,key:generate()};map.set(path,next);return next.key;},done(path:string){map.delete(path);}};}
