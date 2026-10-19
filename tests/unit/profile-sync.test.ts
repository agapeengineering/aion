import { describe, it, expect } from 'vitest';
import {
  ProfileSync,
  ACCOUNT_MARKER,
  accountKey,
  type ProfileSnapshot,
} from '../../apps/web/src/profile-sync';
import { ApiError, type Transport, type RequestOptions } from '../../apps/web/src/api';
import { STORAGE_KEY, type Settings } from '../../apps/web/src/storage';

const owner = '00000000-0000-4000-8000-000000000001';
const other = '00000000-0000-4000-8000-000000000002';
const guest: Settings = {
  version: 1,
  birthDate: '2000-01-01',
  lifespanYears: 90,
  language: 'en',
  unit: 'weeks',
  hideRemaining: false,
};
function memory() {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => {
      data.set(k, v);
    },
    removeItem: (k: string) => {
      data.delete(k);
    },
  };
}
function server() {
  let id = owner;
  let snapshot: ProfileSnapshot = { user_id: owner, revision: 0, profile: null };
  const operations = new Map<string, number>();
  const calls: { path: string; options?: RequestOptions }[] = [];
  let loseResponse = false;
  let unauthorized = false;
  const transport: Transport = async <T>(path: string, options?: RequestOptions) => {
    calls.push({ path, options });
    if (unauthorized) throw new ApiError('unauthenticated', 0, 401);
    if (path === '/me') return { id, email: 'person@example.test' } as T;
    if (path === '/auth/csrf') return { csrf_token: 'synthetic' } as T;
    if (path === '/auth/logout') return undefined as T;
    if (path === '/profile') {
      if (options?.headers?.['X-Aion-Account'] !== id)
        throw new ApiError('account_changed', 0, 409);
      if (!options?.method) return structuredClone(snapshot) as T;
      const op = options.headers['Idempotency-Key'];
      if (operations.has(op)) {
        if (operations.get(op) !== snapshot.revision)
          throw new ApiError('profile_conflict', 0, 409, snapshot);
        return structuredClone(snapshot) as T;
      }
      if (options.headers['If-Match'] !== `"profile-${snapshot.revision}"`)
        throw new ApiError('profile_conflict', 0, 409, snapshot);
      snapshot = {
        user_id: id,
        revision: snapshot.revision + 1,
        profile: options.method === 'DELETE' ? null : (options.body as Settings),
      };
      operations.set(op, snapshot.revision);
      if (loseResponse) {
        loseResponse = false;
        throw new Error('Response lost after commit');
      }
      return structuredClone(snapshot) as T;
    }
    throw new Error('Unexpected request');
  };
  return {
    transport,
    calls,
    get snapshot() {
      return snapshot;
    },
    set snapshot(v) {
      snapshot = v;
    },
    switchAccount: () => {
      id = other;
    },
    lose: () => {
      loseResponse = true;
    },
    expire: () => {
      unauthorized = true;
    },
  };
}
const who = { id: owner, email: 'person@example.test' };

