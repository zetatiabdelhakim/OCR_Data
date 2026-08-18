import random
import re
import contextvars

# Global context var to hold the current DocumentContext for a given generated image
current_document = contextvars.ContextVar("current_document", default=None)


class DocumentContext:
    def __init__(self, books_pool):
        self.books_pool = books_pool
        self.figure_counter = 0   # incremented by get_figure_caption() per page

        # Lazy import avoids circular dependency (assets imports current_document from here)
        from core import assets as _assets
        fonts = _assets.FONTS
        if fonts:
            self.body_font = random.choice(fonts)
            # ~30% chance title uses same font (single-font page), 70% picks a distinct one
            if random.random() < 0.30:
                self.title_font = self.body_font
            else:
                self.title_font = random.choice(fonts)
        else:
            self.body_font = ""
            self.title_font = ""

        self._load_random_book()

    def _load_random_book(self):
        self.full_text = random.choice(self.books_pool)
        self.words = self.full_text.split()
        self.cursor = 0
        self.extracted_title = None
        self.extracted_author = None
        self._chosen_title = None

        self._extract_metadata()
        self._set_random_cursor()

    def _extract_metadata(self):
        """Use robust regex to find clean metadata like titles and authors."""
        # 1. Extract Author
        author_match = re.search(
            r"(?:تأليف|بقلم|للكاتب|المؤلف|ترجمة|إعداد)\s*[:\-]*\s*([^\n\.,\d]+)",
            self.full_text,
        )
        if author_match:
            candidate = author_match.group(1).strip()
            if 2 <= len(candidate.split()) <= 5:
                self.extracted_author = candidate
        else:
            author_match = re.search(
                r"(?:الدكتور|الشيخ|الأستاذ|الباحث)\s+([^\n\.,\d]+)",
                self.full_text,
            )
            if author_match:
                candidate = author_match.group(1).strip()
                if 2 <= len(candidate.split()) <= 5:
                    self.extracted_author = candidate

        # 2. Extract Title — check explicit title prefixes on the opening lines
        first_lines = "\n".join(self.full_text.splitlines()[:5])
        title_match = re.search(
            r"(?:كتاب|عنوان|قصة|رواية|ديوان|رسالة|دراسة)\s*[:\-]+\s*([^\n\.]{4,60})",
            first_lines,
        )
        if title_match:
            title = title_match.group(1).strip()
            words = title.split()
            # Must be a clean, valid phrase (not religious opening or general boilerplate)
            _invalid_substrings = ["بسم الله", "الحمد لله", "أما بعد", "مقدمة", "فهرس"]
            if 2 <= len(words) <= 8 and not any(inv in title for inv in _invalid_substrings):
                self.extracted_title = title

    def _set_random_cursor(self):
        """Start reading from a random point so different pages don't overlap."""
        if len(self.words) > 50:
            self.cursor = random.randint(0, len(self.words) - 50)
        else:
            self.cursor = 0

    def get_title(self):
        """Return the best available coherent title for this document.

        Priority:
          1. Cleanly regex-extracted title from book metadata (book-level heading)
          2. Cached curated title from ARABIC_BOOK_TITLES pool (ensures consistency within the same page)
        """
        if self.extracted_title:
            return self.extracted_title

        if self._chosen_title is None:
            from core.assets import ARABIC_BOOK_TITLES
            self._chosen_title = random.choice(ARABIC_BOOK_TITLES)

        return self._chosen_title

    def get_author(self):
        if self.extracted_author:
            # Trim to a reasonable length (some extractions can be long)
            words = self.extracted_author.split()
            if 2 <= len(words) <= 5:
                return self.extracted_author
        from core.assets import ARABIC_PERSON_NAMES
        return random.choice(ARABIC_PERSON_NAMES)

    def get_words(self, min_words, max_words):
        """Return a contiguous chunk of words, advancing the cursor.
        If the book runs out, smoothly transitions to a fresh book."""
        count = random.randint(min_words, max_words)

        if self.cursor >= len(self.words):
            self._load_random_book()
            if len(self.words) == 0:
                return "نص إضافي."

        end = min(self.cursor + count, len(self.words))
        chunk = " ".join(self.words[self.cursor:end])
        self.cursor = end
        return chunk
