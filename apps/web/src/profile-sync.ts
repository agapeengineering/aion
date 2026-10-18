import { ApiError, request, type Transport } from './api';
import { decodeSettings, type Settings, type StorageLike } from './storage';

export const ACCOUNT_MARKER = 'aion:account';
export const accountKey = (id: string) => `aion:profile:${id}`;
export type Identity = { id: string; email: string };
export type ProfileSnapshot = { user_id: string; revision: number; profile: Settings | null };
export type PendingProfile = { base: number; operation: string; profile: Settings; sent: boolean };
export type SyncState = {
  identity: Identity | null;
  selected: boolean;
  snapshot: ProfileSnapshot | null;
  pending: PendingProfile | null;
  conflict: ProfileSnapshot | null;
  phase:
    | 'guest'
    | 'checking'
    | 'choice'
    | 'saved'
    | 'pending'
    | 'offline'
    | 'error'
    | 'conflict'
    | 'expired';
  busy: boolean;
  cacheIssue: boolean;
};
const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const empty = (): SyncState => ({
  identity: null,
  selected: false,
  snapshot: null,
  pending: null,
  conflict: null,
  phase: 'guest',
  busy: false,
  cacheIssue: false,
});
function identity(value: unknown): Identity {
  const x = value as Identity;
  if (!x || !uuid.test(x.id) || typeof x.email !== 'string' || x.email.length > 254)
    throw new Error('Invalid identity');
  return { id: x.id, email: x.email };
}
export function decodeProfile(value: unknown, owner: string): ProfileSnapshot {
  const x = value as ProfileSnapshot;
  if (!x || x.user_id !== owner || !Number.isSafeInteger(x.revision) || x.revision < 0)
    throw new Error('Invalid profile revision');
  const decoded = decodeSettings(JSON.stringify(x.profile));
  if (x.profile !== null && (!decoded.settings || decoded.status !== 'ok'))
    throw new Error('Unsupported profile format');
  if (x.revision === 0 && x.profile !== null) throw new Error('Invalid initial profile');
  return {
    user_id: owner,
    revision: x.revision,
    profile: x.profile === null ? null : decoded.settings,
  };
}

