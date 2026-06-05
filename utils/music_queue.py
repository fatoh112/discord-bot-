from typing import List, Optional, Dict, Any
import random

class QueueManager:
    def __init__(self, max_size: int = 100):
        self.tracks: List[Dict[str, Any]] = []
        self.max_size = max_size
        
        # Loop modes: 0 = off, 1 = track, 2 = queue
        self.loop_mode: int = 0 
        
        self.history: List[Dict[str, Any]] = []

    def is_empty(self) -> bool:
        return len(self.tracks) == 0

    def is_full(self) -> bool:
        return len(self.tracks) >= self.max_size

    def add_track(self, track: Dict[str, Any]) -> bool:
        if self.is_full():
            return False
        self.tracks.append(track)
        return True

    def get_next(self, current_track: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Gets the next track depending on the loop mode."""
        if current_track:
            if self.loop_mode == 1:
                # Loop current track
                return current_track
            elif self.loop_mode == 2:
                # Loop queue - add the current track to the end before fetching next
                if len(self.tracks) < self.max_size:
                    self.tracks.append(current_track)
            else:
                self.history.append(current_track)
                if len(self.history) > 50:
                    self.history.pop(0)

        if self.is_empty():
            return None
        return self.tracks.pop(0)

    def shuffle(self) -> None:
        random.shuffle(self.tracks)

    def remove(self, index: int) -> Optional[Dict[str, Any]]:
        if 0 <= index < len(self.tracks):
            return self.tracks.pop(index)
        return None

    def clear(self) -> None:
        self.tracks.clear()
        
    def get_queue(self) -> List[Dict[str, Any]]:
        return list(self.tracks)
