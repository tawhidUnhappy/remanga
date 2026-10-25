"""Managing what remanga makes (user request, 2026-10-25: "nothing gets
overwritten or corrupt or lost ... save compute if already computed").

    objects.py   the store: every expensive result kept once, by the hash of
                 what made it - written atomically, checksummed, read-only
    locks.py     one job at a time on a chapter
    versions.py  a chapter's versions (every video made of it, restorable),
                 the take cache narration asks first, the video's key"""

from remanga.store.locks import ChapterBusy, chapter_lock
from remanga.store.objects import Store, recipe_key
from remanga.store.versions import TakeCache, video_key

__all__ = ["ChapterBusy", "Store", "TakeCache", "chapter_lock", "recipe_key", "video_key"]
