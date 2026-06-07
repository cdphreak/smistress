const KEY = 'smistress.profileId';

function load(): string | null {
  if (typeof localStorage === 'undefined') return null;
  return localStorage.getItem(KEY);
}

class Session {
  profileId = $state<string | null>(load());

  setProfileId(id: string) {
    this.profileId = id;
    if (typeof localStorage !== 'undefined') localStorage.setItem(KEY, id);
  }
  clear() {
    this.profileId = null;
    if (typeof localStorage !== 'undefined') localStorage.removeItem(KEY);
  }
}

export const session = new Session();
