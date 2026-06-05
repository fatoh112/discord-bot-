from utils.music_queue import QueueManager
q = QueueManager()
print("has add?", hasattr(q, 'add'))
print("has add_track?", hasattr(q, 'add_track'))
