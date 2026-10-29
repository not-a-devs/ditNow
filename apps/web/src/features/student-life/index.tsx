import { useEffect,useRef,useState,type FormEvent } from 'react';
import { ApiError } from '../../lib/api';
import { CHOICES,KINDS,STATES,intentTracker,loadGuides,loadMe,writeRequest,type Choice,type GuidePage,type LifeRequest,type Overview } from './api';

const date=(v:string)=>new Intl.DateTimeFormat('ko-KR',{dateStyle:'medium',timeStyle:'short'}).format(new Date(v));
const message=(e:unknown)=>e instanceof ApiError && e.status===503?'생활·학생지원 저장소·가상 정책·인증 연결을 준비하고 있습니다.':e instanceof ApiError && e.code==='INVALID_RESPONSE'?'응답의 출처와 개인정보 경계를 확인하지 못했습니다.':e instanceof ApiError?e.message:'요청을 확인하지 못했습니다. 다시 시도하세요.';

export default function StudentLifePage() {
  const [guides,setGuides]=useState<GuidePage|null>(null);const [me,setMe]=useState<Overview|null>(null);
  const [loading,setLoading]=useState(true);const [busy,setBusy]=useState(false);
  const [errors,setErrors]=useState<Record<string,string>>({});const [notice,setNotice]=useState('');
  const [program,setProgram]=useState('');const [choice,setChoice]=useState<Choice>('demo_dorm_a');
  const [editing,setEditing]=useState<LifeRequest|null>(null);
  const keys=useRef(intentTracker());const read=useRef<AbortController|null>(null);const alive=useRef(true);
  async function reload() {
    read.current?.abort();const controller=new AbortController();read.current=controller;
    setLoading(true);setErrors({});
    await Promise.all([
      loadGuides(controller.signal).then(d=>{if(!controller.signal.aborted)setGuides(d);}).catch(e=>{if(!controller.signal.aborted){setGuides(null);setErrors(x=>({...x,guides:message(e)}));}}),
      loadMe(controller.signal).then(d=>{if(!controller.signal.aborted){const selected=d.policies.find(p=>p.program_id===program)??d.policies[0];setMe(d);setEditing(null);setProgram(selected?.program_id||'');setChoice(x=>selected?.allowed_choices.includes(x)?x:selected?.allowed_choices[0]||'demo_dorm_a');}}).catch(e=>{if(!controller.signal.aborted){setMe(null);setEditing(null);setErrors(x=>({...x,me:message(e)}));}}),
    ]);if(!controller.signal.aborted)setLoading(false);
  }
  useEffect(()=>{alive.current=true;void reload();return()=>{alive.current=false;read.current?.abort();};},[]);
  const policy=me?.policies.find(p=>p.program_id===program);
  async function mutate(path:string,body:object,method='POST') {
    setBusy(true);setErrors(x=>({...x,action:''}));setNotice('');
    try {const row=await writeRequest(path,body,keys.current.key(path,body),method);if(!alive.current)return;
      keys.current.done(path);setMe(x=>x?{...x,requests:[...x.requests.filter(r=>r.id!==row.id),row]}:x);
      if(editing?.id===row.id)setEditing(row);setNotice('가상 신청 기록을 반영했습니다. 실제 입사·기관 민원·봉사 실적이 아닙니다.');
    } catch(e){if(!alive.current)return;setErrors(x=>({...x,action:message(e)}));if(e instanceof ApiError && [401,403].includes(e.status)){setMe(null);setEditing(null);}}
    finally{if(alive.current)setBusy(false);}
  }
  function save(e:FormEvent){e.preventDefault();if(!policy||busy)return;const fields={choice,expected_policy_revision:policy.revision};
    if(editing)void mutate(`/student-life/me/requests/${editing.id}`,{...fields,expected_revision:editing.revision},'PATCH');
    else void mutate('/student-life/me/requests',{...fields,program_id:policy.program_id});
  }
  function cancel(row:LifeRequest){const p=me?.policies.find(x=>x.program_id===row.program_id);if(p)void mutate(`/student-life/me/requests/${row.id}/cancel`,{expected_revision:row.revision,expected_policy_revision:p.revision});}

  return <section className="mx-auto flex max-w-5xl flex-col gap-5 p-4" aria-labelledby="life-title">
    <header><h1 id="life-title" className="text-2xl font-semibold">생활 · 학생지원</h1><p>공개 안내와 나의 가상 신청·참여 기록을 구분해 살펴보세요.</p></header>
    <p className="rounded bg-amber-50 p-3">시연 전용입니다. 실명·연락처·장애 정보·고충·성희롱 상담·개인 사연·증빙 서류를 입력하지 마세요. 공식 입사 배정·봉사 실적·서명된 디지털 배지는 제공하지 않습니다.</p>
    <button type="button" disabled={loading||busy} onClick={()=>void reload()} className="self-start rounded border p-2">다시 확인</button>
    {loading&&<p role="status">생활 안내와 본인 기록을 확인하고 있어요…</p>}{Object.entries(errors).filter(([,v])=>v).map(([k,v])=><p role="alert" key={k}>{v}</p>)}{notice&&<p role="status">{notice}</p>}
    <section className="rounded border p-4"><h2 className="text-lg font-semibold">공개 생활관 · 장애지원 · 봉사 안내</h2>
      {guides?.items.length===0&&<p>검증해 등록한 공개 안내가 없습니다. 학교 규정과 담당 정보를 추측하지 않습니다.</p>}
      {guides?.items.map(g=><article key={g.id} className="my-3 border-t pt-3"><h3>{g.title}</h3><p>{g.summary}</p><p>버전 {g.revision} · {g.source_kind==='OFFICIAL_PUBLIC'?'공개 원문 근거':g.source_kind==='DEMO'?'가상 안내':'출처 미확인'}</p>{g.source_url&&<a href={g.source_url} target="_blank" rel="noopener noreferrer" className="underline">근거 원문</a>}{g.checked_at&&<p>반환본 확인 {date(g.checked_at)}</p>}</article>)}
      {guides?.has_more&&<p>첫 20개 안내를 표시합니다. 전체 탐색은 후속 태스크입니다.</p>}
      <p className="mt-3">고충·성희롱 상담 접수와 본문 처리는 승인 전 차단되어 있습니다. 일반 민원에 민감한 사유를 입력하는 기능은 없습니다.</p>
    </section>
    <section className="rounded border p-4"><h2 className="text-lg font-semibold">본인 가상 신청 · 문의 · 참여</h2>
      {me?.policies.length===0&&<p>허용된 가상 프로그램이 없습니다.</p>}
      {me&&policy&&<form onSubmit={save} className="my-3 flex max-w-lg flex-col gap-2"><p>주입된 가상 정책: {policy.name} · 버전 {policy.revision}. 학교 규정이 아닙니다.</p><p>{date(policy.opens_at)} ~ {date(policy.closes_at)}</p>
        <label htmlFor="life-program">가상 프로그램</label><select id="life-program" value={program} disabled={busy||!!editing} onChange={e=>{setProgram(e.target.value);setChoice(me.policies.find(p=>p.program_id===e.target.value)?.allowed_choices[0]||'demo_dorm_a');}}>{me.policies.map(p=><option key={p.program_id} value={p.program_id}>{KINDS[p.kind]} · {p.name}</option>)}</select>
        <label htmlFor="life-choice">가상 제목 · 사유 선택</label><select id="life-choice" disabled={busy} value={choice} onChange={e=>setChoice(e.target.value as Choice)}>{policy.allowed_choices.map(c=><option key={c} value={c}>{CHOICES[c]}</option>)}</select>
        <button disabled={busy||(!!editing&&editing.state!=='requested')} className="rounded bg-blue-700 p-2 text-white">{editing?'가상 신청 수정':'가상 신청 저장'}</button>{editing&&<button type="button" disabled={busy} onClick={()=>setEditing(null)}>새 가상 신청 작성</button>}
      </form>}
      {me?.requests.length===0&&<p>본인 가상 신청 기록이 없습니다.</p>}<ul>{me?.requests.map(r=><li key={r.id} className="my-3 rounded bg-slate-50 p-3"><h3>{KINDS[r.kind]} · {STATES[r.state]}</h3><p>{CHOICES[r.choice]} · 개정 {r.revision}</p>{r.answer_code&&<p>가상 답변: {r.answer_code==='demo_information_referred'?'관련 공개 안내 확인 요청':'가상 안내 확인 상태'}. 실제 담당자의 답변이 아닙니다.</p>}
        {r.state==='requested'&&<button disabled={busy} onClick={()=>{setEditing(r);setProgram(r.program_id);setChoice(r.choice);}}>신청 수정</button>}{['requested','processing','participating'].includes(r.state)&&<button disabled={busy||!me.policies.some(p=>p.program_id===r.program_id)} onClick={()=>cancel(r)}>가상 취소 요청</button>}</li>)}</ul>
    </section>
    <section className="rounded border p-4"><h2 className="text-lg font-semibold">나의 가상 디지털 배지</h2><p>공식 발급·서명·공유 검증·관리자 부여 기능이 아닙니다.</p>{me?.badges.length===0&&<p>본인 가상 배지가 없습니다.</p>}<ul>{me?.badges.map(b=><li key={b.id}>{b.title} · {b.state==='DEMO_REVOKED'?'가상 철회 상태':'가상 표시 기록'} · 공식 검증 불가</li>)}</ul></section>
  </section>;
}
