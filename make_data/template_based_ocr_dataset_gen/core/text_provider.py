import random
import re
import contextvars

# Global context var to hold the current DocumentContext for a given generated image
current_document = contextvars.ContextVar("current_document", default=None)

# Fallback names in case regex doesn't find any
FALLBACK_NAMES = [
    "أحمد عبد الرحمن", "محمود إبراهيم", "فاطمة الزهراء", "محمد علي", 
    "خالد بن الوليد", "طارق بن زياد", "عبد الله سعيد", "عائشة عبد الرحمن"
]

class DocumentContext:
    def __init__(self, books_pool):
        self.books_pool = books_pool
        self._load_random_book()
        
    def _load_random_book(self):
        self.full_text = random.choice(self.books_pool)
        self.words = self.full_text.split()
        self.cursor = 0
        self.extracted_title = None
        self.extracted_author = None
        
        self._extract_metadata()
        self._set_random_cursor()
        
    def _extract_metadata(self):
        """Use robust regex to creatively find metadata like titles and authors."""
        # 1. Extract Author
        author_match = re.search(r"(?:تأليف|بقلم|للكاتب|المؤلف|ترجمة|إعداد)\s*[:\-]*\s*([^\n\.,\d]+)", self.full_text)
        if author_match:
            self.extracted_author = author_match.group(1).strip()
        else:
            # Fallback regex for titles
            author_match = re.search(r"(?:الدكتور|الشيخ|الأستاذ|الباحث)\s+([^\n\.,\d]+)", self.full_text)
            if author_match:
                self.extracted_author = author_match.group(1).strip()
                
        # 2. Extract Title (first line or matched pattern)
        title_match = re.search(r"^(?:كتاب|عنوان|قصة|رواية)?\s*[:\-]*\s*([^\n\.]{3,60})", self.full_text)
        if title_match:
            title = title_match.group(1).strip()
            # If the extracted line is too long, it's probably a paragraph, not a title
            if 1 <= len(title.split()) <= 8:
                self.extracted_title = title

        # Fallback for title if regex failed
        if not self.extracted_title and self.words:
            # Grab first 3-6 words as a synthetic title
            self.extracted_title = " ".join(self.words[:min(random.randint(3,6), len(self.words))])

    def _set_random_cursor(self):
        """Start reading from a random point in the book so different pages using the same book don't overlap."""
        if len(self.words) > 50:
            # Leave at least 50 words buffer at the end
            self.cursor = random.randint(0, len(self.words) - 50)
        else:
            self.cursor = 0

    def get_title(self):
        return self.extracted_title or "عنوان تجريبي"
        
    def get_author(self):
        if self.extracted_author:
            return self.extracted_author
        return random.choice(FALLBACK_NAMES)
        
    def get_words(self, min_words, max_words):
        """Returns a contiguous chunk of words and strictly advances the cursor.
           If the book runs out, it smoothly transitions to a new book to avoid spam."""
        count = random.randint(min_words, max_words)
        
        if self.cursor >= len(self.words):
            # We ran out of text in this book.
            # Instead of spamming or looping the same book (which repeats text), we pull a fresh random book.
            self._load_random_book()
            # If the new book is also empty (e.g., fallback text), we just return a placeholder.
            if len(self.words) == 0:
                return "نص إضافي."
            
        end = min(self.cursor + count, len(self.words))
        chunk = " ".join(self.words[self.cursor:end])
        self.cursor = end
        return chunk
