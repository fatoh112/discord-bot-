import pytest
from utils.music_queue import QueueManager
from unittest.mock import MagicMock, AsyncMock
import asyncio

def test_queue_add_remove():
    q = QueueManager(max_size=3)
    
    assert q.is_empty()
    assert not q.is_full()
    
    # Add tracks
    assert q.add_track({"title": "Track 1"})
    assert q.add_track({"title": "Track 2"})
    assert q.add_track({"title": "Track 3"})
    
    # Queue is full now
    assert q.is_full()
    assert not q.add_track({"title": "Track 4"})
    
    # Check length
    assert len(q.get_queue()) == 3
    
    # Remove by index
    removed = q.remove(1)
    assert removed["title"] == "Track 2"
    assert len(q.get_queue()) == 2
    
    # Pop next
    next_track = q.get_next()
    assert next_track["title"] == "Track 1"
    
def test_queue_shuffle():
    q = QueueManager(max_size=10)
    for i in range(10):
        q.add_track({"title": f"Track {i}"})
        
    original = [t["title"] for t in q.get_queue()]
    q.shuffle()
    shuffled = [t["title"] for t in q.get_queue()]
    
    assert len(original) == len(shuffled)
    assert original != shuffled or len(original) < 2

def test_loop_modes():
    q = QueueManager(max_size=3)
    q.add_track({"title": "Track 1"})
    q.add_track({"title": "Track 2"})
    
    # Normal play
    q.loop_mode = 0
    t1 = q.get_next()
    t2 = q.get_next(t1)
    assert t1["title"] == "Track 1"
    assert t2["title"] == "Track 2"
    
    # Reset queue
    q.clear()
    q.add_track({"title": "A"})
    q.add_track({"title": "B"})
    
    # Loop track
    q.loop_mode = 1
    current = q.get_next()
    assert current["title"] == "A"
    
    # Should get the same track back
    next_t = q.get_next(current)
    assert next_t["title"] == "A"
    
    # Loop queue
    q.clear()
    q.add_track({"title": "1"})
    q.loop_mode = 2
    
    current = q.get_next()
    assert current["title"] == "1"
    assert len(q.get_queue()) == 0
    
    # When getting next, "1" should be added to the end of queue and then popped since it's the only one
    next_t = q.get_next(current)
    assert next_t["title"] == "1"
    # Our logic:
    # if len(self.tracks) < self.max_size:
    #     self.tracks.append(current_track)
    # Then it does: return self.tracks.pop(0)
    # Let's fix loop mode test