describe('account profile sync', () => {
  it('makes no guest requests and sign-in never uploads guest data', async () => {
    const s = server(),
      disk = memory();
    disk.setItem(STORAGE_KEY, JSON.stringify(guest));
    const client = new ProfileSync(disk, () => guest, s.transport);
    await client.refresh();
    expect(s.calls).toEqual([]);
    await client.signIn(who);
    expect(client.getSnapshot().selected).toBe(false);
    expect(s.snapshot.profile).toBeNull();
    expect(s.calls.some((x) => x.options?.method === 'PUT')).toBe(false);
    expect(disk.getItem(STORAGE_KEY)).toBe(JSON.stringify(guest));
  });
  it('imports explicitly, restores on a fresh device and preserves guest data on sign-out', async () => {
    const s = server(),
      disk = memory();
    disk.setItem(STORAGE_KEY, JSON.stringify(guest));
    const a = new ProfileSync(disk, () => guest, s.transport);
    await a.signIn(who);
    a.importGuest();
    await a.refresh();
    expect(s.snapshot.profile).toEqual(guest);
    expect(s.snapshot.revision).toBe(1);
    const b = new ProfileSync(memory(), () => null, s.transport);
    await b.signIn(who);
    expect(b.getSnapshot().selected).toBe(true);
    expect(b.settings).toEqual(guest);
    await a.signOut();
    expect(disk.getItem(accountKey(owner))).toBeNull();
    expect(disk.getItem(ACCOUNT_MARKER)).toBeNull();
    expect(disk.getItem(STORAGE_KEY)).toBe(JSON.stringify(guest));
  });
  it('retains one latest offline edit through reload and does not overwrite a concurrent server edit', async () => {
    const s = server(),
      disk = memory();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    const client = new ProfileSync(disk, () => null, s.transport);
    await client.signIn(who);
    client.setOnline(false);
    client.edit({ ...guest, lifespanYears: 91 });
    client.edit({ ...guest, lifespanYears: 92 });
    const reloaded = new ProfileSync(disk, () => null, s.transport);
    reloaded.setOnline(false);
    expect(reloaded.settings?.lifespanYears).toBe(92);
    s.snapshot = { user_id: owner, revision: 2, profile: { ...guest, lifespanYears: 95 } };
    reloaded.setOnline(true);
    await reloaded.refresh();
    expect(reloaded.getSnapshot().phase).toBe('conflict');
    expect(s.snapshot.profile?.lifespanYears).toBe(95);
    reloaded.reapply();
    await reloaded.refresh();
    expect(s.snapshot.profile?.lifespanYears).toBe(92);
  });
  it('retries a lost response with the same operation key and never rewrites newer data', async () => {
    const s = server(),
      disk = memory();
    const client = new ProfileSync(disk, () => guest, s.transport);
    await client.signIn(who);
    s.lose();
    client.importGuest();
    await client.refresh();
    expect(client.getSnapshot().pending?.sent).toBe(true);
    expect(s.snapshot.revision).toBe(1);
    const operation = client.getSnapshot().pending?.operation;
    await client.refresh();
    expect(client.getSnapshot().pending).toBeNull();
    expect(s.snapshot.revision).toBe(1);
    const writes = s.calls.filter((x) => x.options?.method === 'PUT');
    expect(writes[0].options?.headers?.['Idempotency-Key']).toBe(operation);
    expect(writes[1].options?.headers?.['Idempotency-Key']).toBe(operation);
  });
  it('clears cached account state on session expiry and never uploads it to another account', async () => {
    const s = server(),
      disk = memory();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    const client = new ProfileSync(disk, () => null, s.transport);
    await client.signIn(who);
    client.setOnline(false);
    client.edit({ ...guest, lifespanYears: 99 });
    s.switchAccount();
    client.setOnline(true);
    await client.refresh();
    expect(client.getSnapshot().identity).toBeNull();
    expect(disk.getItem(accountKey(owner))).toBeNull();
    expect(s.snapshot.profile?.lifespanYears).toBe(90);
  });
  it('preserves future cache versions and reports storage failures honestly', async () => {
    const s = server(),
      disk = memory();
    disk.setItem(ACCOUNT_MARKER, JSON.stringify({ version: 2 }));
    const client = new ProfileSync(disk, () => guest, s.transport);
    await client.signIn(who);
    expect(disk.getItem(ACCOUNT_MARKER)).toBe(JSON.stringify({ version: 2 }));
    expect(client.getSnapshot().cacheIssue).toBe(true);
    const denied = new ProfileSync(
      {
        getItem: () => {
          throw new Error();
        },
        setItem: () => {
          throw new Error();
        },
        removeItem: () => {
          throw new Error();
        },
      },
      () => guest,
      s.transport,
    );
    await denied.signIn(who);
    expect(denied.getSnapshot().cacheIssue).toBe(true);
  });
  it('preserves the revision seen when an edit form was opened', async () => {
    const s = server();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    const client = new ProfileSync(memory(), () => null, s.transport);
    await client.signIn(who);
    const openedAt = client.getSnapshot().snapshot!.revision;
    s.snapshot = { user_id: owner, revision: 2, profile: { ...guest, lifespanYears: 95 } };
    await client.refresh();
    client.edit({ ...guest, lifespanYears: 91 }, openedAt);
    await client.refresh();
    expect(client.getSnapshot().phase).toBe('conflict');
    expect(s.snapshot.profile?.lifespanYears).toBe(95);
    client.keepServer();
    expect(client.settings?.lifespanYears).toBe(95);
  });
  it('requires online reset and observes a reset tombstone on the next refresh', async () => {
    const s = server();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    const a = new ProfileSync(memory(), () => null, s.transport),
      b = new ProfileSync(memory(), () => null, s.transport);
    await a.signIn(who);
    await b.signIn(who);
    a.setOnline(false);
    await expect(a.reset()).rejects.toThrow();
    a.setOnline(true);
    await a.refresh();
    await a.reset();
    await b.refresh();
    expect(b.settings).toBeNull();
    expect(s.snapshot.revision).toBe(2);
  });
  it('does not erase another tab’s offline queue when its own storage write collides', async () => {
    const s = server(),
      disk = memory();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    const a = new ProfileSync(disk, () => null, s.transport);
    await a.signIn(who);
    const b = new ProfileSync(disk, () => null, s.transport);
    await b.refresh();
    a.setOnline(false);
    b.setOnline(false);
    a.edit({ ...guest, lifespanYears: 91 });
    const preserved = disk.getItem(accountKey(owner));
    b.edit({ ...guest, lifespanYears: 92 });
    expect(b.getSnapshot().cacheIssue).toBe(true);
    expect(disk.getItem(accountKey(owner))).toBe(preserved);
    expect(b.settings?.lifespanYears).toBe(92);
  });
});

