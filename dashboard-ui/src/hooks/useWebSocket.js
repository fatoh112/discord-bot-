// useWebSocket.js - Live status update hook
// Supports mock in-memory tick/simulation and live Server-Sent Events (SSE) sync.

import { useState, useEffect, useRef } from 'react';
import * as api from '../services/api';

const API_MODE = import.meta.env.VITE_API_MODE || 'mock';
const BASE_URL = import.meta.env.VITE_API_BASE_URL || (typeof window !== 'undefined' ? window.location.origin : 'http://localhost:8080');

export const useWebSocket = (guildId) => {
  const [playerState, setPlayerState] = useState({
    status: 'idle',
    current_track: null,
    queue: [],
    volume: 100,
    loop_mode: 0,
    autoplay: false,
    connected: false,
    voice_channel: null
  });
  
  const [elapsedTime, setElapsedTime] = useState(0);
  const [recentlyPlayed, setRecentlyPlayed] = useState([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState(null);
  
  const tickIntervalRef = useRef(null);
  
  // Track elapsed time ticking
  useEffect(() => {
    if (tickIntervalRef.current) {
      clearInterval(tickIntervalRef.current);
    }
    
    if (playerState.status === 'playing' && playerState.current_track) {
      tickIntervalRef.current = setInterval(() => {
        setElapsedTime((prev) => {
          const totalDuration = playerState.current_track.duration || 0;
          if (prev >= totalDuration) {
            // Auto skip in mock mode
            if (API_MODE === 'mock') {
              clearInterval(tickIntervalRef.current);
              api.skip(guildId).catch(console.error);
            }
            return 0;
          }
          return prev + 1;
        });
      }, 1000);
    }
    
    return () => {
      if (tickIntervalRef.current) clearInterval(tickIntervalRef.current);
    };
  }, [playerState.status, playerState.current_track, guildId]);

  // Main listener setup (Mock vs Live)
  useEffect(() => {
    if (!guildId) return;

    if (API_MODE === 'mock') {
      setConnected(true);
      setError(null);
      
      const unsubscribe = api.subscribeMockState((newState) => {
        setPlayerState((prev) => {
          // Reset elapsed time if current track changes
          const trackChanged = (!prev.current_track && newState.current_track) || 
                               (prev.current_track && newState.current_track && prev.current_track.id !== newState.current_track.id) ||
                               (prev.status !== newState.status && newState.status === 'idle');
          if (trackChanged) {
            setElapsedTime(0);
          }
          return {
            status: newState.status,
            current_track: newState.current_track,
            queue: newState.queue,
            volume: newState.volume,
            loop_mode: newState.loop_mode,
            autoplay: newState.autoplay,
            connected: newState.connected,
            voice_channel: newState.voice_channel
          };
        });
        
        if (newState.recentlyPlayed) {
          setRecentlyPlayed(newState.recentlyPlayed);
        }
      });

      return () => {
        unsubscribe();
      };
    } else {
      // --- LIVE MODE (REST + SSE) ---
      let eventSource = null;
      let isSubscribed = true;

      // 1. Initial State Load
      const loadInitialState = async () => {
        try {
          const data = await api.getMusicStatus(guildId);
          if (!isSubscribed) return;
          
          setPlayerState({
            status: data.status || 'idle',
            current_track: data.current_track || null,
            queue: data.queue || [],
            volume: data.volume !== undefined ? data.volume : 100,
            loop_mode: data.loop_mode !== undefined ? data.loop_mode : 0,
            autoplay: data.autoplay || false,
            connected: data.status !== 'idle',
            voice_channel: data.voice_channel || (data.status !== 'idle' ? 'Voice Channel' : null)
          });
          
          // Initialize elapsed time (if provided by backend, otherwise 0)
          setElapsedTime(data.elapsed || 0);
          
          const history = await api.getRecentlyPlayed(guildId);
          if (isSubscribed) setRecentlyPlayed(history);
          
          setConnected(true);
          setError(null);
        } catch (err) {
          if (isSubscribed) {
            setError('Could not connect to bot backend API.');
            setConnected(false);
          }
        }
      };

      loadInitialState();

      // 2. Establish Server-Sent Events (SSE) for Real-Time Sync
      try {
        eventSource = new EventSource(`${BASE_URL}/music/${guildId}/stream`, { withCredentials: true });
        
        eventSource.onopen = () => {
          if (isSubscribed) setConnected(true);
        };

        eventSource.onmessage = (event) => {
          if (!isSubscribed) return;
          try {
            const data = JSON.parse(event.data);
            if (data.error) {
              setError(data.error);
              return;
            }

            setPlayerState((prev) => {
              const trackChanged = (!prev.current_track && data.current_track) ||
                                   (prev.current_track && data.current_track && prev.current_track.title !== data.current_track.title);
              if (trackChanged) {
                setElapsedTime(0);
              }

              // Update state from stream data
              return {
                ...prev,
                status: data.status || prev.status,
                current_track: data.current_track || null,
                queue: data.queue || prev.queue,
                volume: data.volume !== undefined ? data.volume : prev.volume,
                loop_mode: data.loop_mode !== undefined ? data.loop_mode : prev.loop_mode
              };
            });
          } catch (e) {
            console.error('Error parsing SSE event data', e);
          }
        };

        eventSource.onerror = () => {
          if (isSubscribed) {
            setConnected(false);
            setError('Real-time sync connection lost. Attempting reconnect...');
          }
        };
      } catch (err) {
        console.error('Error establishing EventSource stream', err);
        setConnected(false);
      }

      // 3. Fallback Periodic Polling just to stay fully in sync with queue/volume shifts
      const pollInterval = setInterval(() => {
        loadInitialState();
      }, 5000);

      return () => {
        isSubscribed = false;
        clearInterval(pollInterval);
        if (eventSource) {
          eventSource.close();
        }
      };
    }
  }, [guildId]);

  return {
    playerState,
    elapsedTime,
    setElapsedTime,
    recentlyPlayed,
    connected,
    error
  };
};
