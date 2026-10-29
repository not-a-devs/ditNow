import type { Channel, Database, Notice, User } from '../../types';
import { readDb, transact, uid, nowIso } from '../store';
import { ApiError, assertValid, latency, notFound, requireRole, requireUser, roleLabel, text, userName } from './core';
import { audienceLabel } from './notices';

/** 소속 기반 채널 접근 판정 (docs/04 §4) — 서버의 can_access_channel()에 해당 */
export function canAccessChannel(user: User, channel: Channel) {
  if (user.role === 'admin') return true;
  if (channel.departmentId !== user.departmentId) return false;
  if (channel.kind === 'year' && user.role === 'student') return channel.academicYear === user.academicYear;
  return true;
}

function getAccessibleChannel(db: Database, user: User, channelId: string) {
  const channel = db.channels.find((c) => c.id === channelId);
  if (!channel) notFound('채널');
  if (!canAccessChannel(user, channel)) throw new ApiError('FORBIDDEN', '소속 학과·학년 채널만 볼 수 있습니다.');
  return channel;
}

export interface ChannelSummary extends Channel {
  lastMessageAt: string | null;
  lastMessagePreview: string | null;
}

export function listMyChannels() {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    const order = { department: 0, year: 1, free: 2 } as const;
    return db.channels
      .filter((c) => canAccessChannel(user, c))
      .sort((a, b) => order[a.kind] - order[b.kind] || (a.academicYear ?? 0) - (b.academicYear ?? 0))
      .map<ChannelSummary>((c) => {
        const msgs = db.messages.filter((m) => m.channelId === c.id && !m.deletedAt);
        const last = msgs[msgs.length - 1];
        let preview: string | null = null;
        if (last) {
          preview =
            last.kind === 'notice_card'
              ? `[공식 공지] ${db.notices.find((n) => n.id === last.referenceNoticeId)?.title ?? ''}`
              : `${userName(db, last.senderId)}: ${last.text}`;
        }
        return { ...c, lastMessageAt: last?.createdAt ?? null, lastMessagePreview: preview };
      });
  });
}

export interface NoticeCardView {
  noticeId: string;
  title: string;
  category: string;
  audience: string;
  authorRole: string;
  deliveredRevision: number;
  currentRevision: number;
  status: 'published' | 'archived' | 'deleted';
}

export interface MessageView {
  id: string;
  kind: 'text' | 'notice_card';
  senderId: string | null;
  senderName: string;
  senderRole: string;
  text: string | null;
  createdAt: string;
  deleted: boolean;
  isMine: boolean;
  card: NoticeCardView | null;
}

function toCard(db: Database, notice: Notice | undefined, deliveredRevision: number): NoticeCardView | null {
  if (!notice) return null;
  const author = db.users.find((u) => u.id === notice.authorId);
  return {
    noticeId: notice.id,
    title: notice.title,
    category: notice.category,
    audience: audienceLabel(db, notice),
    authorRole: author ? `${author.name} ${roleLabel[author.role]}` : '공식',
    deliveredRevision,
    currentRevision: notice.revision,
    status: notice.deletedAt ? 'deleted' : notice.status,
  };
}

export function getChannelWithMessages(channelId: string, limit = 50) {
  return latency(() => {
    const db = readDb();
    const user = requireUser(db);
    const channel = getAccessibleChannel(db, user, channelId);
    const all = db.messages.filter((m) => m.channelId === channelId);
    const page = all.slice(-limit);
    const messages = page.map<MessageView>((m) => {
      const sender = m.senderId ? db.users.find((u) => u.id === m.senderId) : undefined;
      return {
        id: m.id,
        kind: m.kind,
        senderId: m.senderId,
        senderName: sender?.name ?? '공식 알림',
        senderRole: sender ? roleLabel[sender.role] : '',
        text: m.deletedAt ? null : m.text,
        createdAt: m.createdAt,
        deleted: !!m.deletedAt,
        isMine: m.senderId === user.id,
        card:
          m.kind === 'notice_card'
            ? toCard(db, db.notices.find((n) => n.id === m.referenceNoticeId), m.noticeRevision ?? 1)
            : null,
      };
    });
    return { channel, messages, hasMore: all.length > page.length };
  }, 60);
}

/** clientNonce로 재전송 시 중복 저장을 막는다 (FR-DEPT-005) */
export function sendMessage(channelId: string, input: string, clientNonce: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      getAccessibleChannel(db, user, channelId);
      const errors: Record<string, string> = {};
      const body = text(errors, 'text', '메시지', input, 1, 2000);
      assertValid(errors);
      const dup = db.messages.find((m) => m.clientNonce === clientNonce);
      if (dup) return dup;
      const msg = {
        id: uid('m'),
        channelId,
        senderId: user.id,
        kind: 'text' as const,
        text: body,
        referenceNoticeId: null,
        noticeRevision: null,
        clientNonce,
        createdAt: nowIso(),
        deletedAt: null,
      };
      db.messages.push(msg);
      return msg;
    }),
  80);
}

export function deleteMessage(messageId: string) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      const msg = db.messages.find((m) => m.id === messageId);
      if (!msg) notFound('메시지');
      if (msg.senderId !== user.id) throw new ApiError('FORBIDDEN', '본인이 보낸 메시지만 삭제할 수 있습니다.');
      msg.deletedAt = nowIso();
    }),
  );
}

export function createFreeChannel(input: { name: string; description: string }) {
  return latency(() =>
    transact((db) => {
      const user = requireUser(db);
      requireRole(user, ['student', 'assistant', 'professor']);
      const errors: Record<string, string> = {};
      const name = text(errors, 'name', '채널 이름', input.name, 2, 60);
      const description = text(errors, 'description', '설명', input.description, 0, 200);
      if (!errors.name && db.channels.some((c) => c.departmentId === user.departmentId && c.name === name)) {
        errors.name = '같은 이름의 채널이 이미 있습니다.';
      }
      assertValid(errors);
      const channel: Channel = {
        id: uid('ch'),
        departmentId: user.departmentId,
        academicYear: null,
        kind: 'free',
        official: false, // 학생 폼은 일반 채널만 생성 가능 (docs/07 §5)
        name,
        description,
        createdBy: user.id,
        createdAt: nowIso(),
      };
      db.channels.push(channel);
      return channel;
    }),
  );
}