function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

describe('account transition coordination', () => {
  it('blocks queued uploads and foreground refreshes until confirmed termination, preserving guest data', async () => {
    const s = server(),
      disk = memory(),
      entered = deferred<void>(),
      release = deferred<void>();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    disk.setItem(STORAGE_KEY, JSON.stringify(guest));
    let gate = false;
    const transport: Transport = async <T>(path: string, options?: RequestOptions) => {
      if (path === '/auth/csrf' && gate) {
        entered.resolve();
        await release.promise;
      }
      return s.transport<T>(path, options);
    };
    const a = new ProfileSync(disk, () => guest, transport);
    await a.signIn(who);
    a.chooseAccount();
    gate = true;
    a.edit({ ...guest, lifespanYears: 91 });
    await entered.promise;
    let actionStarted = false;
    const ending = a.accountAction(
      owner,
      async () => {
        actionStarted = true;
      },
      'revoked',
    );
    const before = s.calls.length;
    await a.refresh();
    a.setOnline(true);
    await a.refresh();
    expect(s.calls.length).toBe(before);
    expect(actionStarted).toBe(false);
    release.resolve();
    await ending;
    expect(s.calls.some((c) => c.options?.method === 'PUT')).toBe(false);
    expect(a.getSnapshot().identity).toBeNull();
    expect(a.getSnapshot().ended).toBe('revoked');
    expect(disk.getItem(ACCOUNT_MARKER)).toBeNull();
    expect(disk.getItem(accountKey(owner))).toBeNull();
    expect(disk.getItem(STORAGE_KEY)).toBe(JSON.stringify(guest));
  });
  it('waits for an already-issued upload before deleting and ignores its late callback', async () => {
    const s = server(),
      entered = deferred<void>(),
      release = deferred<void>();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    const transport: Transport = async <T>(path: string, options?: RequestOptions) => {
      const result = await s.transport<T>(path, options);
      if (options?.method === 'PUT') {
        entered.resolve();
        await release.promise;
      }
      return result;
    };
    const a = new ProfileSync(memory(), () => null, transport);
    await a.signIn(who);
    a.edit({ ...guest, lifespanYears: 91 });
    await entered.promise;
    let started = false;
    const ending = a.accountAction(
      owner,
      async () => {
        started = true;
      },
      'deleted',
    );
    await a.refresh();
    expect(started).toBe(false);
    release.resolve();
    await ending;
    expect(started).toBe(true);
    expect(a.getSnapshot().phase).toBe('guest');
    expect(a.getSnapshot().ended).toBe('deleted');
    expect(a.getSnapshot().snapshot).toBeNull();
  });
  it('retains pending edits on an unconfirmed failure and allows a later retry', async () => {
    const s = server();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    const a = new ProfileSync(memory(), () => null, s.transport);
    await a.signIn(who);
    a.setOnline(false);
    a.edit({ ...guest, lifespanYears: 92 });
    const action = a.accountAction(owner, async () => {}, 'deleted');
    await expect(action).rejects.toThrow();
    // Reconnect while holding a refresh at its first network await.
    a.setOnline(true);
    await expect(
      a.accountAction(
        owner,
        async () => {
          throw new Error('Unknown outcome');
        },
        'deleted',
      ),
    ).rejects.toThrow('Unknown outcome');
    expect(a.getSnapshot().pending?.profile.lifespanYears).toBe(92);
    expect(a.getSnapshot().identity?.id).toBe(owner);
    expect(a.getSnapshot().ended).toBeNull();
    expect(a.getSnapshot().busy).toBe(false);
    await a.refresh();
    expect(s.snapshot.profile?.lifespanYears).toBe(92);
  });
  it('ignores a stale 401 and fetches a new CSRF nonce after credential rotation before replaying edits', async () => {
    const s = server(),
      entered = deferred<void>(),
      release = deferred<void>();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    let gate = false,
      nonce = 'old';
    const nonces: string[] = [];
    const transport: Transport = async <T>(path: string, options?: RequestOptions) => {
      if (path === '/auth/csrf') {
        const value = nonce;
        if (gate) {
          gate = false;
          entered.resolve();
          await release.promise;
          throw new ApiError('unauthenticated', 0, 401);
        }
        return { csrf_token: value } as T;
      }
      if (options?.method === 'PUT') nonces.push(options.headers!['X-CSRF-Token']);
      return s.transport<T>(path, options);
    };
    const a = new ProfileSync(memory(), () => null, transport);
    await a.signIn(who);
    gate = true;
    a.edit({ ...guest, lifespanYears: 93 });
    await entered.promise;
    const verifying = a.accountAction(owner, async () => {
      nonce = 'new';
    });
    await a.refresh();
    release.resolve();
    await verifying;
    await a.refresh();
    expect(a.getSnapshot().identity?.id).toBe(owner);
    expect(a.getSnapshot().phase).toBe('saved');
    expect(nonces).toEqual(['new']);
  });
  it('does not clear a newly signed-in account when an older termination response arrives', async () => {
    const s = server(),
      entered = deferred<void>(),
      release = deferred<void>();
    const disk = memory(),
      a = new ProfileSync(disk, () => null, s.transport);
    await a.signIn(who);
    const ending = a.accountAction(
      owner,
      async () => {
        entered.resolve();
        await release.promise;
      },
      'deleted',
    );
    await entered.promise;
    s.switchAccount();
    s.snapshot = { user_id: other, revision: 1, profile: guest };
    await a.signIn({ id: other, email: 'other@example.test' });
    release.resolve();
    await expect(ending).rejects.toThrow('account_changed');
    expect(a.getSnapshot().identity?.id).toBe(other);
    expect(a.getSnapshot().ended).toBeNull();
    expect(disk.getItem(accountKey(other))).not.toBeNull();
  });
  it('sessionEnded invalidates late refreshes and clears only the account cache', async () => {
    const s = server(),
      disk = memory(),
      entered = deferred<void>(),
      release = deferred<void>();
    let gate = false;
    disk.setItem(STORAGE_KEY, JSON.stringify(guest));
    const transport: Transport = async <T>(path: string, options?: RequestOptions) => {
      if (path === '/me' && gate) {
        entered.resolve();
        await release.promise;
      }
      return s.transport<T>(path, options);
    };
    const a = new ProfileSync(disk, () => guest, transport);
    await a.signIn(who);
    gate = true;
    const refreshing = a.refresh();
    await entered.promise;
    a.sessionEnded();
    release.resolve();
    await refreshing;
    expect(a.getSnapshot().identity).toBeNull();
    expect(disk.getItem(accountKey(owner))).toBeNull();
    expect(disk.getItem(STORAGE_KEY)).toBe(JSON.stringify(guest));
  });
});

