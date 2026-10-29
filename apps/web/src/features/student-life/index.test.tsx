import { fireEvent,render,screen,waitFor } from '@testing-library/react';
import { describe,expect,it,vi } from 'vitest';
import StudentLifePage from './index';
import { intentTracker,isOverview,loadGuides,loadMe,officialUrl,writeRequest,type LifeRequest } from './api';

const PROGRAM='11111111-1111-4111-8111-111111111111';
const ID='22222222-2222-4222-8222-222222222222';
const NOW='2026-10-30T00:00:00Z';
const policy={program_id:PROGRAM,kind:'dorm',name:'가상 생활관 테스트',revision:1,allowed_choices:['demo_dorm_a','demo_dorm_b'],opens_at:'2026-10-29T00:00:00Z',closes_at:'2026-10-31T00:00:00Z',cancel_until:'2026-11-01T00:00:00Z',max_per_user:1,capacity:1,source_kind:'DEMO'};
const row:LifeRequest={id:ID,program_id:PROGRAM,kind:'dorm',choice:'demo_dorm_a',state:'requested',answer_code:null,revision:1,policy_revision:1,created_at:NOW,updated_at:NOW,source_kind:'DEMO',official_effect:false};
const badge={id:ID,title:'가상 참여 확인',state:'DEMO_ISSUED',recorded_at:NOW,source_kind:'DEMO',official_effect:false,verification:'NOT_OFFICIALLY_VERIFIABLE'};
const overview={requests:[],badges:[],policies:[policy],source_kind:'DEMO',sensitive_support:'BLOCKED'};
const guide={id:ID,category:'dorm',title:'가상 안내 예시',summary:'실제 학교 안내가 아닌 테스트',revision:1,source_kind:'DEMO',source_url:null,checked_at:null};
const ok=(data:unknown)=>new Response(JSON.stringify({data}),{status:200});
const fail=(status:number,code:string)=>new Response(JSON.stringify({code,message:'private-driver-detail'}),{status});
function stub(handler:(url:URL,init:RequestInit)=>Response|Promise<Response>){const fetch=vi.fn((url:string,init:RequestInit={})=>Promise.resolve(handler(new URL(url),init)));vi.stubGlobal('fetch',fetch);return fetch;}
const writes=(fetch:ReturnType<typeof stub>)=>fetch.mock.calls.filter(([,init])=>!!init?.method).map(([,init])=>init!);

describe('student life contract guards and paths',()=>{
  it('sends one shared API prefix and preserves explicit intent headers',async()=>{
    const fetch=stub((_u,init)=>ok(init.method?row:{items:[],offset:0,has_more:false}));
    await loadGuides();await writeRequest(`/student-life/me/requests/${ID}`,{choice:'demo_dorm_b'},'life-key-123456789','PATCH');
    expect(fetch.mock.calls[0][0]).toBe(`${window.location.origin}/api/v1/student-life/guides?limit=20`);
    expect(fetch.mock.calls[1][0]).toBe(`${window.location.origin}/api/v1/student-life/me/requests/${ID}`);
    expect(writes(fetch)[0].headers).toMatchObject({'Idempotency-Key':'life-key-123456789'});
  });
  it('respects a configured absolute server base',async()=>{
    vi.stubEnv('VITE_API_BASE_URL','https://api.example.test/api/v1');const fetch=stub(()=>ok(overview));await loadMe();
    expect(fetch.mock.calls[0][0]).toBe('https://api.example.test/api/v1/student-life/me');
  });
  it('rejects identity leaks, official badges and unsafe source links',()=>{
    expect(isOverview({...overview,requests:[{...row,owner_id:'private-user'}]})).toBe(false);
    expect(isOverview({...overview,badges:[{...badge,official_effect:true}]})).toBe(false);
    expect(isOverview({...overview,sensitive_support:'ENABLED'})).toBe(false);
    expect(officialUrl('javascript:alert(1)')).toBe(false);
    expect(officialUrl('https://user:password@www.dit.ac.kr/kr/')).toBe(false);
  });
  it('reuses only unchanged intent keys',()=>{
    let n=0;const t=intentTracker(()=>`key-${++n}`);expect(t.key('/a',{x:1})).toBe(t.key('/a',{x:1}));
    expect(t.key('/a',{x:2})).toBe('key-2');expect(t.key('/b',{x:2})).toBe('key-3');t.done('/a');expect(t.key('/a',{x:2})).toBe('key-4');
  });
});

