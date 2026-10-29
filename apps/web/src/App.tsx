import { useEffect, useRef, useState } from 'react';
import { Icon } from './components/Icon';
import { StatusPanel } from './components/StatusPanel';
import { ApiError, requestData } from './lib/api';
import { navigation, type SectionId } from './navigation';
import type { components } from './lib/generated/api';
import CampusAssistantPage from './features/ai';
import PublicCampusPage from './features/public-campus';

type Health = components['schemas']['HealthData'];
type HealthState = { kind: 'loading' | 'idle' } | { kind: 'success'; data: Health } | { kind: 'error'; error: ApiError };

function HealthStatus() {
  const [state, setState] = useState<HealthState>({ kind: 'idle' });
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => active.current?.abort(), []);
  async function check() {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setState({ kind: 'loading' });
    try {
      const data = await requestData<Health>('/health', { signal: controller.signal });
      if (!data || data.status !== 'ok' || data.service !== 'ditnow-api') throw new ApiError('INVALID_RESPONSE', 200);
      if (!controller.signal.aborted) setState({ kind: 'success', data });
    } catch (error) {
      if (!controller.signal.aborted) setState({ kind: 'error', error: error instanceof ApiError ? error : new ApiError('NETWORK', 0) });
    }
  }
  return <section className="connection-card" aria-label="공개 서버 연결 확인">
    <div className="eyebrow">SERVICE STATUS</div><h3>서버 연결 확인</h3>
    {state.kind === 'success' ? <p role="status">공개 서버가 응답했습니다. 인증·DB 연결 상태는 확인하지 않습니다.</p>
      : state.kind === 'error' ? <p role="alert">{state.error.message}</p>
      : <p role="status">{state.kind === 'loading' ? '공개 서버 응답을 확인하고 있어요…' : '현재 화면은 공개 탐색입니다. 연결 확인으로 서버 상태를 확인할 수 있어요.'}</p>}
    <button className="outline-button" onClick={check} disabled={state.kind === 'loading'}>{state.kind === 'error' ? '다시 확인' : '연결 확인'} <span aria-hidden="true">↗</span></button>
  </section>;
}

function Home({ navigate }: { navigate: (id: SectionId) => void }) {
  return <>
    <section className="hero">
      <div className="hero-copy"><span className="eyebrow">YOUR CAMPUS, CONNECTED</span><h1>이번 학기도,<br />나답게.</h1><p>배움과 사람, 새로운 기회.<br />당신의 대학 생활을 한곳에서 이어가요.</p><button className="primary-button" onClick={() => navigate('opportunities')}>새로운 기회 살펴보기 <span aria-hidden="true">↗</span></button></div>
      <div className="hero-art" aria-hidden="true"><div className="orb orb-one" /><div className="orb orb-two" /><div className="art-card"><span>DIT</span><b>NOW<span className="art-dot">✳</span></b><small>Make your next move.</small></div><div className="art-caption">배움의 오늘, 가능성의 내일.</div></div>
    </section>
    <section className="section-block" aria-labelledby="quick-title"><div className="section-heading"><div><span className="eyebrow">QUICK ACCESS</span><h2 id="quick-title">나의 캠퍼스로 바로</h2></div><span className="muted">하루를 더 가볍게</span></div>
      <div className="quick-grid">{(['classrooms', 'academic', 'department', 'support'] as const).map(id => { const item = navigation.find(item => item.id === id)!; return <button className="quick-card" key={id} onClick={() => navigate(id)}><span className={`icon-tile tile-${id}`}><Icon name={id} size={26} /></span><strong>{item.label}</strong><span>{item.description}</span><span className="quick-arrow" aria-hidden="true">↗</span></button>; })}</div>
    </section>
    <div className="dashboard-grid"><section className="surface section-block" aria-labelledby="action-title"><div className="section-heading"><div><span className="eyebrow">MY ACTIONS</span><h2 id="action-title">내가 챙길 일</h2></div><span className="badge">개인화 준비 중</span></div><StatusPanel title="나만의 하루를 준비하고 있어요" tone="empty">개인 일정과 알림은 인증·권한 연결 후 제공됩니다. 현재 개인 학적이나 알림을 조회하지 않습니다.</StatusPanel><div className="inline-links"><button onClick={() => navigate('classrooms')}>내 강의실 <span aria-hidden="true">→</span></button><button onClick={() => navigate('opportunities')}>기회 준비 관리 <span aria-hidden="true">→</span></button></div></section>
      <section className="community-card"><span className="eyebrow">BETTER TOGETHER</span><h2>혼자보다<br />함께하는 다음.</h2><p>편하게 나누는 생각부터<br />같이 도전할 팀원까지.</p><div className="community-actions"><button onClick={() => navigate('community')}>익명 커뮤니티 <span aria-hidden="true">↗</span></button><button onClick={() => navigate('recruitments')}>실명 팀원 모집 <span aria-hidden="true">↗</span></button></div></section></div>
    <HealthStatus />
  </>;
}

