import hashlib
import os

class DedupManager:
    def __init__(self, filename="data/seen_urls.txt"):
        self.filename = filename
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        # Load existing hashes into memory (Set) for O(1) lookup speed
        self.seen_hashes = set()
        self._load_hashes()

    def _load_hashes(self):
        """Load all previously seen URLs from the file into RAM."""
        if not os.path.exists(self.filename):
            return
        
        try:
            with open(self.filename, 'r') as f:
                for line in f:
                    hash_val = line.strip()
                    if hash_val:
                        self.seen_hashes.add(hash_val)
            print(f"[Dedup] Loaded {len(self.seen_hashes)} known URLs.")
        except Exception as e:
            print(f"[Dedup] Error loading file: {e}")

    def is_seen(self, url):
        """
        Check if URL has been processed.
        Returns True if already seen, False if new.
        """
        # Create a unique fingerprint of the URL
        url_hash = hashlib.sha256(url.encode('utf-8')).hexdigest()
        
        if url_hash in self.seen_hashes:
            return True # It's old news, skip it
        else:
            # It's new! Save it immediately to memory and disk
            self.seen_hashes.add(url_hash)
            self._save_to_disk(url_hash)
            return False

    def _save_to_disk(self, hash_val):
        """Append new hash to file (Append mode is fast)."""
        try:
            with open(self.filename, 'a') as f:
                f.write(f"{hash_val}\n")
        except Exception as e:
            print(f"[Dedup] Error saving to disk: {e}")
