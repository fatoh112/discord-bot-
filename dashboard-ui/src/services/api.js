// api.js - Service layer for dashboard API requests (REST)
// Supports mock and live modes based on environment configuration.

const API_MODE = import.meta.env.VITE_API_MODE || 'mock';
const BASE_URL = import.meta.env.VITE_API_BASE_URL || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8080');

// --- Mock Store (In-Memory State) ---
let mockState = {
  status: 'playing', // playing, paused, idle
  current_track: {
    id: 'track-1',
    title: 'Antigravity Chill Lofi Beats',
    duration: 180, // seconds
    thumbnail: 'https://images.unsplash.com/photo-1614680376593-902f74fa0d41?w=400&q=80',
    artist: 'Lofi Beats Co.',
    channel: 'Music Lounge'
  },
  queue: [
    { id: 'track-2', title: 'Coding Focus Session', artist: 'DeepMind Sounds', duration: 320, thumbnail: 'https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=400&q=80' },
    { id: 'track-3', title: 'Synthwave Night Ride', artist: 'Retrowave', duration: 245, thumbnail: 'https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=400&q=80' },
    { id: 'track-4', title: 'Acoustic Guitar Cover', artist: 'Acoustic Duo', duration: 190, thumbnail: 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=400&q=80' }
  ],
  volume: 75,
  loop_mode: 0, // 0 = off, 1 = track, 2 = queue
  autoplay: false,
  connected: true,
  voice_channel: 'General VC'
};

const recentlyPlayed = [
  { title: 'Relaxing Rain Sounds', artist: 'Nature Sync', duration: 600, thumbnail: 'https://images.unsplash.com/photo-1534274988757-a28bf1a57c17?w=400&q=80' },
  { title: 'Neo-Jazz Cafe Ambient', artist: 'Jazz Club', duration: 400, thumbnail: 'https://images.unsplash.com/photo-1511192336575-5a79af67a629?w=400&q=80' }
];

const mockGuilds = [
  { id: '1450204870064996384', name: 'Antigravity Dev Lounge', icon: null, member_count: 42 },
  { id: '222222222222222222', name: 'Vibe Check Room', icon: null, member_count: 1056 },
  { id: '333333333333333333', name: 'Chill Coding Beats', icon: null, member_count: 8 }
];

// Subscriptions for state updates in mock mode
let mockListeners = [];

export const subscribeMockState = (listener) => {
  if (API_MODE !== 'mock') return () => {};
  mockListeners.push(listener);
  // Send initial state
  listener({ ...mockState, recentlyPlayed });
  return () => {
    mockListeners = mockListeners.filter(l => l !== listener);
  };
};

const notifyMockUpdate = () => {
  mockListeners.forEach(listener => listener({ ...mockState, recentlyPlayed }));
};

// Helper for random mock track creations
const getMockTrack = (query) => {
  const isUrl = query.startsWith('http');
  const title = isUrl ? query.split('/').pop().replace(/[?&=]/g, ' ') : query;
  return {
    id: `track-${Date.now()}`,
    title: title.length > 30 ? title.substring(0, 30) + '...' : title,
    artist: isUrl ? 'Online Streamer' : 'Web Search Result',
    duration: 120 + Math.floor(Math.random() * 200),
    thumbnail: 'https://images.unsplash.com/photo-1470225620780-dba8ba36b745?w=400&q=80',
    channel: 'Searched Item'
  };
};

// --- API Service Methods ---

export const getGuilds = async () => {
  if (API_MODE === 'mock') {
    return mockGuilds;
  }
  
  const response = await fetch(`${BASE_URL}/api/guilds`);
  if (!response.ok) throw new Error('Failed to fetch guilds');
  return response.json();
};

export const getMusicStatus = async (guildId) => {
  if (API_MODE === 'mock') {
    return { ...mockState };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}`);
  if (!response.ok) throw new Error('Failed to fetch music status');
  return response.json();
};

export const play = async (guildId, query) => {
  if (API_MODE === 'mock') {
    const newTrack = getMockTrack(query);
    if (mockState.status === 'idle' || !mockState.current_track) {
      mockState.current_track = newTrack;
      mockState.status = 'playing';
    } else {
      mockState.queue.push(newTrack);
    }
    notifyMockUpdate();
    return { success: true, added: 1 };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/play`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query })
  });
  if (!response.ok) {
    const errorData = await response.json();
    throw new Error(errorData.error || 'Failed to play track');
  }
  return response.json();
};