it('retries a cross-tab CSRF rotation once with the same profile body and operation key', async () => {
  const s = server();
  s.snapshot = { user_id: owner, revision: 1, profile: guest };
  const writes: RequestOptions[] = [];
  let nonce = 0;
  const transport: Transport = async <T>(path: string, options?: RequestOptions) => {
    if (path === '/auth/csrf') return { csrf_token: String(++nonce) } as T;
    if (options?.method === 'PUT') {
      writes.push(options);
      if (writes.length === 1) throw new ApiError('csrf_failed', 0, 403);
    }
    return s.transport<T>(path, options);
  };
  const a = new ProfileSync(memory(), () => null, transport);
  await a.signIn(who);
  a.edit({ ...guest, lifespanYears: 94 });
  await a.refresh();
  expect(a.getSnapshot().phase).toBe('saved');
  expect(writes).toHaveLength(2);
  expect(writes[0].body).toEqual(writes[1].body);
  expect(writes[0].headers!['Idempotency-Key']).toBe(writes[1].headers!['Idempotency-Key']);
  expect(writes.map((w) => w.headers!['X-CSRF-Token'])).toEqual(['1', '2']);
});
it('does not loop on repeated CSRF rejection or retry an unrelated forbidden write', async () => {
  for (const code of ['csrf_failed', 'origin_failed']) {
    const s = server();
    s.snapshot = { user_id: owner, revision: 1, profile: guest };
    let writes = 0;
    const transport: Transport = async <T>(path: string, options?: RequestOptions) => {
      if (options?.method === 'PUT') {
        writes++;
        throw new ApiError(code, 0, 403);
      }
      return s.transport<T>(path, options);
    };
    const a = new ProfileSync(memory(), () => null, transport);
    await a.signIn(who);
    a.edit({ ...guest, lifespanYears: 95 });
    await a.refresh();
    expect(writes).toBe(code === 'csrf_failed' ? 2 : 1);
    expect(a.getSnapshot().phase).toBe('error');
    expect(a.getSnapshot().pending).not.toBeNull();
  }
});

it('sign-out clears an expired account without treating the completed local cleanup as an outage', async () => {
  const s = server(),
    disk = memory();
  const a = new ProfileSync(disk, () => guest, s.transport);
  await a.signIn(who);
  s.expire();
  await expect(a.signOut()).resolves.toBeUndefined();
  expect(a.getSnapshot().identity).toBeNull();
  expect(disk.getItem(ACCOUNT_MARKER)).toBeNull();
});
