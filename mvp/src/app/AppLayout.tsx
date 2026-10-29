import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { roleLabel } from '../shared/data/api';
import { resetDb } from '../shared/data/store';
import { cx } from '../shared/ui';
import { CalendarIcon, ChatIcon, HomeIcon, LogoutIcon, MegaphoneIcon, StarIcon, UsersIcon } from '../shared/ui/icons';
import { useAuth } from './auth';

type NavItem = { to: string; label: string; icon: typeof HomeIcon; end?: boolean };

const studentNav: NavItem[] = [
  { to: '/app', label: '홈', icon: HomeIcon, end: true },
  { to: '/app/department', label: '우리 학과', icon: ChatIcon },
  { to: '/app/community', label: '커뮤니티', icon: UsersIcon },
  { to: '/app/opportunities', label: '기회', icon: StarIcon },
  { to: '/app/timetable', label: '시간표', icon: CalendarIcon },
];

const staffNav: NavItem[] = [
  { to: '/staff/notices', label: '공지 관리', icon: MegaphoneIcon },
  { to: '/app/department', label: '학과 채널', icon: ChatIcon },
];

export function Logo({ light }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600 text-[11px] font-black tracking-tight text-white">DIT</span>
      <span className={cx('text-lg font-extrabold tracking-tight', light ? 'text-white' : 'text-navy-900')}>
        DIT <span className="text-brand-600">NOW</span>
      </span>
    </span>
  );
}

/** 사전 MVP 고지 — 실제 학교 시스템 연동으로 오해하지 않도록 항상 노출 (docs/12 §4) */
export function DemoBanner() {
  return (
    <div className="bg-navy-900 px-4 py-1.5 text-center text-[11px] font-medium text-navy-100">
      사전 MVP · 가상 데이터 · 이 브라우저에만 저장됩니다 · 실제 학교 시스템과 연결되어 있지 않습니다
    </div>
  );
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;
  const nav = user.role === 'student' ? studentNav : staffNav;
  const profileLine = user.role === 'student' ? `${user.departmentName} ${user.academicYear}학년` : `${user.departmentName} ${roleLabel[user.role]}`;

  const onLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  return (
    <div className="min-h-screen bg-[#f6f7fa]">
      <DemoBanner />
      {/* 상단 헤더 (모바일·데스크톱 공통) */}
      <header className="sticky top-0 z-30 border-b border-navy-100 bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
          <NavLink to={nav[0].to} aria-label="DIT NOW 홈">
            <Logo />
          </NavLink>
          <div className="flex items-center gap-2">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-semibold text-navy-900">{user.name}</p>
              <p className="text-[11px] text-navy-500">{profileLine}</p>
            </div>
            <button onClick={onLogout} className="grid h-11 w-11 place-items-center rounded-xl text-navy-500 hover:bg-navy-50" aria-label="로그아웃" title="로그아웃">
              <LogoutIcon />
            </button>
          </div>
        </div>
      </header>

      <div className="mx-auto flex max-w-6xl gap-6 px-4 lg:py-6">
        {/* 데스크톱 사이드바 */}
        <aside className="sticky top-24 hidden h-fit w-56 shrink-0 lg:block">
          <nav className="space-y-1" aria-label="주요 메뉴">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  cx(
                    'flex min-h-[44px] items-center gap-3 rounded-xl px-3 text-sm font-semibold transition-colors',
                    isActive ? 'bg-brand-600 text-white shadow-sm' : 'text-navy-600 hover:bg-white',
                  )
                }
              >
                <item.icon /> {item.label}
              </NavLink>
            ))}
          </nav>
          <div className="mt-6 rounded-2xl bg-white p-4 text-xs text-navy-500 ring-1 ring-navy-100">
            <p className="font-semibold text-navy-800">{user.name}</p>
            <p>{profileLine}</p>
            <button
              className="mt-3 text-[11px] text-navy-400 underline hover:text-brand-600"
              onClick={() => {
                if (confirm('시연 데이터를 초기 상태로 되돌릴까요? 이 브라우저에 저장된 변경 내용이 모두 사라집니다.')) resetDb();
              }}
            >
              시연 데이터 초기화
            </button>
          </div>
        </aside>

        <main className="min-w-0 flex-1 pb-28 pt-5 lg:pb-10 lg:pt-0">
          <Outlet />
        </main>
      </div>

      {/* 모바일 하단 탭 */}
      <nav aria-label="주요 메뉴" className="fixed inset-x-0 bottom-0 z-30 border-t border-navy-100 bg-white pb-[env(safe-area-inset-bottom)] lg:hidden">
        <div className="mx-auto flex max-w-lg">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cx('flex min-h-[56px] flex-1 flex-col items-center justify-center gap-0.5 text-[11px] font-semibold', isActive ? 'text-brand-600' : 'text-navy-400')
              }
            >
              <item.icon className="h-[22px] w-[22px]" />
              {item.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