export const pause = async (guildId) => {
  if (API_MODE === 'mock') {
    mockState.status = 'paused';
    notifyMockUpdate();
    return { success: true, status: 'paused' };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/pause`, {
    method: 'POST'
  });
  if (!response.ok) throw new Error('Failed to pause');
  return response.json();
};

export const resume = async (guildId) => {
  if (API_MODE === 'mock') {
    mockState.status = 'playing';
    notifyMockUpdate();
    return { success: true, status: 'playing' };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/resume`, {
    method: 'POST'
  });
  if (!response.ok) throw new Error('Failed to resume');
  return response.json();
};

export const skip = async (guildId) => {
  if (API_MODE === 'mock') {
    if (mockState.current_track) {
      // Add to recently played
      recentlyPlayed.unshift(mockState.current_track);
      if (recentlyPlayed.length > 5) recentlyPlayed.pop();
    }
    
    if (mockState.queue.length > 0) {
      mockState.current_track = mockState.queue.shift();
      mockState.status = 'playing';
    } else {
      mockState.current_track = null;
      mockState.status = 'idle';
    }
    notifyMockUpdate();
    return { success: true, status: 'skipped' };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/skip`, {
    method: 'POST'
  });
  if (!response.ok) throw new Error('Failed to skip');
  return response.json();
};

export const setVolume = async (guildId, volume) => {
  if (API_MODE === 'mock') {
    mockState.volume = volume;
    notifyMockUpdate();
    return { success: true, volume };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/volume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ volume: volume / 100 }) // Convert back to 0-2 scale if needed
  });
  if (!response.ok) throw new Error('Failed to change volume');
  return response.json();
};

export const setLoopMode = async (guildId, mode) => {
  if (API_MODE === 'mock') {
    mockState.loop_mode = mode; // 0 = off, 1 = track, 2 = queue
    notifyMockUpdate();
    return { success: true, loop_mode: mode };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/loop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode })
  });
  if (!response.ok) throw new Error('Failed to toggle loop');
  return response.json();
};

export const setAutoplay = async (guildId, enabled) => {
  if (API_MODE === 'mock') {
    mockState.autoplay = enabled;
    notifyMockUpdate();
    return { success: true, autoplay: enabled };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/autoplay`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ autoplay: enabled })
  });
  if (!response.ok) throw new Error('Failed to toggle autoplay');
  return response.json();
};

export const reorderQueue = async (guildId, fromIndex, toIndex) => {
  if (API_MODE === 'mock') {
    const [moved] = mockState.queue.splice(fromIndex, 1);
    mockState.queue.splice(toIndex, 0, moved);
    notifyMockUpdate();
    return { success: true };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/queue/reorder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ from: fromIndex, to: toIndex })
  });
  if (!response.ok) throw new Error('Failed to reorder queue');
  return response.json();
};

export const removeQueueTrack = async (guildId, position) => {
  if (API_MODE === 'mock') {
    mockState.queue.splice(position - 1, 1);
    notifyMockUpdate();
    return { success: true };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/remove`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ position }) // 1-based index
  });
  if (!response.ok) throw new Error('Failed to remove track');
  return response.json();
};

export const clearQueue = async (guildId) => {
  if (API_MODE === 'mock') {
    mockState.queue = [];
    notifyMockUpdate();
    return { success: true };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/clearqueue`, {
    method: 'POST'
  });
  if (!response.ok) throw new Error('Failed to clear queue');
  return response.json();
};

export const shuffle = async (guildId) => {
  if (API_MODE === 'mock') {
    const queue = mockState.queue;
    for (let i = queue.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [queue[i], queue[j]] = [queue[j], queue[i]];
    }
    notifyMockUpdate();
    return { success: true };
  }

  const response = await fetch(`${BASE_URL}/music/${guildId}/shuffle`, {
    method: 'POST'
  });
  if (!response.ok) throw new Error('Failed to shuffle queue');
  return response.json();
};

export const getRecentlyPlayed = async (guildId) => {
  if (API_MODE === 'mock') {
    return recentlyPlayed;
  }
  // Fallback: in live mode recently played is kept client-side or queried
  return recentlyPlayed;
};
