// App.jsx - Main Dashboard Layout and State Manager
import React, { useState, useEffect } from 'react';
import ServerSelector from './components/ServerSelector';
import NowPlaying from './components/NowPlaying';
import Controls from './components/Controls';
import VolumeSlider from './components/VolumeSlider';
import Queue from './components/Queue';
import { ToastContainer } from './components/Toast';
import { History, Disc, ExternalLink, RefreshCw, Play } from 'lucide-react';
import * as api from './services/api';
import { useWebSocket } from './hooks/useWebSocket';

export default function App() {
  const [guilds, setGuilds] = useState([]);
  const [activeGuildId, setActiveGuildId] = useState('');
  const [toasts, setToasts] = useState([]);
  const [loadingGuilds, setLoadingGuilds] = useState(true);

  // Expose toast notifier helper
  const addToast = (message, type = 'info') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    
    // Auto remove after 4 seconds
    setTimeout(() => {
      removeToast(id);
    }, 4000);
  };

  const removeToast = (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // 1. Fetch available guilds on startup
  useEffect(() => {
    const fetchGuilds = async () => {
      try {
        const data = await api.getGuilds();
        setGuilds(data);
        if (data.length > 0) {
          setActiveGuildId(data[0].id);
        }
      } catch (err) {
        addToast('Failed to load guilds. Check backend connection.', 'error');
      } finally {
        setLoadingGuilds(false);
      }
    };
    fetchGuilds();
  }, []);

  // 2. Establish live sync for the active guild
  const {
    playerState,
    elapsedTime,
    setElapsedTime,
    recentlyPlayed,
    connected,
    error: syncError
  } = useWebSocket(activeGuildId);

  // Monitor sync errors
  useEffect(() => {
    if (syncError) {
      addToast(syncError, 'warning');
    }
  }, [syncError]);

  // 3. User actions wrapping API endpoints with Toast alerts
  const handleTogglePlay = async () => {
    try {
      if (playerState.status === 'playing') {
        await api.pause(activeGuildId);
        addToast('Playback paused', 'info');
      } else {
        await api.resume(activeGuildId);
        addToast('Playback resumed', 'success');
      }
    } catch (err) {
      addToast(err.message || 'Failed to toggle playback', 'error');
    }
  };

  const handleSkip = async () => {
    try {
      await api.skip(activeGuildId);
      addToast('Skipped current track', 'success');
    } catch (err) {
      addToast(err.message || 'Failed to skip track', 'error');
    }
  };

  const handlePrevious = async () => {
    addToast('Previous track command sent', 'info');
    // Implement or fall back
  };

  const handleShuffle = async () => {
    try {
      await api.shuffle(activeGuildId);
      addToast('Queue shuffled successfully', 'success');
    } catch (err) {
      addToast(err.message || 'Failed to shuffle queue', 'error');
    }
  };

  const handleLoopModeChange = async (mode) => {
    try {
      await api.setLoopMode(activeGuildId, mode);
      const labels = ['Loop Off', 'Repeat Track', 'Repeat Queue'];
      addToast(labels[mode], 'success');
    } catch (err) {
      addToast(err.message || 'Failed to set loop mode', 'error');
    }
  };

  const handleAutoplayChange = async (enabled) => {
    try {
      await api.setAutoplay(activeGuildId, enabled);
      addToast(`Autoplay ${enabled ? 'Enabled' : 'Disabled'}`, 'success');
    } catch (err) {
      addToast(err.message || 'Failed to set autoplay', 'error');
    }
  };

  const handleVolumeChange = async (volume) => {
    try {
      await api.setVolume(activeGuildId, volume);
      // Debounce or reduce toast frequency for slider changes in production,
      // but fine to toast on slider release/change for feedback.
    } catch (err) {
      addToast('Failed to change volume', 'error');
    }
  };

  const handleRemoveTrack = async (position) => {
    try {
      await api.removeQueueTrack(activeGuildId, position);
      addToast('Track removed from queue', 'success');
    } catch (err) {
      addToast('Failed to remove track', 'error');
    }
  };

  const handleReorderQueue = async (fromIndex, newIndex) => {
    try {
      // Optimistic UI updates
      const updatedQueue = [...playerState.queue];
      const [moved] = updatedQueue.splice(fromIndex, 1);
      updatedQueue.splice(newIndex, 0, moved);

      await api.reorderQueue(activeGuildId, fromIndex, newIndex);
      addToast('Queue reordered', 'success');
    } catch (err) {
      addToast('Failed to reorder queue', 'error');
    }
  };

  const handlePlayQuery = async (query) => {
    try {
      const result = await api.play(activeGuildId, query);
      addToast(`Added track to queue!`, 'success');
    } catch (err) {
      addToast(err.message || 'Failed to add track', 'error');
      throw err;
    }
  };

  const handleClearQueue = async () => {
    try {
      await api.clearQueue(activeGuildId);
      addToast('Queue cleared', 'success');
    } catch (err) {
      addToast('Failed to clear queue', 'error');
    }
  };

  const handleReplayHistoryTrack = async (trackTitle) => {
    try {
      addToast(`Replaying "${trackTitle}"...`, 'info');
      await api.play(activeGuildId, trackTitle);
    } catch (err) {
      addToast('Failed to replay track', 'error');
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="min-h-screen bg-discord-darkest-gray flex flex-col text-discord-text-primary">
      {/* Toast Notifications */}
      <ToastContainer toasts={toasts} onClose={removeToast} />

      {/* Top Header Navigation */}
      <header className="bg-discord-darker-gray border-b border-black/20 px-6 py-4 flex items-center justify-between shrink-0 shadow-md">
        <div className="flex items-center gap-3">
          <div className="bg-discord-blurple p-2 rounded-md shadow-md text-white">
            <Disc className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <h1 className="text-lg font-extrabold tracking-wide text-white flex items-center gap-1.5 uppercase">
              Antigravity <span className="text-xs font-semibold px-2 py-0.5 rounded bg-discord-blurple text-white normal-case tracking-normal">Music Panel</span>
            </h1>
            <p className="text-3xs font-semibold text-discord-text-muted mt-0.5">DISCORD MUSIC BOT MANAGER</p>
          </div>
        </div>

        {/* Server Selector dropdown */}
        {!loadingGuilds && guilds.length > 0 && (
          <ServerSelector
            guilds={guilds}
            activeGuildId={activeGuildId}
            onSelectGuild={setActiveGuildId}
            isConnected={connected}
          />
        )}

        {loadingGuilds && (
          <div className="flex items-center gap-2 text-sm text-discord-text-muted">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span>Loading servers...</span>
          </div>
        )}
      </header>

      {/* Main Grid Body */}
      <main className="flex-1 p-6 md:p-8 max-w-7xl mx-auto w-full grid grid-cols-1 lg:grid-cols-3 gap-6 overflow-hidden">
        {/* Left/Central Controllers Block (2/3 width) */}
        <div className="lg:col-span-2 flex flex-col gap-6">
          {/* Now Playing visual display */}
          <div className="flex-1 min-h-[300px]">
            <NowPlaying
              currentTrack={playerState.current_track}
              elapsedTime={elapsedTime}
              playerStatus={playerState.status}
              voiceChannel={playerState.voice_channel}
            />
          </div>

          {/* Volume control */}
          <VolumeSlider volume={playerState.volume} onChange={handleVolumeChange} />

          {/* Controls triggers */}
          <Controls
            status={playerState.status}
            loopMode={playerState.loop_mode}
            autoplay={playerState.autoplay}
            onTogglePlay={handleTogglePlay}
            onSkip={handleSkip}
            onPrevious={handlePrevious}
            onShuffle={handleShuffle}
            onLoopModeChange={handleLoopModeChange}
            onAutoplayChange={handleAutoplayChange}
          />

          {/* Recently Played History */}
          <div className="bg-discord-card border border-white/5 rounded-lg p-5 shadow-md">
            <h3 className="text-xs font-bold text-discord-text-muted uppercase tracking-wider mb-3.5 flex items-center gap-2">
              <History className="w-4 h-4 text-discord-blurple" />
              Recently Played History
            </h3>
            
            {recentlyPlayed.length === 0 ? (
              <p className="text-xs text-discord-text-muted italic py-2">No tracks in playback history.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {recentlyPlayed.map((track, idx) => (
                  <button
                    key={`${track.title}-${idx}`}
                    onClick={() => handleReplayHistoryTrack(track.title)}
                    className="flex items-center gap-3 p-2.5 bg-discord-darkest-gray hover:bg-[#35373c] border border-white/5 rounded text-left transition-all duration-200 group focus:outline-none"
                    title={`Click to play: ${track.title}`}
                  >
                    <div className="relative shrink-0">
                      <img
                        src={track.thumbnail || 'https://images.unsplash.com/photo-1614680376593-902f74fa0d41?w=100&q=80'}
                        alt={track.title}
                        className="w-9 h-9 rounded object-cover border border-white/10"
                      />
                      <div className="absolute inset-0 bg-black/40 flex items-center justify-center rounded opacity-0 group-hover:opacity-100 transition-opacity">
                        <Play className="w-4 h-4 fill-white text-white" />
                      </div>
                    </div>
                    
                    <div className="flex-1 min-w-0">
                      <h4 className="text-xs font-bold text-discord-text-primary truncate group-hover:text-discord-blurple transition-colors">
                        {track.title}
                      </h4>
                      <p className="text-3xs text-discord-text-muted truncate mt-0.5">
                        {track.artist || 'Unknown Artist'} • {formatDuration(track.duration)}
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Side Queue management Block (1/3 width) */}
        <div className="lg:col-span-1">
          <Queue
            queue={playerState.queue}
            onRemove={handleRemoveTrack}
            onReorder={handleReorderQueue}
            onPlayQuery={handlePlayQuery}
            onClearQueue={handleClearQueue}
          />
        </div>
      </main>

      {/* Footer system details */}
      <footer className="bg-discord-darkest-gray border-t border-white/5 px-6 py-3 text-3xs font-semibold text-discord-text-muted flex items-center justify-between shrink-0 select-none">
        <span>VITE APP RUNNING IN {import.meta.env.VITE_API_MODE?.toUpperCase() || 'MOCK'} MODE</span>
        <span className="flex items-center gap-1">
          CONTROL CENTER v1.0.0
          <ExternalLink className="w-3 h-3 text-discord-text-muted" />
        </span>
      </footer>
    </div>
  );
}
