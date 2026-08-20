from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class ScanStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass
class URLResult:
    url: str
    status_code: Optional[int] = None
    final_url: Optional[str] = None
    redirect_count: int = 0
    redirect_chain: list[str] = field(default_factory=list)
    response_time: float = 0.0
    content_type: str = ""
    content_length: int = 0
    error: str = ""
    is_disallowed: bool = False

    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0
    h1: str = ""
    h1_count: int = 0
    word_count: int = 0
    canonical: str = ""
    robots: str = ""
    indexable: bool = True

    issues: list[str] = field(default_factory=list)


@dataclass
class ScanState:
    scan_id: str
    status: ScanStatus = ScanStatus.QUEUED
    sitemaps: list[str] = field(default_factory=list)
    total_urls: int = 0
    completed: int = 0
    success: int = 0
    redirects: int = 0
    client_errors: int = 0
    server_errors: int = 0
    timeouts: int = 0
    dns_errors: int = 0
    ssl_errors: int = 0
    other_errors: int = 0
    seo_issues: int = 0
    content_issues: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: str = ""
    results: list[URLResult] = field(default_factory=list)
    is_cancelled: bool = False
    report_path: str = ""
    robots_info: dict = field(default_factory=dict)

    @property
    def elapsed_seconds(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.completed_at or datetime.utcnow()
        return (end - self.started_at).total_seconds()

    @property
    def percentage(self) -> float:
        if self.total_urls == 0:
            return 0.0
        return round((self.completed / self.total_urls) * 100, 2)