export class ProfileSync {
  private state = empty();
  private listeners = new Set<() => void>();
  private epoch = 0;
  private flight: Promise<void> | null = null;
  private online = true;
  private blocked = new Set<string>();
  private diskPending: string | null = null;
  constructor(
    private storage: StorageLike,
    private guest: () => Settings | null,
    private transport: Transport = request,
  ) {
    try {
      const raw = storage.getItem(ACCOUNT_MARKER);
      if (raw) {
        const marker = JSON.parse(raw);
        if (marker.version !== 1) {
          this.blocked.add(ACCOUNT_MARKER);
          throw new Error('Unsupported account marker');
        }
        this.activate(identity(marker.identity));
      }
    } catch {
      this.blocked.add(ACCOUNT_MARKER);
      this.state = { ...empty(), cacheIssue: true };
    }
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  get settings(): Settings | null {
    return this.state.pending?.profile ?? this.state.snapshot?.profile ?? null;
  }
  private publish(next: Partial<SyncState>, persist = true) {
    this.state = { ...this.state, ...next };
    if (persist && this.state.identity) {
      const key = accountKey(this.state.identity.id);
      try {
        if (this.blocked.has(key) || this.blocked.has(ACCOUNT_MARKER))
          throw new Error('Unsupported account cache');
        const raw = this.storage.getItem(key);
        if (raw) {
          const disk = JSON.parse(raw);
          if (
            disk.version !== 1 ||
            (disk.pending &&
              disk.pending.operation !== this.diskPending &&
              disk.pending.operation !== this.state.pending?.operation)
          )
            throw new Error('Other tab has pending changes');
        }
        this.storage.setItem(
          ACCOUNT_MARKER,
          JSON.stringify({ version: 1, identity: this.state.identity }),
        );
        this.storage.setItem(
          key,
          JSON.stringify({
            version: 1,
            selected: this.state.selected,
            snapshot: this.state.snapshot,
            pending: this.state.pending,
          }),
        );
        this.diskPending = this.state.pending?.operation ?? null;
      } catch {
        this.state = { ...this.state, cacheIssue: true };
      }
    }
    this.listeners.forEach((listener) => listener());
  }
  private cached(owner: string): Pick<SyncState, 'selected' | 'snapshot' | 'pending'> {
    const key = accountKey(owner);
    try {
      const raw = this.storage.getItem(key);
      if (!raw) return { selected: false, snapshot: null, pending: null };
      const x = JSON.parse(raw);
      if (x.version !== 1 || typeof x.selected !== 'boolean') throw new Error('Unsupported cache');
      const snapshot = x.snapshot === null ? null : decodeProfile(x.snapshot, owner);
      let pending: PendingProfile | null = null;
      if (x.pending) {
        const p = x.pending;
        const profile = decodeSettings(JSON.stringify(p.profile)).settings;
        if (
          !profile ||
          !uuid.test(p.operation) ||
          !Number.isSafeInteger(p.base) ||
          p.base < 0 ||
          typeof p.sent !== 'boolean' ||
          !x.selected ||
          !snapshot ||
          p.base > snapshot.revision
        )
          throw new Error('Invalid pending operation');
        pending = { base: p.base, operation: p.operation, profile, sent: p.sent };
      }
      this.diskPending = pending?.operation ?? null;
      return { selected: x.selected, snapshot, pending };
    } catch {
      this.blocked.add(key);
      this.state = { ...this.state, cacheIssue: true };
      return { selected: false, snapshot: null, pending: null };
    }
  }
  private activate(who: Identity) {
    this.epoch++;
    this.flight = null;
    this.diskPending = null;
    const cached = this.cached(who.id);
    this.publish({ identity: who, ...cached, conflict: null, phase: 'checking', busy: false });
  }
  private forget(phase: 'guest' | 'expired') {
    const owner = this.state.identity?.id;
    this.epoch++;
    this.flight = null;
    let issue = false;
    try {
      if (owner) this.storage.removeItem(accountKey(owner));
      this.storage.removeItem(ACCOUNT_MARKER);
      this.blocked.delete(ACCOUNT_MARKER);
      if (owner) this.blocked.delete(accountKey(owner));
    } catch {
      issue = true;
    }
    this.diskPending = null;
    this.publish({ ...empty(), phase, cacheIssue: issue }, false);
  }
  async resume() {
    if (this.state.identity) return this.refresh();
    const generation = this.epoch;
    this.publish({ busy: true }, false);
    try {
      const who = identity(await this.transport('/me'));
      if (generation !== this.epoch) return;
      this.activate(who);
      await this.refresh();
    } catch (error) {
      if (generation !== this.epoch) return;
      if (!(error instanceof ApiError && error.status === 401))
        this.publish({ phase: 'error' }, false);
    } finally {
      if (generation === this.epoch) this.publish({ busy: false }, false);
    }
  }
  async signIn(who: Identity) {
    if (this.state.identity && this.state.identity.id !== who.id) this.forget('guest');
    this.activate(identity(who));
    await this.refresh();
  }
  setOnline(value: boolean) {
    this.online = value;
    if (!value && this.state.identity)
      this.publish({ phase: this.state.pending ? 'pending' : 'offline' });
    if (value && this.state.identity) void this.refresh();
  }
  refresh(): Promise<void> {
    if (this.flight) return this.flight;
    if (!this.state.identity || !this.online) return Promise.resolve();
    const owner = this.state.identity.id,
      generation = this.epoch;
    this.publish({ busy: true });
    let followup = false;
    const work = (async () => {
      try {
        const who = identity(await this.transport('/me'));
        if (generation !== this.epoch) return;
        if (who.id !== owner) {
          this.forget('expired');
          return;
        }
        const current = decodeProfile(
          await this.transport('/profile', { headers: { 'X-Aion-Account': owner } }),
          owner,
        );
        if (generation !== this.epoch) return;
        const pending = this.state.pending;
        if (!pending) {
          const selected =
            this.state.selected || (current.profile !== null && this.guest() === null);
          this.publish({
            snapshot: current,
            selected,
            conflict: null,
            phase: selected ? 'saved' : 'choice',
          });
          return;
        }
        if (current.revision !== pending.base && !pending.sent) {
          this.publish({ conflict: current, phase: 'conflict' });
          return;
        }
        this.publish({ pending: { ...pending, sent: true }, phase: 'pending' });
        const csrf = await this.transport<{ csrf_token: string }>('/auth/csrf');
        if (generation !== this.epoch) return;
        const updated = decodeProfile(
          await this.transport('/profile', {
            method: 'PUT',
            body: pending.profile,
            headers: {
              'X-Aion-Account': owner,
              'X-CSRF-Token': csrf.csrf_token,
              'If-Match': `"profile-${pending.base}"`,
              'Idempotency-Key': pending.operation,
            },
          }),
          owner,
        );
        if (generation !== this.epoch) return;
        const newer = this.state.pending;
        if (newer && newer.operation !== pending.operation) {
          this.publish({
            snapshot: updated,
            pending: { ...newer, base: updated.revision },
            conflict: null,
            phase: 'pending',
          });
          followup = true;
        } else this.publish({ snapshot: updated, pending: null, conflict: null, phase: 'saved' });
      } catch (error) {
        if (generation !== this.epoch) return;
        if (
          error instanceof ApiError &&
          (error.status === 401 || error.code === 'account_changed')
        ) {
          this.forget('expired');
          return;
        }
        if (error instanceof ApiError && error.status === 409 && error.current) {
          try {
            this.publish({ conflict: decodeProfile(error.current, owner), phase: 'conflict' });
          } catch {
            this.publish({ phase: 'error' });
          }
        } else this.publish({ phase: this.online ? 'error' : 'offline' });
      } finally {
        if (generation === this.epoch) {
          this.flight = null;
          this.publish({ busy: false });
          if (followup)
            queueMicrotask(() => {
              void this.refresh();
            });
        }
      }
    })();
    this.flight = work;
    return work;
  }
  chooseAccount() {
    this.publish({ selected: true, pending: null, conflict: null, phase: 'saved' });
  }
  chooseSetup() {
    this.publish({ selected: true, pending: null, conflict: null, phase: 'saved' });
  }
  useGuest() {
    this.publish({ selected: false, pending: null, conflict: null, phase: 'choice' });
  }
  edit(profile: Settings, expectedRevision?: number) {
    if (!this.state.identity || !this.state.selected || !this.state.snapshot) return;
    const valid = decodeSettings(JSON.stringify(profile)).settings;
    if (!valid) throw new Error('Invalid profile');
    const base = expectedRevision ?? this.state.pending?.base ?? this.state.snapshot.revision;
    this.publish({
      pending: { base, profile: valid, operation: crypto.randomUUID(), sent: false },
      phase: this.state.conflict ? 'conflict' : 'pending',
    });
    if (!this.state.conflict) void this.refresh();
  }
  importGuest() {
    const guest = this.guest();
    if (!guest || !this.state.snapshot) return;
    this.publish({ selected: true });
    this.edit(guest);
  }
  keepServer() {
    const current = this.state.conflict;
    if (!current) return;
    this.publish({
      snapshot: current,
      pending: null,
      conflict: null,
      selected: true,
      phase: 'saved',
    });
  }
  reapply() {
    const pending = this.state.pending,
      current = this.state.conflict;
    if (!pending || !current) return;
    this.publish({
      snapshot: current,
      pending: { ...pending, base: current.revision, operation: crypto.randomUUID(), sent: false },
      conflict: null,
      phase: 'pending',
    });
    void this.refresh();
  }
  async reset() {
    if (!this.online || this.state.busy || !this.state.identity || !this.state.snapshot)
      throw new Error('Online account required');
    const owner = this.state.identity.id,
      generation = this.epoch,
      expected = this.state.snapshot.revision;
    this.publish({ busy: true });
    try {
      const who = identity(await this.transport('/me'));
      if (generation !== this.epoch || who.id !== owner)
        throw new ApiError('account_changed', 0, 409);
      const current = decodeProfile(
        await this.transport('/profile', { headers: { 'X-Aion-Account': owner } }),
        owner,
      );
      if (generation !== this.epoch) return;
      if (current.revision !== expected) {
        this.publish({ conflict: current, phase: 'conflict' });
        throw new Error('Profile changed');
      }
      const csrf = await this.transport<{ csrf_token: string }>('/auth/csrf');
      if (generation !== this.epoch) return;
      const result = decodeProfile(
        await this.transport('/profile', {
          method: 'DELETE',
          headers: {
            'X-Aion-Account': owner,
            'X-CSRF-Token': csrf.csrf_token,
            'If-Match': `"profile-${expected}"`,
            'Idempotency-Key': crypto.randomUUID(),
          },
        }),
        owner,
      );
      if (generation !== this.epoch) return;
      this.publish({ snapshot: result, pending: null, conflict: null, phase: 'saved' });
    } catch (error) {
      if (generation === this.epoch) {
        if (error instanceof ApiError && (error.status === 401 || error.code === 'account_changed'))
          this.forget('expired');
        else if (error instanceof ApiError && error.current)
          this.publish({ conflict: decodeProfile(error.current, owner), phase: 'conflict' });
      }
      throw error;
    } finally {
      if (generation === this.epoch) this.publish({ busy: false });
    }
  }
  async signOut() {
    if (!this.online) throw new Error('Reconnect to revoke this session');
    const generation = ++this.epoch;
    this.flight = null;
    this.publish({ busy: true });
    try {
      const csrf = await this.transport<{ csrf_token: string }>('/auth/csrf');
      await this.transport('/auth/logout', {
        method: 'POST',
        body: {},
        headers: { 'X-CSRF-Token': csrf.csrf_token },
      });
      if (generation === this.epoch) this.forget('guest');
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) this.forget('expired');
      else throw error;
    } finally {
      if (generation === this.epoch) this.publish({ busy: false });
    }
  }
  storageChanged() {
    try {
      const raw = this.storage.getItem(ACCOUNT_MARKER);
      if (!raw) {
        this.forget('guest');
        return;
      }
      const marker = JSON.parse(raw);
      if (marker.version !== 1) {
        this.publish({ cacheIssue: true }, false);
        return;
      }
      const who = identity(marker.identity);
      if (who.id !== this.state.identity?.id) {
        if (this.state.identity) this.forget('expired');
        this.activate(who);
      } else if (!this.state.pending) this.publish({ ...this.cached(who.id) }, false);
      void this.refresh();
    } catch {
      this.publish({ cacheIssue: true }, false);
    }
  }
}