describe('student life page',()=>{
  it('shows loading and honest 503 without fictional success data',async()=>{
    stub(()=>fail(503,'UNAVAILABLE'));render(<StudentLifePage/>);
    expect(screen.getByText(/생활 안내와 본인 기록을 확인/)).toBeInTheDocument();
    expect(await screen.findAllByRole('alert')).toHaveLength(2);
    expect(screen.queryByRole('button',{name:'가상 신청 저장'})).not.toBeInTheDocument();
    expect(screen.queryByText('private-driver-detail')).not.toBeInTheDocument();
  });
  it('renders an empty guide registry and empty eligible programs honestly',async()=>{
    stub(url=>ok(url.pathname.endsWith('/guides')?{items:[],offset:0,has_more:false}:{...overview,policies:[]}));
    render(<StudentLifePage/>);expect(await screen.findByText(/검증해 등록한 공개 안내가 없습니다/)).toBeInTheDocument();
    expect(await screen.findByText('허용된 가상 프로그램이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
  it('keeps public guidance separate from a private 401 response',async()=>{
    stub(url=>url.pathname.endsWith('/guides')?ok({items:[guide],offset:0,has_more:false}):fail(401,'UNAUTHORIZED'));
    render(<StudentLifePage/>);expect(await screen.findByText(guide.title)).toBeInTheDocument();
    expect(await screen.findByRole('alert')).toHaveTextContent('로그인이 필요한');
    expect(screen.queryByRole('button',{name:'가상 신청 저장'})).not.toBeInTheDocument();
  });
  it('preserves an uncertain retry key and rotates it when the selected reason changes',async()=>{
    const fetch=stub((url,init)=>{if(init.method)throw new TypeError('offline');return ok(url.pathname.endsWith('/guides')?{items:[],offset:0,has_more:false}:overview);});
    render(<StudentLifePage/>);const save=await screen.findByRole('button',{name:'가상 신청 저장'});
    fireEvent.click(save);await screen.findByRole('alert');await waitFor(()=>expect(save).toBeEnabled());
    fireEvent.click(save);await waitFor(()=>expect(writes(fetch)).toHaveLength(2));await waitFor(()=>expect(save).toBeEnabled());
    fireEvent.change(screen.getByLabelText('가상 제목 · 사유 선택'),{target:{value:'demo_dorm_b'}});fireEvent.click(save);
    await waitFor(()=>expect(writes(fetch)).toHaveLength(3));
    const keys=writes(fetch).map(i=>(i.headers as Record<string,string>)['Idempotency-Key']);expect(keys[0]).toBe(keys[1]);expect(keys[1]).not.toBe(keys[2]);
    expect(screen.getByLabelText('가상 제목 · 사유 선택')).toHaveValue('demo_dorm_b');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
  it('creates, edits and cancels only server-provided virtual records',async()=>{
    let current:LifeRequest|null=null;
    stub((url,init)=>{if(!init.method)return ok(url.pathname.endsWith('/guides')?{items:[],offset:0,has_more:false}:overview);
      const body=JSON.parse(String(init.body));current=url.pathname.endsWith('/requests')?row:{...current!,revision:current!.revision+1,...(init.method==='PATCH'?{choice:body.choice}:{state:'cancelled' as const})};return ok(current);});
    render(<StudentLifePage/>);fireEvent.click(await screen.findByRole('button',{name:'가상 신청 저장'}));
    expect(await screen.findByText(/생활관 가상 신청 · 가상 신청됨/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button',{name:'신청 수정'}));fireEvent.change(screen.getByLabelText('가상 제목 · 사유 선택'),{target:{value:'demo_dorm_b'}});
    fireEvent.click(screen.getByRole('button',{name:'가상 신청 수정'}));await screen.findByText(/개정 2/);
    fireEvent.click(screen.getByRole('button',{name:'가상 취소 요청'}));expect(await screen.findByText(/생활관 가상 신청 · 가상 취소됨/)).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'가상 취소 요청'})).not.toBeInTheDocument();
  });
  it('clears private records after 403 without granting staff access',async()=>{
    stub((url,init)=>init.method?fail(403,'FORBIDDEN'):ok(url.pathname.endsWith('/guides')?{items:[guide],offset:0,has_more:false}:{...overview,requests:[row],badges:[badge]}));
    render(<StudentLifePage/>);fireEvent.click(await screen.findByRole('button',{name:'가상 취소 요청'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('접근할 권한');expect(screen.queryByText(/생활관 가상 신청 · 가상 신청됨/)).not.toBeInTheDocument();
    expect(screen.queryByText(/가상 참여 확인/)).not.toBeInTheDocument();expect(screen.getByText(guide.title)).toBeInTheDocument();
  });
  it('displays only fictional badge status with no issue or share action',async()=>{
    stub(url=>ok(url.pathname.endsWith('/guides')?{items:[],offset:0,has_more:false}:{...overview,badges:[badge]}));render(<StudentLifePage/>);
    expect(await screen.findByText(/가상 참여 확인 · 가상 표시 기록 · 공식 검증 불가/)).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:/발급|서명|공유/})).not.toBeInTheDocument();
  });
  it('initializes the choice from the selected program rather than another kind',async()=>{
    const volunteer={...policy,program_id:ID,kind:'volunteer',allowed_choices:['demo_volunteer_a']};
    stub(url=>ok(url.pathname.endsWith('/guides')?{items:[],offset:0,has_more:false}:{...overview,policies:[volunteer,policy]}));render(<StudentLifePage/>);
    expect(await screen.findByLabelText('가상 제목 · 사유 선택')).toHaveValue('demo_volunteer_a');
  });
});
