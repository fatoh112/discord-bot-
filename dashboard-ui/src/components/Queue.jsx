// Queue.jsx - Queue Management and Search Component
import React, { useState } from 'react';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from '@dnd-kit/core';
import {
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import { GripVertical, Trash2, Search, Trash, Plus, AlertCircle } from 'lucide-react';

// Format seconds to MM:SS helper
const formatTime = (seconds) => {
  if (isNaN(seconds) || seconds === null || seconds === undefined) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

// Sortable queue item child component
function SortableTrackItem({ track, index, onRemove }) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging
  } = useSortable({ id: track.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.6 : 1,
    zIndex: isDragging ? 20 : 1
  };

  return (
    <li
      ref={setNodeRef}
      style={style}
      className={`p-3 bg-discord-card border border-white/5 rounded-md flex items-center gap-3 group transition-all duration-200 hover:bg-[#35373c] ${
        isDragging ? 'shadow-lg border-discord-blurple/30 bg-[#35373c]' : ''
      }`}
    >
      {/* Handle wrapper */}
      <div
        {...attributes}
        {...listeners}
        className="cursor-grab active:cursor-grabbing text-discord-text-muted hover:text-discord-text-primary p-1 shrink-0 select-none transition-colors"
        title="Drag to reorder"
      >
        <GripVertical className="w-4.5 h-4.5" />
      </div>

      {/* Position */}
      <span className="text-xs font-bold text-discord-text-muted w-4 text-center shrink-0 select-none">
        {index + 1}
      </span>

      {/* Album cover */}
      {track.thumbnail ? (
        <img
          src={track.thumbnail}
          alt={track.title}
          className="w-10 h-10 rounded object-cover shrink-0 border border-white/10"
        />
      ) : (
        <div className="w-10 h-10 rounded bg-discord-darkest-gray border border-white/10 flex items-center justify-center shrink-0">
          <GripVertical className="w-4 h-4 text-discord-text-muted" />
        </div>
      )}

      {/* Details */}
      <div className="flex-1 min-w-0">
        <h4 className="text-sm font-semibold text-discord-text-primary truncate" title={track.title}>
          {track.title}
        </h4>
        <p className="text-2xs text-discord-text-muted truncate mt-0.5">
          {track.artist || 'Unknown Artist'}
        </p>
      </div>

      {/* Time & Remove Button */}
      <div className="flex items-center gap-3 shrink-0">
        <span className="text-xs text-discord-text-muted font-semibold select-none">
          {formatTime(track.duration)}
        </span>
        <button
          onClick={() => onRemove(index + 1)} // 1-based index for API
          className="p-1.5 hover:bg-discord-red/20 text-discord-text-muted hover:text-discord-red rounded transition-all duration-200 focus:outline-none opacity-0 group-hover:opacity-100 focus:opacity-100"
          title="Remove Track"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </li>
  );
}

export default function Queue({
  queue,
  onRemove,
  onReorder,
  onPlayQuery,
  onClearQueue
}) {
  const [searchQuery, setSearchQuery] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);

  // DnD sensors setup
  const sensors = useSensors(
    useSensor(PointerSensor, {
      activationConstraint: {
        distance: 8, // Require dragging 8px before activating sort to let click events pass through
      },
    }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleDragEnd = (event) => {
    const { active, over } = event;
    if (!over) return;
    
    if (active.id !== over.id) {
      const oldIndex = queue.findIndex((t) => t.id === active.id);
      const newIndex = queue.findIndex((t) => t.id === over.id);
      
      onReorder(oldIndex, newIndex);
    }
  };

  const handleSearchSubmit = async (e) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    
    setIsAdding(true);
    try {
      await onPlayQuery(searchQuery.trim());
      setSearchQuery('');
    } catch (err) {
      console.error(err);
    } finally {
      setIsAdding(false);
    }
  };

  return (
    <div className="bg-discord-card border border-white/5 rounded-lg flex flex-col h-[600px] shadow-lg relative">
      {/* Header Panel */}
      <div className="p-4 border-b border-white/5 flex items-center justify-between shrink-0 bg-white/[0.01]">
        <div>
          <h3 className="text-md font-bold text-discord-text-primary">Play Queue</h3>
          <p className="text-2xs text-discord-text-muted mt-0.5">{queue.length} Tracks upcoming</p>
        </div>
        
        {/* Clear Queue Button with Inline Confirm */}
        {queue.length > 0 && (
          <div className="relative">
            {!showClearConfirm ? (
              <button
                onClick={() => setShowClearConfirm(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-discord-text-muted hover:text-discord-red bg-discord-darkest-gray hover:bg-discord-red/10 rounded border border-white/5 transition-all duration-200 focus:outline-none"
              >
                <Trash className="w-3.5 h-3.5" />
                <span>Clear</span>
              </button>
            ) : (
              <div className="flex items-center gap-1.5 animate-fade-in bg-discord-darkest-gray p-1 rounded border border-discord-red/30">
                <span className="text-[10px] font-bold text-discord-red px-1 flex items-center gap-0.5">
                  <AlertCircle className="w-3 h-3 shrink-0" /> Clear?
                </span>
                <button
                  onClick={() => {
                    onClearQueue();
                    setShowClearConfirm(false);
                  }}
                  className="px-2 py-0.5 text-3xs font-bold bg-discord-red text-white rounded hover:bg-discord-red-hover transition-colors"
                >
                  Yes
                </button>
                <button
                  onClick={() => setShowClearConfirm(false)}
                  className="px-2 py-0.5 text-3xs font-bold bg-discord-card text-discord-text-primary rounded hover:bg-[#35373c] transition-colors"
                >
                  No
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Add track search bar */}
      <div className="p-4 border-b border-white/5 shrink-0 bg-discord-darkest-gray/30">
        <form onSubmit={handleSearchSubmit} className="relative flex gap-2">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-discord-text-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search YouTube or paste link..."
              disabled={isAdding}
              className="w-full pl-9 pr-4 py-2 bg-discord-darkest-gray border border-white/5 rounded text-sm text-discord-text-primary placeholder:text-discord-text-muted focus:outline-none focus:border-discord-blurple transition-all"
            />
          </div>
          <button
            type="submit"
            disabled={isAdding || !searchQuery.trim()}
            className="flex items-center gap-1.5 px-4 py-2 bg-discord-blurple hover:bg-discord-blurple-hover disabled:bg-discord-blurple/40 text-white text-sm font-semibold rounded transition-all duration-200 focus:outline-none shrink-0"
          >
            {isAdding ? (
              <span className="animate-spin w-4 h-4 border-2 border-white border-t-transparent rounded-full" />
            ) : (
              <>
                <Plus className="w-4 h-4" />
                <span>Add</span>
              </>
            )}
          </button>
        </form>
      </div>

      {/* Draggable Queue List */}
      <div className="flex-1 overflow-y-auto p-4">
        {queue.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-discord-text-muted select-none">
            <div className="w-12 h-12 rounded-full bg-discord-darkest-gray flex items-center justify-center mb-3">
              <Search className="w-5 h-5" />
            </div>
            <p className="text-sm font-bold">Queue is Empty</p>
            <p className="text-2xs max-w-xs mt-1">
              Add some tracks using the search bar above to start playing music!
            </p>
          </div>
        ) : (
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragEnd={handleDragEnd}
            modifiers={[restrictToVerticalAxis]}
          >
            <SortableContext items={queue.map((t) => t.id)} strategy={verticalListSortingStrategy}>
              <ul className="flex flex-col gap-2">
                {queue.map((track, index) => (
                  <SortableTrackItem
                    key={track.id}
                    track={track}
                    index={index}
                    onRemove={onRemove}
                  />
                ))}
              </ul>
            </SortableContext>
          </DndContext>
        )}
      </div>
    </div>
  );
}
