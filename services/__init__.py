"""services 包：封装业务逻辑，UI 只应调用 services 层。"""

from .book_service import BookService
from .chapter_service import ChapterService
from .crawler_service import CrawlerService
from .download_manager import DownloadManager

__all__ = ["BookService", "ChapterService", "CrawlerService", "DownloadManager"]
