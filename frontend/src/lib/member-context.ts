const LAST_MEMBER_KEY = "last-used-member";
const RECENT_MEMBERS_KEY = "recent-members";
const MAX_RECENT = 3;

interface MemberRef {
  id: string;
  name: string;
}

export function getLastUsedMember(): MemberRef | null {
  try {
    const raw = localStorage.getItem(LAST_MEMBER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function setLastUsedMember(id: string, name: string): void {
  localStorage.setItem(LAST_MEMBER_KEY, JSON.stringify({ id, name }));

  const recent = getRecentMembers();
  const filtered = recent.filter((m) => m.id !== id);
  filtered.unshift({ id, name });
  localStorage.setItem(RECENT_MEMBERS_KEY, JSON.stringify(filtered.slice(0, MAX_RECENT)));
}

export function getRecentMembers(): MemberRef[] {
  try {
    const raw = localStorage.getItem(RECENT_MEMBERS_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}
