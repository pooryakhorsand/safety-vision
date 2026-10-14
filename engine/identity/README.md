# identity/

`recent_gallery.py` keeps the appearance of people who recently violated a rule, so that the same
person violating again within `events.merge_window_minutes` reopens one event instead of creating many.
It compares ReID embeddings (cosine similarity), only for the same module and event type, on the same
or a neighbouring camera, and never merges two people who are visible at the same time.
It is meant for minutes within a shift. It does not identify anyone and holds no names.
