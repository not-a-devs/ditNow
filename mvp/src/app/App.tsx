import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { LoginPage } from '../features/auth/LoginPage';
import { AnonPostDetailPage, AnonPostEditPage, AnonPostNewPage } from '../features/community/AnonymousPages';
import { CommunityPage } from '../features/community/CommunityPage';
import { RecruitmentDetailPage, RecruitmentEditPage, RecruitmentNewPage } from '../features/community/RecruitmentPages';
import { ChannelPage } from '../features/department/ChannelPage';
import { DepartmentPage } from '../features/department/DepartmentPage';
import { HomePage } from '../features/home/HomePage';
import { TimetablePage } from '../features/home/TimetablePage';
import { NoticeDetailPage } from '../features/notices/NoticeDetailPage';
import { StaffNoticeEditPage, StaffNoticeNewPage, StaffNoticesPage } from '../features/notices/StaffNoticesPage';
import { OpportunitiesPage, OpportunityDetailPage } from '../features/opportunities/OpportunityPages';
import { EmptyState } from '../shared/ui';
import { ToastProvider } from '../shared/ui/toast';
import { AppLayout } from './AppLayout';
import { AuthProvider, RequireAuth, useAuth, homePathFor } from './auth';

function RootRedirect() {
  const { user } = useAuth();
  return <Navigate to={user ? homePathFor(user.role) : '/login'} replace />;
}

const student = ['student'] as const;
const staff = ['assistant', 'professor', 'admin'] as const;

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route path="/" element={<RootRedirect />} />
            <Route path="/login" element={<LoginPage />} />
            <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
              {/* 학생 전용 */}
              <Route path="/app" element={<RequireAuth roles={[...student]}><HomePage /></RequireAuth>} />
              <Route path="/app/timetable" element={<RequireAuth roles={[...student]}><TimetablePage /></RequireAuth>} />
              <Route path="/app/community" element={<RequireAuth roles={[...student]}><CommunityPage /></RequireAuth>} />
              <Route path="/app/community/anonymous/new" element={<RequireAuth roles={[...student]}><AnonPostNewPage /></RequireAuth>} />
              <Route path="/app/community/anonymous/:id" element={<RequireAuth roles={[...student]}><AnonPostDetailPage /></RequireAuth>} />
              <Route path="/app/community/anonymous/:id/edit" element={<RequireAuth roles={[...student]}><AnonPostEditPage /></RequireAuth>} />
              <Route path="/app/community/recruitments/new" element={<RequireAuth roles={[...student]}><RecruitmentNewPage /></RequireAuth>} />
              <Route path="/app/community/recruitments/:id" element={<RequireAuth roles={[...student]}><RecruitmentDetailPage /></RequireAuth>} />
              <Route path="/app/community/recruitments/:id/edit" element={<RequireAuth roles={[...student]}><RecruitmentEditPage /></RequireAuth>} />
              <Route path="/app/opportunities" element={<RequireAuth roles={[...student]}><OpportunitiesPage /></RequireAuth>} />
              <Route path="/app/opportunities/:id" element={<RequireAuth roles={[...student]}><OpportunityDetailPage /></RequireAuth>} />
              {/* 공통 (소속 기반 권한은 api에서 검사) */}
              <Route path="/app/department" element={<DepartmentPage />} />
              <Route path="/app/department/channels/:id" element={<ChannelPage />} />
              <Route path="/app/notices/:id" element={<NoticeDetailPage />} />
              {/* 교직원 */}
              <Route path="/staff/notices" element={<RequireAuth roles={[...staff]}><StaffNoticesPage /></RequireAuth>} />
              <Route path="/staff/notices/new" element={<RequireAuth roles={[...staff]}><StaffNoticeNewPage /></RequireAuth>} />
              <Route path="/staff/notices/:id/edit" element={<RequireAuth roles={[...staff]}><StaffNoticeEditPage /></RequireAuth>} />
              <Route path="*" element={<EmptyState title="페이지를 찾을 수 없습니다" description="주소를 확인하거나 메뉴에서 이동해 주세요." />} />
            </Route>
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