function PendingSection({ id }: { id: Exclude<SectionId, 'home'> }) {
  const item = navigation.find(item => item.id === id)!;
  return <section className="surface pending-page"><span className="icon-tile"><Icon name={id} size={32} /></span><span className="eyebrow">CONNECTED CAMPUS</span><h1>{item.label}</h1><p className="page-description">{item.description}</p><StatusPanel title="이 기능은 아직 연결되지 않았어요">현재는 통합 탐색 화면입니다. 실제 데이터 조회·작성 기능은 서버와 권한 검증이 연결된 후 제공됩니다.</StatusPanel><p className="pending-note">{id === 'community' ? '익명 글에는 작성자의 실명이나 내부 계정 식별자를 노출하지 않습니다.' : id === 'recruitments' ? '팀원 모집은 익명 게시판과 구분되는 실명 기반 활동입니다.' : id === 'opportunities' ? '외부 기관 제출과 앱의 개인 준비 상태는 구분됩니다.' : '실제 학교의 학적·출결·상담 정보가 연결된 화면이 아닙니다.'}</p></section>;
}

export default function App() {
  const [path, setPath] = useState(window.location.pathname.replace(/\/$/, '') || '/app');
  const [menuOpen, setMenuOpen] = useState(false);
  const main = useRef<HTMLElement>(null);
  const current = navigation.find(item => item.path === path);
  useEffect(() => { const pop = () => { setPath(window.location.pathname.replace(/\/$/, '') || '/app'); setMenuOpen(false); }; window.addEventListener('popstate', pop); return () => window.removeEventListener('popstate', pop); }, []);
  function navigate(id: SectionId) { const item = navigation.find(item => item.id === id)!; window.history.pushState(null, '', item.path); setPath(item.path); setMenuOpen(false); main.current?.focus(); window.scrollTo?.({ top: 0 }); }
  return <div className="app-layout"><a className="skip-link" href="#main-content">본문으로 건너뛰기</a><aside className={`sidebar ${menuOpen ? 'sidebar-open' : ''}`} id="campus-navigation"><a className="brand" href="/app" onClick={event => { event.preventDefault(); navigate('home'); }} aria-label="DIT NOW 홈"><span className="brand-symbol" aria-hidden="true">✳</span><span>DIT <b>NOW</b><small>나의 캠퍼스, 지금</small></span></a><nav aria-label="캠퍼스 전체 메뉴">{navigation.map((item, index) => <div key={item.id}>{(index === 0 || navigation[index - 1].category !== item.category) && <p className="nav-group">{item.category}</p>}<a href={item.path} className={`nav-link ${current?.id === item.id ? 'active' : ''}`} aria-current={current?.id === item.id ? 'page' : undefined} onClick={event => { if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); navigate(item.id); } }}><Icon name={item.id} /><span>{item.label}</span>{item.id === 'ai' && <span className="nav-new">AI</span>}</a></div>)}</nav><div className="sidebar-foot"><span className="live-dot" /> 새로운 캠퍼스를 연결하는 중<small>독립 플랫폼 · 공개 탐색</small></div></aside>
    <div className="workspace"><header className="topbar"><button className="menu-button" aria-label={menuOpen ? '전체 메뉴 닫기' : '전체 메뉴 열기'} aria-expanded={menuOpen} aria-controls="campus-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? '닫기' : '메뉴'}</button><div className="breadcrumb">나의 캠퍼스 <span aria-hidden="true">/</span> <strong>{current?.label ?? '페이지 안내'}</strong></div><div className="visitor"><span className="visitor-avatar" aria-hidden="true">D</span><span>공개 탐색<small>로그인되지 않음</small></span></div></header><main id="main-content" ref={main} tabIndex={-1}><div className="page-intro"><span>DIT NOW <span className="intro-dot">●</span> CAMPUS PLATFORM</span><span className="preview-badge">개발 중 · 실제 학교 연동 없음</span></div>{current?.id === 'home' ? <Home navigate={navigate} /> : current?.id === 'ai' ? <CampusAssistantPage /> : current?.id === 'information' ? <PublicCampusPage /> : current ? <PendingSection key={current.id} id={current.id} /> : <StatusPanel title="페이지를 찾을 수 없어요" tone="error"><button className="text-button" onClick={() => navigate('home')}>캠퍼스 홈으로 이동</button></StatusPanel>}<footer>DIT NOW <span>배움과 사람, 기회를 연결합니다.</span><small>공개 탐색 화면 · 개인 정보 연결 전</small></footer></main></div>
    <nav className="mobile-bar" aria-label="빠른 메뉴">{(['home', 'classrooms', 'department', 'community'] as const).map(id => <button key={id} aria-current={current?.id === id ? 'page' : undefined} onClick={() => navigate(id)}><Icon name={id} size={20} /><span>{navigation.find(item => item.id === id)!.label.replace('캠퍼스 ', '')}</span></button>)}<button aria-expanded={menuOpen} aria-controls="campus-navigation" onClick={() => setMenuOpen(!menuOpen)}><span className="more-icon" aria-hidden="true">•••</span><span>전체 메뉴</span></button></nav>
  </div>;
}
